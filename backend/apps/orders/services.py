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

Phase 13 (docs/todo.md §0.3 #14): the cart is read **inside** that block,
under ``select_for_update()``. Validation used to run on a snapshot taken
before the transaction opened, so a concurrent add/quantity/price change
could rewrite the cart between "this is fine" and the charge — a classic
TOCTOU where the validated lines and the ordered lines were different carts.
"""

import hashlib
from collections import defaultdict

from django.db import IntegrityError, transaction

from apps.inventory.services import check_stock_availability, reserve_inventory_for_order
from apps.payments.services import process_simulated_payment
from apps.users.models import Address

from .exceptions import (
    EmptyCartError,
    IdempotencyKeyConflictError,
    InsufficientStockError,
    PaymentFailedError,
    PriceChangedError,
    ProductUnavailableError,
    ShippingAddressNotFoundError,
)
from .models import CartItem, Order, OrderItem


def purchasability_error(product) -> str | None:
    """Why this listing cannot enter (or complete) checkout, or ``None``.

    Phase 13: only a live ``STORE_PRODUCT`` with a store is buyable.
    Classifieds are contact-first and carry no inventory; a SOLD/EXPIRED/
    ARCHIVED store product stopped being buyable the moment its status moved.
    """
    from apps.products.models import ListingStatus, ListingType

    if product.listing_type != ListingType.STORE_PRODUCT or product.store_id is None:
        return "This listing is not available for checkout."
    if product.status != ListingStatus.ACTIVE or not product.is_available:
        return "This listing is no longer available."
    return None


def checkout_fingerprint(shipping_address, shipping_method) -> str:
    """Digest of what the client *asked* for in this checkout (Phase 13).

    The cart lines are server-side and cannot differ between two requests of
    one Idempotency-Key — the first success empties the cart — so the parts
    the client controls are the address and the shipping method. Reusing a
    finished key with either changed is a different order wearing an old
    order's receipt: it answers 409 ``idempotency_key_conflict`` instead of
    silently replaying yesterday's address.
    """
    raw = f"{shipping_address.pk}:{shipping_method or 'standard'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    """Fail fast before anything is written: sellability and current price."""
    unavailable = [
        {"product_id": item.product_id, "product_name": item.product.name}
        for item in cart_items
        if not item.product.is_available or purchasability_error(item.product) is not None
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


def _ensure_same_payload(replay, fingerprint):
    """The retry must be asking for what the original asked for (Phase 13).

    ``None`` on the stored side is a pre-Phase-13 order: no fingerprint to
    compare, so it replays as it always did.
    """
    stored = replay[0].idempotency_fingerprint
    if stored is not None and stored != fingerprint:
        raise IdempotencyKeyConflictError(
            "This Idempotency-Key was already used for a different checkout.",
            details={"idempotency_fingerprint": fingerprint},
        )


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

    fingerprint = checkout_fingerprint(shipping_address, shipping_method)

    # A retry of an already-completed checkout replays before anything else:
    # its cart has been emptied by the first attempt, and re-validating it
    # would answer "empty cart" instead of the orders the client asked for.
    if idempotency_key:
        replay = _replayed_checkout(user, idempotency_key)
        if replay is not None:
            _ensure_same_payload(replay, fingerprint)
            return replay, True

    try:
        with transaction.atomic():
            # Phase 13 (#14): read the cart HERE, under a row lock. The old
            # read sat outside the transaction, so a concurrent add, quantity
            # change, remove or *price change* could rewrite the cart between
            # validation and capture — the classic TOCTOU where the validated
            # lines and the ordered lines were different carts.
            #
            # ``of=("self",)`` locks the CartItem rows only. It must: since
            # Phase 13 made ``Product.store`` nullable, the
            # ``select_related("product__store")`` join is a LEFT OUTER JOIN
            # and Postgres refuses to lock across one. It is also the right
            # lock: the price charged is ``item.product.base_price`` from this
            # same loaded snapshot that ``_validate_cart`` just compared
            # against, so there is no second read for a price edit to race,
            # and the authoritative oversell guard is the inventory-row lock
            # inside ``reserve_inventory_for_order``.
            cart_items = list(
                CartItem.objects.select_for_update(of=("self",))
                .filter(cart__user=user)
                .select_related("product", "product__store")
                .order_by("product__store_id", "product_id", "id")
            )
            if not cart_items:
                raise EmptyCartError("Cart is empty")

            _validate_cart(cart_items)

            items_by_store = defaultdict(list)
            for item in cart_items:
                items_by_store[item.product.store_id].append(item)

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
                    idempotency_fingerprint=fingerprint if idempotency_key else None,
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
            # Exactly the lines we ordered, not the whole cart: an item added
            # to this cart while the checkout held the lock was never part of
            # the charge, and deleting it would lose the buyer's addition.
            CartItem.objects.filter(pk__in=[item.pk for item in cart_items]).delete()
    except IntegrityError:
        # A concurrent request retried the same idempotency key: the unique
        # constraint on (idempotency_key, store) rejected our insert and the
        # atomic block above rolled back our work. Hand back their orders.
        if idempotency_key:
            replay = _replayed_checkout(user, idempotency_key)
            if replay is not None:
                _ensure_same_payload(replay, fingerprint)
                return replay, True
        raise

    return orders, False
