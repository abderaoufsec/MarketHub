"""Rebuild ``Product.search_document`` (Phase 15).

``Product.save()`` maintains the document, and a data migration backfills
pre-Phase-15 rows. Run this after changing the document builder (a new synonym
section, a new indexed field) or after a bulk ``QuerySet.update()``:

    python manage.py rebuild_search_index

It walks in ``iterator()`` batches and only writes the derived column, so it
is safe on a live catalogue.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.products.models import Product
from apps.search.documents import build_search_document


class Command(BaseCommand):
    help = "Rebuild the denormalized search document for every product."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500, help="Rows per iterator batch.")

    def handle(self, *args, **options):
        updated = 0
        queryset = Product.objects.select_related(
            "category", "wilaya", "commune", "store"
        ).order_by("pk")
        for product in queryset.iterator(chunk_size=options["batch_size"]):
            document = build_search_document(product)
            if document != product.search_document:
                Product.objects.filter(pk=product.pk).update(search_document=document)
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"search documents rebuilt: {updated} updated"))
