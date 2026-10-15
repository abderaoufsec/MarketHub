"""``manage.py load_categories`` — load/refresh the launch category tree (Phase 12).

Idempotent by design: it upserts categories on their stable ``slug`` and
attribute definitions on ``(category, key)``, so it can be re-run whenever
the fixture grows (Phase 29 owns the full taxonomy expansion) without
touching products that already reference existing rows. Nothing is ever
deleted here — a category that disappears is deactivated by hand, which also
keeps it fileable by the products that still point at it (the FK is PROTECT).

Ends with ``Category.objects.rebuild()``: stores.0005 created the nine legacy
roots with hand-written mptt fields, and the rebuild recomputes every
``tree_id``/``lft``/``rght``/``level`` from the actual parent links — one
cheap pass over a tree this size, and it makes the whole load self-healing.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import AttributeDefinition, Category

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "categories.json"

VALID_TYPES = set(AttributeDefinition.Type.values)


class Command(BaseCommand):
    help = "Load or refresh the category tree + attribute definitions (apps/catalog)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(FIXTURE_PATH), help="Path to categories.json")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Fixture not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Fixture is not valid JSON: {exc}") from exc

        rows = data.get("categories", [])
        if not rows:
            raise CommandError("Fixture has no categories.")

        with transaction.atomic():
            categories_created, definitions_created = self._upsert_tree(rows, parent=None)
            # Self-heal mptt fields (hand-written roots from stores.0005,
            # any partial load interrupted last time).
            Category.objects.rebuild()

        total_defs = AttributeDefinition.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {Category.objects.count()} categories "
                f"({categories_created} new) and {total_defs} attribute definitions "
                f"({definitions_created} new)."
            )
        )

    def _upsert_tree(self, rows, parent):
        """Upsert one level of the fixture tree.

        Returns ``(categories_created, definitions_created)``.
        """
        categories_created = 0
        definitions_created = 0
        for row in rows:
            for field in ("slug", "name_fr", "name_ar"):
                if not row.get(field):
                    raise CommandError(
                        f"Category under {getattr(parent, 'slug', None)!r} is missing {field!r}"
                    )
            category, was_created = Category.objects.update_or_create(
                slug=row["slug"],
                defaults={
                    "name_fr": row["name_fr"],
                    "name_ar": row["name_ar"],
                    "name_en": row.get("name_en", ""),
                    "parent": parent,
                    "icon": row.get("icon", ""),
                    "order": row.get("order", 0),
                    "is_active": True,
                },
            )
            categories_created += was_created
            definitions_created += self._upsert_definitions(
                category, row.get("attribute_definitions", [])
            )
            children_created, children_definitions_created = self._upsert_tree(
                row.get("children", []), parent=category
            )
            categories_created += children_created
            definitions_created += children_definitions_created
        return categories_created, definitions_created

    def _upsert_definitions(self, category, rows):
        created = 0
        for row in rows:
            key = row.get("key")
            if not key:
                raise CommandError(f"Category {category.slug} has a definition without a key")
            if row.get("type") not in VALID_TYPES:
                raise CommandError(
                    f"Category {category.slug}.{key} has unknown type {row.get('type')!r}"
                )
            if row["type"] == AttributeDefinition.Type.ENUM and not row.get("choices"):
                raise CommandError(f"Category {category.slug}.{key} is an enum without choices")
            _obj, was_created = AttributeDefinition.objects.update_or_create(
                category=category,
                key=key,
                defaults={
                    "label_fr": row.get("label_fr", ""),
                    "label_ar": row.get("label_ar", ""),
                    "label_en": row.get("label_en", ""),
                    "type": row["type"],
                    "required": bool(row.get("required", False)),
                    "filterable": bool(row.get("filterable", False)),
                    "unit": row.get("unit", ""),
                    "choices": row.get("choices", []),
                    "order": row.get("order", 0),
                    "is_active": True,
                },
            )
            created += was_created
        return created
