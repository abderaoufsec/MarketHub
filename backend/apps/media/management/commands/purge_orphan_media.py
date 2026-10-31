"""Delete uploads no listing references, and their files.

The wizard autosaves a draft the moment the seller leaves step 1, and photos
can be uploaded before that draft exists; abandoning the flow leaves rows
behind. This command reclaims them — only rows older than a grace window
(default 24h), only ones no listing references.

    python manage.py purge_orphan_media --dry-run
    python manage.py purge_orphan_media --older-than-hours 6
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.media.models import Image
from apps.media.processing import delete_files


class Command(BaseCommand):
    help = "Delete media uploads that no listing references (and their files)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=24,
            help="Grace window before an unattached upload is reclaimed (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without touching anything.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=max(0, options["older_than_hours"]))
        orphans = Image.objects.filter(product_images__isnull=True, created_at__lt=cutoff)
        total = orphans.count()

        if options["dry_run"]:
            self.stdout.write(f"Would delete {total} orphaned image(s).")
            return

        for image in orphans.iterator():
            delete_files(image)
            image.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {total} orphaned image(s)."))
