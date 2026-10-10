"""Checkout: order creation, per-store split, and the transactional defects.

docs/todo.md §0.3 #3/#4 — ``return Response(...)`` *inside*
``transaction.atomic()`` commits partial state (an order for a FAILED payment,
or an order whose inventory reservation failed).
"""

from decimal import Decimal

import pytest

from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.payments.models import PlatformCommissionLedger, Transaction
from tests.factories import (
    CartFactory,
    CartItemFactory,
    InventoryFactory,
    ProductFactory,
    StoreFactory,
)

pytestmark = pytest.mark.django_db

CHECKOUT_URL = "/api/orders/checkout/"
ORDERS_URL = "/api/orders/"
SELLER_ORDERS_URL = "/api/orders/seller/list/"


def checkout_payload(address, **overrides):
    data = {"shipping_address_id": address.id, "shipping_method": "standard"}
    data.update(overrides)
    return data


def fill_cart(buyer, product, quantity=1, price=None):
    cart, _ = Cart.objects.get_or_create(user=buyer)
    return CartItemFactory(
        cart=cart,
        product=product,
        quantity=quantity,
        price_at_time_of_addition=price if price is not None else product.base_price,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_checkout_creates_paid_order_and_reserves_stock(
    buyer_client, buyer, address, product, inventory
):
    fill_cart(buyer, product, quantity=2)

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 201
    order = Order.objects.get()
    assert order.order_status == "PROCESSING"
    assert order.payment_status == "SUCCESSFUL"
    assert order.total_amount == Decimal("200.00")
    assert order.items.count() == 1
    assert order.shipping_address == address

    inventory.refresh_from_db()
    assert inventory.stock_quantity == 8

    assert Transaction.objects.filter(order=order).exists()
    assert PlatformCommissionLedger.objects.filter(transaction__order=order).exists()
    assert not CartItem.objects.exists()
    assert len(response.data["orders"]) == 1


def test_checkout_splits_cart_per_store(buyer_client, buyer, address, product, inventory):
    other_store = StoreFactory()
    other_product = ProductFactory(store=other_store)
    InventoryFactory(product=other_product, stock_quantity=5)
    fill_cart(buyer, product)
    fill_cart(buyer, other_product, quantity=2)

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 201
    assert Order.objects.count() == 2
    assert {order.store_id for order in Order.objects.all()} == {
        product.store_id,
        other_store.id,
    }


def test_checkout_empty_cart_rejected(buyer_client, address):
    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 400


def test_checkout_requires_auth(api_client, address):
    response = api_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 401


def test_checkout_rejects_foreign_shipping_address(buyer_client, address, buyer):
    """docs/todo.md §0.3 #3 claimed Address.objects.get() → HTTP 500.

    ``CheckoutSerializer.validate_shipping_address_id`` already scopes the
    lookup to the requesting user, so the guard exists: green regression test.
    """
    from tests.factories import AddressFactory, UserFactory

    foreign = AddressFactory(user=UserFactory())

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(foreign), format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0


# ---------------------------------------------------------------------------
# Defects (failing-first, fixed in Phase 6)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="docs/todo.md §0.3 #1/#4: the stock-failure branch returns inside "
    "transaction.atomic(), committing an order with no inventory reserved "
    "(fixed in Phase 6 by raising a domain exception outside the block)",
    strict=True,
)
def test_checkout_rolls_back_when_stock_is_missing(buyer_client, buyer, address, product):
    """No inventory row at all -> reservation must fail and commit nothing."""
    fill_cart(buyer, product, quantity=1)

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0


@pytest.mark.xfail(
    reason="docs/todo.md §0.3 #4: a FAILED order is committed with its stock "
    "still reserved because the failure branch returns inside the atomic block "
    "(fixed in Phase 6)",
    strict=True,
)
def test_failed_payment_leaves_no_order_and_no_reserved_stock(
    buyer_client, buyer, address, product, inventory, monkeypatch
):
    monkeypatch.setattr(
        "apps.orders.views.process_simulated_payment",
        lambda order: {"success": False, "error": "declined"},
    )
    fill_cart(buyer, product, quantity=2)

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    assert response.status_code == 400
    assert Order.objects.count() == 0
    inventory.refresh_from_db()
    assert inventory.stock_quantity == 10


