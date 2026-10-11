"""Concurrency regression test for the inventory oversell race (Phase 6).

Kept in its own module because it needs a *transactional* database (real
commits, separate connections per thread) while the rest of the suite runs in
a rolled-back transaction.

Both workers are released by the same barrier so they genuinely overlap, and
the assertions hold whatever order Postgres happens to pick in.
"""

import threading

import pytest
from django.db import connections
from django.db.models import Sum

from apps.inventory import services as inventory_services
from apps.inventory.models import InventoryAuditLog
from tests.factories import InventoryFactory, ProductFactory


def run_concurrently(worker, count=2):
    """Start ``count`` copies of ``worker`` on the same barrier; return errors."""
    barrier = threading.Barrier(count, timeout=10)
    errors = []

    def runner():
        try:
            barrier.wait()
            worker()
        except Exception as exc:  # surfaced in the assertions below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=runner) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    return errors


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_cannot_oversell():
    """Two threads race for the last unit; only one may win."""
    product = ProductFactory()
    inventory = InventoryFactory(product=product, stock_quantity=1)
    initial_stock = 1

    def worker():
        inventory_services.reserve_inventory_for_order(
            [{"product": product, "quantity": 1, "selected_attributes": {}}]
        )

    errors = run_concurrently(worker)

    inventory.refresh_from_db()
    sold = (
        InventoryAuditLog.objects.filter(inventory=inventory, action_type="SALE").aggregate(
            total=Sum("quantity_delta")
        )["total"]
        or 0
    )

    # Invariant: every unit sold must be reflected in the stock counter.
    assert inventory.stock_quantity == initial_stock + sold, (
        f"Lost update detected: stock={inventory.stock_quantity} but the audit "
        f"log accounts for {sold} units (expected {initial_stock + sold})."
    )

    unexpected = [exc for exc in errors if "Insufficient stock" not in str(exc)]
    assert not unexpected, f"Unexpected worker errors: {unexpected!r}"
    # The row lock serializes the two attempts: one sells the unit, the other
    # is told there is nothing left to sell.
    assert len(errors) == 1
    assert inventory.stock_quantity == 0
    assert InventoryAuditLog.objects.filter(inventory=inventory, action_type="SALE").count() == 1
