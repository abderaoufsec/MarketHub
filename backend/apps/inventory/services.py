from django.db import transaction

from .models import Inventory, InventoryAuditLog


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
        previous_quantity = inventory.stock_quantity
        new_quantity = previous_quantity + quantity_delta

        # Prevent negative inventory
        if new_quantity < 0:
            raise ValueError(
                f"Insufficient stock. Available: {previous_quantity}, Required: {abs(quantity_delta)}"
            )

        # Update inventory
        inventory.stock_quantity = new_quantity
        inventory.save()

        # Create audit log
        InventoryAuditLog.objects.create(
            product=inventory.product,
            inventory=inventory,
            quantity_delta=quantity_delta,
            action_type=action_type,
            reason=reason,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
        )

        return inventory


def check_stock_availability(product, selected_attributes, required_quantity):
    """
    Check if sufficient stock is available for a product

    Args:
        product: Product instance
        selected_attributes: Dict of selected attributes
        required_quantity: Required quantity

    Returns:
        tuple: (is_available, inventory_instance or None)
    """
    try:
        inventory = Inventory.objects.get(
            product=product, attribute_config=selected_attributes or {}
        )

        if inventory.stock_quantity >= required_quantity:
            return True, inventory
        else:
            return False, inventory
    except Inventory.DoesNotExist:
        return False, None


def reserve_inventory_for_order(order_items):
    """
    Reserve inventory for order items

    Args:
        order_items: List of order items with product and quantity

    Returns:
        bool: True if all items reserved successfully

    Raises:
        ValueError: If insufficient stock
    """
    with transaction.atomic():
        for item in order_items:
            is_available, inventory = check_stock_availability(
                item["product"], item.get("selected_attributes", {}), item["quantity"]
            )

            if not is_available:
                product_name = (
                    item["product"].name
                    if hasattr(item["product"], "name")
                    else str(item["product"])
                )
                available_qty = inventory.stock_quantity if inventory else 0
                raise ValueError(
                    f"Insufficient stock for {product_name}. "
                    f"Available: {available_qty}, Required: {item['quantity']}"
                )

            # Reduce inventory
            update_inventory(inventory, -item["quantity"], "SALE", "Order placement")

        return True


def return_inventory_for_order(order_items):
    """
    Return inventory for cancelled order

    Args:
        order_items: List of order items to return
    """
    with transaction.atomic():
        for item in order_items:
            try:
                inventory = Inventory.objects.get(
                    product=item["product"], attribute_config=item.get("selected_attributes", {})
                )

                update_inventory(inventory, item["quantity"], "RETURN", "Order cancellation")
            except Inventory.DoesNotExist:
                # Create inventory if it doesn't exist
                inventory = Inventory.objects.create(
                    product=item["product"],
                    attribute_config=item.get("selected_attributes", {}),
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
