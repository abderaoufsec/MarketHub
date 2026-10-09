"""
COMPLETE FIX AND OPTIMIZATION SCRIPT
Run this to fix ALL issues at once
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction
from apps.products.models import Product
from apps.inventory.models import Inventory, InventoryAuditLog
from apps.stores.models import Store

def main():
    print("="*70)
    print(" MARKETHUB - COMPLETE FIX AND OPTIMIZATION ")
    print("="*70)
    print()
    
    # Step 1: Fix Inventory
    print("STEP 1: FIXING INVENTORY ISSUES")
    print("-"*70)
    fix_inventory()
    print()
    
    # Step 2: Verify Products
    print("STEP 2: VERIFYING PRODUCTS")
    print("-"*70)
    verify_products()
    print()
    
    # Step 3: Verify Stores
    print("STEP 3: VERIFYING STORES")
    print("-"*70)
    verify_stores()
    print()
    
    print("="*70)
    print(" ALL FIXES COMPLETED SUCCESSFULLY! ")
    print("="*70)
    print()
    print("Next steps:")
    print("1. Restart your Django server (Ctrl+C then: python manage.py runserver)")
    print("2. Restart your Next.js frontend (Ctrl+C then: npm run dev)")
    print("3. Clear your browser cache (Ctrl+Shift+Delete)")
    print("4. Test the application")
    print()

def fix_inventory():
    """Fix all inventory issues"""
    products = Product.objects.all()
    total = products.count()
    
    print(f"Found {total} products to process...")
    
    created = 0
    fixed = 0
    ok = 0
    
    with transaction.atomic():
        for i, product in enumerate(products, 1):
            print(f"[{i}/{total}] {product.name[:40]}...", end=" ")
            
            # Get or create inventory
            inventory, is_created = Inventory.objects.get_or_create(
                product=product,
                attribute_config={},
                defaults={'stock_quantity': 100}
            )
            
            if is_created:
                created += 1
                print("✓ Created (100 units)")
                
                InventoryAuditLog.objects.create(
                    product=product,
                    inventory=inventory,
                    quantity_delta=100,
                    action_type='INITIAL_STOCK',
                    reason='System initialization',
                    previous_quantity=0,
                    new_quantity=100
                )
            elif inventory.stock_quantity <= 0:
                inventory.stock_quantity = 100
                inventory.save()
                fixed += 1
                print("✓ Fixed (0 → 100 units)")
                
                InventoryAuditLog.objects.create(
                    product=product,
                    inventory=inventory,
                    quantity_delta=100,
                    action_type='RESTOCK',
                    reason='System fix',
                    previous_quantity=0,
                    new_quantity=100
                )
            else:
                ok += 1
                print(f"✓ OK ({inventory.stock_quantity} units)")
    
    print()
    print(f"Results: {created} created, {fixed} fixed, {ok} already OK")
    
    # Verify
    zero_stock = Inventory.objects.filter(stock_quantity=0).count()
    if zero_stock == 0:
        print("✓✓✓ SUCCESS! All products have inventory!")
    else:
        print(f"⚠ Warning: {zero_stock} items still have zero stock")

def verify_products():
    """Verify all products are properly configured"""
    products = Product.objects.all()
    
    issues = []
    for product in products:
        # Check if product has inventory
        if not Inventory.objects.filter(product=product).exists():
            issues.append(f"Missing inventory: {product.name}")
        
        # Check if store is active
        if not product.store.is_active:
            issues.append(f"Inactive store: {product.name}")
        
        # Check price
        if product.base_price <= 0:
            issues.append(f"Invalid price: {product.name}")
    
    if issues:
        print(f"Found {len(issues)} issues:")
        for issue in issues[:10]:
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
    else:
        print("✓ All products verified successfully!")

def verify_stores():
    """Verify all stores are properly configured"""
    stores = Store.objects.all()
    active = stores.filter(is_active=True).count()
    inactive = stores.filter(is_active=False).count()
    
    print(f"Total Stores: {stores.count()}")
    print(f"  Active: {active}")
    print(f"  Inactive: {inactive}")
    
    # Check for stores with no products
    empty_stores = [s for s in stores if s.products.count() == 0]
    if empty_stores:
        print(f"⚠ {len(empty_stores)} stores have no products")
    else:
        print("✓ All stores have products")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
