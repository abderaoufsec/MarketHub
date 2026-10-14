from rest_framework import serializers

from apps.users.serializers import UserSerializer
from core.i18n import choice_label

from .models import Store


class StoreSerializer(serializers.ModelSerializer):
    """Serializer for Store model"""

    owner = UserSerializer(read_only=True)
    product_count = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id",
            "owner",
            "store_name",
            "store_slug",
            "description",
            "category",
            "category_label",
            "logo_url",
            "banner_image_url",
            "is_active",
            "created_at",
            "updated_at",
            "product_count",
        ]
        read_only_fields = ["id", "store_slug", "created_at", "updated_at"]

    def get_category_label(self, obj) -> str:
        return choice_label(Store.CATEGORY_CHOICES, obj.category)

    def get_product_count(self, obj) -> int:
        """The ``product_count`` annotation when the queryset carries one.

        The list and detail views annotate it, so a page of stores counts
        products once instead of once per row; the fallback keeps the
        single-store responses (create, ``my_store``) correct without
        demanding the annotation everywhere.
        """
        annotated = obj.__dict__.get("product_count")
        if annotated is not None:
            return annotated
        try:
            return obj.products.count()
        except Exception:
            # Return 0 if products table doesn't exist yet
            return 0


class StoreCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a store"""

    class Meta:
        model = Store
        fields = ["store_name", "description", "category", "logo_url", "banner_image_url"]

    def validate(self, attrs):
        user = self.context["request"].user

        # Check if user is a seller
        if not user.is_seller:
            raise serializers.ValidationError("Only sellers can create stores")

        # Check if user already has a store
        if hasattr(user, "store"):
            raise serializers.ValidationError("You already have a store")

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["owner"] = user
        return super().create(validated_data)
