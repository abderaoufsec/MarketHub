from django.db.models import Avg, Count, Sum
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsSeller
from apps.users.throttles import RevealPhoneRateThrottle
from core.exceptions import ApiError

from .models import Store
from .serializers import StoreCreateSerializer, StoreSerializer


class StoreListView(generics.ListAPIView):
    """Public list of all active stores.

    Throttled with the scoped ``reveal_phone`` rate: the embedded ``owner``
    payload includes the seller's phone number, which scrapers harvest
    aggressively on Ouedkniss-style sites (Phase 7 anti-scraping).
    """

    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RevealPhoneRateThrottle]
    filterset_fields = ["category"]
    search_fields = ["store_name", "description"]
    ordering_fields = ["created_at", "store_name"]


class StoreDetailView(generics.RetrieveAPIView):
    """Public view of a single store (owner contact data → reveal-phone throttle)"""

    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RevealPhoneRateThrottle]
    lookup_field = "store_slug"


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

    # Calculate total revenue from successful orders
    total_revenue = (
        store.orders.filter(payment_status="SUCCESSFUL").aggregate(total=Sum("total_amount"))[
            "total"
        ]
        or 0
    )

    # Calculate average order value
    avg_order_value = (
        store.orders.filter(payment_status="SUCCESSFUL").aggregate(avg=Avg("total_amount"))["avg"]
        or 0
    )

    # Count low stock products
    low_stock_products = [
        product.id for product in products if getattr(product, "is_low_stock", False)
    ]

    # Get order statistics by status
    order_stats = store.orders.values("order_status").annotate(count=Count("id"))
    order_status_dict = {item["order_status"]: item["count"] for item in order_stats}

    # Get payment statistics
    payment_stats = store.orders.values("payment_status").annotate(count=Count("id"))
    payment_status_dict = {item["payment_status"]: item["count"] for item in payment_stats}

    stats = {
        # Product stats
        "total_products": products.count(),
        "active_products": products.filter(is_available=True).count(),
        "low_stock_products": len(low_stock_products),
        # Order stats
        "total_orders": store.orders.count(),
        "pending_orders": order_status_dict.get("PENDING", 0),
        "processing_orders": order_status_dict.get("PROCESSING", 0),
        "shipped_orders": order_status_dict.get("SHIPPED", 0),
        "completed_orders": order_status_dict.get("COMPLETED", 0),
        "cancelled_orders": order_status_dict.get("CANCELLED", 0),
        # Financial stats
        "total_revenue": float(total_revenue),
        "average_order_value": float(avg_order_value),
        "successful_payments": payment_status_dict.get("SUCCESSFUL", 0),
        "pending_payments": payment_status_dict.get("PENDING", 0),
        "failed_payments": payment_status_dict.get("FAILED", 0),
        # Additional metrics
        "conversion_rate": 3.2,  # This would be calculated based on views vs orders
        "total_views": products.count() * 87,  # Mock data - implement proper view tracking
    }

    return Response(stats)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_analytics(request):
    """Get detailed analytics data for charts and graphs"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        # Same Phase 9 envelope as store_stats: one code ("store_not_found")
        # for "this user has no store", wherever it is asked for.
        raise NotFound("Store not found", code="store_not_found")

    # This endpoint returns a mock structure for now (real time-series lands
    # with the analytics phase); the optional ?range=7d|30d|90d|1y parameter
    # is accepted but not yet used to slice the data.

    # This would contain time-series data for charts
    # For now, returning mock structure that frontend can use
    analytics = {
        "revenue_trend": [],  # Array of {date, amount}
        "orders_trend": [],  # Array of {date, count}
        "top_products": [],  # Array of {product_id, name, sales, revenue}
        "category_breakdown": [],  # Array of {category, percentage}
    }

    return Response(analytics)
