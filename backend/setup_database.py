#!/usr/bin/env python
"""
Database Setup and Migration Script for MarketHub
Run this to fix all database issues
"""

import os
import sys
import django

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.management import call_command
from django.db import connection

def check_database_connection():
    """Check if database is accessible"""
    try:
        connection.ensure_connection()
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def run_migrations():
    """Run all migrations"""
    print("\n" + "="*60)
    print("STEP 1: Creating Migrations")
    print("="*60)
    
    apps = ['users', 'stores', 'products', 'inventory', 'orders', 'payments']
    
    for app in apps:
        try:
            print(f"\nCreating migrations for {app}...")
            call_command('makemigrations', app, interactive=False)
            print(f"✓ Migrations created for {app}")
        except Exception as e:
            print(f"⚠ Warning for {app}: {e}")
    
    print("\n" + "="*60)
    print("STEP 2: Applying Migrations")
    print("="*60)
    
    try:
        print("\nApplying all migrations...")
        call_command('migrate', interactive=False)
        print("✓ All migrations applied successfully")
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False
    
    return True

def show_migration_status():
    """Show the status of all migrations"""
    print("\n" + "="*60)
    print("Migration Status")
    print("="*60)
    try:
        call_command('showmigrations')
    except Exception as e:
        print(f"Error showing migrations: {e}")

def check_stores():
    """Check existing stores"""
    print("\n" + "="*60)
    print("STEP 3: Checking Existing Stores")
    print("="*60)
    
    try:
        from apps.stores.models import Store
        stores = Store.objects.all()
        
        if stores.exists():
            print(f"\n✓ Found {stores.count()} store(s) in database:")
            for store in stores:
                print(f"  - {store.store_name} (Slug: {store.store_slug}, Active: {store.is_active})")
                print(f"    Owner: {store.owner.email}")
                print(f"    Category: {store.category}")
        else:
            print("\n⚠ No stores found in database")
            
    except Exception as e:
        print(f"✗ Error checking stores: {e}")

def check_users():
    """Check existing users"""
    print("\n" + "="*60)
    print("Checking Users")
    print("="*60)
    
    try:
        from apps.users.models import User
        sellers = User.objects.filter(is_seller=True)
        
        print(f"\n✓ Found {sellers.count()} seller(s):")
        for seller in sellers:
            print(f"  - {seller.email} (Verified: {seller.is_verified})")
            if hasattr(seller, 'store'):
                print(f"    Has store: {seller.store.store_name}")
            else:
                print(f"    No store yet")
                
    except Exception as e:
        print(f"✗ Error checking users: {e}")

def main():
    """Main execution"""
    print("\n" + "="*60)
    print("MarketHub Database Setup & Fix Script")
    print("="*60)
    
    # Check database connection
    if not check_database_connection():
        print("\n✗ Cannot proceed without database connection")
        print("\nPlease check:")
        print("1. PostgreSQL is running")
        print("2. Database 'markethub' exists")
        print("3. Database credentials in .env.local are correct")
        return
    
    # Run migrations
    if not run_migrations():
        print("\n✗ Migration failed. Please check errors above.")
        return
    
    # Show migration status
    show_migration_status()
    
    # Check stores and users
    check_stores()
    check_users()
    
    print("\n" + "="*60)
    print("Setup Complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Restart your Django server: python manage.py runserver")
    print("2. Try accessing your store in the frontend")
    print("3. If store still doesn't show, check the logs above")
    print("\n")

if __name__ == '__main__':
    main()
