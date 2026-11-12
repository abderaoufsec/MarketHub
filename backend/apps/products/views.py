from django.db.models import Count, F, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import filters, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.services import reveal_phone
from apps.search.facets import localized
from apps.search.services import get_search_service
from apps.stores.models import Store
from apps.users.permissions import IsListingOwner, IsStoreOwner
from apps.users.plans import (
    count_active_listings,
    get_listing_quota,
    get_plan,
    get_product_quota,
    max_draft_listings,
)
from apps.users.throttles import RevealPhoneRateThrottle
from core.exceptions import ApiError
from core.idempotency import IdempotentPostMixin
from core.pagination import FeedCursorPagination, WishlistCursorPagination

from . import lifecycle
from .duplicates import more_from_seller as _more_from_seller
from .duplicates import similar_to
from .filters import apply_location_filters, apply_search_filters
from .lifecycle import ListingLifecycleError
from .models import (
    ListingStatus,
    Product,
    ProductImage,
    ProductReview,
    Wishlist,
    nested_product_queryset,
)
from .serializers import (
    ListingActionSerializer,
    ProductCreateUpdateSerializer,
    ProductListSerializer,
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    ProductSearchPageSerializer,
    ProductSerializer,
    WishlistSerializer,
)


def _images_prefetch(lookup: str = "images") -> Prefetch:
    """Images *and* their upload in one extra query.

    ``ProductImage.display_url`` walks to ``upload`` for the card URL and the
    LQIP; without ``select_related`` that walk is one query per image, and a
    catalogue page would trade its N+1 for a bigger one. One Prefetch object
    keeps the query count constant for every list path.
    """
    return Prefetch(lookup, queryset=ProductImage.objects.select_related("upload"))


class ProductListView(generics.ListAPIView):
    """Public list of all available products with search and filter"""

    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    # Phase 12: ``?category`` and ``?attr_<key>`` are handled by
    # apply_search_filters (slug + subtree semantics the generic filterset
    # cannot express); only the plain booleans stay here.
    filterset_fields = ["is_available"]
    ordering_fields = ["created_at", "base_price", "name"]
    ordering = ["-created_at"]
    #: The catalogue is the feed people scroll, and it is the endpoint that
    #: has to survive 100k+ rows — keyset, not offset (core.pagination).
    pagination_class = FeedCursorPagination

    def get_queryset(self):
        queryset = (
            # ``public()`` is the whole visibility rule (live, available, not
            # behind a dead store) — see ProductQuerySet.public.
            Product.objects.public()
            .select_related("store", "category", "seller", "wilaya")
            .prefetch_related(_images_prefetch())
            .with_catalog_stats()
            .for_user(self.request.user)
        )
        # Phase 15: the catalogue's ``?search=`` uses the same FTS + trigram
        # matcher as /search/ (it used to be a set of icontains ORs, which
        # ignored accents, Arabic spellings and typos).
        search = self.request.query_params.get("search") or self.request.query_params.get("q")
        if search:
            queryset = get_search_service().matching(queryset, search)
        return apply_search_filters(queryset, self.request.query_params)


class ProductDetailView(generics.RetrieveAPIView):
    """Public view of a single product with reviews"""

    queryset = Product.objects.public()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("store", "category", "seller", "wilaya", "commune")
            .prefetch_related(_images_prefetch(), "attributes", "reviews__user")
            .with_catalog_stats()
            .for_user(self.request.user)
        )

    def get_object(self):
        obj = super().get_object()
        # Lazy expiry (Phase 13): without the beat (Phase 22) a listing must
        # not render ACTIVE the morning after its window closed.
        obj = lifecycle.expire_if_due(obj)
        # Phase 15 trending: one atomic increment per detail view. F() not
        # read-modify-write, so two visitors cannot swallow each other's count.
        if obj.status == ListingStatus.ACTIVE:
            Product.objects.filter(pk=obj.pk).update(views_count=F("views_count") + 1)
            obj.views_count += 1
        return obj


