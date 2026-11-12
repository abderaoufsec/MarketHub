"""Offer negotiation: make, accept, counter, decline and withdraw (Phase 16)."""

import pytest
from rest_framework.test import APIClient

from apps.messaging.models import Message, Offer, OfferStatus
from apps.products.models import ContactMode, ListingStatus, PriceMode
from tests.factories import ProductFactory

pytestmark = pytest.mark.django_db

CONVERSATIONS = "/api/v1/messages/conversations/"


def _negotiable(seller):
    return ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        contact_mode=ContactMode.CHAT,
        price_mode=PriceMode.NEGOTIABLE,
        base_price="100.00",
    )


def _conversation(client, listing):
    response = client.post(CONVERSATIONS, {"listing_id": listing.pk}, format="json")
    assert response.status_code in (200, 201)
    return response.data["id"]


def _offer(client, conversation_id, amount, note=""):
    return client.post(
        f"{CONVERSATIONS}{conversation_id}/offers/",
        {"amount": amount, "note": note},
        format="json",
    )


def _act(client, offer_id, action, data=None):
    return client.post(
        f"/api/v1/messages/offers/{offer_id}/{action}/",
        data or {},
        format="json",
    )


def test_an_offer_can_be_made_and_accepted(buyer_client, seller):
    conversation_id = _conversation(buyer_client, _negotiable(seller))

    created = _offer(buyer_client, conversation_id, "90.00", "Would you take 90?")
    assert created.status_code == 201
    offer_id = created.data["offer"]["id"]
    assert created.data["offer"]["status"] == OfferStatus.PENDING
    assert created.data["message"]["kind"] == "OFFER"
    assert Offer.objects.get(pk=offer_id).currency == "DZD"

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    accepted = _act(seller_client, offer_id, "accept")

    assert accepted.status_code == 200
    assert accepted.data["offer"]["status"] == OfferStatus.ACCEPTED
    assert Offer.objects.get(pk=offer_id).responded_at is not None


def test_a_counter_closes_the_parent_and_a_buyer_can_accept_it(buyer_client, seller):
    conversation_id = _conversation(buyer_client, _negotiable(seller))
    parent_id = _offer(buyer_client, conversation_id, "80.00").data["offer"]["id"]

    seller_client = APIClient()
    seller_client.force_authenticate(user=seller)
    countered = _act(
        seller_client, parent_id, "counter", {"amount": "95.00", "note": "95 is my floor"}
    )

    assert countered.status_code == 200
    assert countered.data["offer"]["status"] == OfferStatus.PENDING
    assert countered.data["offer"]["parent"] == parent_id
    assert Offer.objects.get(pk=parent_id).status == OfferStatus.COUNTERED
    new_id = countered.data["offer"]["id"]
    assert countered.data["message"]["offer"]["id"] == new_id

    accepted = _act(buyer_client, new_id, "accept")
    assert accepted.status_code == 200
    assert accepted.data["offer"]["status"] == OfferStatus.ACCEPTED


def test_only_one_offer_can_be_pending_at_a_time(buyer_client, seller):
    conversation_id = _conversation(buyer_client, _negotiable(seller))
    assert _offer(buyer_client, conversation_id, "80.00").status_code == 201

    second = _offer(buyer_client, conversation_id, "70.00")

    assert second.status_code == 409
    assert second.data["code"] == "open_offer_exists"
    assert Offer.objects.filter(conversation_id=conversation_id).count() == 1


def test_offers_are_refused_on_a_fixed_price_listing(buyer_client, seller):
    listing = ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        contact_mode=ContactMode.CHAT,
        price_mode=PriceMode.FIXED,
    )
    conversation_id = _conversation(buyer_client, listing)

    response = _offer(buyer_client, conversation_id, "90.00")

    assert response.status_code == 400
    assert response.data["code"] == "offer_not_allowed"


def test_the_creator_cannot_accept_their_own_offer_and_can_withdraw(buyer_client, seller):
    conversation_id = _conversation(buyer_client, _negotiable(seller))
    offer_id = _offer(buyer_client, conversation_id, "90.00").data["offer"]["id"]

    refused = _act(buyer_client, offer_id, "accept")
    assert refused.status_code == 403
    assert refused.data["code"] == "offer_action_not_allowed"

    withdrawn = _act(buyer_client, offer_id, "withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.data["offer"]["status"] == OfferStatus.WITHDRAWN

    # With the old offer closed, a new one can be made.
    assert _offer(buyer_client, conversation_id, "85.00").status_code == 201


def test_offer_actions_are_scoped_to_conversation_participants(buyer_client, seller):
    conversation_id = _conversation(buyer_client, _negotiable(seller))
    offer_id = _offer(buyer_client, conversation_id, "90.00").data["offer"]["id"]

    stranger = APIClient()
    from tests.factories import UserFactory

    stranger.force_authenticate(user=UserFactory())
    response = _act(stranger, offer_id, "decline")

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert Message.objects.filter(offer_id=offer_id).count() == 1
