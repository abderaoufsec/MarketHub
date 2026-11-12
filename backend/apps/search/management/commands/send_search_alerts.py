"""Daily saved-search digest (Phase 15).

Run it from cron/Beat (Phase 22) once a day:

    python manage.py send_search_alerts

``--dry-run`` evaluates and reports without sending; ``--limit`` caps the
number of saved searches for a smoke run on a large table.
"""

from django.core.management.base import BaseCommand

from apps.search.alerts import send_daily_digests


class Command(BaseCommand):
    help = "Send daily digest emails/SMS/WhatsApp for due saved searches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Evaluate and report without sending or updating timestamps.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N saved searches (oldest first).",
        )

    def handle(self, *args, **options):
        report = send_daily_digests(dry_run=options["dry_run"], limit=options["limit"])
        self.stdout.write(
            "saved searches: {searched} checked, {with_matches} with matches, "
            "{sent} sent, {failed} failed".format(**report)
        )
