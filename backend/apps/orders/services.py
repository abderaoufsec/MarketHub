"""Checkout domain logic (docs/todo.md Phase 6).

Everything that creates an order lives here so the views stay thin and the
transactional rules are unit-testable:

* every write happens inside **one** ``transaction.atomic()`` block;
* expected failures are raised as :mod:`apps.orders.exceptions` errors and
  propagate *out* of that block, which rolls the whole checkout back — a
  ``return`` inside the block (the pre-Phase 6 defect) can no longer commit a
  FAILED order with reserved stock;
* stock is reserved with row locks held, and the payment is captured by the
  single authoritative path in :mod:`apps.payments.services`.
"""

from collections import defaultdict

from django.db import IntegrityError, transaction

from apps.inventory.services import check_stock_availability, reserve_inventory_for_order
from apps.payments.services import process_simulated_payment
from apps.users.models import Address

from .exceptions import (
    EmptyCartError,
    InsufficientStockError,
    PaymentFailedError,
    PriceChangedError,
    ProductUnavailableError,
    ShippingAddressNotFoundError,
)
from .models import CartItem, Order, OrderItem


def stock_error_for(product, selected_attributes, quantity):
    """Return a user-facing message when ``quantity`` units are unavailable.

    Returns ``None`` when the quantity can be sold. A product without an
    ``Inventory`` row is not sellable anywhere else in the codebase (see
    ``reserve_inventory_for_order``), so it is not sellable here either.
    """
    is_available, inventory = check_stock_availability(product, selected_attributes, quantity)
    if is_available:
        return None

    available = inventory.stock_quantity if inventory else 0
    return f"Insufficient stock for {product.name}. Available: {available}, Required: {quantity}"


def price_changes_for(cart_items):
    """List the cart lines whose stored price differs from the live price."""
    return [
        {
            "product_id": item.product_id,
            "product_name": item.product.name,
            "old_price": item.price_at_time_of_addition,
            "new_price": item.product.base_price,
        }
        for item in cart_items
        if item.price_at_time_of_addition != item.product.base_price
    ]


def refresh_cart_prices(user):
    """Re-price the buyer's cart to the current catalogue prices.

    Used by the "price changed" recovery flow: checkout refuses to charge a
    stale price, and this is the explicit way for the buyer to accept the new
    prices before trying again. Returns the changes it applied, in the same
    shape ``price_changes_for()`` reports them.
    """
    cart_items = list(
        CartItem.objects.filter(cart__user=user).select_related("product").order_by("id")
    )
    changes = price_changes_for(cart_items)
    changed_products = {change["product_id"] for change in changes}

    for item in cart_items:
        if item.product_id not in changed_products:
            continue
        item.price_at_time_of_addition = item.product.base_price
        item.save(update_fields=["price_at_time_of_addition", "updated_at"])

    return changes


def _validate_cart(cart_items):
    """Fail fast before anything is written: availability and current price."""
    unavailable = [
        {"product_id": item.product_id, "product_name": item.product.name}
        for item in cart_items
        if not item.product.is_available
    ]
    if unavailable:
        raise ProductUnavailableError(
            "Some products in your cart are no longer available.",
            details=unavailable,
        )

    changes = price_changes_for(cart_items)
    if changes:
        raise PriceChangedError(
            "The price of one or more items in your cart has changed.",
            details=changes,
        )


def _replayed_checkout(user, idempotency_key):
    """Orders already created for this key, or ``None``."""
    existing = list(
        Order.objects.filter(user=user, idempotency_key=idempotency_key).order_by("store_id", "id")
    )
    return existing or None


def place_order(*, user, shipping_address_id, shipping_method="standard", idempotency_key=None):
    """Turn the buyer's cart into per-store orders and charge them once.

    Returns ``(orders, is_replay)``.

    Raises an :class:`~apps.orders.exceptions.OrderDomainError` subclass for
    every expected failure; by then the transaction has been rolled back, so no
    order, stock reservation or payment can survive a failure.
    """
    shipping_address = Address.objects.filter(id=shipping_address_id, user=user).first()
    if shipping_address is None:
        raise ShippingAddressNotFoundError("Shipping address not found")

    # A retry of an already-completed checkout replays before anything else:
    # its cart has been emptied by the first attempt, and re-validating it
    # would answer "empty cart" instead of the orders the client asked for.
    if idempotency_key:
        replay = _replayed_checkout(user, idempotency_key)
        if replay is not None:
            return replay, True

    cart_items = list(
        CartItem.objects.filter(cart__user=user)
        .select_related("product", "product__store")
        .order_by("product__store_id", "product_id", "id")
    )
    if not cart_items:
        raise EmptyCartError("Cart is empty")

    _validate_cart(cart_items)

    items_by_store = defaultdict(list)
    for item in cart_items:
        items_by_store[item.product.store_id].append(item)

    try:
        with transaction.atomic():
            orders = []
            # Ascending store id (and, inside the reservation, ascending
            # product id) gives every concurrent checkout the same lock order,
            # so overlapping carts cannot deadlock on inventory rows.
            for store_id in sorted(items_by_store):
                items = items_by_store[store_id]
                store = items[0].product.store

                order = Order.objects.create(
                    user=user,
                    store=store,
                    # The price was re-validated above; charge the live price.
                    total_amount=sum(item.product.base_price * item.quantity for item in items),
                    shipping_address=shipping_address,
                    shipping_method=shipping_method or "standard",
                    order_status="PENDING",
                    payment_status="PENDING",
                    idempotency_key=idempotency_key,
                )

                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        unit_price_at_purchase=item.product.base_price,
                        selected_attributes=item.selected_attributes,
                    )

                try:
                    reserve_inventory_for_order(
                        [
                            {
                                "product": item.product,
                                "quantity": item.quantity,
                                "selected_attributes": item.selected_attributes,
                            }
                            for item in items
                        ]
                    )
                except ValueError as exc:
                    raise InsufficientStockError(str(exc)) from exc

                result = process_simulated_payment(order)
                if not result["success"]:
                    raise PaymentFailedError(
                        "Payment could not be processed. Nothing was charged "
                        "and no stock was taken."
                    )

                orders.append(order)

            # Only reached when every store's stock and payment succeeded.
            CartItem.objects.filter(cart__user=user).delete()
    except IntegrityError:
        # A concurrent request retried the same idempotency key: the unique
        # constraint on (idempotency_key, store) rejected our insert and the
        # atomic block above rolled back our work. Hand back their orders.
        if idempotency_key:
            replay = _replayed_checkout(user, idempotency_key)
            if replay is not None:
                return replay, True
        raise

    return orders, False
