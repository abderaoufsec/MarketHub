"""Store catalogue, seller store management and dashboard stats."""

import pytest

from tests.factories import (
    InventoryFactory,
    ProductFactory,
    StoreFactory,
    default_category,
)

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/stores/"
CREATE_URL = "/api/v1/stores/seller/create/"
MY_STORE_URL = "/api/v1/stores/seller/my-store/"
STATS_URL = "/api/v1/stores/seller/stats/"


def store_payload(**overrides):
    data = {
        "store_name": "Gadget Zone",
        "description": "Phones, tablets and accessories.",
        # Phase 12: the write contract is the catalog FK (``category_id``).
        "category_id": default_category().id,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------
def test_store_list_is_public(api_client, store):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    # Cursor-paginated (Phase 10): no ``count`` on a feed page.
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["store_slug"] == store.store_slug


def test_store_list_hides_inactive_stores(api_client, store):
    StoreFactory(store_name="Closed Store", is_active=False)

    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    names = [item["store_name"] for item in response.data["results"]]
    assert "Closed Store" not in names


def test_store_detail_by_slug(api_client, store):
    response = api_client.get(f"{LIST_URL}{store.store_slug}/")

    assert response.status_code == 200
    assert response.data["owner"]["email"] == store.owner.email


def test_store_detail_unknown_slug_404(api_client):
    response = api_client.get(f"{LIST_URL}does-not-exist/")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Seller store management
# ---------------------------------------------------------------------------
def test_create_store_requires_seller_flag(buyer_client):
    response = buyer_client.post(CREATE_URL, store_payload(), format="json")

    assert response.status_code == 403


def test_create_store_requires_authentication(api_client):
    response = api_client.post(CREATE_URL, store_payload(), format="json")

    assert response.status_code == 401


def test_seller_creates_store(seller_client, seller):
    response = seller_client.post(CREATE_URL, store_payload(), format="json")

    assert response.status_code == 201
    assert response.data["store_slug"] == "gadget-zone"
    assert seller.store.store_name == "Gadget Zone"


def test_create_store_twice_is_rejected(seller_client):
    from apps.stores.models import Store

    first = seller_client.post(CREATE_URL, store_payload(), format="json")
    assert first.status_code == 201

    response = seller_client.post(CREATE_URL, store_payload(), format="json")

    assert response.status_code == 400
    # Phase 9 envelope: the duplicate create is refused with a branchable code,
    # and refused means *no second store* — Store.owner is a OneToOne, so the
    # database enforces it too (the listing-create view needs IdempotentPostMixin;
    # this one cannot double-create without it).
    assert response.data["code"] == "store_exists"
    assert response.data["request_id"] == response["X-Request-ID"]
    assert Store.objects.count() == 1


def test_create_store_rejects_unknown_category(seller_client):
    response = seller_client.post(CREATE_URL, store_payload(category_id=999999), format="json")

    assert response.status_code == 400
    # Field errors arrive in the envelope's details, keyed by field name.
    # Phase 12: the write contract is the catalog FK, ``category_id``.
    assert response.data["code"] == "validation_error"
    assert "category_id" in response.data["details"]


def test_my_store_round_trip(seller_client, store):
    assert seller_client.get(MY_STORE_URL).status_code == 200

    response = seller_client.put(
        MY_STORE_URL, {"description": "Updated description."}, format="json"
    )

    assert response.status_code == 200
    store.refresh_from_db()
    assert store.description == "Updated description."


def test_my_store_404_for_seller_without_store(seller_client):
    response = seller_client.get(MY_STORE_URL)

    assert response.status_code == 404
    assert response.data["code"] == "store_not_found"
    assert response.data["request_id"] == response["X-Request-ID"]


def test_my_store_403_for_non_seller(buyer_client):
    response = buyer_client.get(MY_STORE_URL)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def test_store_stats_reports_real_counts(seller_client, store, product, inventory):
    unavailable = ProductFactory(store=store, is_available=False)
    InventoryFactory(product=unavailable, stock_quantity=10)

    response = seller_client.get(STATS_URL)

    assert response.status_code == 200
    assert response.data["total_products"] == 2
    assert response.data["active_products"] == 1
    assert response.data["total_orders"] == 0
    assert response.data["low_stock_products"] == 0


def test_store_stats_requires_store(buyer_client):
    response = buyer_client.get(STATS_URL)

    assert response.status_code == 404
    assert response.data["code"] == "store_not_found"


# ---------------------------------------------------------------------------
# Anti-scraping (Phase 7): the store payload embeds the owner's phone number,
# so the public endpoints carry the scoped `reveal_phone` throttle.
# ---------------------------------------------------------------------------
def test_store_list_exposes_owner_contact(api_client, store):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert "phone_number" in response.data["results"][0]["owner"]


def test_reveal_phone_scoped_throttle_trips():
    from rest_framework.test import APIClient

    from tests.helpers import throttle_rate

    client = APIClient()
    with throttle_rate("reveal_phone", "2/min"):
        codes = [client.get(LIST_URL).status_code for _ in range(4)]

    assert codes[:2] == [200, 200]
    assert codes[2:] == [429, 429]
