from decimal import Decimal, InvalidOperation

from django.db.models import Count, DecimalField, Prefetch, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import filters, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import AttributeDefinition, Category
from apps.stores.models import Store
from apps.users.permissions import IsListingOwner, IsStoreOwner
from apps.users.plans import (
    count_active_listings,
    get_listing_quota,
    get_plan,
    get_product_quota,
    max_draft_listings,
)
from core.exceptions import ApiError
from core.idempotency import IdempotentPostMixin
from core.pagination import FeedCursorPagination, WishlistCursorPagination

from . import lifecycle
from .duplicates import more_from_seller as _more_from_seller
from .duplicates import similar_to
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

#: Numeric attribute comparisons (``?attr_km_min=…``) cast the stored jsonb
#: to numeric; GIN cannot serve those, only the exact filters can (Phase 15
#: owns search performance at catalogue scale).
NUMERIC_ATTRIBUTE_TYPES = {AttributeDefinition.Type.NUMBER, AttributeDefinition.Type.YEAR}

#: Casts of ``attributes_json`` values need an explicit precision: a bare
#: ``DecimalField()`` renders ``CAST(… AS numeric(None, None))``, which
#: PostgreSQL rejects outright ("invalid input syntax for type integer:
#: none" — it reads the ``None`` modifiers as input). 20 digits is far beyond
#: any attribute value; 6 decimals keeps fractional bounds exact.
ATTRIBUTE_DECIMAL_FIELD = DecimalField(max_digits=20, decimal_places=6)


def _images_prefetch(lookup: str = "images") -> Prefetch:
    """Images *and* their upload in one extra query.

    ``ProductImage.display_url`` walks to ``upload`` for the card URL and the
    LQIP; without ``select_related`` that walk is one query per image, and a
    catalogue page would trade its N+1 for a bigger one. One Prefetch object
    keeps the query count constant for every list path.
    """
    return Prefetch(lookup, queryset=ProductImage.objects.select_related("upload"))


def apply_catalog_filters(queryset, query_params):
    """Phase 12 catalogue filters: ``?category=`` and ``?attr_<key>``.

    - ``?category=<slug>`` matches the category **and every descendant**
      (filtering the "Vehicles" sidebar must show the cars), via one
      ``get_descendants()`` query on mptt's materialized path. An unknown or
      deactivated slug yields an empty page, not a 404 — a stale bookmark
      should not error.
    - ``?attr_<key>=<value>`` filters on ``attributes_json`` for *filterable*
      definitions inside the filtered subtree (any filterable definition when
      no category filter is given). ``number``/``year`` attributes also accept
      ``?attr_<key>_min=`` / ``?attr_<key>_max=``; ``range`` attributes accept
      them as *overlap* bounds (a salary range matches any posting whose own
      range intersects it).

    Unknown or non-filterable keys raise a 400 instead of being ignored: a
    typo'd filter that silently returns everything is a bug report weeks
    later.
    """
    category_slug = query_params.get("category")
    subtree_ids = None
    if category_slug:
        root = Category.objects.filter(slug=category_slug, is_active=True).first()
        subtree_ids = (
            list(root.get_descendants(include_self=True).values_list("id", flat=True))
            if root is not None
            else []
        )
        queryset = queryset.filter(category_id__in=subtree_ids)

    definitions = AttributeDefinition.objects.filter(is_active=True, filterable=True)
    if subtree_ids is not None:
        definitions = definitions.filter(category_id__in=subtree_ids)
    filterable = {definition.key: definition for definition in definitions}

    for param, raw_value in query_params.items():
        if not param.startswith("attr_"):
            continue
        body = param[len("attr_") :]
        modifier = ""
        for candidate in ("_min", "_max"):
            if body.endswith(candidate):
                body, modifier = body[: -len(candidate)], candidate

        definition = filterable.get(body)
        if definition is None:
            raise ValidationError(
                {param: _("Unknown or non-filterable attribute for this category.")}
            )

        if not modifier:
            if definition.type in NUMERIC_ATTRIBUTE_TYPES:
                # The query string is text; comparing it to the stored jsonb
                # *number* would be string ≠ number forever. Compare through
                # the same numeric cast the bounds use — an unparseable value
                # falls through to the jsonb exact match, which never equals a
                # number, so a bogus filter yields an empty page, not a 500.
                try:
                    number = Decimal(raw_value)
                except InvalidOperation:
                    number = None
                if number is not None:
                    exact_alias = f"attr_{body}_exact"
                    queryset = queryset.annotate(
                        **{
                            exact_alias: Cast(
                                KeyTextTransform(body, "attributes_json"),
                                ATTRIBUTE_DECIMAL_FIELD,
                            )
                        }
                    )
                    queryset = queryset.filter(**{exact_alias: number})
                    continue
            value = raw_value
            if definition.type == AttributeDefinition.Type.BOOLEAN:
                if raw_value not in ("true", "false"):
                    raise ValidationError({param: _("Must be true or false.")})
                value = raw_value == "true"
            queryset = queryset.filter(**{f"attributes_json__{body}": value})
            continue

        # Numeric / range bounds: cast the stored jsonb and compare. The cast
        # must be *annotated* — `filter(low__lte=…)` names a field or an
        # annotation, never a local variable — and each modifier gets its own
        # alias so `?attr_x_min=` and `?attr_x_max=` in one request do not
        # collide on a duplicate annotation name.
        if definition.type == AttributeDefinition.Type.RANGE:
            low_alias = f"attr_{body}{modifier}_low"
            high_alias = f"attr_{body}{modifier}_high"
            queryset = queryset.annotate(
                **{
                    low_alias: Cast(
                        KeyTextTransform("min", KeyTextTransform(body, "attributes_json")),
                        ATTRIBUTE_DECIMAL_FIELD,
                    ),
                    high_alias: Cast(
                        KeyTextTransform("max", KeyTextTransform(body, "attributes_json")),
                        ATTRIBUTE_DECIMAL_FIELD,
                    ),
                }
            )
            # Overlap: the posting's range intersects [min, max].
            queryset = (
                queryset.filter(**{f"{high_alias}__gte": raw_value})
                if modifier == "_min"
                else queryset.filter(**{f"{low_alias}__lte": raw_value})
            )
            continue

        if definition.type not in NUMERIC_ATTRIBUTE_TYPES:
            raise ValidationError(
                {param: _("Only number, year and range attributes accept bounds.")}
            )
        numeric_alias = f"attr_{body}{modifier}_value"
        queryset = queryset.annotate(
            **{
                numeric_alias: Cast(
                    KeyTextTransform(body, "attributes_json"), ATTRIBUTE_DECIMAL_FIELD
                ),
            }
        )
        queryset = (
            queryset.filter(**{f"{numeric_alias}__gte": raw_value})
            if modifier == "_min"
            else queryset.filter(**{f"{numeric_alias}__lte": raw_value})
        )

    return queryset


