"""Search analytics report (Phase 15): top queries and the zero-result backlog.

    python manage.py search_report --days 30
    python manage.py search_report --days 7 --json

The second list is the product input: every repeated zero-result query is a
missing synonym, a typo worth a suggestion, or a category the catalogue does
not have yet.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.search.models import SearchQuery


class Command(BaseCommand):
    help = "Report top and zero-result search queries."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=options["days"])
        queryset = SearchQuery.objects.filter(created_at__gte=since).exclude(normalized="")
        top = list(
            queryset.values("query", "normalized")
            .annotate(hits=Count("id"))
            .order_by("-hits")[: options["limit"]]
        )
        zero = list(
            queryset.filter(zero_results=True)
            .values("query", "normalized")
            .annotate(hits=Count("id"))
            .order_by("-hits")[: options["limit"]]
        )
        payload = {
            "days": options["days"],
            "top_queries": top,
            "zero_result_queries": zero,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        self.stdout.write(f"Search report - last {options['days']} days")
        self.stdout.write("\nTop queries:")
        for row in top:
            self.stdout.write(f"  {row['hits']:>5}  {row['query']}")
        self.stdout.write("\nZero-result queries (synonym/catalogue backlog):")
        for row in zero:
            self.stdout.write(f"  {row['hits']:>5}  {row['query']}")
