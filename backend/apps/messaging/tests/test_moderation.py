"""Phone reveal, blocks and reports (Phase 16 safety surface)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.messaging.models import PhoneReveal, Report, UserBlock
from apps.products.models import ContactMode, ListingStatus
from tests.factories import (
    ConversationFactory,
    MessageFactory,
    ProductFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

CONVERSATIONS = "/api/v1/messages/conversations/"
REVEAL = "/api/v1/products/{pk}/reveal-phone/"


def _phone_listing(seller, **kwargs):
    seller.phone_number = "+213555123400"
    seller.phone_verified_at = timezone.now()
    seller.save(update_fields=["phone_number", "phone_verified_at"])
    return ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        contact_mode=ContactMode.PHONE,
        **kwargs,
    )


def test_reveal_phone_returns_deep_links_and_writes_an_audit_row(buyer_client, buyer, seller):
    listing = _phone_listing(seller)

    # The public payload tells the UI a reveal is possible, never the number.
    public = buyer_client.get(f"/api/v1/products/{listing.pk}/")
    assert public.data["phone_available"] is True
    assert "seller_phone" not in public.data

    revealed = buyer_client.post(REVEAL.format(pk=listing.pk))

    assert revealed.status_code == 200
    assert revealed.data["phone_number"] == "+213555123400"
    assert revealed.data["call_url"] == "tel:+213555123400"
    assert revealed.data["sms_url"] == "sms:+213555123400"
    assert revealed.data["whatsapp_url"] == "https://wa.me/213555123400"
    row = PhoneReveal.objects.get(listing=listing, viewer=buyer)
    assert row.seller == seller
    assert row.phone_number == "+213555123400"
    assert row.ip_address


def test_reveal_phone_is_auth_gated_and_respects_chat_only_and_blocks(
    api_client, buyer_client, buyer, seller
):
    listing = _phone_listing(seller)
    assert api_client.post(REVEAL.format(pk=listing.pk)).status_code == 401

    listing.contact_mode = ContactMode.CHAT
    listing.save(update_fields=["contact_mode", "updated_at"])
    chat_only = buyer_client.post(REVEAL.format(pk=listing.pk))
    assert chat_only.status_code == 400
    assert chat_only.data["code"] == "phone_not_available"

    listing.contact_mode = ContactMode.PHONE
    listing.save(update_fields=["contact_mode", "updated_at"])
    UserBlock.objects.create(blocker=seller, blocked=buyer)
    blocked = buyer_client.post(REVEAL.format(pk=listing.pk))
    assert blocked.status_code == 403
    assert blocked.data["code"] == "user_blocked"


def test_a_seller_cannot_reveal_their_own_number(seller_client, seller):
    listing = _phone_listing(seller)

    response = seller_client.post(REVEAL.format(pk=listing.pk))

    assert response.status_code == 400
    assert response.data["code"] == "cannot_contact_yourself"
    assert not PhoneReveal.objects.filter(listing=listing).exists()


def test_reveal_phone_is_rate_limited(buyer_client, seller):
    listing = _phone_listing(seller)
    for _ in range(30):
        assert buyer_client.post(REVEAL.format(pk=listing.pk)).status_code == 200

    limited = buyer_client.post(REVEAL.format(pk=listing.pk))

    assert limited.status_code == 429


def test_a_message_can_be_reported_and_the_recipient_is_derived(buyer_client, buyer, seller):
    conversation = ConversationFactory(
        listing=ProductFactory(
            store=None,
            seller=seller,
            status=ListingStatus.ACTIVE,
            contact_mode=ContactMode.CHAT,
        ),
        buyer=buyer,
        seller=seller,
    )
    message = MessageFactory(conversation=conversation, sender=seller, body="Pay now")

    response = buyer_client.post(
        "/api/v1/messages/reports/",
        {"message_id": message.pk, "reason": "SCAM", "details": "Asked for advance payment"},
        format="json",
    )

    assert response.status_code == 201
    report = Report.objects.get(pk=response.data["id"])
    assert report.reporter == buyer
    assert report.reported_user == seller
    assert report.conversation == conversation
    assert report.message == message
    assert report.reason == "SCAM"
    assert report.status == "OPEN"


def test_reporting_yourself_is_refused(buyer_client, buyer):
    response = buyer_client.post(
        "/api/v1/messages/reports/",
        {"reported_user_id": buyer.pk, "reason": "OTHER"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "cannot_report_yourself"


def test_report_requires_a_target_and_a_valid_reason(buyer_client):
    no_target = buyer_client.post("/api/v1/messages/reports/", {"reason": "SPAM"}, format="json")
    bad_reason = buyer_client.post(
        "/api/v1/messages/reports/", {"reported_user_id": 9999, "reason": "NOPE"}, format="json"
    )

    assert no_target.status_code == 400
    assert no_target.data["code"] == "validation_error"
    assert bad_reason.status_code == 400
    assert bad_reason.data["code"] == "validation_error"


def test_block_list_and_unblock_are_per_user(buyer_client, buyer):
    blocked = UserFactory(first_name="Bad", last_name="Actor")
    another = UserFactory()

    assert (
        buyer_client.post(
            f"/api/v1/messages/users/{blocked.pk}/block/", {}, format="json"
        ).status_code
        == 200
    )
    assert (
        buyer_client.post(
            f"/api/v1/messages/users/{another.pk}/block/", {}, format="json"
        ).status_code
        == 200
    )

    rows = buyer_client.get("/api/v1/messages/blocks/").data
    assert {row["user_id"] for row in rows} == {blocked.pk, another.pk}

    assert buyer_client.delete(f"/api/v1/messages/users/{blocked.pk}/block/").status_code == 200
    rows = buyer_client.get("/api/v1/messages/blocks/").data
    assert {row["user_id"] for row in rows} == {another.pk}


def test_unread_count_aggregates_buyer_and_seller_threads(buyer_client, buyer, seller):
    listing = _phone_listing(seller)
    conversation_id = buyer_client.post(
        CONVERSATIONS, {"listing_id": listing.pk}, format="json"
    ).data["id"]
    buyer_client.post(f"{CONVERSATIONS}{conversation_id}/messages/", {"body": "One"}, format="json")
    buyer_client.post(f"{CONVERSATIONS}{conversation_id}/messages/", {"body": "Two"}, format="json")

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    assert seller_client.get("/api/v1/messages/unread-count/").data["unread_count"] == 2
    assert buyer_client.get("/api/v1/messages/unread-count/").data["unread_count"] == 0
