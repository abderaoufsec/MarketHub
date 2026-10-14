"""``manage.py load_geography`` — load/refresh wilayas + communes (Phase 11).

Idempotent by design: it upserts on the stable ``code`` fields, so it can be
re-run whenever the fixture is refreshed after an administrative reform
(48 → 58 → 69 wilayas) without touching addresses that reference existing
rows. Nothing is ever deleted here — a wilaya that disappears from the
official list is deactivated by hand.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.geography.models import Commune, Wilaya

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "geography.json"


class Command(BaseCommand):
    help = "Load or refresh the Algerian wilaya/commune fixture (apps/geography)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(FIXTURE_PATH), help="Path to geography.json")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Fixture not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Fixture is not valid JSON: {exc}") from exc

        wilaya_rows = data.get("wilayas", [])
        commune_rows = data.get("communes", [])
        if not wilaya_rows or not commune_rows:
            raise CommandError("Fixture has no wilayas or communes.")

        with transaction.atomic():
            wilaya_by_code = {}
            for row in wilaya_rows:
                wilaya, _ = Wilaya.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "name_fr": row["name_fr"],
                        "name_ar": row["name_ar"],
                        "name_en": row.get("name_en", ""),
                        "latitude": row.get("latitude"),
                        "longitude": row.get("longitude"),
                        "is_active": True,
                    },
                )
                wilaya_by_code[row["code"]] = wilaya

            created = 0
            for row in commune_rows:
                wilaya = wilaya_by_code.get(row["wilaya_code"])
                if wilaya is None:
                    raise CommandError(
                        f"Commune {row['code']} references unknown wilaya {row['wilaya_code']!r}"
                    )
                _, was_created = Commune.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "name_fr": row["name_fr"],
                        "name_ar": row["name_ar"],
                        "name_en": row.get("name_en", ""),
                        "wilaya": wilaya,
                        "latitude": row.get("latitude"),
                        "longitude": row.get("longitude"),
                        "is_active": True,
                    },
                )
                created += was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(wilaya_rows)} wilayas and "
                f"{len(commune_rows)} communes ({created} new)."
            )
        )
