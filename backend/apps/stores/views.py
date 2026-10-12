from django.db.models import Avg, Count, F, Q, Sum
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.orders.models import OrderItem
from apps.users.permissions import IsSeller
from apps.users.throttles import RevealPhoneRateThrottle
from core.exceptions import ApiError
from core.pagination import FeedCursorPagination

from .models import Store
from .serializers import StoreCreateSerializer, StoreSerializer


def _stores_with_product_counts():
    """Stores with their owner and their product count in the same query.

    The embedded ``owner`` payload and the per-row product count were each
    their own query, so a page of stores cost two queries per row.
    """
    return (
        Store.objects.filter(is_active=True)
        .select_related("owner")
        .annotate(product_count=Count("products", distinct=True))
    )


class StoreListView(generics.ListAPIView):
    """Public list of all active stores.

    Throttled with the scoped ``reveal_phone`` rate: the embedded ``owner``
    payload includes the seller's phone number, which scrapers harvest
    aggressively on Ouedkniss-style sites (Phase 7 anti-scraping).
    """

    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RevealPhoneRateThrottle]
    filterset_fields = ["category"]
    search_fields = ["store_name", "description"]
    ordering_fields = ["created_at", "store_name"]
    ordering = ["-created_at"]
    pagination_class = FeedCursorPagination

    def get_queryset(self):
        return _stores_with_product_counts()


class StoreDetailView(generics.RetrieveAPIView):
    """Public view of a single store (owner contact data → reveal-phone throttle)"""

    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RevealPhoneRateThrottle]
    lookup_field = "store_slug"

    def get_queryset(self):
        return _stores_with_product_counts()


@extend_schema(request=StoreCreateSerializer, responses={201: StoreSerializer})
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSeller])
def create_store(request):
    """Create a new store (seller only — enforced by ``IsSeller``).

    Phase 9 note: deliberately *not* mixed with ``IdempotentPostMixin`` the way
    the seller listing-create view is. A retried create can never publish a
    second store — the guard below rejects it and ``Store.owner`` is a
    ``OneToOneField``, so the database refuses a duplicate as well — which is
    exactly the harm the mixin exists to prevent for listings. Turning this
    function view into a class just to replay the first 201 instead of the
    already-safe 400 would be a larger change than the guarantee needs; a
    client that lost the response can confirm success with ``my_store``.
    """
    if hasattr(request.user, "store"):
        # Phase 9: raised, not hand-built, so the 400 is the standard envelope
        # ({"code": "store_exists", …}).
        raise ApiError("You already have a store", code="store_exists")

    serializer = StoreCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    store = serializer.save()
    return Response(StoreSerializer(store).data, status=status.HTTP_201_CREATED)


@extend_schema(request=StoreSerializer, responses={200: StoreSerializer})
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, IsSeller])
def my_store(request):
    """Get or update seller's own store"""
    if not hasattr(request.user, "store"):
        # Phase 9: raised so the 404 is the standard envelope
        # ({"code": "store_not_found", …}) rather than {"error": …}.
        raise NotFound("You do not have a store yet", code="store_not_found")

    store = request.user.store

    if request.method == "GET":
        serializer = StoreSerializer(store)
        return Response(serializer.data)

    elif request.method == "PUT":
        # raise_exception keeps the 200 body untouched and lets the shared
        # exception handler render any field errors as the Phase 9 envelope.
        serializer = StoreSerializer(store, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_stats(request):
    """Get comprehensive store statistics for seller dashboard"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        # Phase 9: raised so the 404 is the standard envelope with a
        # branchable code, instead of {"error": "Store not found"}.
        raise NotFound("Store not found", code="store_not_found")

    store = request.user.store

    # Get all products for this store
    products = store.products.all()

    # One aggregate per pair of metrics instead of one per metric: revenue
    # and average order value read the same rows, and so do the two product
    # counts.
    financials = store.orders.filter(payment_status="SUCCESSFUL").aggregate(
        total=Sum("total_amount"), avg=Avg("total_amount")
    )
    product_counts = products.aggregate(
        total=Count("id"), active=Count("id", filter=Q(is_available=True))
    )

    # Low stock, counted in SQL. This used to be a Python loop over every
    # product in the store, and each iteration ran its own SUM of inventory.
    low_stock_products = (
        products.with_stock().filter(total_stock__lte=F("low_stock_threshold")).count()
    )

    # Get order statistics by status
    order_stats = store.orders.values("order_status").annotate(count=Count("id"))
    order_status_dict = {item["order_status"]: item["count"] for item in order_stats}

    # Get payment statistics
    payment_stats = store.orders.values("payment_status").annotate(count=Count("id"))
    payment_status_dict = {item["payment_status"]: item["count"] for item in payment_stats}

    stats = {
        # Product stats
        "total_products": product_counts["total"],
        "active_products": product_counts["active"],
        "low_stock_products": low_stock_products,
        # Order stats
        "total_orders": store.orders.count(),
        "pending_orders": order_status_dict.get("PENDING", 0),
        "processing_orders": order_status_dict.get("PROCESSING", 0),
        "shipped_orders": order_status_dict.get("SHIPPED", 0),
        "completed_orders": order_status_dict.get("COMPLETED", 0),
        "cancelled_orders": order_status_dict.get("CANCELLED", 0),
        # Financial stats
        "total_revenue": float(financials["total"] or 0),
        "average_order_value": float(financials["avg"] or 0),
        "successful_payments": payment_status_dict.get("SUCCESSFUL", 0),
        "pending_payments": payment_status_dict.get("PENDING", 0),
        "failed_payments": payment_status_dict.get("FAILED", 0),
        # Additional metrics
        "conversion_rate": 3.2,  # This would be calculated based on views vs orders
        "total_views": product_counts["total"] * 87,  # Mock data - implement proper view tracking
    }

    return Response(stats)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_analytics(request):
    """Get detailed analytics data for charts and graphs

    Previously defined but never routed, so it could not be reached at all
    (docs/todo.md Phase 10). The two series a dashboard can draw today are
    computed from real rows; the two time-series stay empty until the
    analytics phase ships view tracking and order history bucketing — an
    empty array is a fact, a fabricated one is a lie with a date on it.
    """
    if not request.user.is_seller or not hasattr(request.user, "store"):
        # Same Phase 9 envelope as store_stats: one code ("store_not_found")
        # for "this user has no store", wherever it is asked for.
        raise NotFound("You do not have a store yet", code="store_not_found")

    store = request.user.store

    # Units sold and revenue per product, from the paid order lines only.
    sales_by_product = (
        OrderItem.objects.filter(order__store=store, order__payment_status="SUCCESSFUL")
        .values("product_id", "product__name")
        .annotate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price_at_purchase")))
        .order_by("-units")[:5]
    )
    top_products = [
        {
            "product_id": row["product_id"],
            "name": row["product__name"],
            "sales": row["units"],
            "revenue": float(row["revenue"] or 0),
        }
        for row in sales_by_product
    ]

    category_totals = list(
        store.products.values("category").annotate(products=Count("id")).order_by("-products")
    )
    grand_total = sum(row["products"] for row in category_totals)
    category_breakdown = [
        {
            "category": row["category"],
            "percentage": round(row["products"] * 100 / grand_total, 1),
        }
        for row in category_totals
    ]

    analytics = {
        "revenue_trend": [],  # Array of {date, amount} — analytics phase
        "orders_trend": [],  # Array of {date, count} — analytics phase
        "top_products": top_products,
        "category_breakdown": category_breakdown,
    }

    return Response(analytics)
