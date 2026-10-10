from rest_framework import serializers

from apps.stores.serializers import StoreSerializer
from apps.users.plans import get_product_quota

from .models import Product, ProductAttribute, ProductImage, ProductReview, Wishlist


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for ProductImage model"""

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "is_primary", "sort_order"]


class ProductAttributeSerializer(serializers.ModelSerializer):
    """Serializer for ProductAttribute model"""

    class Meta:
        model = ProductAttribute
        fields = ["id", "attribute_name", "attribute_value", "sku"]


class ProductReviewSerializer(serializers.ModelSerializer):
    """Serializer for ProductReview model"""

    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "product",
            "user",
            "user_email",
            "user_name",
            "rating",
            "comment",
            "is_approved",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "user_email", "user_name", "created_at", "updated_at"]

    def get_user_name(self, obj):
        """Get user's display name"""
        if obj.user.first_name and obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return obj.user.email.split("@")[0]


class ProductReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating product reviews"""

    class Meta:
        model = ProductReview
        fields = ["product", "rating", "comment"]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

    def validate(self, data):
        # Check if user already reviewed this product
        request = self.context.get("request")
        if request and request.user:
            existing = ProductReview.objects.filter(
                product=data["product"], user=request.user
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    "You have already reviewed this product. Please update your existing review."
                )
        return data

    def create(self, validated_data):
        # Automatically set the user from request
        request = self.context.get("request")
        validated_data["user"] = request.user
        return super().create(validated_data)


class WishlistSerializer(serializers.ModelSerializer):
    """Serializer for Wishlist model"""

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(
        source="product.base_price", max_digits=10, decimal_places=2, read_only=True
    )
    product_image = serializers.SerializerMethodField()
    product_available = serializers.BooleanField(source="product.is_available", read_only=True)

    class Meta:
        model = Wishlist
        fields = [
            "id",
            "product",
            "product_name",
            "product_price",
            "product_image",
            "product_available",
            "added_at",
        ]
        read_only_fields = ["id", "added_at"]

    def get_product_image(self, obj):
        """Get primary product image"""
        primary = obj.product.images.filter(is_primary=True).first()
        if primary:
            return primary.image_url
        first_image = obj.product.images.first()
        return first_image.image_url if first_image else None


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""

    store = StoreSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    total_stock = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    reviews = ProductReviewSerializer(many=True, read_only=True)
    is_wishlisted = serializers.SerializerMethodField()
    user_review = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "store",
            "name",
            "description",
            "base_price",
            "category",
            "is_available",
            "low_stock_threshold",
            "attributes_json",
            "created_at",
            "updated_at",
            "images",
            "attributes",
            "total_stock",
            "is_low_stock",
            "average_rating",
            "review_count",
            "reviews",
            "is_wishlisted",
            "user_review",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_is_wishlisted(self, obj):
        """Check if current user has wishlisted this product"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return Wishlist.objects.filter(user=request.user, product=obj).exists()
        return False

    def get_user_review(self, obj):
        """Get current user's review for this product"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            review = ProductReview.objects.filter(user=request.user, product=obj).first()
            if review:
                return ProductReviewSerializer(review).data
        return None


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings"""

    store_name = serializers.CharField(source="store.store_name", read_only=True)
    store_slug = serializers.CharField(source="store.store_slug", read_only=True)
    primary_image = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    is_wishlisted = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "base_price",
            "category",
            "is_available",
            "store_name",
            "store_slug",
            "primary_image",
            "total_stock",
            "created_at",
            "average_rating",
            "review_count",
            "is_wishlisted",
        ]

    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first()
        return primary.image_url if primary else None

    def get_is_wishlisted(self, obj):
        """Check if current user has wishlisted this product"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return Wishlist.objects.filter(user=request.user, product=obj).exists()
        return False


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products"""

    images = ProductImageSerializer(many=True, required=False)
    attributes = ProductAttributeSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "base_price",
            "category",
            "is_available",
            "low_stock_threshold",
            "attributes_json",
            "images",
            "attributes",
        ]

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        attributes_data = validated_data.pop("attributes", [])

        # Get the store from the request user
        user = self.context["request"].user
        if not hasattr(user, "store"):
            raise serializers.ValidationError("You must have a store to create products")

        # Plan-based listing quota (free plan now; real plans in Phase 21)
        quota = get_product_quota(user)
        if quota is not None and user.store.products.count() >= quota:
            raise serializers.ValidationError(
                f"You have reached the maximum limit of {quota} products for your plan"
            )

        validated_data["store"] = user.store
        product = Product.objects.create(**validated_data)

        # Create images
        for image_data in images_data:
            ProductImage.objects.create(product=product, **image_data)

        # Create attributes
        for attr_data in attributes_data:
            ProductAttribute.objects.create(product=product, **attr_data)

        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        attributes_data = validated_data.pop("attributes", None)

        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update images if provided
        if images_data is not None:
            instance.images.all().delete()
            for image_data in images_data:
                ProductImage.objects.create(product=instance, **image_data)

        # Update attributes if provided
        if attributes_data is not None:
            instance.attributes.all().delete()
            for attr_data in attributes_data:
                ProductAttribute.objects.create(product=instance, **attr_data)

        return instance
