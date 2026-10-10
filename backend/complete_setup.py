#!/usr/bin/env python
"""
Complete MarketHub Setup Script
Handles all database migrations and setup for new features
"""

import os
import sys

import django

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.core.management import call_command


def main():
    print("=" * 70)
    print("MARKETHUB COMPLETE SETUP")
    print("=" * 70)
    print()

    print("Step 1: Creating migrations for all apps...")
    apps = ["users", "stores", "products", "inventory", "orders", "payments"]

    for app in apps:
        try:
            print(f"  - Creating migrations for {app}...")
            call_command("makemigrations", app, interactive=False)
        except Exception as e:
            print(f"  ⚠ Warning for {app}: {e}")

    print("\nStep 2: Applying all migrations...")
    try:
        call_command("migrate", interactive=False)
        print("  ✓ All migrations applied successfully")
    except Exception as e:
        print(f"  ✗ Migration error: {e}")
        return False

    print("\nStep 3: Collecting static files...")
    try:
        call_command("collectstatic", "--noinput", interactive=False)
        print("  ✓ Static files collected")
    except Exception as e:
        print(f"  ⚠ Static files warning: {e}")

    print("\n" + "=" * 70)
    print("SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("New features added:")
    print("  ✓ Profile pictures for users and stores")
    print("  ✓ Product reviews and ratings")
    print("  ✓ Wishlist functionality")
    print("  ✓ Store following system")
    print("  ✓ Payment simulation for checkout")
    print()
    print("Next steps:")
    print("  1. Run: python manage.py runserver")
    print("  2. Access: http://localhost:8000/admin/")
    print("  3. Test all new features!")
    print()

    return True


if __name__ == "__main__":
    main()
