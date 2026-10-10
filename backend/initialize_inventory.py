"""
Comprehensive Inventory Initialization and Fix Script
Run with: python manage.py shell < initialize_inventory.py
"""

from django.db import transaction

from apps.inventory.models import Inventory, InventoryAuditLog
from apps.products.models import Product


def initialize_inventory():
    print("=" * 60)
    print("COMPREHENSIVE INVENTORY INITIALIZATION")
    print("=" * 60)
    print()

    # Get all products
    products = Product.objects.all()
    total_products = products.count()

    print(f"Found {total_products} products")
    print()

    created_count = 0
    updated_count = 0
    already_ok_count = 0

    with transaction.atomic():
        for product in products:
            print(f"Processing: {product.name[:50]}...")

            # Get or create default inventory (empty attributes)
            inventory, created = Inventory.objects.get_or_create(
                product=product, attribute_config={}, defaults={"stock_quantity": 100}
            )

            if created:
                created_count += 1
                print("  ✓ Created inventory with 100 units")

                # Create audit log
                InventoryAuditLog.objects.create(
                    product=product,
                    inventory=inventory,
                    quantity_delta=100,
                    action_type="INITIAL_STOCK",
                    reason="System initialization",
                    previous_quantity=0,
                    new_quantity=100,
                )
            elif inventory.stock_quantity == 0:
                # Update zero stock to 100
                previous = inventory.stock_quantity
                inventory.stock_quantity = 100
                inventory.save()
                updated_count += 1
                print(f"  ✓ Updated from {previous} to 100 units")

                # Create audit log
                InventoryAuditLog.objects.create(
                    product=product,
                    inventory=inventory,
                    quantity_delta=100,
                    action_type="RESTOCK",
                    reason="System fix - zero stock",
                    previous_quantity=previous,
                    new_quantity=100,
                )
            else:
                already_ok_count += 1
                print(f"  ✓ Already has {inventory.stock_quantity} units")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Products:           {total_products}")
    print(f"New Inventory Created:    {created_count}")
    print(f"Zero Stock Updated:       {updated_count}")
    print(f"Already OK:               {already_ok_count}")
    print()

    # Final verification
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    total_inventory = Inventory.objects.count()
    zero_stock = Inventory.objects.filter(stock_quantity=0).count()
    low_stock = Inventory.objects.filter(stock_quantity__lte=10, stock_quantity__gt=0).count()
    good_stock = Inventory.objects.filter(stock_quantity__gt=10).count()

    print(f"Total Inventory Records:  {total_inventory}")
    print(f"Zero Stock Items:         {zero_stock}")
    print(f"Low Stock (1-10):         {low_stock}")
    print(f"Good Stock (>10):         {good_stock}")
    print()

    if zero_stock == 0:
        print("✓✓✓ SUCCESS! All products have inventory! ✓✓✓")
    else:
        print("⚠ WARNING: Some items still have zero stock")
        print("Products with zero stock:")
        for inv in Inventory.objects.filter(stock_quantity=0)[:10]:
            print(f"  - {inv.product.name}")

    print()
    print("=" * 60)
    print("INITIALIZATION COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    initialize_inventory()
