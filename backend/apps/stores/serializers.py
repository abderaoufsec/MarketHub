from rest_framework import serializers

from apps.catalog.models import Category
from apps.catalog.serializers import CategoryMiniSerializer
from apps.users.serializers import UserSerializer

from .models import Store


class StoreSerializer(serializers.ModelSerializer):
    """Serializer for Store model.

    Phase 12: ``category`` is the nested catalog object (read), ``category_id``
    the write contract (same pattern as the address fields in Phase 11);
    ``category_label`` keeps its name but now reads the category's
    request-language display name instead of the retired choice list.
    """

    owner = UserSerializer(read_only=True)
    product_count = serializers.SerializerMethodField()
    category = CategoryMiniSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        source="category",
        write_only=True,
    )
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
            "category_id",
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
        """Request-language name (fr fallback); legacy rows may have none."""
        return obj.category.display_name if obj.category else ""

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
    """Serializer for creating a store.

    Phase 12: the category is chosen from the catalog tree — ``category_id``
    (the FK), required: a store without a category cannot be browsed or
    filtered. Legacy rows migrated with ``NULL`` stay readable; they are
    re-filed through the update endpoint or the admin.
    """

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        source="category",
        required=True,
    )

    class Meta:
        model = Store
        fields = [
            "store_name",
            "description",
            "category_id",
            "logo_url",
            "banner_image_url",
        ]

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
