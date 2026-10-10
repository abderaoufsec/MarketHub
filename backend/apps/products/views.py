from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Product, ProductReview, Wishlist
from .serializers import (
    ProductCreateUpdateSerializer,
    ProductListSerializer,
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    ProductSerializer,
    WishlistSerializer,
)


class ProductListView(generics.ListAPIView):
    """Public list of all available products with search and filter"""

    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "is_available", "store__category"]
    search_fields = ["name", "description", "category"]
    ordering_fields = ["created_at", "base_price", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = (
            Product.objects.filter(is_available=True, store__is_active=True)
            .select_related("store")
            .prefetch_related("images")
        )

        # Custom price range filter
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")

        if min_price:
            queryset = queryset.filter(base_price__gte=min_price)
        if max_price:
            queryset = queryset.filter(base_price__lte=max_price)

        return queryset


class ProductDetailView(generics.RetrieveAPIView):
    """Public view of a single product with reviews"""

    queryset = Product.objects.filter(is_available=True, store__is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("store")
            .prefetch_related("images", "attributes", "reviews__user")
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def featured_products(request):
    """Get featured/recent products"""
    products = (
        Product.objects.filter(is_available=True, store__is_active=True)
        .select_related("store")
        .prefetch_related("images")
        .order_by("-created_at")[:12]
    )

    serializer = ProductListSerializer(products, many=True, context={"request": request})
    return Response(serializer.data)


class SellerProductListView(generics.ListAPIView):
    """List products for the authenticated seller"""

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return Product.objects.none()

        return Product.objects.filter(store=self.request.user.store).prefetch_related(
            "images", "attributes", "inventory"
        )


class SellerProductCreateView(generics.CreateAPIView):
    """Create a new product (seller only)"""

    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        if not self.request.user.is_seller:
            raise permissions.PermissionDenied("Only sellers can create products")

        if not hasattr(self.request.user, "store"):
            raise permissions.PermissionDenied("You must have a store to create products")

        serializer.save()


class SellerProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a product (seller only)"""

    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_seller or not hasattr(self.request.user, "store"):
            return Product.objects.none()

        return Product.objects.filter(store=self.request.user.store)

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductSerializer
        return ProductCreateUpdateSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def search_products(request):
    """Advanced product search"""
    query = request.query_params.get("q", "")
    category = request.query_params.get("category")
    min_price = request.query_params.get("min_price")
    max_price = request.query_params.get("max_price")
    in_stock = request.query_params.get("in_stock") == "true"

    products = (
        Product.objects.filter(is_available=True, store__is_active=True)
        .select_related("store")
        .prefetch_related("images")
    )

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__icontains=query)
        )

    if category:
        products = products.filter(category=category)

    if min_price:
        products = products.filter(base_price__gte=min_price)

    if max_price:
        products = products.filter(base_price__lte=max_price)

    if in_stock:
        products = products.filter(id__in=[p.id for p in products if p.total_stock > 0])

    serializer = ProductListSerializer(products, many=True, context={"request": request})
    return Response(serializer.data)


# ==================== PRODUCT REVIEWS ====================


class ProductReviewListView(generics.ListAPIView):
    """List all reviews for a product"""

    serializer_class = ProductReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        product_id = self.kwargs.get("product_id")
        return (
            ProductReview.objects.filter(product_id=product_id, is_approved=True)
            .select_related("user")
            .order_by("-created_at")
        )


class ProductReviewCreateView(generics.CreateAPIView):
    """Create a review for a product"""

    serializer_class = ProductReviewCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Check if user already reviewed this product
        product_id = request.data.get("product")
        existing = ProductReview.objects.filter(product_id=product_id, user=request.user).first()

        if existing:
            return Response(
                {"error": "You have already reviewed this product", "review_id": existing.id},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().create(request, *args, **kwargs)


class UserReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update or delete user's own review"""

    serializer_class = ProductReviewCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductReview.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductReviewSerializer
        return ProductReviewCreateSerializer


class UserReviewsListView(generics.ListAPIView):
    """List all reviews by the current user"""

    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ProductReview.objects.filter(user=self.request.user)
            .select_related("product")
            .order_by("-created_at")
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_user_review(request, product_id):
    """Check if user has reviewed a specific product"""
    review = ProductReview.objects.filter(product_id=product_id, user=request.user).first()

    if review:
        return Response({"has_reviewed": True, "review": ProductReviewSerializer(review).data})
    return Response({"has_reviewed": False})


# ==================== WISHLIST ====================


class WishlistListView(generics.ListAPIView):
    """List all items in user's wishlist"""

    serializer_class = WishlistSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Wishlist.objects.filter(user=self.request.user)
            .select_related("product", "product__store")
            .prefetch_related("product__images")
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_wishlist(request):
    """Add a product to wishlist"""
    product_id = request.data.get("product_id")

    if not product_id:
        return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        product = Product.objects.get(id=product_id, is_available=True)
    except Product.DoesNotExist:
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check if already in wishlist
    wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, product=product)

    if created:
        serializer = WishlistSerializer(wishlist_item)
        return Response(
            {"message": "Product added to wishlist", "wishlist_item": serializer.data},
            status=status.HTTP_201_CREATED,
        )
    else:
        return Response({"message": "Product already in wishlist"}, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_from_wishlist(request, product_id):
    """Remove a product from wishlist"""
    try:
        wishlist_item = Wishlist.objects.get(user=request.user, product_id=product_id)
        wishlist_item.delete()
        return Response({"message": "Product removed from wishlist"}, status=status.HTTP_200_OK)
    except Wishlist.DoesNotExist:
        return Response({"error": "Product not in wishlist"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_wishlist_status(request, product_id):
    """Check if a product is in user's wishlist"""
    is_wishlisted = Wishlist.objects.filter(user=request.user, product_id=product_id).exists()

    return Response({"is_wishlisted": is_wishlisted})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_wishlist(request):
    """Clear all items from wishlist"""
    deleted_count, _ = Wishlist.objects.filter(user=request.user).delete()
    return Response(
        {"message": f"Removed {deleted_count} items from wishlist", "deleted_count": deleted_count},
        status=status.HTTP_200_OK,
    )
