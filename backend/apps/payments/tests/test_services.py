"""Payment domain services: simulated capture, commission math, refunds."""
from decimal import Decimal

import pytest

from apps.payments import services as payment_services
from apps.payments.models import PlatformCommissionLedger, Transaction
from tests.factories import OrderFactory, TransactionFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_simulated_payment_creates_transaction_and_commission(buyer):
    order = OrderFactory(user=buyer, total_amount=Decimal('200.00'))

    result = payment_services.process_simulated_payment(order)

    assert result['success'] is True
    assert result['commission'] == pytest.approx(30.0)
    assert result['net_payout'] == pytest.approx(170.0)

    txn = Transaction.objects.get(order=order)
    assert txn.transaction_id.startswith('SIM-')
    assert txn.payment_status == 'SUCCESSFUL'

    ledger = PlatformCommissionLedger.objects.get(transaction=txn)
    assert ledger.commission_rate == Decimal('0.15')
    assert ledger.commission_amount == Decimal('30.00')
    assert ledger.net_payout_to_seller == Decimal('170.00')
    assert ledger.payout_status == 'PENDING'


def test_simulated_payment_failure_is_reported_not_raised(buyer, monkeypatch):
    def explode(**kwargs):
        raise RuntimeError('gateway down')

    monkeypatch.setattr(Transaction, 'objects', type('O', (), {'create': staticmethod(explode)}))
    order = OrderFactory(user=buyer)

    result = payment_services.process_simulated_payment(order)

    assert result['success'] is False
    assert 'error' in result


def test_refund_without_successful_transaction(buyer):
    order = OrderFactory(user=buyer, payment_status='PENDING')

    result = payment_services.process_refund(order)

    assert result['success'] is False
    assert 'No successful transaction' in result['error']


def test_refund_creates_negative_transaction(buyer):
    order = OrderFactory(user=buyer, total_amount=Decimal('200.00'), payment_status='SUCCESSFUL')
    original = TransactionFactory(order=order, amount=Decimal('200.00'))
    PlatformCommissionLedger.objects.create(
        transaction=original,
        order_total=Decimal('200.00'),
        commission_rate=Decimal('0.15'),
        commission_amount=Decimal('30.00'),
        net_payout_to_seller=Decimal('170.00'),
        payout_status='PENDING',
    )

    result = payment_services.process_refund(order)

    assert result['success'] is True
    assert result['refund_amount'] == pytest.approx(200.0)

    refund = Transaction.objects.get(transaction_id=result['transaction_id'])
    assert refund.amount == Decimal('-200.00')
    # Creating the ledger with transaction=original populated Django's reverse
    # one-to-one cache on `original`, so re-fetch before asserting: the service
    # updated a separately loaded instance.
    original.commission.refresh_from_db()
    assert original.commission.payout_status == 'FAILED'
