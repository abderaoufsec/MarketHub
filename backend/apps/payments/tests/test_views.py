"""Payment endpoints: simulation, refunds, status, commission ledger.

Phase 9 of docs/todo.md: failures are asserted through the standard envelope
(``code`` / ``message`` / ``details`` / ``request_id``) instead of the old
hand-built ``{"error": …}`` bodies, and the two money-moving endpoints are
exercised with the ``Idempotency-Key`` header as well as the Phase 6 body
field. Success bodies are asserted exactly as before: they did not change.
"""

from decimal import Decimal

import pytest

from apps.payments.models import PlatformCommissionLedger, Transaction
from tests.factories import (
    OrderFactory,
    TransactionFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

TRANSACTIONS_URL = "/api/v1/payments/transactions/"
SIMULATE_URL = "/api/v1/payments/simulate/"
COMMISSIONS_URL = "/api/v1/payments/seller/commissions/"


def refund_url(order_id):
    return f"/api/v1/payments/refund/{order_id}/"


def status_url(order_id):
    return f"/api/v1/payments/status/{order_id}/"


def paid_order(user, amount=Decimal("200.00")):
    order = OrderFactory(
        user=user,
        total_amount=amount,
        payment_status="SUCCESSFUL",
        order_status="PROCESSING",
    )
    txn = TransactionFactory(order=order, amount=amount)
    PlatformCommissionLedger.objects.create(
        transaction=txn,
        order_total=amount,
        commission_rate=Decimal("0.15"),
        commission_amount=Decimal("30.00"),
        net_payout_to_seller=Decimal("170.00"),
        payout_status="PENDING",
    )
    return order


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def test_transactions_require_auth(api_client):
    assert api_client.get(TRANSACTIONS_URL).status_code == 401


def test_transactions_scoped_to_own_orders(buyer_client, buyer):
    mine = OrderFactory(user=buyer)
    TransactionFactory(order=mine)
    TransactionFactory(order=OrderFactory(user=UserFactory()))

    response = buyer_client.get(TRANSACTIONS_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# Simulated payment
# ---------------------------------------------------------------------------
def test_simulate_payment_succeeds(buyer_client, buyer):
    order = OrderFactory(user=buyer, total_amount=Decimal("200.00"))

    response = buyer_client.post(
        SIMULATE_URL, {"order_id": order.id, "payment_method": "cib"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["commission"] == 30.0
    assert response.data["net_to_seller"] == 170.0

    order.refresh_from_db()
    assert order.payment_status == "SUCCESSFUL"
    assert order.order_status == "PROCESSING"

    txn = Transaction.objects.get(order=order)
    assert txn.gateway_used == "SIMULATED"
    assert txn.commission.commission_amount == Decimal("30.00")


def test_simulate_payment_requires_order_id(buyer_client):
    response = buyer_client.post(SIMULATE_URL, {}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "order_id_required"


def test_simulate_payment_unknown_order(buyer_client):
    response = buyer_client.post(SIMULATE_URL, {"order_id": 999999}, format="json")

    assert response.status_code == 404
    # The envelope, not {"error": …}: "no such order" and "not yours" answer
    # identically, so the endpoint cannot be used to probe which ids exist.
    assert response.data["code"] == "order_not_found"
    assert response.data["request_id"] == response["X-Request-ID"]


def test_simulate_payment_rejects_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory())

    response = buyer_client.post(SIMULATE_URL, {"order_id": foreign.id}, format="json")

    assert response.status_code == 404
    assert response.data["code"] == "order_not_found"


def test_simulate_payment_rejects_cancelled_order(buyer_client, buyer):
    order = OrderFactory(user=buyer, order_status="CANCELLED")

    response = buyer_client.post(SIMULATE_URL, {"order_id": order.id}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "order_cancelled"


def test_second_payment_for_same_order_is_rejected(buyer_client, buyer):
    """No double charge: an already-paid order cannot be simulated again."""
    order = paid_order(buyer)

    response = buyer_client.post(SIMULATE_URL, {"order_id": order.id}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "already_paid"
    assert Transaction.objects.filter(order=order).count() == 1


def test_payment_idempotency_key_replays_the_first_result(buyer_client, buyer):
    """A client retrying with the same key gets its original answer back."""
    order = OrderFactory(user=buyer, total_amount=Decimal("200.00"))
    payload = {"order_id": order.id, "idempotency_key": "retry-after-timeout"}

    first = buyer_client.post(SIMULATE_URL, payload, format="json")
    second = buyer_client.post(SIMULATE_URL, payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data["idempotent_replay"] is True
    assert second.data["transaction_id"] == first.data["transaction_id"]
    assert second.data["amount_paid"] == first.data["amount_paid"]

    assert Transaction.objects.filter(order=order).count() == 1
    order.refresh_from_db()
    assert order.payment_status == "SUCCESSFUL"


def test_idempotency_key_cannot_be_reused_on_another_order(buyer_client, buyer):
    """Keys are scoped to one order: another order charging under the same key
    must go through a fresh capture instead of replaying somebody else's."""
    first_order = OrderFactory(user=buyer, total_amount=Decimal("200.00"))
    payload = {"order_id": first_order.id, "idempotency_key": "shared-key"}

    assert buyer_client.post(SIMULATE_URL, payload, format="json").status_code == 200

    second_order = OrderFactory(user=buyer, total_amount=Decimal("50.00"))
    response = buyer_client.post(
        SIMULATE_URL,
        {"order_id": second_order.id, "idempotency_key": "shared-key"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["idempotent_replay"] is False
    assert Transaction.objects.filter(order=second_order).count() == 1


def test_simulate_payment_honours_the_idempotency_key_header(buyer_client, buyer):
    """The Phase 6 body field is no longer the only way to be retry-safe: the
    standard ``Idempotency-Key`` header replays the first result too."""
    order = OrderFactory(user=buyer, total_amount=Decimal("200.00"))
    payload = {"order_id": order.id}

    first = buyer_client.post(
        SIMULATE_URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="simulate-header-retry"
    )
    second = buyer_client.post(
        SIMULATE_URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="simulate-header-retry"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data["idempotent_replay"] is True
    assert second.data["transaction_id"] == first.data["transaction_id"]
    assert Transaction.objects.filter(order=order).count() == 1


def test_the_idempotency_header_wins_over_the_body_field(buyer_client, buyer):
    """When both key sources are sent the header decides — so the body field
    may change between retries without the order being charged twice."""
    order = OrderFactory(user=buyer, total_amount=Decimal("200.00"))

    first = buyer_client.post(
        SIMULATE_URL,
        {"order_id": order.id, "idempotency_key": "body-key"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="header-key",
    )
    second = buyer_client.post(
        SIMULATE_URL,
        {"order_id": order.id, "idempotency_key": "a-different-body-key"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="header-key",
    )

    assert first.status_code == 200
    # Had the body field won, this retry would find no replay (different key)
    # and be refused as already_paid instead of replaying.
    assert second.status_code == 200
    assert second.data["idempotent_replay"] is True
    assert Transaction.objects.filter(order=order).count() == 1


def test_payment_failure_does_not_leak_internal_details(buyer_client, buyer, monkeypatch):
    """The real cause (a driver error with a password in it) is logged
    server-side by the service; the client only gets the generic
    ``payment_failed`` envelope, never the exception text."""

    def explode(**kwargs):
        raise RuntimeError('psycopg2.OperationalError: password "12345" failed')

    monkeypatch.setattr(Transaction, "objects", type("O", (), {"create": staticmethod(explode)}))
    order = OrderFactory(user=buyer)

    response = buyer_client.post(SIMULATE_URL, {"order_id": order.id}, format="json")

    body = response.content.decode()
    assert response.status_code == 400
    assert response.data["code"] == "payment_failed"
    assert "12345" not in body
    assert "psycopg2" not in body


def test_unexpected_payment_error_does_not_leak_stack_trace(buyer_client, buyer, monkeypatch):
    def boom(order, **kwargs):
        raise RuntimeError("secret internal state")

    monkeypatch.setattr("apps.payments.views.process_simulated_payment", boom)
    order = OrderFactory(user=buyer)

    response = buyer_client.post(SIMULATE_URL, {"order_id": order.id}, format="json")

    body = response.content.decode()
    assert response.status_code == 500
    assert response.data["code"] == "server_error"
    assert "secret internal state" not in body
    assert "Traceback" not in body


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
def test_refund_succeeds_and_marks_commission_failed(buyer_client, buyer):
    order = paid_order(buyer)

    response = buyer_client.post(refund_url(order.id), format="json")

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.order_status == "CANCELLED"
    assert order.payment_status == "FAILED"

    ledger = PlatformCommissionLedger.objects.get(transaction__order=order)
    assert ledger.payout_status == "FAILED"
    assert Transaction.objects.filter(order=order).count() == 2


def test_refund_rejected_when_never_paid(buyer_client, buyer):
    order = OrderFactory(user=buyer, payment_status="PENDING")

    response = buyer_client.post(refund_url(order.id), format="json")

    assert response.status_code == 400
    assert response.data["code"] == "not_paid"
    # The envelope always carries the key; it is null when there is nothing
    # structured to add (the old body simply omitted it).
    assert response.data["details"] is None


def test_refund_rejected_for_delivered_order(buyer_client, buyer):
    order = paid_order(buyer)
    order.order_status = "DELIVERED"
    order.save()

    response = buyer_client.post(refund_url(order.id), format="json")

    assert response.status_code == 400
    assert response.data["code"] == "already_delivered"


def test_refund_unknown_order(buyer_client):
    response = buyer_client.post(refund_url(999999), format="json")

    assert response.status_code == 404
    assert response.data["code"] == "order_not_found"


def test_refund_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory(), payment_status="SUCCESSFUL")

    assert buyer_client.post(refund_url(foreign.id), format="json").status_code == 404


def test_refund_replayed_with_the_same_idempotency_key_pays_out_once(buyer_client, buyer):
    """A retried refund (flaky connection, response lost in transit) must not
    pay the buyer twice: the first 200 is replayed byte for byte."""
    order = paid_order(buyer)

    first = buyer_client.post(
        refund_url(order.id), format="json", HTTP_IDEMPOTENCY_KEY="refund-header-retry"
    )
    second = buyer_client.post(
        refund_url(order.id), format="json", HTTP_IDEMPOTENCY_KEY="refund-header-retry"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data == first.data
    assert second["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first
    # One refund transaction, not two.
    assert Transaction.objects.filter(order=order).count() == 2


def test_refund_key_reused_with_a_different_payload_is_a_conflict(buyer_client, buyer):
    """A reused key with different data is a client bug; replaying the old
    answer would hide the data loss, so it is a 409 instead."""
    order = paid_order(buyer)

    assert (
        buyer_client.post(
            refund_url(order.id), format="json", HTTP_IDEMPOTENCY_KEY="refund-header-conflict"
        ).status_code
        == 200
    )
    response = buyer_client.post(
        refund_url(order.id),
        {"reason": "damaged"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="refund-header-conflict",
    )

    assert response.status_code == 409
    assert response.data["code"] == "idempotency_key_conflict"
    # The conflict is refused before any money moves.
    assert Transaction.objects.filter(order=order).count() == 2


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def test_payment_status_endpoint(buyer_client, buyer):
    order = paid_order(buyer)

    response = buyer_client.get(status_url(order.id))

    assert response.status_code == 200
    assert response.data["payment_status"] == "SUCCESSFUL"
    assert response.data["transaction_count"] == 1
    assert response.data["latest_transaction"] is not None
    assert float(response.data["total_amount"]) == 200.0


def test_payment_status_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory())

    response = buyer_client.get(status_url(foreign.id))

    assert response.status_code == 404
    assert response.data["code"] == "order_not_found"


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------
def test_commission_list_requires_seller(buyer_client):
    assert buyer_client.get(COMMISSIONS_URL).status_code == 200
    assert buyer_client.get(COMMISSIONS_URL).data["count"] == 0


def test_commission_list_scoped_to_seller_store(seller_client, seller, store, buyer):
    """The endpoint lists PlatformCommissionLedger rows, so create ledgers,
    not bare transactions."""

    def ledger_for(order):
        txn = TransactionFactory(order=order, amount=order.total_amount)
        return PlatformCommissionLedger.objects.create(
            transaction=txn,
            order_total=order.total_amount,
            commission_rate=Decimal("0.15"),
            commission_amount=order.total_amount * Decimal("0.15"),
            net_payout_to_seller=order.total_amount * Decimal("0.85"),
            payout_status="PENDING",
        )

    ledger_for(OrderFactory(user=buyer, store=store, payment_status="SUCCESSFUL"))
    ledger_for(OrderFactory(user=buyer, payment_status="SUCCESSFUL"))

    response = seller_client.get(COMMISSIONS_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1
