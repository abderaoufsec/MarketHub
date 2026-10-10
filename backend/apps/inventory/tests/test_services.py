"""Inventory domain services: stock mutation, audit trail, reservations."""
import pytest
from django.db.models import Sum

from apps.inventory import services as inventory_services
from apps.inventory.models import Inventory, InventoryAuditLog
from tests.factories import InventoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


def test_update_inventory_increases_stock_and_writes_audit(inventory):
    inventory_services.update_inventory(inventory, 5, 'RESTOCK', 'New shipment')

    inventory.refresh_from_db()
    assert inventory.stock_quantity == 15

    log = InventoryAuditLog.objects.get(inventory=inventory)
    assert log.action_type == 'RESTOCK'
    assert log.quantity_delta == 5
    assert log.previous_quantity == 10
    assert log.new_quantity == 15
    assert log.reason == 'New shipment'


def test_update_inventory_refuses_negative_stock(inventory):
    with pytest.raises(ValueError) as excinfo:
        inventory_services.update_inventory(inventory, -100, 'SALE', 'too much')

    assert 'Insufficient stock' in str(excinfo.value)
    inventory.refresh_from_db()
    assert inventory.stock_quantity == 10
    assert not InventoryAuditLog.objects.exists()


def test_check_stock_availability(inventory):
    ok, found = inventory_services.check_stock_availability(inventory.product, {}, 10)
    assert ok is True and found == inventory

    ok, found = inventory_services.check_stock_availability(inventory.product, {}, 11)
    assert ok is False and found == inventory

    ok, found = inventory_services.check_stock_availability(
        inventory.product, {'color': 'red'}, 1
    )
    assert ok is False and found is None


def test_reserve_inventory_for_order(inventory):
    inventory_services.reserve_inventory_for_order(
        [{'product': inventory.product, 'quantity': 4, 'selected_attributes': {}}]
    )

    inventory.refresh_from_db()
    assert inventory.stock_quantity == 6
    log = InventoryAuditLog.objects.get(inventory=inventory)
    assert log.action_type == 'SALE'
    assert log.quantity_delta == -4


def test_reserve_inventory_rejects_insufficient_stock(inventory):
    with pytest.raises(ValueError) as excinfo:
        inventory_services.reserve_inventory_for_order(
            [{'product': inventory.product, 'quantity': 99, 'selected_attributes': {}}]
        )

    assert 'Insufficient stock' in str(excinfo.value)
    inventory.refresh_from_db()
    assert inventory.stock_quantity == 10


def test_reserve_inventory_rejects_unknown_inventory_row(product):
    """A product with no Inventory row must not be sellable."""
    with pytest.raises(ValueError):
        inventory_services.reserve_inventory_for_order(
            [{'product': product, 'quantity': 1, 'selected_attributes': {}}]
        )


def test_return_inventory_for_order_restores_stock(inventory):
    inventory_services.reserve_inventory_for_order(
        [{'product': inventory.product, 'quantity': 4, 'selected_attributes': {}}]
    )

    inventory_services.return_inventory_for_order(
        [{'product': inventory.product, 'quantity': 4, 'selected_attributes': {}}]
    )

    inventory.refresh_from_db()
    assert inventory.stock_quantity == 10
    deltas = InventoryAuditLog.objects.filter(inventory=inventory).aggregate(
        total=Sum('quantity_delta')
    )['total']
    assert deltas == 0


def test_return_inventory_creates_missing_row():
    product = ProductFactory()

    inventory_services.return_inventory_for_order(
        [{'product': product, 'quantity': 7, 'selected_attributes': {}}]
    )

    row = Inventory.objects.get(product=product)
    assert row.stock_quantity == 7
