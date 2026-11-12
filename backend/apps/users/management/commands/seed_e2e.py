"""Seed verified demo accounts and listings for the Playwright smoke suite.

docs/todo.md Phase 4 — registration only creates *unverified* users and
login rejects them (403), so the e2e journeys need a pre-verified buyer and
a pre-verified seller with a store and one listing. This command is
idempotent: re-running it updates the same rows instead of duplicating them.

    python manage.py seed_e2e
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Category
from apps.geography.models import Wilaya
from apps.inventory.models import Inventory
from apps.messaging.models import Conversation, PhoneReveal, Report, UserBlock
from apps.messaging.stats import invalidate_seller_response_time
from apps.products.models import ContactMode, ListingType, PriceMode, Product
from apps.stores.models import Store

User = get_user_model()

BUYER_EMAIL = "e2e-buyer@example.com"
SELLER_EMAIL = "e2e-seller@example.com"
PASSWORD = "E2e!SmokeTest123"
SELLER_PHONE = "+213555123456"

PRODUCT_NAME = "E2E Test Phone"
# Phase 16: a classified, negotiable listing the contact/chat/offer journeys
# start from. It belongs to the seller (the buyer is the contact side).
NEGOTIABLE_NAME = "E2E Negotiable Phone"
# Products created by the Playwright "post a listing" journey (timestamped).
STALE_PRODUCT_PREFIX = "E2E Listing "
# Classifieds the Playwright "post a classified" wizard journey creates.
STALE_AD_PREFIX = "E2E Ad "


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
        # Phase 16 phone reveal: the classified seller needs a *verified*
        # number, otherwise the reveal endpoint answers `phone_not_available`.
        seller.phone_number = SELLER_PHONE
        seller.phone_verified_at = seller.phone_verified_at or timezone.now()
        seller.set_password(PASSWORD)
        seller.save()

        # Phase 12: the fixtures file the store under "electronics" and the
        # listing under "phones-tablets"; the launch tree must exist first.
        call_command("load_categories", verbosity=0)
        call_command("load_geography", verbosity=0)
        electronics = Category.objects.get(slug="electronics")
        phones = Category.objects.get(slug="phones-tablets")
        alger = Wilaya.objects.get(code="16")

        store, _ = Store.objects.get_or_create(
            owner=seller,
            defaults={
                "store_name": "E2E Smoke Store",
                "description": "Store used by the Playwright smoke suite.",
                "category": electronics,
                "is_active": True,
            },
        )
        if store.category_id != electronics.id:
            store.category = electronics
            store.save(update_fields=["category"])

        product, _ = Product.objects.get_or_create(
            store=store,
            name=PRODUCT_NAME,
            defaults={
                "seller": seller,
                "description": "A phone listed by the e2e seed command.",
                "base_price": 45000,
                "category": phones,
                "is_available": True,
            },
        )
        if product.category_id != phones.id:
            product.category = phones
            product.save(update_fields=["category"])
        if product.seller_id is None:
            # Row from before Phase 13's seller FK (its backfill may predate
            # this command's first run on a long-lived dev database).
            product.seller = store.owner
            product.save(update_fields=["seller"])
        if not product.slug:
            # Phase 13: the canonical URL is /l/<slug>-<id>; give the seeded
            # listing a real slug (publish would have) so the journey clicks
            # through a URL users actually see.
            product.slug = slugify(product.name)[:230]
            product.save(update_fields=["slug"])
        Inventory.objects.get_or_create(
            product=product,
            attribute_config={},
            defaults={"stock_quantity": 10},
        )

        # Phase 16: a contact-first classified the buyer can chat about, reveal
        # the seller's phone on, and negotiate. It is deliberately *not* a
        # store product, so the UI offers chat/offers instead of checkout.
        negotiable = (
            Product.objects.filter(seller=seller, name=NEGOTIABLE_NAME)
            .order_by("pk")
            .first()
        )
        if negotiable is None:
            negotiable = Product(seller=seller, name=NEGOTIABLE_NAME)
        negotiable.store = None
        negotiable.description = (
            "A negotiable phone used by the Playwright contact/chat/offer journeys."
        )
        negotiable.base_price = 25000
        negotiable.price_mode = PriceMode.NEGOTIABLE
        negotiable.category = phones
        negotiable.listing_type = ListingType.FOR_SALE
        negotiable.contact_mode = ContactMode.PHONE
        negotiable.wilaya = alger
        negotiable.commune = None
        negotiable.slug = slugify(NEGOTIABLE_NAME)[:230]
        negotiable.is_available = True
        negotiable.save()

        # Deterministic reruns: the chat specs create conversations, messages,
        # offers and reveals for these two accounts. Clear them in the global
        # setup run so the inbox starts empty and read counts are predictable.
        parties = Q(buyer__in=[buyer, seller]) | Q(seller__in=[buyer, seller])
        Conversation.objects.filter(parties).delete()
        PhoneReveal.objects.filter(
            Q(viewer__in=[buyer, seller]) | Q(seller__in=[buyer, seller])
        ).delete()
        UserBlock.objects.filter(
            Q(blocker__in=[buyer, seller]) | Q(blocked__in=[buyer, seller])
        ).delete()
        Report.objects.filter(
            Q(reporter__in=[buyer, seller]) | Q(reported_user__in=[buyer, seller])
        ).delete()
        # The response-time badge is cached from those (now deleted) replies.
        invalidate_seller_response_time(seller.pk)

        # The "post a listing" journey creates one new product per run and the
        # free plan caps listings (settings.MAX_PRODUCTS_PER_SELLER). Prune the
        # leftovers from earlier runs so the suite never trips the quota.
        pruned, _ = (
            store.products.exclude(pk=product.pk)
            .filter(name__startswith=STALE_PRODUCT_PREFIX)
            .delete()
        )
        # Same story for the wizard's classifieds: the buyer's free tier caps
        # active listings (settings.MAX_ACTIVE_LISTINGS_PER_USER).
        pruned_ads, _ = Product.objects.filter(
            seller=buyer, name__startswith=STALE_AD_PREFIX
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded buyer {BUYER_EMAIL}, seller {SELLER_EMAIL} "
                f"(password {PASSWORD}), store '{store.store_name}', "
                f"product '{product.name}' (id={product.pk}), "
                f"negotiable '{negotiable.name}' (id={negotiable.pk})"
                + (
                    f", pruned {pruned} stale listing(s) and {pruned_ads} stale ad(s)."
                    if pruned or pruned_ads
                    else "."
                )
            )
        )
