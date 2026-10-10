"""Payment endpoints: simulation, refunds, status, commission ledger."""
from decimal import Decimal

import pytest

from apps.payments.models import PlatformCommissionLedger, Transaction
from tests.factories import (
    OrderFactory,
    TransactionFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

TRANSACTIONS_URL = '/api/payments/transactions/'
SIMULATE_URL = '/api/payments/simulate/'
COMMISSIONS_URL = '/api/payments/seller/commissions/'


def refund_url(order_id):
    return f'/api/payments/refund/{order_id}/'


def status_url(order_id):
    return f'/api/payments/status/{order_id}/'


def paid_order(user, amount=Decimal('200.00')):
    order = OrderFactory(
        user=user, total_amount=amount, payment_status='SUCCESSFUL',
        order_status='PROCESSING',
    )
    txn = TransactionFactory(order=order, amount=amount)
    PlatformCommissionLedger.objects.create(
        transaction=txn,
        order_total=amount,
        commission_rate=Decimal('0.15'),
        commission_amount=Decimal('30.00'),
        net_payout_to_seller=Decimal('170.00'),
        payout_status='PENDING',
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
    assert response.data['count'] == 1


# ---------------------------------------------------------------------------
# Simulated payment
# ---------------------------------------------------------------------------
def test_simulate_payment_succeeds(buyer_client, buyer):
    order = OrderFactory(user=buyer, total_amount=Decimal('200.00'))

    response = buyer_client.post(
        SIMULATE_URL, {'order_id': order.id, 'payment_method': 'cib'}, format='json'
    )

    assert response.status_code == 200
    assert response.data['commission'] == 30.0
    assert response.data['net_to_seller'] == 170.0

    order.refresh_from_db()
    assert order.payment_status == 'SUCCESSFUL'
    assert order.order_status == 'PROCESSING'

    txn = Transaction.objects.get(order=order)
    assert txn.gateway_used == 'SIMULATED'
    assert txn.commission.commission_amount == Decimal('30.00')


def test_simulate_payment_requires_order_id(buyer_client):
    response = buyer_client.post(SIMULATE_URL, {}, format='json')

    assert response.status_code == 400


def test_simulate_payment_unknown_order(buyer_client):
    response = buyer_client.post(SIMULATE_URL, {'order_id': 999999}, format='json')

    assert response.status_code == 404


def test_simulate_payment_rejects_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory())

    response = buyer_client.post(SIMULATE_URL, {'order_id': foreign.id}, format='json')

    assert response.status_code == 404


def test_simulate_payment_rejects_cancelled_order(buyer_client, buyer):
    order = OrderFactory(user=buyer, order_status='CANCELLED')

    response = buyer_client.post(SIMULATE_URL, {'order_id': order.id}, format='json')

    assert response.status_code == 400


def test_second_payment_for_same_order_is_rejected(buyer_client, buyer):
    """No double charge: an already-paid order cannot be simulated again."""
    order = paid_order(buyer)

    response = buyer_client.post(SIMULATE_URL, {'order_id': order.id}, format='json')

    assert response.status_code == 400
    assert Transaction.objects.filter(order=order).count() == 1


def test_payment_failure_does_not_leak_internal_details(buyer_client, buyer, monkeypatch):
    monkeypatch.setattr(
        'apps.payments.views.process_simulated_payment',
        lambda order: {
            'success': False,
            'error': 'psycopg2.OperationalError: password "12345" failed',
        },
    )
    order = OrderFactory(user=buyer)

    response = buyer_client.post(SIMULATE_URL, {'order_id': order.id}, format='json')

    body = response.content.decode()
    assert response.status_code == 400
    assert '12345' not in body
    assert 'psycopg2' not in body


def test_unexpected_payment_error_does_not_leak_stack_trace(
    buyer_client, buyer, monkeypatch
):
    def boom(order):
        raise RuntimeError('secret internal state')

    monkeypatch.setattr('apps.payments.views.process_simulated_payment', boom)
    order = OrderFactory(user=buyer)

    response = buyer_client.post(SIMULATE_URL, {'order_id': order.id}, format='json')

    body = response.content.decode()
    assert response.status_code == 500
    assert 'secret internal state' not in body
    assert 'Traceback' not in body


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
def test_refund_succeeds_and_marks_commission_failed(buyer_client, buyer):
    order = paid_order(buyer)

    response = buyer_client.post(refund_url(order.id), format='json')

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.order_status == 'CANCELLED'
    assert order.payment_status == 'FAILED'

    ledger = PlatformCommissionLedger.objects.get(transaction__order=order)
    assert ledger.payout_status == 'FAILED'
    assert Transaction.objects.filter(order=order).count() == 2


def test_refund_rejected_when_never_paid(buyer_client, buyer):
    order = OrderFactory(user=buyer, payment_status='PENDING')

    response = buyer_client.post(refund_url(order.id), format='json')

    assert response.status_code == 400
    assert 'details' not in response.data


def test_refund_rejected_for_delivered_order(buyer_client, buyer):
    order = paid_order(buyer)
    order.order_status = 'DELIVERED'
    order.save()

    response = buyer_client.post(refund_url(order.id), format='json')

    assert response.status_code == 400


def test_refund_unknown_order(buyer_client):
    assert buyer_client.post(refund_url(999999), format='json').status_code == 404


def test_refund_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory(), payment_status='SUCCESSFUL')

    assert buyer_client.post(refund_url(foreign.id), format='json').status_code == 404


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def test_payment_status_endpoint(buyer_client, buyer):
    order = paid_order(buyer)

    response = buyer_client.get(status_url(order.id))

    assert response.status_code == 200
    assert response.data['payment_status'] == 'SUCCESSFUL'
    assert response.data['transaction_count'] == 1
    assert response.data['latest_transaction'] is not None
    assert float(response.data['total_amount']) == 200.0


def test_payment_status_foreign_order(buyer_client):
    foreign = OrderFactory(user=UserFactory())

    assert buyer_client.get(status_url(foreign.id)).status_code == 404


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------
def test_commission_list_requires_seller(buyer_client):
    assert buyer_client.get(COMMISSIONS_URL).status_code == 200
    assert buyer_client.get(COMMISSIONS_URL).data['count'] == 0


def test_commission_list_scoped_to_seller_store(seller_client, seller, store, buyer):
    """The endpoint lists PlatformCommissionLedger rows, so create ledgers,
    not bare transactions."""
    def ledger_for(order):
        txn = TransactionFactory(order=order, amount=order.total_amount)
        return PlatformCommissionLedger.objects.create(
            transaction=txn,
            order_total=order.total_amount,
            commission_rate=Decimal('0.15'),
            commission_amount=order.total_amount * Decimal('0.15'),
            net_payout_to_seller=order.total_amount * Decimal('0.85'),
            payout_status='PENDING',
        )

    ledger_for(OrderFactory(user=buyer, store=store, payment_status='SUCCESSFUL'))
    ledger_for(OrderFactory(user=buyer, payment_status='SUCCESSFUL'))

    response = seller_client.get(COMMISSIONS_URL)

    assert response.status_code == 200
    assert response.data['count'] == 1
