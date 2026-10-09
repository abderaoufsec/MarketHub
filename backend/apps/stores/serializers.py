from rest_framework import serializers
from .models import Store
from apps.users.serializers import UserSerializer


class StoreSerializer(serializers.ModelSerializer):
    """Serializer for Store model"""
    owner = UserSerializer(read_only=True)
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Store
        fields = ['id', 'owner', 'store_name', 'store_slug', 'description', 
                  'category', 'logo_url', 'banner_image_url', 'is_active', 
                  'created_at', 'updated_at', 'product_count']
        read_only_fields = ['id', 'store_slug', 'created_at', 'updated_at']
    
    def get_product_count(self, obj):
        """Safely get product count"""
        try:
            return obj.products.count()
        except Exception:
            # Return 0 if products table doesn't exist yet
            return 0


class StoreCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a store"""
    
    class Meta:
        model = Store
        fields = ['store_name', 'description', 'category', 'logo_url', 'banner_image_url']
    
    def validate(self, attrs):
        user = self.context['request'].user
        
        # Check if user is a seller
        if not user.is_seller:
            raise serializers.ValidationError("Only sellers can create stores")
        
        # Check if user already has a store
        if hasattr(user, 'store'):
            raise serializers.ValidationError("You already have a store")
        
        return attrs
    
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['owner'] = user
        return super().create(validated_data)
