"""Concurrency regression test for the double-charge race (docs/todo.md Phase 6).

Kept in its own module because it needs a *transactional* database (real
commits, separate connections per thread) while the rest of the suite runs in
a rolled-back transaction.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections

from apps.payments import services as payment_services
from apps.payments.models import Transaction
from tests.factories import OrderFactory, UserFactory


@pytest.mark.django_db(transaction=True)
def test_concurrent_payment_attempts_charge_the_order_only_once():
    """Two simultaneous captures for one order must produce one Transaction."""
    buyer = UserFactory()
    order = OrderFactory(
        user=buyer,
        total_amount=Decimal("200.00"),
        payment_status="PENDING",
        order_status="PENDING",
    )

    barrier = threading.Barrier(2, timeout=10)
    results = []

    def worker():
        try:
            barrier.wait()
            results.append(payment_services.process_simulated_payment(order))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    order.refresh_from_db()

    assert Transaction.objects.filter(order=order).count() == 1
    assert sum(1 for result in results if result["success"]) == 1, (
        f"exactly one attempt may capture the order, got {results!r}"
    )
    # The order ends up paid exactly once, in the same transaction as the
    # Transaction row that recorded it.
    assert order.payment_status == "SUCCESSFUL"
    assert order.order_status == "PROCESSING"


@pytest.mark.django_db(transaction=True)
def test_idempotency_key_survives_a_concurrent_retry():
    """Replaying the same key concurrently must not create a second charge."""
    buyer = UserFactory()
    order = OrderFactory(
        user=buyer,
        total_amount=Decimal("200.00"),
        payment_status="PENDING",
        order_status="PENDING",
    )
    key = "retry-after-timeout"

    barrier = threading.Barrier(2, timeout=10)

    def worker():
        try:
            barrier.wait()
            payment_services.process_simulated_payment(order, idempotency_key=key)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert Transaction.objects.filter(order=order).count() == 1
    assert Transaction.objects.get(order=order).idempotency_key == key
