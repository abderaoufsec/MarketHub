from rest_framework import serializers

from apps.stores.serializers import StoreSerializer
from apps.users.plans import get_product_quota

from .models import Product, ProductAttribute, ProductImage, ProductReview, Wishlist


def _is_wishlisted(product, request):
    """Read the ``is_wishlisted`` annotation, falling back to one query.

    Every list path annotates it with ``ProductQuerySet.for_user()``; the
    fallback keeps single-instance uses (a detail response, a nested
    serializer built from a plain queryset) correct at the cost of one query
    instead of letting them read a field that is not there.
    """
    annotated = product.__dict__.get("is_wishlisted")
    if annotated is not None:
        return bool(annotated)
    if request is not None and request.user.is_authenticated:
        return Wishlist.objects.filter(user=request.user, product=product).exists()
    return False


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

    def get_user_name(self, obj) -> str:
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

    def get_product_image(self, obj) -> str | None:
        """Primary image, falling back to whatever image comes first.

        Reads ``obj.product.images`` rather than filtering it, so the view's
        ``prefetch_related("product__images")`` actually serves the row —
        ``.filter(...)`` would bypass the cache and query per wishlist line.
        """
        images = list(obj.product.images.all())  # prefetched: no query on the list path
        primary = next((image.image_url for image in images if image.is_primary), None)
        if primary is not None:
            return primary
        return images[0].image_url if images else None


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""

    store = StoreSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    # total_stock / average_rating / review_count / is_wishlisted are read
    # straight off the annotations ProductQuerySet adds; an un-annotated
    # queryset raises rather than silently querying once per row.
    total_stock = serializers.IntegerField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.SerializerMethodField()
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

    def get_is_wishlisted(self, obj) -> bool:
        """Annotation-backed — see :func:`_is_wishlisted`."""
        return _is_wishlisted(obj, self.context.get("request"))

    def get_is_low_stock(self, obj) -> bool:
        """``total_stock`` against this product's own threshold.

        Derived in Python from the annotated total: the threshold is a
        per-row column, so there is no constant to filter on in SQL.
        """
        return obj.total_stock <= obj.low_stock_threshold

    def get_user_review(self, obj) -> dict | None:
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

    def get_primary_image(self, obj) -> str | None:
        """The primary image, read from the prefetched ``images``.

        The old ``obj.images.filter(is_primary=True).first()`` bypassed the
        ``prefetch_related("images")`` cache and ran one query per row.
        The cache is already ordered ``-is_primary, sort_order``, but the
        fallback still has to be explicit: this endpoint returns no image at
        all when a product has none flagged primary.
        """
        return next((image.image_url for image in obj.images.all() if image.is_primary), None)

    def get_is_wishlisted(self, obj) -> bool:
        """Annotation-backed — see :func:`_is_wishlisted`."""
        return _is_wishlisted(obj, self.context.get("request"))


class PaginatedProductListSerializer(serializers.Serializer):
    """``{next, previous, results}`` — the page envelope of FeedCursorPagination.

    ``search_products`` is a ``@api_view``, so there is no view object for
    drf-spectacular to read ``pagination_class`` off; without this the docs
    would advertise a bare array for a body that is actually a page.
    """

    next = serializers.URLField(allow_null=True, read_only=True)
    previous = serializers.URLField(allow_null=True, read_only=True)
    results = ProductListSerializer(many=True, read_only=True)


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
