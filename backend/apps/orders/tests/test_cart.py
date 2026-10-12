"""Cart endpoints, including the bad-input defects from docs/todo.md §0.3."""

from decimal import Decimal

import pytest

from apps.orders.models import Cart, CartItem
from tests.factories import CartItemFactory, ProductFactory

pytestmark = pytest.mark.django_db

CART_URL = "/api/v1/orders/cart/"
ADD_URL = "/api/v1/orders/cart/add/"
CLEAR_URL = "/api/v1/orders/cart/clear/"
REFRESH_URL = "/api/v1/orders/cart/refresh-prices/"


def item_url(item_id):
    return f"{CART_URL}items/{item_id}/"


def remove_url(item_id):
    return f"{CART_URL}items/{item_id}/remove/"


def test_cart_requires_auth(api_client):
    assert api_client.get(CART_URL).status_code == 401


def test_get_cart_creates_empty_cart(buyer_client, buyer):
    response = buyer_client.get(CART_URL)

    assert response.status_code == 200
    assert response.data["items"] == []
    assert response.data["total_items"] == 0
    assert Cart.objects.filter(user=buyer).exists()


def test_add_to_cart(buyer_client, buyer, product, inventory):
    response = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 2}, format="json")

    assert response.status_code == 201
    assert response.data["quantity"] == 2
    assert float(response.data["price_at_time_of_addition"]) == 100.0
    assert float(response.data["subtotal"]) == 200.0


def test_add_to_cart_increments_existing_line(buyer_client, product, inventory):
    buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 1}, format="json")

    response = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 2}, format="json")

    assert response.status_code == 200
    assert response.data["quantity"] == 3
    assert CartItem.objects.count() == 1


def test_add_unknown_product_is_rejected_not_500(buyer_client):
    """docs/todo.md §0.3 #1 claimed an unguarded Product.objects.get() → HTTP 500.

    The serializer's ``validate_product_id`` already guards it, so this is a
    green regression test: the endpoint must answer 400, never 500.
    """
    response = buyer_client.post(ADD_URL, {"product_id": 999999}, format="json")

    assert response.status_code == 400


def test_add_unavailable_product_is_rejected(buyer_client, product, inventory):
    product.is_available = False
    product.save()

    response = buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")

    assert response.status_code == 400


def test_add_to_cart_rejects_zero_quantity(buyer_client, product, inventory):
    response = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 0}, format="json")

    assert response.status_code == 400


def test_add_to_cart_rejects_more_than_stock(buyer_client, product, inventory):
    """docs/todo.md Phase 6: stock is validated at cart/add, not first at checkout."""
    response = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 11}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "insufficient_stock"
    # Phase 9 envelope: the id in the body is the X-Request-ID header.
    assert response.data["request_id"] == response["X-Request-ID"]
    assert not CartItem.objects.exists()


def test_add_to_cart_rejects_growing_a_line_past_stock(buyer_client, product, inventory):
    buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 8}, format="json")

    response = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 3}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "insufficient_stock"
    # The rejected increment must not have been applied.
    assert CartItem.objects.get().quantity == 8


def test_add_to_cart_rejects_product_without_inventory(buyer_client):
    """A product with no Inventory row is not sellable anywhere, so it must not
    become a cart line that checkout would only reject later."""
    product = ProductFactory(is_available=True)

    response = buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "insufficient_stock"
    assert not CartItem.objects.exists()


def test_update_cart_quantity(buyer_client, product, inventory):
    added = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 1}, format="json")
    item_id = added.data["id"]

    response = buyer_client.put(item_url(item_id), {"quantity": 5}, format="json")

    assert response.status_code == 200
    assert response.data["quantity"] == 5


def test_update_cart_rejects_non_numeric_quantity(buyer_client, product, inventory):
    """docs/todo.md §0.3 #2 (Phase 6): int() on raw input raised ValueError ->
    HTTP 500; DRF now answers 400. The inventory fixture keeps the only other
    400 path (stock) out of the picture, so this stays a real assertion."""
    added = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 1}, format="json")

    response = buyer_client.put(item_url(added.data["id"]), {"quantity": "lots"}, format="json")

    assert response.status_code == 400