class RevealPhoneView(APIView):
    """Authenticated, throttled, audited phone reveal (Phase 16).

    The public detail payload only says whether a number *can* be revealed.
    The number itself leaves the server here, once per click, with a
    ``PhoneReveal`` audit row (who, which listing, which number, IP, UA). The
    client gets ready-made ``tel:``/``sms:``/WhatsApp deep links so a phone
    number never has to be parsed or concatenated in the browser.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [RevealPhoneRateThrottle]

    def _deep_links(self, phone: str) -> dict:
        digits = "".join(character for character in phone if character.isdigit())
        if digits.startswith("00"):
            digits = digits[2:]
        international = f"213{digits[1:]}" if digits.startswith("0") else digits
        return {
            "call_url": f"tel:{phone}",
            "sms_url": f"sms:{phone}",
            "whatsapp_url": f"https://wa.me/{international}",
        }

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        listing = get_object_or_404(
            Product.objects.public().select_related("seller"),
            pk=pk,
        )
        phone = reveal_phone(listing, request.user, request)
        return Response(
            {
                "listing_id": listing.pk,
                "phone_number": phone,
                **self._deep_links(phone),
            }
        )


@extend_schema(responses={200: ProductListSerializer(many=True)})
@api_view(["GET"])
@permission_classes([AllowAny])
def featured_products(request):
    """Get featured/recent products"""
    products = (
        Product.objects.public()
        .select_related("store", "category", "seller", "wilaya")
        .prefetch_related(_images_prefetch())
        .with_catalog_stats()
        .for_user(request.user)
        .order_by("-created_at")[:12]
    )

    serializer = ProductListSerializer(products, many=True, context={"request": request})
    return Response(serializer.data)


@extend_schema(responses={200: ProductSearchPageSerializer})
@api_view(["GET"])
@permission_classes([AllowAny])
def feed_products(request):
    """The home feed: ``?section=latest|trending``, cursor-paginated.

    ``latest`` honours ``?wilaya=`` (the "in my wilaya" row) and is newest
    first. ``trending`` ranks by detail views + wishlists + reviews, so a new
    catalogue still produces a sensible order instead of an empty section.
    The cursor contract is the same as the catalogue's: follow ``next``
    forever without repeats.
    """
    section = request.query_params.get("section", "latest")
    if section not in ("latest", "trending"):
        raise ValidationError({"section": _("Must be latest or trending.")})

    queryset = (
        Product.objects.public()
        .select_related("store", "category", "seller", "wilaya")
        .prefetch_related(_images_prefetch())
        .with_catalog_stats()
        .for_user(request.user)
    )
    if section == "trending":
        wishlists = (
            Wishlist.objects.filter(product=OuterRef("pk"))
            .order_by()
            .values("product")
            .annotate(n=Count("id"))
            .values("n")
        )
        queryset = queryset.annotate(
            wishlist_count=Coalesce(Subquery(wishlists, output_field=IntegerField()), Value(0))
        ).annotate(
            trend_score=F("views_count") * 3 + F("wishlist_count") * 6 + F("review_count") * 2
        )
        ordering = ["-trend_score", "-created_at", "-id"]
    else:
        queryset = apply_location_filters(queryset, request.query_params)
        ordering = ["-created_at", "-id"]

    paginator = FeedCursorPagination()
    paginator.ordering = ordering
    page = paginator.paginate_queryset(queryset, request)
    serializer = ProductListSerializer(page, many=True, context={"request": request})
    payload = paginator.get_paginated_response(serializer.data).data
    payload["section"] = section
    return Response(payload)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([AllowAny])
def feed_categories(request):
    """Recommended categories for the home page, by live listing count.

    Optional ``?wilaya=`` makes the row local ("what is popular here"), which
    is the first thing an Algerian classifieds visitor wants to see. Only the
    top 10 are returned; the full tree is ``/catalog/categories/``.
    """
    queryset = Product.objects.public().filter(category__isnull=False)
    queryset = apply_location_filters(queryset, request.query_params)
    rows = (
        queryset.values(
            "category_id",
            "category__slug",
            "category__icon",
            "category__name_fr",
            "category__name_ar",
            "category__name_en",
        )
        .annotate(count=Count("id"))
        .order_by("-count", "category__name_fr")[:10]
    )
    return Response(
        [
            {
                "id": row["category_id"],
                "slug": row["category__slug"],
                "icon": row["category__icon"] or "",
                "name": localized(
                    row["category__name_fr"],
                    row["category__name_ar"],
                    row["category__name_en"],
                ),
                "count": row["count"],
            }
            for row in rows
        ]
    )


class SellerProductListView(generics.ListAPIView):
    """The authenticated user's own listings — every kind.

    Phase 13: ownership is the ``seller`` FK, so an individual's classifieds
    and a store owner's SKUs land on one page (``?status=DRAFT`` etc. filters
    it), instead of the endpoint returning nothing at all to anyone without a
    store — which it did before, because "seller" used to mean "store owner".
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # The store rides in through an annotated ``Prefetch`` instead of a
        # join: ``StoreSerializer`` embeds the store's owner, its category
        # *and* a ``product_count`` — a join can provide the first two but
        # not the aggregate, and the fallback counts products *per row*. One
        # extra query for the page, never one per store row (Phase 13,
        # finding #15's sibling).
        queryset = (
            Product.objects.filter(seller=self.request.user)
            .select_related("category", "seller", "wilaya", "commune")
            .prefetch_related(
                Prefetch(
                    "store",
                    queryset=Store.objects.select_related("owner", "category").annotate(
                        product_count=Count("products")
                    ),
                ),
                _images_prefetch(),
                "attributes",
                "inventory",
                "reviews__user",
            )
            .with_catalog_stats()
            .for_user(self.request.user)
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in ListingStatus.values:
                raise ValidationError({"status": _("Unknown listing status.")})
            queryset = queryset.filter(status=status_filter)
        return queryset


class SellerProductCreateView(IdempotentPostMixin, generics.CreateAPIView):
    """Create a new store product (seller with a store only).

    The *wizard* endpoint is :class:`ListingCreateView` (``/products/create/``)
    — any signed-in user, draft-first, no store. This one keeps the Phase 6/12
    store contract: immediate ``ACTIVE``, store quota, ``STORE_PRODUCT`` no
    matter what the payload claims.

    docs/todo.md §0.3 #8: the two rejection checks used to raise
    ``permissions.PermissionDenied`` — an attribute that does not exist on
    ``rest_framework.permissions`` — so every rejection came back as an
    AttributeError → HTTP 500. Phase 7 replaced them with the reusable
    ``IsStoreOwner`` permission class (403 before the view body runs).

    Phase 9: also mixed with ``IdempotentPostMixin``. Publishing a listing is
    not something a client should be able to duplicate by retrying a request
    whose 201 got lost on a flaky connection, so a POST replayed with the same
    ``Idempotency-Key`` returns the cached 201 body (with
    ``Idempotency-Replayed: true``) instead of creating a second product, and
    reusing the key with a *different* payload is rejected as a 409
    ``idempotency_key_conflict`` rather than silently overwriting. Without the
    header nothing changes: the key is ``None`` and the mixin passes straight
    through to DRF's create.
    """

    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAuthenticated, IsStoreOwner]
    #: Replay namespace: two endpoints under the same user must not collide on
    #: the same key (see ``core/idempotency.py``).
    idempotency_scope = "listing"

    def perform_create(self, serializer):
        serializer.save()


