"""Payment endpoints: capture, refund, status, commission ledger.

Phase 9 of docs/todo.md: these views used to translate the service's
``{"success": False, "error": …}`` dicts into hand-built ``{"error": …}``
bodies — about fourteen branches that had to stay in sync with what the
service logged. The service raises now (``apps/payments/exceptions.py``), so a
failure travels untouched to ``core.exceptions.api_exception_handler`` and the
views are left with one job: build the *success* bodies, exactly as before.
"""

from django.db import transaction
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from core.exceptions import ApiError, InternalServerError
from core.idempotency import IdempotentPostMixin, idempotency_key

from .exceptions import (
    OrderNotFoundError,
    RefundAlreadyDeliveredError,
    RefundNotPaidError,
)
from .models import PlatformCommissionLedger, Transaction
from .serializers import PlatformCommissionLedgerSerializer, TransactionSerializer
from .services import process_refund, process_simulated_payment


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


# Note on decorator order (drf-spectacular): ``@extend_schema`` must sit
# *above* ``@api_view``. Applied below it, it annotates the bare function and
# is silently dropped — ``api_view`` copies ``schema``/``permission_classes``
# off the function but not the ``kwargs`` the annotation lives in, so
# ``manage.py spectacular`` would keep logging "unable to guess serializer"
# for the route. ``@permission_classes`` stays innermost: that attribute *is*
# copied by ``api_view``.
@extend_schema(
    # Both sides are hand-built: the request is the bare {"order_id",
    # "payment_method", "idempotency_key"} dict in the docstring, and the 2xx
    # body is assembled from the service result plus the order. No serializer
    # models them, so they are documented as free-form objects rather than
    # with a schema that would silently drift away from the view.
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def simulate_payment(request):
    """
    Simulate payment processing for an order

    The order row is locked before ``payment_status`` is read, and the capture
    itself re-checks it under that lock, so two concurrent attempts cannot both
    charge the same order. An ``idempotency_key`` — the body field, or the
    standard ``Idempotency-Key`` header, which wins when both are sent —
    replays the original result instead of charging again.

    Expected payload:
    {
        "order_id": 123,
        "payment_method": "credit_card",  # optional, for demonstration
        "idempotency_key": "…"            # optional, makes retries safe
    }

    Failures raise (apps/payments/exceptions.py) and come back as the standard
    ``{code, message, details, request_id}`` envelope.
    """
    order_id = request.data.get("order_id")
    payment_method = request.data.get("payment_method", "credit_card")
    # The standard header wins; the Phase 6 body field keeps working for
    # clients that only ever sent that (core/idempotency.py).
    key = idempotency_key(request, body_value=request.data.get("idempotency_key"))

    if not order_id:
        # Raised, not hand-built: the envelope carries the branchable code.
        raise ApiError("order_id is required", code="order_id_required")

    try:
        with transaction.atomic():
            try:
                # Get the order, locked for the rest of this transaction.
                order = Order.objects.select_for_update().get(id=order_id, user=request.user)
            except Order.DoesNotExist:
                # ``from None``: "no such order" and "not yours" must be
                # indistinguishable, or the endpoint becomes an order-id oracle.
                raise OrderNotFoundError("Order not found") from None

            # Every decision (already paid? cancelled? replay?) is made by the
            # service, which re-reads the order under the same lock: one
            # authoritative path instead of a pre-check that can go stale.
            # Refusals raise out of here; only a real result returns.
            result = process_simulated_payment(order, idempotency_key=key)
    except ApiError:
        # Expected failures (already_paid, order_cancelled, payment_failed, …)
        # already carry their own code and status: pass them through untouched.
        raise
    except Exception as exc:
        # Never expose internal error details to the client. InternalServerError
        # logs the traceback with the request id and renders the generic 500.
        raise InternalServerError(
            "An unexpected error occurred while processing the payment.", cause=exc
        ) from exc

    # Success body — unchanged since Phase 6.
    return Response(
        {
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
        },
        status=status.HTTP_200_OK,
    )


class RefundActionView(APIView):
    """The refund action itself, split into its own class so that
    :class:`IdempotentPostMixin` can sit *in front of* ``post`` in the MRO
    (see :class:`ProcessRefundView`)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        """Process refund for an order; only the order's owner can request it."""
        try:
            with transaction.atomic():
                try:
                    # Lock before reading payment_status so a refund cannot
                    # race a payment or a second refund for the same order.
                    order = Order.objects.select_for_update().get(id=order_id, user=request.user)
                except Order.DoesNotExist:
                    raise OrderNotFoundError("Order not found") from None

                # Check if order can be refunded
                if order.payment_status != "SUCCESSFUL":
                    raise RefundNotPaidError("Order payment was not successful, cannot refund")

                if order.order_status == "DELIVERED":
                    raise RefundAlreadyDeliveredError(
                        "Cannot refund delivered orders. Please contact support."
                    )

                # Raises (no_successful_transaction / refund_failed) rather
                # than reporting failure with a dict.
                result = process_refund(order)

                # Update order status inside the same transaction as the
                # refund rows, so they can never disagree.
                order.payment_status = "FAILED"  # Mark payment as failed after refund
                order.order_status = "CANCELLED"
                order.save(update_fields=["payment_status", "order_status"])
        except ApiError:
            raise
        except Exception as exc:
            # Never expose internal error details to the client.
            raise InternalServerError(
                "An unexpected error occurred while processing the payment.", cause=exc
            ) from exc

        # Success body — unchanged since Phase 6.
        return Response(
            {
                "message": "Refund processed successfully",
                "transaction_id": result["transaction_id"],
                "refund_amount": result["refund_amount"],
                "order": {
                    "id": order.id,
                    "status": order.order_status,
                    "payment_status": order.payment_status,
                },
            },
            status=status.HTTP_200_OK,
        )


# Class-based views annotate themselves by decorating the *routed* class (a
# method-level annotation would be shadowed by the mixin's ``post``). The
# request body is empty in practice — the order is in the path — but it is
# still documented, because every mutating operation must say so.
@extend_schema(
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT},
)
class ProcessRefundView(IdempotentPostMixin, RefundActionView):
    """Process refund for an order; only the order's owner can request it.

    Phase 9: mixed with ``IdempotentPostMixin`` so a retried refund cannot pay
    the buyer out twice. The first 200 is cached per (user,
    ``Idempotency-Key``) and replayed with ``Idempotency-Replayed: true``;
    reusing the key with a *different* payload is a 409
    ``idempotency_key_conflict``. No header, no replay: exactly the old
    behaviour.

    The mixin defines ``post``, so it must come *before* the class that holds
    the action in the MRO — otherwise the view's own ``post`` would shadow it
    and the idempotency would never run. Hence the small split with
    :class:`RefundActionView`.
    """

    #: Replay namespace: two endpoints under the same user must not collide on
    #: the same key (see ``core/idempotency.py``).
    idempotency_scope = "refund"


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request, order_id):
    """
    Get payment status for an order
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
    except Order.DoesNotExist:
        raise OrderNotFoundError("Order not found") from None

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
