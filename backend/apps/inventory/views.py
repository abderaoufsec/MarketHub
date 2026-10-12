"""Inventory endpoints (seller-scoped).

Phase 9: every failure is **raised**, never returned as a hand-built
``{"error": …}`` dict — ``core.exceptions.api_exception_handler`` renders it
as the ``{code, message, details, request_id}`` envelope all ``/api/`` failures
share. Status codes are unchanged; only the body shape moved.
"""

from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.products.models import Product
from apps.users.permissions import IsStoreOwner
from core.exceptions import ApiError
from core.pagination import AuditCursorPagination

from .models import Inventory, InventoryAuditLog
from .serializers import InventoryAuditLogSerializer, InventorySerializer, InventoryUpdateSerializer
from .services import update_inventory


class InventoryListView(generics.ListAPIView):
    """List inventory for seller's products"""

    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return Inventory.objects.none()

        return Inventory.objects.filter(product__store=self.request.user.store).select_related(
            "product"
        )


class InventoryDetailView(generics.RetrieveAPIView):
    """Get inventory details"""

    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return Inventory.objects.none()

        return Inventory.objects.filter(product__store=self.request.user.store)


@extend_schema(request=InventoryUpdateSerializer, responses={200: InventorySerializer})
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStoreOwner])
def update_product_inventory(request, product_id):
    """Update inventory for a product (own store only — ``IsStoreOwner``)."""
    try:
        product = Product.objects.get(id=product_id, store=request.user.store)
    except Product.DoesNotExist:
        # ``from None``: the DoesNotExist is an implementation detail of the
        # lookup, not a cause the client or the error log needs to chain to.
        raise NotFound("Product not found", code="product_not_found") from None

    serializer = InventoryUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Get or create inventory
    attribute_config = request.data.get("attribute_config", {})
    inventory, _created = Inventory.objects.get_or_create(
        product=product, attribute_config=attribute_config, defaults={"stock_quantity": 0}
    )

    try:
        updated_inventory = update_inventory(
            inventory,
            serializer.validated_data["quantity_delta"],
            serializer.validated_data["action_type"],
            serializer.validated_data.get("reason", ""),
        )
    except ValueError as exc:
        # ``update_inventory`` refuses to drive stock below zero and that is
        # the only ValueError it raises, so the code says what went wrong.
        raise ApiError(str(exc), code="insufficient_stock") from exc

    return Response(InventorySerializer(updated_inventory).data, status=status.HTTP_200_OK)


@extend_schema(responses={200: InventorySerializer(many=True)})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def low_stock_items(request):
    """Get products with low stock"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        raise PermissionDenied("Only sellers can access this endpoint", code="seller_required")

    # Get all inventory items for seller's products
    inventory_items = Inventory.objects.filter(product__store=request.user.store).select_related(
        "product"
    )

    # Filter low stock items — in SQL. This used to materialise every
    # inventory row the store had and test ``is_low_stock`` one at a time.
    # The predicate is the one the ``is_low_stock`` property implements:
    # more than zero left, but at or under the product's own threshold.
    low_stock = inventory_items.filter(
        stock_quantity__gt=0, stock_quantity__lte=F("product__low_stock_threshold")
    )

    serializer = InventorySerializer(low_stock, many=True)
    return Response(serializer.data)


class InventoryAuditLogListView(generics.ListAPIView):
    """List inventory audit logs for seller's products

    Keyset-paginated: the log grows with every stock change and is scrolled
    from the newest entry backwards.
    """

    serializer_class = InventoryAuditLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AuditCursorPagination

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return InventoryAuditLog.objects.none()

        queryset = InventoryAuditLog.objects.filter(
            product__store=self.request.user.store
        ).select_related("product", "inventory")

        # Optional filter by product
        product_id = self.request.query_params.get("product_id")
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset
