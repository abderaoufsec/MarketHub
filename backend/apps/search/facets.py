"""Facet counts for the search sidebar (Phase 15).

Every facet is counted on the query **with its own selection removed** - the
standard "OR inside a facet, AND across facets" rule. Picking "Samsung" must
not make the brand list collapse to Samsung, but it must narrow the wilaya
list to the wilayas where Samsung listings exist. ``apply_search_filters``
makes that a matter of passing ``skip``.

The payload is deliberately presentation-neutral: ``value``/``count`` plus a
localized ``label`` the server can build from the same fr/ar/en columns the
rest of the API uses. The frontend maps price bands and date windows to its
translated copy (numbers and date wording are locale decisions).
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import get_language

from apps.catalog.models import AttributeDefinition
from apps.products.filters import apply_search_filters
from apps.products.models import Product

#: Stable keys; the SPA translates the labels (see ``search.priceBands``).
PRICE_BUCKETS = (
    ("under_5k", 0, 5000),
    ("5k_20k", 5000, 20000),
    ("20k_100k", 20000, 100000),
    ("over_100k", 100000, None),
)

POSTED_BUCKETS = ("today", "7d", "30d", "older")

MAX_CATEGORY_FACETS = 14
MAX_WILAYA_FACETS = 12
MAX_ATTRIBUTE_FACETS = 8
MAX_ATTRIBUTE_VALUES = 12


def localized(fr: str, ar: str, en: str = "") -> str:
    language = (get_language() or "fr").split("-")[0]
    if language == "ar":
        return ar or fr
    if language == "en":
        return en or fr
    return fr


def _base_queryset(text_queryset):
    """Facets start from the public catalogue narrowed by the text query.

    ``pk__in`` a subquery, not a join: the text query carries rank annotations
    that must not become GROUP BY terms in every facet aggregate.
    """
    base = Product.objects.public()
    if text_queryset is not None:
        base = base.filter(pk__in=text_queryset.values("pk"))
    return base


def build_facets(query_params, text_queryset=None) -> dict:
    base = _base_queryset(text_queryset)

    def scoped(*, skip=(), skip_attr=None):
        return apply_search_filters(base, query_params, skip=skip, skip_attr=skip_attr)

    facets = {
        "category": _category_facet(scoped(skip=("category",))),
        "wilaya": _wilaya_facet(scoped(skip=("location",))),
        "price": _price_facet(scoped(skip=("price",))),
        "condition": _condition_facet(scoped(skip=("condition",))),
        "seller_type": _seller_type_facet(scoped(skip=("seller_type",))),
        "verified": _verified_facet(scoped(skip=("verified",))),
        "photos": _photos_facet(scoped(skip=("photos",))),
        "posted": _posted_facet(scoped(skip=("posted",))),
        "attributes": _attribute_facets(scoped, query_params),
    }
    return facets


def _category_facet(queryset):
    rows = (
        queryset.filter(category_id__isnull=False)
        .values(
            "category_id",
            "category__slug",
            "category__icon",
            "category__name_fr",
            "category__name_ar",
            "category__name_en",
        )
        .annotate(count=Count("id"))
        .order_by("-count", "category__name_fr")[:MAX_CATEGORY_FACETS]
    )
    return [
        {
            "value": row["category__slug"],
            "label": localized(
                row["category__name_fr"], row["category__name_ar"], row["category__name_en"]
            ),
            "icon": row["category__icon"] or "",
            "count": row["count"],
        }
        for row in rows
    ]


def _wilaya_facet(queryset):
    rows = (
        queryset.filter(wilaya_id__isnull=False)
        .values(
            "wilaya_id",
            "wilaya__name_fr",
            "wilaya__name_ar",
            "wilaya__name_en",
        )
        .annotate(count=Count("id"))
        .order_by("-count", "wilaya__name_fr")[:MAX_WILAYA_FACETS]
    )
    return [
        {
            "value": str(row["wilaya_id"]),
            "label": localized(
                row["wilaya__name_fr"], row["wilaya__name_ar"], row["wilaya__name_en"]
            ),
            "count": row["count"],
        }
        for row in rows
    ]


def _price_facet(queryset):
    buckets = {}
    for key, low, high in PRICE_BUCKETS:
        filters = Q(base_price__gte=low)
        if high is not None:
            filters &= Q(base_price__lt=high)
        buckets[key] = Count("id", filter=filters)
    row = queryset.aggregate(**buckets)
    return [{"value": key, "count": row.get(key, 0)} for key, _low, _high in PRICE_BUCKETS]


def _condition_facet(queryset):
    rows = (
        queryset.filter(attributes_json__condition__isnull=False)
        .values("attributes_json__condition")
        .annotate(count=Count("id"))
        .order_by("-count")[:MAX_ATTRIBUTE_VALUES]
    )
    labels = condition_labels()
    return [
        {
            "value": row["attributes_json__condition"],
            "label": labels.get(
                str(row["attributes_json__condition"]), str(row["attributes_json__condition"])
            ),
            "count": row["count"],
        }
        for row in rows
        if row["attributes_json__condition"] not in (None, "")
    ]


def condition_labels() -> dict[str, str]:
    """``used_good`` → localized label, from whichever category defines it."""
    labels: dict[str, str] = {}
    definitions = AttributeDefinition.objects.filter(key="condition", is_active=True).order_by(
        "category__level"
    )
    for definition in definitions:
        for choice in definition.choices or []:
            value = str(choice.get("value", ""))
            if value and value not in labels:
                labels[value] = localized(
                    choice.get("label_fr", value),
                    choice.get("label_ar", value),
                    choice.get("label_en", ""),
                )
    return labels


def _seller_type_facet(queryset):
    row = queryset.aggregate(
        stores=Count("id", filter=Q(store__isnull=False)),
        individuals=Count("id", filter=Q(store__isnull=True)),
    )
    return [
        {"value": "store", "count": row["stores"]},
        {"value": "individual", "count": row["individuals"]},
    ]


def _verified_facet(queryset):
    predicate = Q(seller__phone_verified_at__isnull=False) | Q(seller__is_verified=True)
    row = queryset.aggregate(
        verified=Count("id", filter=predicate),
        unverified=Count("id", filter=~predicate),
    )
    return [
        {"value": "true", "count": row["verified"]},
        {"value": "false", "count": row["unverified"]},
    ]


def _photos_facet(queryset):
    with_photos = queryset.filter(images__isnull=False).distinct().count()
    without_photos = queryset.filter(images__isnull=True).count()
    return [
        {"value": "true", "count": with_photos},
        {"value": "false", "count": without_photos},
    ]


def _posted_facet(queryset):
    now = timezone.now()
    row = queryset.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(created_at__gte=now - timedelta(days=1))),
        week=Count("id", filter=Q(created_at__gte=now - timedelta(days=7))),
        month=Count("id", filter=Q(created_at__gte=now - timedelta(days=30))),
    )
    return [
        {"value": "today", "count": row["today"]},
        {"value": "7d", "count": max(row["week"] - row["today"], 0)},
        {"value": "30d", "count": max(row["month"] - row["week"], 0)},
        {"value": "older", "count": max(row["total"] - row["month"], 0)},
    ]


def _attribute_facets(scoped, query_params):
    definitions = AttributeDefinition.objects.filter(
        is_active=True,
        filterable=True,
        type__in=(AttributeDefinition.Type.ENUM, AttributeDefinition.Type.BOOLEAN),
    ).select_related("category")
    category_slug = query_params.get("category")
    if category_slug:
        from apps.catalog.models import Category

        category = Category.objects.filter(slug=category_slug, is_active=True).first()
        if category is not None:
            ids = list(category.get_descendants(include_self=True).values_list("id", flat=True))
            # A child's definition overrides its ancestor's for the same key.
            definitions = definitions.filter(category_id__in=ids)

    by_key: dict[str, AttributeDefinition] = {}
    for definition in sorted(definitions, key=lambda d: d.category.level):
        by_key[definition.key] = definition

    results: dict[str, dict] = {}
    for definition in sorted(by_key.values(), key=lambda d: (d.order, d.key)):
        values = _attribute_values(scoped(skip_attr=definition.key), definition.key)
        if not values:
            continue
        results[definition.key] = {
            "label": localized(definition.label_fr, definition.label_ar, definition.label_en),
            "type": definition.type,
            "unit": definition.unit,
            "values": values,
        }
        if len(results) >= MAX_ATTRIBUTE_FACETS:
            break
    return results


def _attribute_values(queryset, key):
    rows = (
        queryset.filter(**{f"attributes_json__{key}__isnull": False})
        .values(f"attributes_json__{key}")
        .annotate(count=Count("id"))
        .order_by("-count")[:MAX_ATTRIBUTE_VALUES]
    )
    choices = {}
    for definition in AttributeDefinition.objects.filter(key=key, is_active=True):
        for choice in definition.choices or []:
            choices.setdefault(str(choice.get("value", "")), choice)

    values = []
    for row in rows:
        raw = row[f"attributes_json__{key}"]
        if isinstance(raw, bool):
            raw = "true" if raw else "false"
        raw = str(raw)
        if raw in ("", "None"):
            continue
        choice = choices.get(raw)
        label = (
            localized(
                choice.get("label_fr", raw),
                choice.get("label_ar", raw),
                choice.get("label_en", ""),
            )
            if choice
            else raw.replace("_", " ").title()
        )
        values.append({"value": raw, "label": label, "count": row["count"]})
    return values
