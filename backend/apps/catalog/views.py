from django.db.models import Count, OuterRef, Q, Subquery
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Category
from .serializers import CategorySerializer


class CategoryTreeView(generics.ListAPIView):
    """Public category tree with attribute definitions (Phase 12).

    ``GET /api/v1/catalog/categories/``. Unpaginated on purpose, like the
    wilayas: a curated tree of tens of nodes that the SPA fetches once per
    locale and keeps in memory. Only active roots are listed; the serializer
    drops inactive children recursively.

    ``product_count`` covers the whole subtree ("Vehicles" shows what "Cars"
    holds too) — one correlated subquery per root row, so the endpoint stays
    two queries regardless of tree depth, per the Phase 10 budget discipline.
    """

    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        # Products of every category inside the outer row's mptt span
        # (same tree, lft/rght nested within), counted in ONE group: the
        # `.values("tree_id")` is what makes it one row — an annotate() on
        # the bare model queryset groups by that row's pk, which would hand
        # LIMIT 1 a single node's count instead of the subtree total.
        subtree_counts = (
            Category.objects.filter(
                tree_id=OuterRef("tree_id"),
                lft__gte=OuterRef("lft"),
                rght__lte=OuterRef("rght"),
            )
            .order_by()
            .values("tree_id")
            .annotate(total=Count("products", filter=Q(products__is_available=True)))
            .values("total")[:1]
        )
        return (
            Category.objects.filter(parent__isnull=True, is_active=True)
            .annotate(descendant_product_count=Subquery(subtree_counts))
            .prefetch_related("children", "attribute_definitions")
            .order_by("order", "slug")
        )
