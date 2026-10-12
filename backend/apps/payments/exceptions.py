"""Domain errors for the payments flow (docs/todo.md Phase 9).

``services.py`` used to *return* its failures — a ``{"success": False,
"error": …}`` dict that the view translated by hand into a ``{"error": …}``
body, in about fourteen branches that all had to stay in sync with what the
service actually logged. ``core.exceptions`` owns that contract now, so the
payment path does what checkout already does (``apps/orders/exceptions.py``):
**raise**, and let the error travel untouched to
``api_exception_handler``, which renders::

    {"code": …, "message": …, "details": …, "request_id": …}

Raising is not only tidier, it is safer: these failures happen *inside*
``transaction.atomic()``, and an exception — unlike a returned dict — rolls
the block back on its way out, so a refused capture can never leave a
half-written ``Transaction`` behind.

One class per distinct failure, so every branch a client can take has its own
``code``. ``details`` is the slot for structured extras (a price diff, the
offending lines): none of the payments paths carried any, so it stays
``None`` — the key is always present in the envelope either way.
"""

from __future__ import annotations

from core.exceptions import ApiError


class PaymentError(ApiError):
    """An expected payment failure that is safe to show to the client."""

    code = "payment_error"
    status_code = 400


class OrderNotFoundError(PaymentError):
    """The order does not exist, or it belongs to somebody else.

    Both cases answer 404 on purpose: telling a stranger "this order exists
    but is not yours" would turn the endpoint into an order-id oracle.
    """

    code = "order_not_found"
    status_code = 404


class OrderAlreadyPaidError(PaymentError):
    """A capture was requested for an order that is already paid.

    Also what a losing concurrent attempt sees: the row lock serialises the
    two captures and the loser re-reads ``SUCCESSFUL`` under it, so this is
    the double-charge guard speaking, not a race that got away.
    """

    code = "already_paid"


class OrderNotPayableError(PaymentError):
    """The order is in a state a capture cannot start from (cancelled)."""

    code = "order_cancelled"


class PaymentCaptureFailedError(PaymentError):
    """The capture itself blew up; the real cause is only in the server log.

    The message is deliberately generic — the previous hand-built body hid
    driver errors from clients for exactly this reason.
    """

    code = "payment_failed"


class RefundNotPaidError(PaymentError):
    """A refund was asked for on an order that was never successfully paid.

    An *already refunded* order lands here too: the refund marks the payment
    ``FAILED``, which is no longer payable.
    """

    code = "not_paid"


class RefundAlreadyDeliveredError(PaymentError):
    """Delivered orders are settled; the buyer has to talk to support."""

    code = "already_delivered"


class RefundNoTransactionError(PaymentError):
    """Paid, but there is no successful ``Transaction`` row to refund against.

    The service refuses to invent a refund for money it cannot trace.
    """

    code = "no_successful_transaction"


class RefundFailedError(PaymentError):
    """The refund itself blew up; the real cause is only in the server log."""

    code = "refund_failed"
