#!/usr/bin/env python3
"""
MarketHub Test Data Generator
Creates sample users, stores, and products for testing
"""

from django.contrib.auth import get_user_model

from apps.inventory.models import Inventory
from apps.products.models import Product
from apps.stores.models import Store

User = get_user_model()


def create_test_data():
    print("🚀 Creating test data for MarketHub...")

    # Create Seller
    print("\n📝 Creating seller account...")
    seller, created = User.objects.get_or_create(
        email="seller@test.com",
        defaults={
            "first_name": "John",
            "last_name": "Seller",
            "is_seller": True,
            "is_verified": True,
        },
    )
    if created:
        seller.set_password("Test123!")
        seller.save()
        print("✅ Seller created: seller@test.com / Test123!")
    else:
        print("ℹ️  Seller already exists")

    # Create Buyer
    print("\n📝 Creating buyer account...")
    buyer, created = User.objects.get_or_create(
        email="buyer@test.com",
        defaults={"first_name": "Jane", "last_name": "Buyer", "is_verified": True},
    )
    if created:
        buyer.set_password("Test123!")
        buyer.save()
        print("✅ Buyer created: buyer@test.com / Test123!")
    else:
        print("ℹ️  Buyer already exists")

    # Create Store
    print("\n🏪 Creating store...")
    store, created = Store.objects.get_or_create(
        owner=seller,
        defaults={
            "store_name": "Electronics Plus",
            "store_slug": "electronics-plus",
            "description": "Your one-stop shop for quality electronics and gadgets",
            "category": "Electronics",
            "is_active": True,
        },
    )
    if created:
        print("✅ Store created: Electronics Plus")
    else:
        print("ℹ️  Store already exists")

    # Create Products
    print("\n📦 Creating products...")
    products_data = [
        {
            "name": "Wireless Headphones",
            "description": "Premium noise-cancelling wireless headphones with 30-hour battery life. Perfect for music lovers and professionals who need to focus.",
            "price": 99.99,
            "stock": 50,
        },
        {
            "name": "Smart Watch Pro",
            "description": "Feature-rich smartwatch with fitness tracking, heart rate monitor, GPS, and smartphone notifications. Water-resistant up to 50m.",
            "price": 199.99,
            "stock": 30,
        },
        {
            "name": "Bluetooth Speaker",
            "description": "Portable waterproof bluetooth speaker with 360-degree sound. 20-hour battery life and hands-free calling.",
            "price": 79.99,
            "stock": 75,
        },
        {
            "name": "USB-C Hub",
            "description": "7-in-1 USB-C hub with HDMI, USB 3.0, SD card readers, and 100W power delivery. Perfect for laptops and tablets.",
            "price": 49.99,
            "stock": 100,
        },
        {
            "name": "Wireless Charger",
            "description": "Fast 15W wireless charging pad compatible with all Qi-enabled devices. LED indicator and cooling system.",
            "price": 29.99,
            "stock": 120,
        },
    ]

    for data in products_data:
        product, created = Product.objects.get_or_create(
            store=store,
            name=data["name"],
            defaults={
                "description": data["description"],
                "base_price": data["price"],
                "category": "Electronics",
                "is_available": True,
                "low_stock_threshold": 10,
            },
        )

        if created:
            # Create inventory
            Inventory.objects.create(product=product, stock_quantity=data["stock"])
            print(f"   ✅ {data['name']} - ${data['price']} ({data['stock']} in stock)")
        else:
            print(f"   ℹ️  {data['name']} already exists")

    print("\n" + "=" * 50)
    print("🎉 Test data creation complete!")
    print("=" * 50)
    print("\n📧 Login Credentials:")
    print("   Seller: seller@test.com / Test123!")
    print("   Buyer:  buyer@test.com / Test123!")
    print("\n🌐 Access the app:")
    print("   Frontend: http://localhost:3000")
    print("   Backend:  http://localhost:8000/admin")
    print("\n💡 Quick Actions:")
    print("   • Login as seller and visit /seller/dashboard")
    print("   • Login as buyer and browse /products")
    print("   • View the store at /stores/electronics-plus")
    print("")


if __name__ == "__main__":
    create_test_data()
