import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.orders.models import Order

from .models import PlatformCommissionLedger, Transaction
from .serializers import PlatformCommissionLedgerSerializer, TransactionSerializer
from .services import process_refund, process_simulated_payment

logger = logging.getLogger(__name__)


class TransactionListView(generics.ListAPIView):
    """List transactions for user's orders"""

    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Transaction.objects.filter(order__user=self.request.user)
            .select_related("order")
            .order_by("-transaction_timestamp")
        )


class SellerCommissionListView(generics.ListAPIView):
    """List commission records for seller"""

    serializer_class = PlatformCommissionLedgerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return PlatformCommissionLedger.objects.none()

        return (
            PlatformCommissionLedger.objects.filter(
                transaction__order__store=self.request.user.store
            )
            .select_related("transaction", "transaction__order")
            .order_by("-created_at")
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def simulate_payment(request):
    """
    Simulate payment processing for an order

    The order row is locked before ``payment_status`` is read, and the capture
    itself re-checks it under that lock, so two concurrent attempts cannot both
    charge the same order. An ``idempotency_key`` replays the original result
    instead of charging again.

    Expected payload:
    {
        "order_id": 123,
        "payment_method": "credit_card",  # optional, for demonstration
        "idempotency_key": "…"            # optional, makes retries safe
    }
    """
    order_id = request.data.get("order_id")
    payment_method = request.data.get("payment_method", "credit_card")
    idempotency_key = request.data.get("idempotency_key") or None

    if not order_id:
        return Response({"error": "order_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            # Get the order, locked for the rest of this transaction.
            order = Order.objects.select_for_update().get(id=order_id, user=request.user)

            # Every decision (already paid? cancelled? replay?) is made by the
            # service, which re-reads the order under the same lock: one
            # authoritative path instead of a pre-check that can go stale.
            result = process_simulated_payment(order, idempotency_key=idempotency_key)

            if result["success"]:
                payload = {
                    "message": "Payment processed successfully",
                    "transaction_id": result["transaction_id"],
                    "amount_paid": result["amount"],
                    "commission": result["commission"],
                    "net_to_seller": result["net_payout"],
                    "payment_method": payment_method,
                    "idempotent_replay": result.get("replay", False),
                    "order": {
                        "id": order.id,
                        "status": order.order_status,
                        "payment_status": order.payment_status,
                    },
                }
                code = status.HTTP_200_OK
            elif result.get("reason") == "already_paid":
                payload = {"error": "Order has already been paid", "code": "already_paid"}
                code = status.HTTP_400_BAD_REQUEST
            elif result.get("reason") == "order_cancelled":
                payload = {
                    "error": "Cannot process payment for cancelled order",
                    "code": "order_cancelled",
                }
                code = status.HTTP_400_BAD_REQUEST
            else:
                # The service logs the real cause; never echo it back.
                logger.error(
                    "Simulated payment failed for order %s: %s", order_id, result.get("error")
                )
                payload = {
                    "error": "Payment processing failed. Please try again.",
                    "code": "payment_failed",
                }
                code = status.HTTP_400_BAD_REQUEST

        return Response(payload, status=code)

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        # Never expose internal error details to the client; log them instead.
        logger.exception("Unexpected error while handling payment request for order %s", order_id)
        return Response(
            {"error": "An unexpected error occurred while processing the payment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_payment_refund(request, order_id):
    """
    Process refund for an order
    Only order owner can request refund
    """
    try:
        with transaction.atomic():
            # Lock before reading payment_status so a refund cannot race a
            # payment or a second refund for the same order.
            order = Order.objects.select_for_update().get(id=order_id, user=request.user)

            # Check if order can be refunded
            if order.payment_status != "SUCCESSFUL":
                payload = {
                    "error": "Order payment was not successful, cannot refund",
                    "code": "not_paid",
                }
                code = status.HTTP_400_BAD_REQUEST
            elif order.order_status == "DELIVERED":
                payload = {
                    "error": "Cannot refund delivered orders. Please contact support.",
                    "code": "already_delivered",
                }
                code = status.HTTP_400_BAD_REQUEST
            else:
                # Process refund
                result = process_refund(order)

                if result["success"]:
                    # Update order status inside the same transaction as the
                    # refund rows, so they can never disagree.
                    order.payment_status = "FAILED"  # Mark payment as failed after refund
                    order.order_status = "CANCELLED"
                    order.save(update_fields=["payment_status", "order_status"])

                    payload = {
                        "message": "Refund processed successfully",
                        "transaction_id": result["transaction_id"],
                        "refund_amount": result["refund_amount"],
                        "order": {
                            "id": order.id,
                            "status": order.order_status,
                            "payment_status": order.payment_status,
                        },
                    }
                    code = status.HTTP_200_OK
                else:
                    logger.error("Refund failed for order %s: %s", order_id, result.get("error"))
                    payload = {
                        "error": "Refund processing failed. Please contact support.",
                        "code": "refund_failed",
                    }
                    code = status.HTTP_400_BAD_REQUEST

        return Response(payload, status=code)

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        # Never expose internal error details to the client; log them instead.
        logger.exception("Unexpected error while handling payment request for order %s", order_id)
        return Response(
            {"error": "An unexpected error occurred while processing the payment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request, order_id):
    """
    Get payment status for an order
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)

        # Get transactions for this order
        transactions = Transaction.objects.filter(order=order).order_by("-transaction_timestamp")

        latest_transaction = transactions.first()

        return Response(
            {
                "order_id": order.id,
                "payment_status": order.payment_status,
                "order_status": order.order_status,
                "total_amount": float(order.total_amount),
                "latest_transaction": TransactionSerializer(latest_transaction).data
                if latest_transaction
                else None,
                "transaction_count": transactions.count(),
            },
            status=status.HTTP_200_OK,
        )

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
