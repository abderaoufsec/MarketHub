"""Domain errors for the orders/checkout flow (docs/todo.md Phase 6).

Checkout used to signal failure with ``return Response(...)`` *inside*
``transaction.atomic()``, which committed half-finished orders. The replacement
contract is: **raise** one of these from the domain layer; the atomic block is
exited by the exception (rolling everything back) and the view — which sits
outside the block — turns the error into an HTTP response.
"""


class OrderDomainError(Exception):
    """An expected checkout failure that is safe to show to the client."""

    code = "order_error"
    status_code = 400

    def __init__(self, message, *, code=None, details=None, status_code=None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def as_response_body(self):
        """The JSON body the view should send back."""
        body = {"error": self.message, "code": self.code}
        if self.details is not None:
            body["details"] = self.details
        return body


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
