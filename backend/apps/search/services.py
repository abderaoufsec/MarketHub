"""The search service interface and its Postgres implementation (Phase 15).

``SearchService`` is the seam docs/todo.md asks for: the API talks to an
interface, and ``SEARCH_BACKEND`` names the class. Today there is one
implementation, Postgres full-text + trigram; swapping in Meilisearch or
Typesense later means implementing ``search``/``matching`` and changing one
environment variable, not rewriting the views or the facets contract.

What the service owns:

* parameter validation/canonicalization (so a saved search is a validated,
  replayable query - not arbitrary query-string JSON);
* text matching, filters and one of four orderings;
* facets and the zero-result recovery block (did-you-mean, removable filters,
  nearby wilayas);
* a bounded, deterministic ordering for cursor pagination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from django.conf import settings
from django.db.models import FloatField, IntegerField, Prefetch, Value
from django.db.models.expressions import F
from django.db.models.functions import ACos, Cast, Cos, Least, Power, Radians, Round, Sin, Sqrt
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.products.filters import apply_search_filters
from apps.products.models import Product, ProductImage

from .facets import build_facets
from .normalization import normalize_text
from .suggestions import did_you_mean, nearby_wilayas
from .text import apply_text_search

SORT_CHOICES = ("relevance", "newest", "price_asc", "price_desc", "distance")

#: Params the search endpoint understands. ``cursor``/``page_size`` are the
#: paginator's, not part of a saved query.
FILTER_KEYS = frozenset(
    {
        "q",
        "search",
        "category",
        "wilaya",
        "commune",
        "min_price",
        "max_price",
        "condition",
        "seller_type",
        "verified",
        "with_photos",
        "posted",
        "in_stock",
        "sort",
        "lat",
        "lng",
    }
)
PAGINATION_KEYS = frozenset({"cursor", "page_size"})

#: Filter groups a zero-result relaxation may drop. Attribute filters are
#: handled one key at a time below.
RELAXABLE_GROUPS = (
    ("category", "category"),
    ("location", "wilaya"),
    ("price", "price"),
    ("condition", "condition"),
    ("seller_type", "seller_type"),
    ("verified", "verified"),
    ("photos", "with_photos"),
    ("posted", "posted"),
    ("in_stock", "in_stock"),
)


@dataclass
class SearchResult:
    queryset: object
    facets: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    sort: str = "relevance"
    total: int = 0
    did_you_mean: str = ""
    relaxations: list = field(default_factory=list)
    nearby_wilayas: list = field(default_factory=list)
    used_fuzzy: bool = False
    ordering: list = field(default_factory=list)


class SearchService:
    """Interface every search engine implements."""

    def search(self, query_params, user=None, include_facets=True) -> SearchResult:
        raise NotImplementedError

    def matching(self, queryset, text: str):
        raise NotImplementedError

    def normalize_params(self, query_params) -> dict:
        raise NotImplementedError


class PostgresSearchService(SearchService):
    """Postgres FTS + ``pg_trgm`` over ``Product.search_document``."""

    def search(self, query_params, user=None, include_facets=True) -> SearchResult:
        params = self.normalize_params(query_params)
        base = (
            Product.objects.public()
            .select_related("store", "category", "seller", "wilaya")
            .prefetch_related(
                # Cards walk image -> upload for the URL/LQIP; without the
                # select_related that is another query per image, which turns
                # a 20-row page into 40+ queries (tests/test_query_performance).
                Prefetch("images", queryset=ProductImage.objects.select_related("upload"))
            )
            .with_catalog_stats()
            .for_user(user)
        )

        text_queryset = None
        used_fuzzy = False
        if params.get("q"):
            base, used_fuzzy = apply_text_search(base, params["q"])
            text_queryset = base

        queryset = apply_search_filters(base, params)
        sort = params.get("sort") or ("relevance" if params.get("q") else "newest")
        queryset, ordering = self._apply_ordering(queryset, params, sort)

        total = queryset.count()
        facets = build_facets(params, text_queryset) if include_facets else {}

        result = SearchResult(
            queryset=queryset,
            facets=facets,
            params=params,
            sort=sort,
            total=total,
            used_fuzzy=used_fuzzy,
            ordering=ordering,
        )
        if total == 0:
            result.did_you_mean = did_you_mean(params.get("q", ""))
            result.relaxations = self._relaxations(params, text_queryset)
            result.nearby_wilayas = nearby_wilayas(params, text_queryset)
        return result

    # -- matching (used by the catalogue list and saved-search alerts) -----

    def matching(self, queryset, text: str):
        if not text:
            return queryset
        return apply_text_search(queryset, text)[0]

    # -- parameters --------------------------------------------------------

    def normalize_params(self, query_params) -> dict:
        """Validate and canonicalize a query string for search/saving.

        Unknown keys are ignored (they are not the search contract); unknown
        *attribute* keys still raise, because those are validated against the
        category's definitions by the shared filter pipeline. Values are
        strings: a saved search is a URL, not a typed model.
        """
        raw: dict[str, str] = {}
        for key, value in query_params.items():
            if key in PAGINATION_KEYS or key in ("format",):
                continue
            if key.startswith("attr_") or key in FILTER_KEYS:
                if isinstance(value, (list, tuple)):
                    value = value[-1] if value else ""
                raw[key] = str(value).strip()

        q = raw.pop("q", "")
        legacy = raw.pop("search", "")
        q = q or legacy
        params: dict[str, str] = {}
        if q:
            params["q"] = q
        for key, value in raw.items():
            if value != "":
                params[key] = value

        sort = params.get("sort", "")
        if sort and sort not in SORT_CHOICES:
            raise ValidationError({"sort": _("Unknown sort order.")})
        if sort:
            params["sort"] = sort

        lat, lng = params.get("lat"), params.get("lng")
        if (lat is None) != (lng is None):
            raise ValidationError({"lat": _("Latitude and longitude must be sent together.")})
        if lat is not None:
            for key, value in (("lat", lat), ("lng", lng)):
                try:
                    number = float(value)
                except ValueError:
                    raise ValidationError({key: _("Enter a valid coordinate.")}) from None
                if not isfinite(number) or not -180 <= number <= 180:
                    raise ValidationError({key: _("Enter a valid coordinate.")})
            if not -90 <= float(lat) <= 90:
                raise ValidationError({"lat": _("Enter a valid coordinate.")})
            if sort and sort != "distance":
                # Coordinates without distance sorting have no meaning; don't
                # reject, simply forget them (a saved URL may keep them).
                pass
        elif sort == "distance":
            raise ValidationError({"sort": _("Distance sorting needs latitude and longitude.")})

        # Run the shared pipeline on an empty set: this validates attribute
        # keys, booleans, prices and the category without returning rows.
        apply_search_filters(Product.objects.public().none(), params)
        return params

    # -- ordering ----------------------------------------------------------

    def _apply_ordering(self, queryset, params, sort):
        if sort == "distance":
            lat, lng = float(params["lat"]), float(params["lng"])
            queryset = queryset.filter(
                wilaya__latitude__isnull=False, wilaya__longitude__isnull=False
            )
            distance = _distance_metres(lat, lng)
            queryset = queryset.annotate(distance_m=Round(distance))
            return queryset, ["distance_m", "-created_at", "-id"]
        if sort == "price_asc":
            return queryset, ["base_price", "-id"]
        if sort == "price_desc":
            return queryset, ["-base_price", "-id"]
        if sort == "relevance" and "search_rank" in queryset.query.annotations:
            relevance = Round((F("search_rank") + F("fuzzy_score")) * 1_000_000)
            queryset = queryset.annotate(relevance_score=relevance)
            return queryset, ["-relevance_score", "-created_at", "-id"]
        return queryset, ["-created_at", "-id"]

    # -- zero-result recovery ---------------------------------------------

    def _relaxations(self, params, text_queryset):
        """Which single filter could be dropped to get results, and how many.

        Only computed when the page is empty: it runs one COUNT per active
        filter, which is fine on a dead end and wasteful on every search.
        """
        base = Product.objects.public()
        if text_queryset is not None:
            base = base.filter(pk__in=text_queryset.values("pk"))

        suggestions = []
        if params.get("q"):
            without_text = apply_search_filters(Product.objects.public(), params)
            count = without_text.count()
            if count:
                suggestions.append({"param": "q", "value": params["q"], "count": count})

        for group, param in RELAXABLE_GROUPS:
            if not _has_filter(params, group, param):
                continue
            count = apply_search_filters(base, params, skip=(group,)).count()
            if count:
                suggestions.append(
                    {
                        "param": param,
                        "value": params.get(param, ""),
                        "count": count,
                    }
                )

        for param in params:
            if not param.startswith("attr_"):
                continue
            body = param[len("attr_") :]
            for suffix in ("_min", "_max"):
                if body.endswith(suffix):
                    body = body[: -len(suffix)]
                    break
            count = apply_search_filters(base, params, skip_attr=body).count()
            if count and not any(item["param"] == param for item in suggestions):
                suggestions.append({"param": param, "value": params.get(param, ""), "count": count})
        return suggestions


def _has_filter(params, group, param):
    if group == "location":
        return "wilaya" in params or "commune" in params
    if group == "price":
        return "min_price" in params or "max_price" in params
    if group == "photos":
        return "with_photos" in params
    return param in params


def _distance_metres(latitude, longitude):
    """Haversine distance from a point to the listing's wilaya centroid.

    A wilaya centroid is not a street address, but it is exactly the
    granularity a classified has before Phase 16's chat; 6 371 km is the
    mean Earth radius. The annotation is rounded to whole metres so a cursor
    carries an integer, not a float with platform-dependent formatting.
    """
    lat = Radians(Value(latitude, output_field=FloatField()))
    lng = Radians(Value(longitude, output_field=FloatField()))
    row_lat = Radians(Cast("wilaya__latitude", FloatField()))
    row_lng = Radians(Cast("wilaya__longitude", FloatField()))
    haversine = Power(Sin((row_lat - lat) / 2), 2) + Cos(lat) * Cos(row_lat) * Power(
        Sin((row_lng - lng) / 2), 2
    )
    distance = 2 * 6_371_000 * ACos(Sqrt(1 - Least(haversine, Value(1.0))))
    return Cast(distance, IntegerField())


def get_search_service() -> SearchService:
    """Instantiate the class named by ``SEARCH_BACKEND``."""
    path = getattr(settings, "SEARCH_BACKEND", "apps.search.services.PostgresSearchService")
    return import_string(path)()


def record_search(request, result: SearchResult) -> None:
    """Persist one first-page search for suggestions and the synonym backlog."""
    from .models import SearchQuery

    if request.query_params.get("cursor") or not result.params:
        return
    query = (result.params.get("q") or "")[:200]
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    filters = {key: value for key, value in result.params.items() if key != "q"}
    SearchQuery.objects.create(
        user=user,
        query=query,
        normalized=normalize_text(query)[:200],
        filters=filters,
        result_count=result.total,
        zero_results=result.total == 0,
        locale=(getattr(request, "LANGUAGE_CODE", "") or "")[:8],
    )
