"""Search API views (Phase 15 of docs/todo.md).

``GET /search/`` is the one advanced endpoint: text, filters, facets, sorts,
cursor pagination and zero-result recovery in a single round trip. The
suggestion/recent/saved-search endpoints are separate on purpose - autocomplete
must stay cheap and must never write an analytics row per keystroke.
"""

from __future__ import annotations

from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Category
from apps.products.models import Product, ProductImage
from core.pagination import FeedCursorPagination

from .models import SavedSearch, SearchQuery
from .normalization import normalize_text
from .serializers import (
    SavedSearchSerializer,
    SearchPageSerializer,
    SearchQuerySerializer,
    SearchResultSerializer,
    SuggestionProductSerializer,
)
from .services import get_search_service, record_search
from .suggestions import did_you_mean, term_suggestions


class SearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: SearchPageSerializer})
    def get(self, request):
        result = get_search_service().search(request.query_params, user=request.user)
        paginator = FeedCursorPagination()
        paginator.ordering = result.ordering
        page = paginator.paginate_queryset(result.queryset, request)
        serializer = SearchResultSerializer(page, many=True, context={"request": request})
        payload = paginator.get_paginated_response(serializer.data).data
        payload["facets"] = result.facets
        payload["meta"] = {
            "total": result.total,
            "sort": result.sort,
            "q": result.params.get("q", ""),
            "did_you_mean": result.did_you_mean,
            "relaxations": result.relaxations,
            "nearby_wilayas": result.nearby_wilayas,
            "used_fuzzy": result.used_fuzzy,
            "filters": result.params,
        }
        record_search(request, result)
        return Response(payload)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([AllowAny])
def suggestions(request):
    """Autocomplete: recent/popular queries, categories, and top products.

    A single request returns everything the dropdown needs so typing does not
    fan out into three round trips. ``q`` under two characters is an empty
    response, not an expensive query.
    """
    text = (request.query_params.get("q") or "").strip()[:100]
    if len(text) < 2:
        return Response(
            {
                "query": text,
                "terms": [],
                "products": [],
                "categories": [],
                "did_you_mean": "",
            }
        )

    service = get_search_service()
    normalized = normalize_text(text)
    products = service.matching(
        Product.objects.public()
        .select_related("category")
        .prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.select_related("upload"))
        )
        .with_catalog_stats(),
        text,
    )
    # Autocomplete is often a *prefix* of a word ("iph", "sams"), which FTS
    # deliberately does not match. Fall back to a substring on the normalized
    # document (served by the trigram index) when the full matcher is empty.
    if not products.exists():
        products = Product.objects.public().filter(search_document__contains=normalized)
    if "search_rank" in products.query.annotations:
        products = products.order_by("-search_rank", "-fuzzy_score", "-created_at")
    else:
        products = products.order_by("-created_at")
    products = products[:5]
    product_payload = []
    for product in products:
        images = list(product.images.all())
        product_payload.append(
            {
                "id": product.pk,
                "name": product.name,
                "canonical_path": product.canonical_path,
                "primary_image": images[0].display_url if images else None,
                "category": product.category.display_name if product.category else None,
            }
        )

    category_payload = []
    for category in Category.objects.filter(is_active=True).order_by("level", "order"):
        haystack = normalize_text(
            " ".join(
                part
                for part in (
                    category.name_fr,
                    category.name_ar,
                    category.name_en,
                    category.slug,
                )
                if part
            )
        )
        if normalized and normalized in haystack:
            category_payload.append(
                {
                    "id": category.pk,
                    "slug": category.slug,
                    "name": category.display_name,
                }
            )
        if len(category_payload) >= 5:
            break

    return Response(
        {
            "query": text,
            "terms": term_suggestions(text, request.user),
            "products": SuggestionProductSerializer(product_payload, many=True).data,
            "categories": category_payload,
            "did_you_mean": did_you_mean(text),
        }
    )


class RecentSearchesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SearchQuerySerializer(many=True)})
    def get(self, request):
        rows = (
            SearchQuery.objects.filter(user=request.user)
            .exclude(normalized="")
            .order_by("-created_at")[:50]
        )
        seen = set()
        payload = []
        for row in rows:
            if row.normalized in seen:
                continue
            seen.add(row.normalized)
            payload.append(row)
            if len(payload) >= 10:
                break
        return Response(SearchQuerySerializer(payload, many=True).data)

    def delete(self, request):
        SearchQuery.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedSearchListCreateView(generics.ListCreateAPIView):
    serializer_class = SavedSearchSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return SavedSearch.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SavedSearchDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SavedSearchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedSearch.objects.filter(user=self.request.user)