@pytest.mark.xfail(
    reason="docs/todo.md Phase 6: checkout charges price_at_time_of_addition "
    "instead of re-validating the current price",
    strict=True,
)
def test_checkout_uses_the_current_price(buyer_client, buyer, address, product, inventory):
    """A price change between add-to-cart and checkout must never be silent."""
    fill_cart(buyer, product, quantity=1, price=Decimal("100.00"))
    product.base_price = Decimal("150.00")
    product.save()

    response = buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    if response.status_code == 201:
        order = Order.objects.get()
        assert order.total_amount == Decimal("150.00")
    else:
        # Rejecting with a "price changed" response is also acceptable.
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Order history
# ---------------------------------------------------------------------------
def test_order_list_requires_auth(api_client):
    assert api_client.get(ORDERS_URL).status_code == 401


def test_order_list_and_detail_are_scoped_to_owner(
    buyer_client, buyer, address, product, inventory
):
    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    listed = buyer_client.get(ORDERS_URL)
    assert listed.status_code == 200
    assert listed.data["count"] == 1

    detail = buyer_client.get(f"{ORDERS_URL}{order.id}/")
    assert detail.status_code == 200
    assert detail.data["id"] == order.id

    other_client_order = buyer_client.get(f"{ORDERS_URL}999999/")
    assert other_client_order.status_code == 404


def test_order_detail_hidden_from_other_users(
    buyer_client, buyer, address, product, inventory, api_client
):
    from rest_framework.test import APIClient

    from tests.factories import UserFactory

    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    other = APIClient()
    other.force_authenticate(user=UserFactory())

    assert other.get(f"{ORDERS_URL}{order.id}/").status_code == 404
    assert other.get(ORDERS_URL).data["count"] == 0
    assert api_client.get(ORDERS_URL).status_code == 401


def test_seller_order_list_scoped_to_store(
    buyer_client, buyer, address, product, inventory, seller_client, seller
):
    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")

    listed = seller_client.get(SELLER_ORDERS_URL)

    assert listed.status_code == 200
    assert listed.data["count"] == 1

    # A buyer without a store sees nothing rather than an error.
    assert buyer_client.get(SELLER_ORDERS_URL).data["count"] == 0


def test_seller_can_update_order_status(
    buyer_client, buyer, address, product, inventory, seller_client
):
    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    response = seller_client.put(
        f"/api/orders/seller/{order.id}/update-status/",
        {"order_status": "SHIPPED", "tracking_number": "TRACK-1"},
        format="json",
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.order_status == "SHIPPED"
    assert order.tracking_number == "TRACK-1"


def test_update_order_status_rejects_invalid_value(
    buyer_client, buyer, address, product, inventory, seller_client
):
    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    response = seller_client.put(
        f"/api/orders/seller/{order.id}/update-status/",
        {"order_status": "TELEPORTED"},
        format="json",
    )

    assert response.status_code == 400


def test_update_order_status_forbidden_for_buyers(buyer_client, buyer, address, product, inventory):
    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    response = buyer_client.put(
        f"/api/orders/seller/{order.id}/update-status/",
        {"order_status": "SHIPPED"},
        format="json",
    )

    assert response.status_code == 403


def test_update_order_status_scoped_to_own_store(buyer_client, buyer, address, product, inventory):
    from rest_framework.test import APIClient

    from tests.factories import StoreFactory

    fill_cart(buyer, product)
    buyer_client.post(CHECKOUT_URL, checkout_payload(address), format="json")
    order = Order.objects.get()

    foreign_store = StoreFactory()
    foreign_client = APIClient()
    foreign_client.force_authenticate(user=foreign_store.owner)

    response = foreign_client.put(
        f"/api/orders/seller/{order.id}/update-status/",
        {"order_status": "CANCELLED"},
        format="json",
    )

    assert response.status_code == 404