def test_update_cart_rejects_zero_quantity(buyer_client, product, inventory):
    added = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 1}, format="json")

    response = buyer_client.put(item_url(added.data["id"]), {"quantity": 0}, format="json")

    assert response.status_code == 400


def test_update_cart_rejects_quantity_above_stock(buyer_client, product, inventory):
    added = buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 1}, format="json")
    item_id = added.data["id"]

    response = buyer_client.put(item_url(item_id), {"quantity": 50}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "insufficient_stock"
    assert CartItem.objects.get().quantity == 1


def test_update_cart_scoped_to_owner(buyer_client):
    foreign_item = CartItemFactory()

    response = buyer_client.put(item_url(foreign_item.id), {"quantity": 2}, format="json")

    assert response.status_code == 404


def test_update_missing_cart_item(buyer_client):
    response = buyer_client.put(item_url(999999), {"quantity": 2}, format="json")

    assert response.status_code == 404


def test_remove_cart_item(buyer_client, product, inventory):
    added = buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")

    response = buyer_client.delete(remove_url(added.data["id"]))

    assert response.status_code == 204
    assert not CartItem.objects.exists()


def test_remove_scoped_to_owner(buyer_client):
    foreign_item = CartItemFactory()

    response = buyer_client.delete(remove_url(foreign_item.id))

    assert response.status_code == 404


def test_clear_cart(buyer_client, product, inventory):
    buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")

    response = buyer_client.delete(CLEAR_URL)

    assert response.status_code == 200
    assert not CartItem.objects.exists()


def test_clear_cart_when_empty_is_idempotent(buyer_client):
    response = buyer_client.delete(CLEAR_URL)

    assert response.status_code == 200


def test_cart_is_per_user(buyer_client, product, inventory, api_client):
    from rest_framework.test import APIClient

    from tests.factories import UserFactory

    buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")
    assert buyer_client.get(CART_URL).data["total_items"] == 1

    other_client = APIClient()
    other_client.force_authenticate(user=UserFactory())
    assert other_client.get(CART_URL).data["total_items"] == 0
    assert api_client.get(CART_URL).status_code == 401


def test_add_product_from_second_store_is_allowed(buyer_client, product, inventory):
    """Cart is multi-store by design; checkout splits it per store."""
    from tests.factories import InventoryFactory, StoreFactory

    other = ProductFactory(store=StoreFactory())
    InventoryFactory(product=other, stock_quantity=5)

    first = buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")
    response = buyer_client.post(ADD_URL, {"product_id": other.id}, format="json")

    assert first.status_code == 201
    assert response.status_code == 201
    assert CartItem.objects.count() == 2


def test_refresh_prices_reprices_the_cart(buyer_client, product, inventory):
    """docs/todo.md Phase 6: checkout refuses stale prices; this is the way a
    buyer accepts the new ones."""
    buyer_client.post(ADD_URL, {"product_id": product.id, "quantity": 2}, format="json")
    product.base_price = Decimal("150.00")
    product.save()

    response = buyer_client.post(REFRESH_URL, {}, format="json")

    assert response.status_code == 200
    assert response.data["updated"] == [
        {
            "product_id": product.id,
            "product_name": product.name,
            "old_price": Decimal("100.00"),
            "new_price": Decimal("150.00"),
        }
    ]
    item = CartItem.objects.get()
    assert item.price_at_time_of_addition == Decimal("150.00")
    assert response.data["cart"]["total_price"] == "300.00"


def test_refresh_prices_is_a_no_op_when_nothing_changed(buyer_client, product, inventory):
    buyer_client.post(ADD_URL, {"product_id": product.id}, format="json")

    response = buyer_client.post(REFRESH_URL, {}, format="json")

    assert response.status_code == 200
    assert response.data["updated"] == []
    assert CartItem.objects.get().price_at_time_of_addition == product.base_price
