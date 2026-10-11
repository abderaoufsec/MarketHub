"""Inventory mutations (docs/todo.md Phase 6).

Every stock change goes through :func:`update_inventory`, which re-reads the
row under a ``SELECT ... FOR UPDATE`` lock. Without that lock two concurrent
checkouts read the same ``stock_quantity``, both decrement from it, and one of
the updates is lost (the oversell race). Reservations additionally take the
lock *before* checking availability, so a losing racer sees the committed
quantity instead of racing ahead of the winner.
"""

import json

from django.db import transaction

from .models import Inventory, InventoryAuditLog


def _inventory_row(product, selected_attributes, *, lock=False):
    """The inventory row for a product/variant, or ``None``.

    ``lock=True`` takes a row lock, so the caller must already be inside a
    transaction (``select_for_update()`` raises outside one).
    """
    queryset = Inventory.objects.filter(product=product, attribute_config=selected_attributes or {})
    if lock:
        queryset = queryset.select_for_update()
    return queryset.first()


def _lock_key(product, selected_attributes):
    """Stable ordering key so concurrent callers lock rows in the same order."""
    return (product.id, json.dumps(selected_attributes or {}, sort_keys=True, default=str))


def update_inventory(inventory, quantity_delta, action_type, reason=""):
    """
    Update inventory and create audit log

    Args:
        inventory: Inventory instance
        quantity_delta: Change in quantity (positive or negative)
        action_type: Type of action (SALE, RETURN, etc.)
        reason: Optional reason for the change

    Returns:
        Updated inventory instance
    """
    with transaction.atomic():
        # Re-read under a row lock: the caller's instance may be stale, and the
        # read-modify-write below is only safe while nobody else can write.
        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)

        previous_quantity = locked.stock_quantity
        new_quantity = previous_quantity + quantity_delta

        # Prevent negative inventory
        if new_quantity < 0:
            raise ValueError(
                f"Insufficient stock. Available: {previous_quantity}, Required: {abs(quantity_delta)}"
            )

        # Update inventory
        locked.stock_quantity = new_quantity
        locked.save(update_fields=["stock_quantity", "updated_at"])

        # Create audit log
        InventoryAuditLog.objects.create(
            product_id=locked.product_id,
            inventory=locked,
            quantity_delta=quantity_delta,
            action_type=action_type,
            reason=reason,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
        )

        # Keep the caller's instance in sync with the database.
        inventory.stock_quantity = new_quantity

        return inventory


def check_stock_availability(product, selected_attributes, required_quantity):
    """
    Check if sufficient stock is available for a product

    Read-only (no row lock) — use it for cart-level validation. Money-moving
    paths must go through ``reserve_inventory_for_order`` instead.

    Args:
        product: Product instance
        selected_attributes: Dict of selected attributes
        required_quantity: Required quantity

    Returns:
        tuple: (is_available, inventory_instance or None)
    """
    inventory = _inventory_row(product, selected_attributes)

    if inventory is None:
        return False, None

    return inventory.stock_quantity >= required_quantity, inventory


def reserve_inventory_for_order(order_items):
    """
    Reserve inventory for order items

    Locks every inventory row before reading it, so two concurrent
    reservations for the last unit can never both succeed.

    Args:
        order_items: List of order items with product and quantity

    Returns:
        bool: True if all items reserved successfully

    Raises:
        ValueError: If insufficient stock
    """
    with transaction.atomic():
        # Lock in a stable (product id, attributes) order: two overlapping
        # checkouts then acquire the same global sequence and cannot deadlock.
        for item in sorted(
            order_items,
            key=lambda entry: _lock_key(entry["product"], entry.get("selected_attributes")),
        ):
            product = item["product"]
            quantity = item["quantity"]
            selected_attributes = item.get("selected_attributes", {}) or {}

            inventory = _inventory_row(product, selected_attributes, lock=True)

            if inventory is None or inventory.stock_quantity < quantity:
                available_qty = inventory.stock_quantity if inventory else 0
                raise ValueError(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {available_qty}, Required: {quantity}"
                )

            # Reduce inventory
            update_inventory(inventory, -quantity, "SALE", "Order placement")

        return True


def return_inventory_for_order(order_items):
    """
    Return inventory for cancelled order

    Args:
        order_items: List of order items to return
    """
    with transaction.atomic():
        for item in sorted(
            order_items,
            key=lambda entry: _lock_key(entry["product"], entry.get("selected_attributes")),
        ):
            selected_attributes = item.get("selected_attributes", {})
            inventory = _inventory_row(item["product"], selected_attributes, lock=True)

            if inventory is not None:
                update_inventory(inventory, item["quantity"], "RETURN", "Order cancellation")
                continue

            # Create inventory if it doesn't exist
            inventory = Inventory.objects.create(
                product=item["product"],
                attribute_config=selected_attributes,
                stock_quantity=item["quantity"],
            )

            InventoryAuditLog.objects.create(
                product=item["product"],
                inventory=inventory,
                quantity_delta=item["quantity"],
                action_type="RETURN",
                reason="Order cancellation - inventory created",
                previous_quantity=0,
                new_quantity=item["quantity"],
            )
