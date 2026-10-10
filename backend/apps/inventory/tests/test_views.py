"""Inventory API endpoints (seller-scoped)."""
import pytest

from apps.inventory import services as inventory_services
from tests.factories import InventoryFactory, ProductFactory

pytestmark = pytest.mark.django_db

LIST_URL = '/api/inventory/'
LOW_STOCK_URL = '/api/inventory/low-stock/'
AUDIT_URL = '/api/inventory/audit-log/'


def update_payload(**overrides):
    data = {'quantity_delta': 5, 'action_type': 'RESTOCK', 'reason': 'New shipment'}
    data.update(overrides)
    return data


def update_url(product):
    return f'/api/inventory/product/{product.id}/update/'


def test_inventory_list_requires_auth(api_client):
    assert api_client.get(LIST_URL).status_code == 401


def test_inventory_list_shows_seller_stock(seller_client, inventory):
    response = seller_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['results'][0]['product_name'] == inventory.product.name
    assert response.data['results'][0]['stock_quantity'] == 10


def test_inventory_list_empty_for_buyer(buyer_client, inventory):
    response = buyer_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.data['count'] == 0


def test_inventory_detail_scoped_to_store(seller_client, inventory):
    assert seller_client.get(f'{LIST_URL}{inventory.id}/').status_code == 200

    other_seller_inventory = InventoryFactory(product=ProductFactory())
    assert seller_client.get(f'{LIST_URL}{other_seller_inventory.id}/').status_code == 404


def test_update_inventory_restocks_and_logs(seller_client, inventory, product):
    response = seller_client.post(update_url(product), update_payload(), format='json')

    assert response.status_code == 200
    assert response.data['stock_quantity'] == 15
    assert inventory.audit_logs.count() == 1


def test_update_inventory_rejects_insufficient_stock(seller_client, product):
    InventoryFactory(product=product, stock_quantity=2)

    response = seller_client.post(
        update_url(product), update_payload(quantity_delta=-5, action_type='SALE'),
        format='json',
    )

    assert response.status_code == 400
    assert 'Insufficient stock' in str(response.data)


def test_update_inventory_rejects_zero_delta(seller_client, product):
    response = seller_client.post(
        update_url(product), update_payload(quantity_delta=0), format='json'
    )

    assert response.status_code == 400


def test_update_inventory_404_for_foreign_product(seller_client, store):
    foreign = ProductFactory()

    response = seller_client.post(update_url(foreign), update_payload(), format='json')

    assert response.status_code == 404


def test_update_inventory_403_for_buyer(buyer_client, product):
    response = buyer_client.post(update_url(product), update_payload(), format='json')

    assert response.status_code == 403


def test_low_stock_items(seller_client, product, inventory):
    InventoryFactory(product=ProductFactory(store=product.store), stock_quantity=3)

    response = seller_client.get(LOW_STOCK_URL)

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]['stock_quantity'] == 3


def test_low_stock_requires_seller(buyer_client):
    response = buyer_client.get(LOW_STOCK_URL)

    assert response.status_code == 403


def test_audit_log_lists_and_filters(seller_client, product, inventory):
    inventory_services.reserve_inventory_for_order(
        [{'product': product, 'quantity': 2, 'selected_attributes': {}}]
    )

    listed = seller_client.get(AUDIT_URL)
    assert listed.status_code == 200
    assert listed.data['count'] == 1

    filtered = seller_client.get(AUDIT_URL, {'product_id': product.id})
    assert filtered.data['count'] == 1

    other = seller_client.get(AUDIT_URL, {'product_id': 999999})
    assert other.data['count'] == 0


def test_audit_log_empty_for_buyer(buyer_client, inventory):
    response = buyer_client.get(AUDIT_URL)

    assert response.status_code == 200
    assert response.data['count'] == 0
