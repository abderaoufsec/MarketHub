from rest_framework import serializers
from .models import Inventory, InventoryAuditLog
from apps.products.serializers import ProductSerializer


class InventorySerializer(serializers.ModelSerializer):
    """Serializer for Inventory model"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Inventory
        fields = ['id', 'product', 'product_name', 'attribute_config', 
                  'stock_quantity', 'is_in_stock', 'is_low_stock',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InventoryAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for InventoryAuditLog model"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = InventoryAuditLog
        fields = ['id', 'product', 'product_name', 'inventory', 'quantity_delta',
                  'action_type', 'reason', 'previous_quantity', 'new_quantity',
                  'timestamp']
        read_only_fields = ['id', 'timestamp']


class InventoryUpdateSerializer(serializers.Serializer):
    """Serializer for updating inventory"""
    quantity_delta = serializers.IntegerField()
    action_type = serializers.ChoiceField(choices=InventoryAuditLog.ACTION_CHOICES)
    reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate_quantity_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity delta cannot be zero")
        return value
