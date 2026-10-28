"""Domain errors for the orders/checkout flow (docs/todo.md Phase 6, Phase 9).

Checkout used to signal failure with ``return Response(...)`` *inside*
``transaction.atomic()``, which committed half-finished orders. The replacement
contract is: **raise** one of these from the domain layer; the atomic block is
exited by the exception (rolling everything back) and the error propagates out
of the view.

Phase 9: these subclass :class:`core.exceptions.ApiError`, so the view builds
no body of its own — the Phase 9 exception handler
(``core.exceptions.api_exception_handler``) renders the standard
``{code, message, details, request_id}`` envelope straight from the
exception's own ``.code``/``.message``/``.details``/``.status_code``. The
class-level codes below (``empty_cart``, ``price_changed``, …) are a contract
clients already branch on, so they stay exactly as they are; only the body
*shape* moved into one place.
"""

from __future__ import annotations

from core.exceptions import ApiError


class OrderDomainError(ApiError):
    """An expected checkout failure that is safe to show to the client."""

    code = "order_error"
    status_code = 400

    def __init__(self, message, *, code=None, details=None, status_code=None):
        # ``ApiError`` calls its first argument ``detail``; every raise site in
        # the services passes ``message`` positionally, so translate the name
        # once here instead of at a dozen call sites.
        super().__init__(detail=message, code=code, details=details, status_code=status_code)
        # ``.message`` has always been part of this family's surface (DRF only
        # keeps ``.detail``, which holds the same string as an ErrorDetail).
        self.message = message

    def __str__(self) -> str:
        # DRF's ``APIException.__init__`` never fills ``Exception.args``, so
        # the inherited ``__str__`` would print ``()`` in a traceback or log
        # line; the plain message is what those lines should show.
        return str(self.message)


class EmptyCartError(OrderDomainError):
    """The buyer has nothing (left) to pay for."""

    code = "empty_cart"


class ShippingAddressNotFoundError(OrderDomainError):
    """The shipping address does not exist or belongs to somebody else."""

    code = "address_not_found"


class ProductUnavailableError(OrderDomainError):
    """A cart line points at a product that was deleted or unpublished."""

    code = "product_unavailable"


class PriceChangedError(OrderDomainError):
    """A cart line is priced below the current price; ``details`` lists them."""

    code = "price_changed"


class InsufficientStockError(OrderDomainError):
    """Stock could not be reserved for one or more lines."""

    code = "insufficient_stock"


class PaymentFailedError(OrderDomainError):
    """The gateway declined the charge; nothing was committed."""

    code = "payment_failed"


class IdempotencyKeyConflictError(OrderDomainError):
    """Same ``Idempotency-Key``, different checkout payload (Phase 13).

    Shares its code with ``core.idempotency``'s POST-replay conflict — same
    meaning to the client ("this key is taken by a different request"), here
    caught in the domain layer where the address and shipping method of the
    original checkout are still comparable. 409, because the original
    *succeeded* and the retry is the one that must give up.
    """

    code = "idempotency_key_conflict"
    status_code = 409
