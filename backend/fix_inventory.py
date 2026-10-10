"""
Script to fix inventory issues
Run with: python manage.py shell < fix_inventory.py
"""

from apps.inventory.models import Inventory
from apps.products.models import Product


def fix_inventory():
    print("Checking inventory...")

    # Get all products
    products = Product.objects.all()

    for product in products:
        # Check if product has inventory
        inventories = Inventory.objects.filter(product=product)

        if not inventories.exists():
            print(f"Creating inventory for: {product.name}")
            # Create default inventory
            Inventory.objects.create(
                product=product,
                attribute_config={},
                stock_quantity=100,  # Default stock
            )
        else:
            # Check for zero stock
            for inv in inventories:
                if inv.stock_quantity == 0:
                    print(f"Updating zero stock for: {product.name}")
                    inv.stock_quantity = 100
                    inv.save()

    print("\nInventory check complete!")

    # Show summary
    total_products = Product.objects.count()
    total_inventory = Inventory.objects.count()
    zero_stock = Inventory.objects.filter(stock_quantity=0).count()

    print("\nSummary:")
    print(f"Total Products: {total_products}")
    print(f"Total Inventory Records: {total_inventory}")
    print(f"Zero Stock Items: {zero_stock}")


if __name__ == "__main__":
    fix_inventory()
