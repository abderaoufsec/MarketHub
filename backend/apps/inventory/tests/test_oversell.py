"""Concurrency regression test for the inventory oversell race.

Kept in its own module because it needs a *transactional* database (real
commits, separate connections per thread) while the rest of the suite runs in
a rolled-back transaction.
"""
import threading

import pytest
from django.db import connections
from django.db.models import Sum

from apps.inventory import services as inventory_services
from apps.inventory.models import Inventory, InventoryAuditLog
from tests.factories import InventoryFactory, ProductFactory


@pytest.mark.django_db(transaction=True)
@pytest.mark.xfail(
    reason="Oversell race: reserve_inventory_for_order() reads availability "
    "without select_for_update()/F(), so two concurrent checkouts can both "
    "reserve the last unit (docs/todo.md §0.3, fixed in Phase 6)",
    strict=True,
)
def test_concurrent_reservations_cannot_oversell(monkeypatch):
    """Two threads race for the last unit; only one may win."""
    product = ProductFactory()
    inventory = InventoryFactory(product=product, stock_quantity=1)
    initial_stock = 1

    # Both threads must finish their availability check before either writes,
    # which is exactly the window the missing row lock leaves open.
    barrier = threading.Barrier(2, timeout=10)
    original_update = inventory_services.update_inventory
    failures = []

    def synchronized_update(inv, quantity_delta, action_type, reason=''):
        barrier.wait()
        return original_update(inv, quantity_delta, action_type, reason)

    monkeypatch.setattr(inventory_services, 'update_inventory', synchronized_update)

    def worker():
        try:
            inventory_services.reserve_inventory_for_order(
                [{'product': product, 'quantity': 1, 'selected_attributes': {}}]
            )
        except Exception as exc:  # noqa: BLE001 - the loser must fail cleanly
            failures.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    inventory.refresh_from_db()
    sold = (
        InventoryAuditLog.objects.filter(
            inventory=inventory, action_type='SALE'
        ).aggregate(total=Sum('quantity_delta'))['total']
        or 0
    )

    # Invariant: every unit sold must be reflected in the stock counter.
    assert inventory.stock_quantity == initial_stock + sold, (
        f'Lost update detected: stock={inventory.stock_quantity} but the audit '
        f'log accounts for {sold} units (expected {initial_stock + sold}). '
        f'Worker errors: {failures!r}'
    )
    assert inventory.stock_quantity >= 0, 'Stock must never go negative'
