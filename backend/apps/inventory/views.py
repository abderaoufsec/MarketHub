from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.products.models import Product

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_product_inventory(request, product_id):
    """Update inventory for a product"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        return Response(
            {"error": "Only sellers can update inventory"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        product = Product.objects.get(id=product_id, store=request.user.store)
    except Product.DoesNotExist:
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = InventoryUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

        return Response(InventorySerializer(updated_inventory).data, status=status.HTTP_200_OK)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def low_stock_items(request):
    """Get products with low stock"""
    if not request.user.is_seller or not hasattr(request.user, "store"):
        return Response(
            {"error": "Only sellers can access this endpoint"}, status=status.HTTP_403_FORBIDDEN
        )

    # Get all inventory items for seller's products
    inventory_items = Inventory.objects.filter(product__store=request.user.store).select_related(
        "product"
    )

    # Filter low stock items
    low_stock = [item for item in inventory_items if item.is_low_stock]

    serializer = InventorySerializer(low_stock, many=True)
    return Response(serializer.data)


class InventoryAuditLogListView(generics.ListAPIView):
    """List inventory audit logs for seller's products"""

    serializer_class = InventoryAuditLogSerializer
    permission_classes = [IsAuthenticated]

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