class ListingCreateView(IdempotentPostMixin, generics.CreateAPIView):
    """``POST /products/create/`` — the fast-posting wizard's save (Phase 13).

    Any authenticated user, no store, no ``is_seller`` gate: posting a
    classified is the marketplace's front door. The row is born ``DRAFT`` —
    autosave calls this once, then PATCHes ``/products/seller/<id>/``; only
    ``POST /products/<id>/lifecycle/ {action: "publish"}`` may take it live,
    after the completeness/quota/duplicate gates.

    The response is the *full* :class:`ProductSerializer`, not the write
    serializer: the wizard needs ``id``, ``status`` and ``canonical_path``
    back from the very first autosave.
    """

    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAuthenticated]
    #: Distinct from the store endpoint's "listing" scope: same user, same
    #: Idempotency-Key, two different bodies must not replay each other.
    idempotency_scope = "classified"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["listing_wizard"] = True
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Serialize the *annotated* row, not the bare one: ProductSerializer
        # reads total_stock / average_rating / review_count off queryset
        # annotations (they are not columns), and a freshly created instance
        # carries none — straight serialization is an AttributeError → 500.
        instance = nested_product_queryset(request.user).get(pk=serializer.instance.pk)
        output = ProductSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class SellerProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete one of *your* listings.

    Phase 13: the queryset is ``seller=request.user`` — store products and
    classifieds alike (the store-scoped filter pre-dated the seller FK and
    returned 404 for every individual's own ad). Object-level ownership is
    still checked by ``IsListingOwner`` behind it.
    """

    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAuthenticated, IsListingOwner]

    def get_queryset(self):
        return (
            Product.objects.filter(seller=self.request.user)
            .select_related("store", "category", "seller", "wilaya", "commune")
            .prefetch_related(_images_prefetch(), "attributes", "inventory")
            .with_catalog_stats()
            .for_user(self.request.user)
        )

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductSerializer
        return ProductCreateUpdateSerializer


# ==================== LISTING LIFECYCLE (Phase 13) ====================


class ListingLifecycleView(generics.GenericAPIView):
    """``POST /products/<id>/lifecycle/ {action}`` — every status change.

    One endpoint for publish/renew/mark-sold/archive/… so the transition
    table in :mod:`apps.products.lifecycle` is the only authority: an
    illegal edge (``renew`` on a live listing, ``archive`` by a stranger)
    is a 400/404 from the same code path a future admin or beat job would
    use, not a per-action view that drifts. Ownership is the queryset
    (``seller=request.user``) plus ``IsListingOwner``.
    """

    permission_classes = [IsAuthenticated, IsListingOwner]

    def get_queryset(self):
        return (
            Product.objects.filter(seller=self.request.user)
            .select_related("store", "category", "seller", "wilaya", "commune")
            .prefetch_related(_images_prefetch(), "attributes", "reviews__user")
            .with_catalog_stats()
            .for_user(self.request.user)
        )

    def get_serializer_class(self):
        return ProductSerializer

    @extend_schema(request=ListingActionSerializer, responses={200: ProductSerializer})
    def post(self, request, pk):
        product = self.get_object()
        action = (request.data.get("action") or "").strip()
        # ``allow_duplicate`` carries the wizard's "publish anyway" confirmation
        # past the similarity gate only — completeness and quota stay absolute.
        # JSON ``true`` is the contract; the string form is accepted so a
        # form-encoded client is not silently ignored.
        allow_duplicate = request.data.get("allow_duplicate") in (True, "true")
        try:
            if action == "publish":
                product = lifecycle.publish(product, allow_duplicate=allow_duplicate)
            else:
                product = lifecycle.transition(product, action)
        except ListingLifecycleError:
            # ApiError subclass: the envelope renders code=invalid_transition
            # with {status, action} details the wizard turns into a sentence.
            raise
        serializer = self.get_serializer(product, context={"request": request})
        return Response(serializer.data)


@extend_schema(responses={200: ProductListSerializer(many=True)})
@api_view(["GET"])
@permission_classes([AllowAny])
def similar_listings(request, pk):
    """ "Similar listings" — same category subtree, live, other sellers."""
    product = generics.get_object_or_404(Product.objects.public().select_related("category"), pk=pk)
    items = similar_to(product)
    return Response(ProductListSerializer(items, many=True, context={"request": request}).data)


@extend_schema(responses={200: ProductListSerializer(many=True)})
@api_view(["GET"])
@permission_classes([AllowAny])
def more_from_seller(request, pk):
    """ "More from this seller" — their other live listings."""
    product = generics.get_object_or_404(Product.objects.public().select_related("seller"), pk=pk)
    items = _more_from_seller(product)
    return Response(ProductListSerializer(items, many=True, context={"request": request}).data)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def seller_quota(request):
    """The caller's listing allowances — what the wizard header and the
    dashboard quota bar render.

    Two numbers on purpose: ``listing_quota``/``active_listings`` govern the
    wizard's *publish* gate (tiered per user, Phase 13), and
    ``store_product_quota``/``store_products`` are the Phase 6 store-SKU cap
    the seller dashboard has always shown (Phase 21 merges the arithmetic).
    ``null`` quota = unlimited.
    """
    user = request.user
    quota = get_listing_quota(user)
    has_store = hasattr(user, "store")
    return Response(
        {
            "plan": get_plan(user),
            "active_listings": count_active_listings(user),
            "listing_quota": quota,  # null = unlimited
            "drafts": Product.objects.filter(seller=user, status=ListingStatus.DRAFT).count(),
            "draft_limit": max_draft_listings(),
            "store_products": user.store.products.count() if has_store else 0,
            "store_product_quota": get_product_quota(user) if has_store else None,
        }
    )


@extend_schema(responses={200: ProductSearchPageSerializer})
@api_view(["GET"])
@permission_classes([AllowAny])
def search_products(request):
    """Advanced product search (the Phase 15 service, cursor-paginated).

    This endpoint used to be a set of ``icontains`` ORs; it now delegates to
    ``PostgresSearchService``: FTS + trigram, facets, relevance/newest/price/
    distance orderings and the zero-result recovery block. The page envelope
    keeps its historical ``{next, previous, results}`` keys and adds
    ``facets``/``meta`` - old clients ignore the new keys.
    """
    result = get_search_service().search(
        request.query_params, user=request.user, include_facets=False
    )
    paginator = FeedCursorPagination()
    paginator.ordering = result.ordering
    page = paginator.paginate_queryset(result.queryset, request)
    serializer = ProductListSerializer(page, many=True, context={"request": request})
    payload = paginator.get_paginated_response(serializer.data).data
    payload["facets"] = result.facets
    payload["meta"] = {
        "total": result.total,
        "sort": result.sort,
        "q": result.params.get("q", ""),
        "did_you_mean": result.did_you_mean,
        "relaxations": result.relaxations,
        "nearby_wilayas": result.nearby_wilayas,
        "used_fuzzy": result.used_fuzzy,
        "filters": result.params,
    }
    return Response(payload)


# ==================== PRODUCT REVIEWS ====================


class ProductReviewListView(generics.ListAPIView):
    """List all reviews for a product

    Keyset-paginated: a popular product accumulates reviews forever and this
    is an endless scroll, not a table with a page 7 you jump back to.
    """

    serializer_class = ProductReviewSerializer
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

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
        # Check if user already reviewed this product. Phase 9: the rejection
        # used to be a hand-built {"error": …, "review_id": …} body that only
        # this endpoint produced; raising the shared ApiError keeps the same
        # 400 but renders the standard envelope, with the offending review id
        # as structured ``details`` instead of a stray top-level key.
        product_id = request.data.get("product")
        existing = ProductReview.objects.filter(product_id=product_id, user=request.user).first()

        if existing:
            raise ApiError(
                "You have already reviewed this product",
                code="already_reviewed",
                details={"review_id": existing.id},
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
    pagination_class = FeedCursorPagination

    def get_queryset(self):
        return (
            ProductReview.objects.filter(user=self.request.user)
            .select_related("product")
            .order_by("-created_at")
        )


@extend_schema(responses={200: OpenApiTypes.OBJECT})
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
    pagination_class = WishlistCursorPagination

    def get_queryset(self):
        return (
            Wishlist.objects.filter(user=self.request.user)
            .select_related("product", "product__store")
            .prefetch_related(_images_prefetch("product__images"))
        )


# The body is a bare {"product_id": …} that no serializer models (the success
# payloads are {"message", "wishlist_item"} / {"message"}), so both sides are
# free-form objects rather than invented schemas. Note: with an @api_view
# function, @extend_schema must sit *above* it — DRF's decorator hides the
# function inside a handler closure, and spectacular only finds the schema
# annotation when it decorates the as_view() result.
@extend_schema(
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_wishlist(request):
    """Add a product to wishlist"""
    product_id = request.data.get("product_id")

    if not product_id:
        # Phase 9: raised, not hand-built — the envelope renderer turns this
        # into {"code": "product_id_required", …} with the request id.
        raise ApiError("product_id is required", code="product_id_required")

    try:
        # ``public()``: drafts and expired listings are not wishlistable —
        # the old bare ``is_available=True`` would have accepted them.
        product = Product.objects.public().get(id=product_id)
    except Product.DoesNotExist:
        # ``from None``: the client only needs to know the product is not
        # (available in) the catalogue, not that an ORM lookup failed.
        raise NotFound("Product not found", code="product_not_found") from None

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


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_from_wishlist(request, product_id):
    """Remove a product from wishlist"""
    try:
        wishlist_item = Wishlist.objects.get(user=request.user, product_id=product_id)
    except Wishlist.DoesNotExist:
        # Phase 9: raised so the 404 arrives in the standard envelope with a
        # branchable code ("not_in_wishlist") instead of {"error": …}.
        raise NotFound("Product not in wishlist", code="not_in_wishlist") from None

    wishlist_item.delete()
    return Response({"message": "Product removed from wishlist"}, status=status.HTTP_200_OK)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_wishlist_status(request, product_id):
    """Check if a product is in user's wishlist"""
    is_wishlisted = Wishlist.objects.filter(user=request.user, product_id=product_id).exists()

    return Response({"is_wishlisted": is_wishlisted})


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_wishlist(request):
    """Clear all items from wishlist"""
    deleted_count, _ = Wishlist.objects.filter(user=request.user).delete()
    return Response(
        {"message": f"Removed {deleted_count} items from wishlist", "deleted_count": deleted_count},
        status=status.HTTP_200_OK,
    )
