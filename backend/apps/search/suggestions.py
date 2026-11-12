"""Suggestions, did-you-mean and nearby-wilaya recovery (Phase 15).

Autocomplete is built from three sources, in this order:

1. what this user searched for recently (their own words are the best
   prediction of the next query);
2. what everybody searched for in the last 30 days (the site's vocabulary);
3. the catalogue's own vocabulary - category names, attribute labels, enum
   choices and the synonym table - so a first-time visitor still gets useful
   completions.

``did_you_mean`` is a small ``difflib`` pass over that same vocabulary. It is
not trying to be a spell checker; it only has to rescue a zero-result page
("samsug" → "samsung") with a correction the user can click.
"""

from __future__ import annotations

from datetime import timedelta
from difflib import get_close_matches

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import get_language

from apps.catalog.models import AttributeDefinition, Category
from apps.geography.models import Wilaya
from apps.products.filters import apply_search_filters
from apps.products.models import Product

from .models import SearchQuery
from .normalization import normalize_text, tokenize
from .synonyms import VOCABULARY

VOCABULARY_CACHE_KEY = "search:did_you_mean:vocabulary"
VOCABULARY_CACHE_SECONDS = 300
MAX_TERMS = 8


def vocabulary_tokens() -> list[str]:
    """Normalized single tokens the catalogue itself contains."""
    cached = cache.get(VOCABULARY_CACHE_KEY)
    if cached is not None:
        return cached

    words: set[str] = set(VOCABULARY)
    for category in Category.objects.filter(is_active=True).values("name_fr", "name_ar", "name_en"):
        for name in category.values():
            words.update(tokenize(name or ""))
    for definition in AttributeDefinition.objects.filter(is_active=True).values(
        "key", "label_fr", "label_ar", "label_en", "choices"
    ):
        words.update(tokenize(definition["key"].replace("_", " ")))
        for name in (definition["label_fr"], definition["label_ar"], definition["label_en"]):
            words.update(tokenize(name or ""))
        for choice in definition["choices"] or []:
            for name in (
                choice.get("label_fr", ""),
                choice.get("label_ar", ""),
                choice.get("label_en", ""),
                choice.get("value", ""),
            ):
                words.update(tokenize(name or ""))

    tokens = sorted(word for word in words if len(word) >= 3)
    cache.set(VOCABULARY_CACHE_KEY, tokens, VOCABULARY_CACHE_SECONDS)
    return tokens


def did_you_mean(text: str) -> str:
    """Best single-token correction for ``text`` ("" when nothing is close)."""
    tokens = tokenize(text)
    vocabulary = vocabulary_tokens()
    if not tokens or not vocabulary:
        return ""
    corrected = list(tokens)
    changed = False
    for index, token in enumerate(tokens):
        if len(token) < 4:
            continue
        matches = get_close_matches(token, vocabulary, n=1, cutoff=0.72)
        if matches and matches[0] != token:
            corrected[index] = matches[0]
            changed = True
            break
    return " ".join(corrected) if changed else ""


def term_suggestions(text: str, user=None, limit: int = MAX_TERMS) -> list[str]:
    """Recent + popular + vocabulary completions, de-duplicated.

    Returns *display* strings (a recent query keeps the way its author wrote
    it); matching is done on the normalized form.
    """
    prefix = normalize_text(text)
    if len(prefix) < 2:
        return []
    seen: dict[str, str] = {}

    def add(display: str, normalized: str):
        if not normalized or normalized in seen:
            return
        if normalized.startswith(prefix) or prefix in normalized:
            seen[normalized] = display

    if user is not None and getattr(user, "is_authenticated", False):
        recent = (
            SearchQuery.objects.filter(user=user)
            .exclude(normalized="")
            .order_by("-created_at")
            .values_list("query", "normalized")[:40]
        )
        for display, normalized in recent:
            add(display or normalized, normalized)

    since = timezone.now() - timedelta(days=30)
    popular = (
        SearchQuery.objects.filter(created_at__gte=since)
        .exclude(normalized="")
        .values("normalized")
        .annotate(hits=Count("id"))
        .order_by("-hits")[:100]
    )
    for row in popular:
        add(row["normalized"], row["normalized"])

    for term in VOCABULARY:
        add(term, term)

    ordered = sorted(seen.items(), key=lambda item: (not item[0].startswith(prefix), item[0]))
    return [display for _normalized, display in ordered[:limit]]


def nearby_wilayas(params, text_queryset=None, limit: int = 3) -> list[dict]:
    """The closest wilayas that *do* have matches, when a filter found none.

    "Nearby" is the geodesic distance between wilaya centroids - the same
    approximation distance sorting uses. Counts are computed with the failing
    location filter removed, so every suggestion is actionable.
    """
    raw_id = params.get("wilaya")
    if not raw_id or not str(raw_id).isdigit():
        return []
    origin = (
        Wilaya.objects.filter(pk=int(raw_id), is_active=True)
        .only("id", "latitude", "longitude")
        .first()
    )
    if origin is None or origin.latitude is None or origin.longitude is None:
        return []

    base = Product.objects.public()
    if text_queryset is not None:
        base = base.filter(pk__in=text_queryset.values("pk"))
    without_location = {
        key: value for key, value in params.items() if key not in ("wilaya", "commune")
    }
    base = apply_search_filters(base, without_location)

    counts = {
        row["wilaya_id"]: row["count"]
        for row in base.filter(wilaya_id__isnull=False)
        .values("wilaya_id")
        .annotate(count=Count("id"))
    }
    if not counts:
        return []

    rows = []
    origin_lat = float(origin.latitude)
    origin_lng = float(origin.longitude)
    for wilaya in Wilaya.objects.filter(pk__in=counts, is_active=True):
        if wilaya.latitude is None or wilaya.longitude is None:
            continue
        rows.append(
            {
                "value": str(wilaya.pk),
                "label": _display_name(wilaya),
                "count": counts[wilaya.pk],
                "distance_km": round(
                    _haversine(
                        origin_lat, origin_lng, float(wilaya.latitude), float(wilaya.longitude)
                    ),
                    1,
                ),
            }
        )
    rows.sort(key=lambda row: row["distance_km"])
    return rows[:limit]


def _display_name(wilaya: Wilaya) -> str:
    language = (get_language() or "fr").split("-")[0]
    if language == "ar":
        return wilaya.name_ar
    if language == "en":
        return wilaya.name_en or wilaya.name_fr
    return wilaya.name_fr


def _haversine(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * 6371 * asin(sqrt(min(a, 1.0)))
