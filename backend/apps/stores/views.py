from django.db.models import Avg, Count, Sum
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Store
from .serializers import StoreCreateSerializer, StoreSerializer


class StoreListView(generics.ListAPIView):
    """Public list of all active stores"""

    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    filterset_fields = ["category"]
    search_fields = ["store_name", "description"]
    ordering_fields = ["created_at", "store_name"]


class StoreDetailView(generics.RetrieveAPIView):
    """Public view of a single store"""

    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer
    permission_classes = [AllowAny]
    lookup_field = "store_slug"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_store(request):
    """Create a new store (seller only)"""
    if not request.user.is_seller:
        return Response(
            {"error": "Only sellers can create stores"}, status=status.HTTP_403_FORBIDDEN
        )

    if hasattr(request.user, "store"):
        return Response({"error": "You already have a store"}, status=status.HTTP_400_BAD_REQUEST)

    serializer = StoreCreateSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        store = serializer.save()
        return Response(StoreSerializer(store).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def my_store(request):
    """Get or update seller's own store"""
    if not request.user.is_seller:
        return Response(
            {"error": "Only sellers can access this endpoint"}, status=status.HTTP_403_FORBIDDEN
        )

    if not hasattr(request.user, "store"):
        return Response({"error": "You do not have a store yet"}, status=status.HTTP_404_NOT_FOUND)

    store = request.user.store

    if request.method == "GET":
        serializer = StoreSerializer(store)
        return Response(serializer.data)

    elif request.method == "PUT":
        serializer = StoreSerializer(store, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_stats(request):
    """Get comprehensive store statistics for seller dashboard"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        return Response({"error": "Store not found"}, status=status.HTTP_404_NOT_FOUND)

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_analytics(request):
    """Get detailed analytics data for charts and graphs"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        return Response({"error": "Store not found"}, status=status.HTTP_404_NOT_FOUND)

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
