"""Cart endpoints, including the bad-input defects from docs/todo.md §0.3."""
import pytest

from apps.orders.models import Cart, CartItem
from tests.factories import CartItemFactory, ProductFactory

pytestmark = pytest.mark.django_db

CART_URL = '/api/orders/cart/'
ADD_URL = '/api/orders/cart/add/'
CLEAR_URL = '/api/orders/cart/clear/'


def item_url(item_id):
    return f'{CART_URL}items/{item_id}/'


def remove_url(item_id):
    return f'{CART_URL}items/{item_id}/remove/'


def test_cart_requires_auth(api_client):
    assert api_client.get(CART_URL).status_code == 401


def test_get_cart_creates_empty_cart(buyer_client, buyer):
    response = buyer_client.get(CART_URL)

    assert response.status_code == 200
    assert response.data['items'] == []
    assert response.data['total_items'] == 0
    assert Cart.objects.filter(user=buyer).exists()


def test_add_to_cart(buyer_client, buyer, product, inventory):
    response = buyer_client.post(
        ADD_URL, {'product_id': product.id, 'quantity': 2}, format='json'
    )

    assert response.status_code == 201
    assert response.data['quantity'] == 2
    assert float(response.data['price_at_time_of_addition']) == 100.0
    assert float(response.data['subtotal']) == 200.0


def test_add_to_cart_increments_existing_line(buyer_client, product):
    buyer_client.post(ADD_URL, {'product_id': product.id, 'quantity': 1}, format='json')

    response = buyer_client.post(
        ADD_URL, {'product_id': product.id, 'quantity': 2}, format='json'
    )

    assert response.status_code == 200
    assert response.data['quantity'] == 3
    assert CartItem.objects.count() == 1


def test_add_unknown_product_is_rejected_not_500(buyer_client):
    """docs/todo.md §0.3 #1 claimed an unguarded Product.objects.get() → HTTP 500.

    The serializer's ``validate_product_id`` already guards it, so this is a
    green regression test: the endpoint must answer 400, never 500.
    """
    response = buyer_client.post(ADD_URL, {'product_id': 999999}, format='json')

    assert response.status_code == 400


def test_add_unavailable_product_is_rejected(buyer_client, product):
    product.is_available = False
    product.save()

    response = buyer_client.post(ADD_URL, {'product_id': product.id}, format='json')

    assert response.status_code == 400


def test_add_to_cart_rejects_zero_quantity(buyer_client, product):
    response = buyer_client.post(
        ADD_URL, {'product_id': product.id, 'quantity': 0}, format='json'
    )

    assert response.status_code == 400


def test_update_cart_quantity(buyer_client, product):
    added = buyer_client.post(ADD_URL, {'product_id': product.id, 'quantity': 1}, format='json')
    item_id = added.data['id']

    response = buyer_client.put(
        item_url(item_id), {'quantity': 5}, format='json'
    )

    assert response.status_code == 200
    assert response.data['quantity'] == 5


@pytest.mark.xfail(
    reason="docs/todo.md §0.3 #2: update_cart_item() calls int() on raw input, "
    "so non-numeric quantities raise ValueError → HTTP 500 (fixed in Phase 6)",
    strict=True,
)
def test_update_cart_rejects_non_numeric_quantity(buyer_client, product):
    added = buyer_client.post(ADD_URL, {'product_id': product.id, 'quantity': 1}, format='json')

    response = buyer_client.put(
        item_url(added.data['id']), {'quantity': 'lots'}, format='json'
    )

    assert response.status_code == 400


def test_update_cart_rejects_zero_quantity(buyer_client, product):
    added = buyer_client.post(ADD_URL, {'product_id': product.id, 'quantity': 1}, format='json')

    response = buyer_client.put(item_url(added.data['id']), {'quantity': 0}, format='json')

    assert response.status_code == 400


def test_update_cart_scoped_to_owner(buyer_client):
    foreign_item = CartItemFactory()

    response = buyer_client.put(item_url(foreign_item.id), {'quantity': 2}, format='json')

    assert response.status_code == 404


def test_update_missing_cart_item(buyer_client):
    response = buyer_client.put(item_url(999999), {'quantity': 2}, format='json')

    assert response.status_code == 404


def test_remove_cart_item(buyer_client, product):
    added = buyer_client.post(ADD_URL, {'product_id': product.id}, format='json')

    response = buyer_client.delete(remove_url(added.data['id']))

    assert response.status_code == 204
    assert not CartItem.objects.exists()


def test_remove_scoped_to_owner(buyer_client):
    foreign_item = CartItemFactory()

    response = buyer_client.delete(remove_url(foreign_item.id))

    assert response.status_code == 404


def test_clear_cart(buyer_client, product):
    buyer_client.post(ADD_URL, {'product_id': product.id}, format='json')

    response = buyer_client.delete(CLEAR_URL)

    assert response.status_code == 200
    assert not CartItem.objects.exists()


def test_clear_cart_when_empty_is_idempotent(buyer_client):
    response = buyer_client.delete(CLEAR_URL)

    assert response.status_code == 200


def test_cart_is_per_user(buyer_client, product, api_client):
    from rest_framework.test import APIClient

    from tests.factories import UserFactory

    buyer_client.post(ADD_URL, {'product_id': product.id}, format='json')
    assert buyer_client.get(CART_URL).data['total_items'] == 1

    other_client = APIClient()
    other_client.force_authenticate(user=UserFactory())
    assert other_client.get(CART_URL).data['total_items'] == 0
    assert api_client.get(CART_URL).status_code == 401


def test_add_product_from_second_store_is_allowed(buyer_client, product):
    """Cart is multi-store by design; checkout splits it per store."""
    from tests.factories import StoreFactory

    other = ProductFactory(store=StoreFactory())

    first = buyer_client.post(ADD_URL, {'product_id': product.id}, format='json')
    response = buyer_client.post(ADD_URL, {'product_id': other.id}, format='json')

    assert first.status_code == 201
    assert response.status_code == 201
    assert CartItem.objects.count() == 2
