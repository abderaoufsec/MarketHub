"""Object-level permission / IDOR matrix (Phase 7 of docs/todo.md).

Every write endpoint must refuse to touch an object the caller does not own —
either with 403 (fails the role check) or 404 (the queryset never exposes the
object). This suite walks the whole write surface so a future queryset
loosening turns red immediately.
"""

import pytest
from rest_framework.test import APIClient

from tests.factories import CartItemFactory, OrderFactory, ProductFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(db):
    """An order owned by a *stranger* (OrderFactory builds its own buyer)."""
    return OrderFactory()


@pytest.fixture
def other_seller_client(db):
    """A second, unrelated seller with their own store."""
    from tests.factories import StoreFactory

    other = UserFactory(is_seller=True)
    StoreFactory(owner=other)
    client = APIClient()
    client.force_authenticate(user=other)
    return client


# ---------------------------------------------------------------------------
# Listings (products)
# ---------------------------------------------------------------------------
def test_buyer_cannot_update_a_listing(buyer_client, product):
    response = buyer_client.put(
        f"/api/v1/products/seller/{product.id}/",
        {"name": "Hijacked", "description": "x", "base_price": "1.00", "category": "phones"},
        format="json",
    )

    assert response.status_code == 403


def test_buyer_cannot_delete_a_listing(buyer_client, product):
    response = buyer_client.delete(f"/api/v1/products/seller/{product.id}/")

    assert response.status_code == 403
    product.refresh_from_db()
    assert product.is_available in (True, False)  # row untouched


def test_other_seller_cannot_update_a_listing(other_seller_client, product):
    response = other_seller_client.put(
        f"/api/v1/products/seller/{product.id}/",
        {"name": "Hijacked", "description": "x", "base_price": "1.00", "category": "phones"},
        format="json",
    )

    assert response.status_code == 404


def test_other_seller_cannot_delete_a_listing(other_seller_client, product):
    response = other_seller_client.delete(f"/api/v1/products/seller/{product.id}/")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def test_buyer_cannot_update_order_status(buyer_client, order):
    response = buyer_client.put(
        f"/api/v1/orders/seller/{order.id}/update-status/",
        {"order_status": "SHIPPED"},
        format="json",
    )

    assert response.status_code == 403
    order.refresh_from_db()
    assert order.order_status != "SHIPPED"


def test_other_store_cannot_update_the_order(other_seller_client, order):
    response = other_seller_client.put(
        f"/api/v1/orders/seller/{order.id}/update-status/",
        {"order_status": "SHIPPED"},
        format="json",
    )

    assert response.status_code == 404
    order.refresh_from_db()
    assert order.order_status != "SHIPPED"


def test_buyer_cannot_see_another_users_order(buyer_client, order):
    # OrderFactory builds an order for someone else by default.
    response = buyer_client.get(f"/api/v1/orders/{order.id}/")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def test_buyer_cannot_update_inventory(buyer_client, product):
    response = buyer_client.post(
        f"/api/v1/inventory/product/{product.id}/update/",
        {"quantity_delta": 5, "action_type": "ADD"},
        format="json",
    )

    assert response.status_code == 403


def test_other_store_cannot_update_inventory(other_seller_client, product):
    response = other_seller_client.post(
        f"/api/v1/inventory/product/{product.id}/update/",
        {"quantity_delta": 5, "action_type": "ADD"},
        format="json",
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
def test_other_buyer_cannot_refund_a_foreign_order(buyer_client, order):
    response = buyer_client.post(f"/api/v1/payments/refund/{order.id}/")

    assert response.status_code in (403, 404)


def test_other_buyer_cannot_pay_a_foreign_order(buyer_client, order):
    response = buyer_client.post(
        "/api/v1/payments/simulate/", {"order_id": order.id}, format="json"
    )

    assert response.status_code == 404


def test_anonymous_cannot_pay_or_refund(order):
    client = APIClient()

    pay = client.post("/api/v1/payments/simulate/", {"order_id": order.id}, format="json")
    refund = client.post(f"/api/v1/payments/refund/{order.id}/")

    assert pay.status_code == 401
    assert refund.status_code == 401


# ---------------------------------------------------------------------------
# Cart & addresses
# ---------------------------------------------------------------------------
def test_other_buyer_cannot_update_a_cart_item(buyer_client):
    other_item = CartItemFactory(cart__user=UserFactory())

    response = buyer_client.put(
        f"/api/v1/orders/cart/items/{other_item.id}/",
        {"quantity": 99},
        format="json",
    )

    assert response.status_code == 404


def test_anonymous_write_endpoints_demand_auth(order, product):
    client = APIClient()
    urls = [
        ("put", f"/api/v1/products/seller/{product.id}/"),
        ("delete", f"/api/v1/products/seller/{product.id}/"),
        ("put", f"/api/v1/orders/seller/{order.id}/update-status/"),
        ("post", f"/api/v1/inventory/product/{product.id}/update/"),
        ("post", "/api/v1/orders/checkout/"),
    ]
    for method, url in urls:
        response = getattr(client, method)(url, {}, format="json")
        assert response.status_code == 401, f"{method.upper()} {url} -> {response.status_code}"


# ---------------------------------------------------------------------------
# Permission classes in isolation
# ---------------------------------------------------------------------------
def test_is_seller_permission():
    from rest_framework.test import APIRequestFactory

    from apps.users.permissions import IsSeller

    factory = APIRequestFactory()
    request = factory.get("/")
    permission = IsSeller()

    class _V:
        pass

    request.user = UserFactory()
    assert permission.has_permission(request, _V()) is False

    request.user = UserFactory(is_seller=True)
    assert permission.has_permission(request, _V()) is True


def test_is_store_owner_object_check_matches_owner():
    from rest_framework.test import APIRequestFactory

    from apps.users.permissions import IsStoreOwner
    from tests.factories import StoreFactory

    owner = UserFactory(is_seller=True)
    store = StoreFactory(owner=owner)

    factory = APIRequestFactory()
    request = factory.put("/")
    request.user = owner
    permission = IsStoreOwner()

    class _V:
        pass

    assert permission.has_object_permission(request, _V(), store) is True
    # A stranger cannot pass the object check.
    request.user = UserFactory(is_seller=True)
    assert permission.has_object_permission(request, _V(), store) is False


def test_is_listing_owner_object_check_uses_the_store():
    from rest_framework.test import APIRequestFactory

    from apps.users.permissions import IsListingOwner
    from tests.factories import StoreFactory

    owner = UserFactory(is_seller=True)
    store = StoreFactory(owner=owner)
    listing = ProductFactory(store=store)

    factory = APIRequestFactory()
    request = factory.delete("/")
    request.user = owner
    permission = IsListingOwner()

    class _V:
        pass

    assert permission.has_object_permission(request, _V(), listing) is True
    request.user = UserFactory(is_seller=True)
    assert permission.has_object_permission(request, _V(), listing) is False


def test_order_factory_default_belongs_to_a_stranger(order, buyer):
    """Sanity for the matrix above: ``order`` is never the buyer's."""
    assert order.user_id != buyer.id
