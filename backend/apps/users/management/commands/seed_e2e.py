"""Seed verified demo accounts and listings for the Playwright smoke suite.

docs/todo.md Phase 4 — registration only creates *unverified* users and
login rejects them (403), so the e2e journeys need a pre-verified buyer and
a pre-verified seller with a store and one listing. This command is
idempotent: re-running it updates the same rows instead of duplicating them.

    python manage.py seed_e2e
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.inventory.models import Inventory
from apps.products.models import Product
from apps.stores.models import Store

User = get_user_model()

BUYER_EMAIL = "e2e-buyer@example.com"
SELLER_EMAIL = "e2e-seller@example.com"
PASSWORD = "E2e!SmokeTest123"

PRODUCT_NAME = "E2E Test Phone"
# Products created by the Playwright "post a listing" journey (timestamped).
STALE_PRODUCT_PREFIX = "E2E Listing "


class Command(BaseCommand):
    help = "Create/refresh verified e2e fixtures (buyer, seller+store, listing)."

    def handle(self, *args, **options):
        buyer, _ = User.objects.get_or_create(
            email=BUYER_EMAIL,
            defaults={
                "username": "e2e_buyer",
                "first_name": "E2E",
                "last_name": "Buyer",
                "is_verified": True,
            },
        )
        # get_or_create does not touch existing rows; make sure the flag and
        # password are correct even when the row already existed.
        changed = False
        if not buyer.is_verified:
            buyer.is_verified = True
            changed = True
        if changed:
            buyer.save()
        buyer.set_password(PASSWORD)
        buyer.save()

        seller, _ = User.objects.get_or_create(
            email=SELLER_EMAIL,
            defaults={
                "username": "e2e_seller",
                "first_name": "E2E",
                "last_name": "Seller",
                "is_verified": True,
                "is_seller": True,
            },
        )
        seller.is_verified = True
        seller.is_seller = True
        seller.set_password(PASSWORD)
        seller.save()

        store, _ = Store.objects.get_or_create(
            owner=seller,
            defaults={
                "store_name": "E2E Smoke Store",
                "description": "Store used by the Playwright smoke suite.",
                "category": "electronics",
                "is_active": True,
            },
        )

        product, _ = Product.objects.get_or_create(
            store=store,
            name=PRODUCT_NAME,
            defaults={
                "description": "A phone listed by the e2e seed command.",
                "base_price": 45000,
                "category": "phones",
                "is_available": True,
            },
        )
        Inventory.objects.get_or_create(
            product=product,
            attribute_config={},
            defaults={"stock_quantity": 10},
        )

        # The "post a listing" journey creates one new product per run and the
        # free plan caps listings (settings.MAX_PRODUCTS_PER_SELLER). Prune the
        # leftovers from earlier runs so the suite never trips the quota.
        pruned, _ = (
            store.products.exclude(pk=product.pk)
            .filter(name__startswith=STALE_PRODUCT_PREFIX)
            .delete()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded buyer {BUYER_EMAIL}, seller {SELLER_EMAIL} "
                f"(password {PASSWORD}), store '{store.store_name}', "
                f"product '{product.name}' (id={product.pk})"
                + (f", pruned {pruned} stale listing(s)." if pruned else ".")
            )
        )
