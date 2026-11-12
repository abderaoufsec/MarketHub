"""Chat and inbox behaviour (Phase 16).

These are API-level tests: they exercise the same real serializers, throttles,
spam checks and read-receipt SQL that production uses, not just service
functions in isolation.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.messaging.models import Conversation, Message, UserBlock
from apps.products.models import ContactMode, ListingStatus
from tests.factories import (
    ConversationFactory,
    ImageFactory,
    MessageFactory,
    ProductFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

CONVERSATIONS = "/api/v1/messages/conversations/"


def _listing(seller, **kwargs):
    return ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        contact_mode=ContactMode.CHAT,
        **kwargs,
    )


def _start(client, listing):
    return client.post(CONVERSATIONS, {"listing_id": listing.pk}, format="json")


def _send(client, conversation_id, body="Bonjour, is this still available?"):
    return client.post(
        f"{CONVERSATIONS}{conversation_id}/messages/",
        {"body": body},
        format="json",
    )


def test_starting_a_conversation_is_idempotent_and_rejects_self_contact(
    buyer_client, buyer, seller
):
    listing = _listing(seller)

    first = _start(buyer_client, listing)
    second = _start(buyer_client, listing)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["id"] == second.data["id"]
    assert first.data["buyer"]["id"] == buyer.pk
    assert first.data["seller"]["id"] == seller.pk
    assert first.data["role"] == "buyer"
    assert first.data["can_send"] is True

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    own = _start(seller_client, listing)
    assert own.status_code == 400
    assert own.data["code"] == "cannot_contact_yourself"


def test_a_stranger_gets_404_for_a_conversation(buyer_client, buyer, seller):
    conversation, _ = Conversation.objects.get_or_create(
        listing=_listing(seller),
        buyer=buyer,
        defaults={"seller": seller},
    )
    stranger = UserFactory()
    stranger_client = APIClient()
    stranger_client.force_authenticate(user=stranger)

    assert stranger_client.get(f"{CONVERSATIONS}{conversation.pk}/").status_code == 404
    assert stranger_client.get(f"{CONVERSATIONS}{conversation.pk}/messages/").status_code == 404


def test_messages_cursor_and_read_receipts(buyer_client, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    sent = _send(buyer_client, conversation_id, "First")
    assert sent.status_code == 201
    message_id = sent.data["id"]
    # The cursor returns only what is new after the id the client already has.
    page = buyer_client.get(f"{CONVERSATIONS}{conversation_id}/messages/", {"after": message_id})
    assert page.status_code == 200
    assert page.data["results"] == []
    assert page.data["next_after"] is None

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    inbox = seller_client.get(CONVERSATIONS)
    assert inbox.status_code == 200
    assert inbox.data[0]["unread_count"] == 1

    read = seller_client.post(f"{CONVERSATIONS}{conversation_id}/read/", {}, format="json")
    assert read.status_code == 200
    assert read.data["unread_count"] == 0

    messages = buyer_client.get(f"{CONVERSATIONS}{conversation_id}/messages/")
    assert messages.status_code == 200
    assert messages.data["results"][0]["is_read"] is True
    assert messages.data["results"][0]["read_at"] is not None


def test_a_malformed_message_cursor_is_a_400_not_a_500(buyer_client, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    response = buyer_client.get(
        f"{CONVERSATIONS}{conversation_id}/messages/", {"after": "not-an-id"}
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_blocking_stops_messages_in_both_directions(buyer_client, buyer, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    response = seller_client.post(f"/api/v1/messages/users/{buyer.pk}/block/", {}, format="json")
    assert response.status_code == 200
    assert UserBlock.objects.filter(blocker=seller, blocked=buyer).exists()

    denied = _send(buyer_client, conversation_id, "Hello?")
    assert denied.status_code == 403
    assert denied.data["code"] == "user_blocked"

    # A second block is idempotent, and unblock restores contact.
    assert (
        seller_client.post(
            f"/api/v1/messages/users/{buyer.pk}/block/", {}, format="json"
        ).status_code
        == 200
    )
    assert seller_client.delete(f"/api/v1/messages/users/{buyer.pk}/block/").status_code == 200
    assert not UserBlock.objects.filter(blocker=seller, blocked=buyer).exists()
    assert _send(buyer_client, conversation_id, "Back").status_code == 201


def test_first_message_rejects_phone_and_links_but_later_messages_only_warn(buyer_client, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    phone = _send(buyer_client, conversation_id, "Call me on +213 555 123 456")
    assert phone.status_code == 400
    assert phone.data["code"] == "spam_filtered"
    assert phone.data["details"]["reasons"] == ["phone_number"]

    link = _send(buyer_client, conversation_id, "Look at https://scam.example")
    assert link.status_code == 400
    assert link.data["details"]["reasons"] == ["link"]
    assert not Message.objects.filter(conversation_id=conversation_id).exists()

    first = _send(buyer_client, conversation_id, "Bonjour, what is the final price?")
    assert first.status_code == 201
    later = _send(buyer_client, conversation_id, "You can also reach me on 0555 12 34 56")
    assert later.status_code == 201
    assert "phone_number" in later.data["safety_flags"]


def test_duplicate_message_flood_is_rejected(buyer_client, seller, settings):
    settings.CHAT_DUPLICATE_LIMIT = 2
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]
    body = "Still available?"

    assert _send(buyer_client, conversation_id, body).status_code == 201
    assert _send(buyer_client, conversation_id, body).status_code == 201
    flood = _send(buyer_client, conversation_id, body)

    assert flood.status_code == 429
    assert flood.data["code"] == "message_flood"
    assert Message.objects.filter(conversation_id=conversation_id, body=body).count() == 2


def test_image_messages_require_ownership_and_ready_status(buyer_client, buyer, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    seller_image = ImageFactory(owner=seller)
    wrong = buyer_client.post(
        f"{CONVERSATIONS}{conversation_id}/messages/",
        {"image_id": seller_image.pk},
        format="json",
    )
    assert wrong.status_code == 404
    assert wrong.data["code"] == "image_not_found"

    own_image = ImageFactory(owner=buyer)
    sent = buyer_client.post(
        f"{CONVERSATIONS}{conversation_id}/messages/",
        {"image_id": own_image.pk},
        format="json",
    )
    assert sent.status_code == 201
    assert sent.data["kind"] == "IMAGE"
    assert sent.data["image"]["id"] == own_image.pk


def test_a_new_message_emails_the_recipient(
    buyer_client, seller, django_capture_on_commit_callbacks
):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]

    with django_capture_on_commit_callbacks(execute=True):
        sent = _send(buyer_client, conversation_id, "Hello from Phase 16")

    assert sent.status_code == 201
    assert len(mail.outbox) == 1
    assert seller.email in mail.outbox[0].to
    # Notification emails use the recipient's own language (default: fr).
    assert mail.outbox[0].subject == f"Nouveau message à propos de {listing.name}"
    assert "Hello from Phase 16" in mail.outbox[0].body


def test_seller_response_time_is_a_cached_badge(api_client, seller):
    buyer_one, buyer_two = UserFactory(), UserFactory()
    listing_one = _listing(seller)
    listing_two = _listing(seller)
    first = ConversationFactory(listing=listing_one, buyer=buyer_one, seller=seller)
    second = ConversationFactory(listing=listing_two, buyer=buyer_two, seller=seller)

    now = timezone.now()
    first_buyer = MessageFactory(conversation=first, sender=buyer_one)
    second_buyer = MessageFactory(conversation=second, sender=buyer_two)
    Message.objects.filter(pk=first_buyer.pk).update(created_at=now - timedelta(minutes=60))
    Message.objects.filter(pk=second_buyer.pk).update(created_at=now - timedelta(minutes=120))
    first_reply = MessageFactory(conversation=first, sender=seller)
    second_reply = MessageFactory(conversation=second, sender=seller)
    Message.objects.filter(pk=first_reply.pk).update(created_at=now - timedelta(minutes=30))
    Message.objects.filter(pk=second_reply.pk).update(created_at=now - timedelta(minutes=60))

    response = api_client.get(f"/api/v1/products/{listing_one.pk}/")

    assert response.status_code == 200
    assert response.data["seller"]["response_time_minutes"] == 45


def test_the_first_message_can_be_an_image(buyer_client, buyer, seller):
    listing = _listing(seller)
    conversation_id = _start(buyer_client, listing).data["id"]
    image = ImageFactory(owner=buyer)

    sent = buyer_client.post(
        f"{CONVERSATIONS}{conversation_id}/messages/",
        {"image_id": image.pk},
        format="json",
    )

    assert sent.status_code == 201
    assert sent.data["body"] == ""
    assert sent.data["kind"] == "IMAGE"