def apply_location_filters(queryset, query_params):
    """Phase 13 location filters: ``?wilaya=<id>`` and ``?commune=<id>``.

    Same philosophy as ``?category=``: an unknown id yields an empty page,
    and a non-numeric one (a stale bookmark, a hand-edited URL) yields an
    empty page too rather than a 500 from the ORM's int cast — the filter
    form is the thing that must be correct, not every link that ever carried
    the parameter.
    """
    wilaya = query_params.get("wilaya")
    commune = query_params.get("commune")
    if wilaya is not None:
        queryset = queryset.filter(wilaya_id=int(wilaya)) if wilaya.isdigit() else queryset.none()
    if commune is not None:
        queryset = (
            queryset.filter(commune_id=int(commune)) if commune.isdigit() else queryset.none()
        )
    return queryset


class ProductListView(generics.ListAPIView):
    """Public list of all available products with search and filter"""

    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Phase 12: ``?category`` and ``?attr_<key>`` are handled by
    # apply_catalog_filters (slug + subtree semantics the generic
    # filterset cannot express); only the plain booleans stay here.
    filterset_fields = ["is_available"]
    search_fields = [
        "name",
        "description",
        "category__name_fr",
        "category__name_ar",
        "category__name_en",
    ]
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
        queryset = apply_catalog_filters(queryset, self.request.query_params)
        queryset = apply_location_filters(queryset, self.request.query_params)

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
        return lifecycle.expire_if_due(obj)


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
    """Advanced product search

    Paginated like the catalogue: without it this endpoint returned the whole
    matching catalogue in one response, which is exactly the failure mode
    Phase 10 exists to remove.
    """
    query = request.query_params.get("q", "")
    min_price = request.query_params.get("min_price")
    max_price = request.query_params.get("max_price")
    in_stock = request.query_params.get("in_stock") == "true"

    products = (
        Product.objects.public()
        .select_related("store", "category", "seller", "wilaya")
        .prefetch_related(_images_prefetch())
        .with_catalog_stats()
        .for_user(request.user)
    )

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name_fr__icontains=query)
            | Q(category__name_ar__icontains=query)
            | Q(category__name_en__icontains=query)
        )

    # Phase 12: ?category=<slug> (whole subtree) + ?attr_<key>=… — the same
    # helper the catalogue list uses.
    products = apply_catalog_filters(products, request.query_params)
    # Phase 13: ?wilaya= / ?commune= — classifieds are location-first.
    products = apply_location_filters(products, request.query_params)

    if min_price:
        products = products.filter(base_price__gte=min_price)

    if max_price:
        products = products.filter(base_price__lte=max_price)

    if in_stock:
        # Filter on the annotation rather than materialising the whole
        # queryset to pick ids out of it in Python: the old list
        # comprehension ran one SUM per candidate row — one query per product
        # in the catalogue — and then re-queried to filter on the ids.
        products = products.filter(total_stock__gt=0)

    paginator = FeedCursorPagination()
    page = paginator.paginate_queryset(products, request)
    serializer = ProductListSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


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
