"""Flip listings whose window closed: ACTIVE & ``expires_at <= now`` → EXPIRED.

``manage.py expire_listings`` — idempotent (a second run finds nothing), so a
cron can wrap it whenever Phase 22's beat lands without changing the command.
The lazy per-row check in :func:`apps.products.lifecycle.expire_if_due` covers
the single listing a visitor opens between sweeps; this covers the feed, where
an expired row would otherwise sit at its old rank until someone visits it.

``--dry-run`` reports what *would* flip — the safe way to check a production
schedule before trusting it.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.products.models import ListingStatus, Product


class Command(BaseCommand):
    help = "Expire listings past their expires_at window (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the count without changing any rows.",
        )

    def handle(self, *args, **options):
        due = Product.objects.filter(status=ListingStatus.ACTIVE, expires_at__lte=timezone.now())
        count = due.count()
        if options["dry_run"]:
            self.stdout.write(f"{count} listing(s) would expire.")
            return

        with transaction.atomic():
            flipped = due.update(status=ListingStatus.EXPIRED, updated_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(f"Expired {flipped} listing(s)."))
