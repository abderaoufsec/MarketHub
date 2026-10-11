"""Payment capture (docs/todo.md Phase 6).

``process_simulated_payment`` is the **single authoritative payment path**: the
checkout transaction calls it, and so does the standalone
``POST /api/payments/simulate/`` retry endpoint. It locks the order row,
re-reads ``payment_status`` under that lock, and only then writes the
``Transaction`` and the commission ledger — so a double click, a retried
request or two app servers can never charge one order twice.

Errors are reported, never raised, and never leak internals: the exception is
logged server-side and the caller gets a stable, generic code.
"""

import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.orders.models import Order

from .models import PlatformCommissionLedger, Transaction

logger = logging.getLogger(__name__)


def _replay_result(existing):
    """The result of a payment that already happened for this idempotency key."""
    commission = PlatformCommissionLedger.objects.filter(transaction=existing).first()
    return {
        "success": True,
        "replay": True,
        "transaction_id": existing.transaction_id,
        "amount": float(existing.amount),
        "commission": float(commission.commission_amount) if commission else 0.0,
        "net_payout": float(commission.net_payout_to_seller)
        if commission
        else float(existing.amount),
    }


def process_simulated_payment(order, idempotency_key=None):
    """
    Simulate payment processing for MVP

    Under the order row lock this decides, in order: whether the request
    replays an earlier one (same ``idempotency_key``), whether the order is
    already paid, and whether it is cancelled. Only then does it capture.

    Args:
        order: Order instance
        idempotency_key: Optional client key; re-sending it replays the first
            result instead of charging again

    Returns:
        dict: ``success`` plus the transaction details on capture, or a stable
        ``reason`` (``already_paid`` / ``order_cancelled`` / ``payment_failed``)
        with a client-safe ``error`` message
    """
    try:
        with transaction.atomic():
            # The order row lock is the single guard against a double charge:
            # a concurrent attempt waits here and then sees SUCCESSFUL.
            locked = Order.objects.select_for_update().get(pk=order.pk)

            if idempotency_key:
                existing = Transaction.objects.filter(
                    idempotency_key=idempotency_key, order_id=locked.pk
                ).first()
                if existing is not None:
                    return _replay_result(existing)

            if locked.payment_status == "SUCCESSFUL":
                return {
                    "success": False,
                    "reason": "already_paid",
                    "already_paid": True,
                    "error": "Order has already been paid.",
                }

            if locked.order_status == "CANCELLED":
                return {
                    "success": False,
                    "reason": "order_cancelled",
                    "error": "Cannot process payment for cancelled order.",
                }

            # Generate unique transaction ID
            transaction_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"

            # Create transaction record
            payment_transaction = Transaction.objects.create(
                order=locked,
                transaction_id=transaction_id,
                amount=locked.total_amount,
                gateway_used="SIMULATED",
                payment_status="SUCCESSFUL",  # Simulated always succeeds
                idempotency_key=idempotency_key,
            )

            # Calculate platform commission
            commission_rate = Decimal(str(settings.PLATFORM_COMMISSION_RATE))
            commission_amount = locked.total_amount * commission_rate
            net_payout = locked.total_amount - commission_amount

            # Create commission ledger entry
            PlatformCommissionLedger.objects.create(
                transaction=payment_transaction,
                order_total=locked.total_amount,
                commission_rate=commission_rate,
                commission_amount=commission_amount,
                net_payout_to_seller=net_payout,
                payout_status="PENDING",
            )

            # The order is paid in the same transaction that wrote the
            # Transaction row: they can never disagree.
            locked.payment_status = "SUCCESSFUL"
            locked.order_status = "PROCESSING"
            locked.save(update_fields=["payment_status", "order_status"])

            # Keep the caller's instance in sync with what was committed.
            order.payment_status = locked.payment_status
            order.order_status = locked.order_status

            return {
                "success": True,
                "replay": False,
                "transaction_id": transaction_id,
                "amount": float(locked.total_amount),
                "commission": float(commission_amount),
                "net_payout": float(net_payout),
            }

    except Exception:
        # Log the real cause; callers only ever see the generic code below.
        logger.exception("Simulated payment failed for order %s", getattr(order, "id", None))
        return {"success": False, "reason": "payment_failed", "error": "payment_failed"}


def process_refund(order):
    """
    Process refund for an order (simulated)

    Args:
        order: Order instance

    Returns:
        dict: Refund result
    """
    try:
        with transaction.atomic():
            # Lock before reading payment_status so a refund can never race a
            # payment (or a second refund) for the same order.
            locked = Order.objects.select_for_update().get(pk=order.pk)

            # Get original transaction
            original_transaction = locked.transactions.filter(payment_status="SUCCESSFUL").first()

            if not original_transaction:
                return {"success": False, "error": "No successful transaction found for this order"}

            # Create refund transaction
            refund_transaction_id = f"REF-{uuid.uuid4().hex[:12].upper()}"

            Transaction.objects.create(
                order=locked,
                transaction_id=refund_transaction_id,
                amount=-locked.total_amount,  # Negative amount for refund
                gateway_used="SIMULATED",
                payment_status="SUCCESSFUL",
            )

            # Update commission ledger
            if hasattr(original_transaction, "commission"):
                original_transaction.commission.payout_status = "FAILED"
                original_transaction.commission.save()

            return {
                "success": True,
                "transaction_id": refund_transaction_id,
                "refund_amount": float(locked.total_amount),
            }

    except Exception:
        logger.exception("Refund failed for order %s", getattr(order, "id", None))
        return {"success": False, "error": "refund_failed"}
