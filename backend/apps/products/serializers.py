from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.catalog.models import Category
from apps.catalog.serializers import CategoryMiniSerializer
from apps.catalog.validation import validate_attributes
from apps.geography.models import Commune, Wilaya
from apps.geography.serializers import CommuneSerializer, WilayaSerializer
from apps.stores.serializers import StoreSerializer
from apps.users.plans import get_product_quota, max_draft_listings
from core.exceptions import ApiError
from core.i18n import choice_label

from .lifecycle import ACTIONS as lifecycle_actions
from .lifecycle import _set_slug
from .models import (
    ContactMode,
    ListingStatus,
    ListingType,
    PriceMode,
    Product,
    ProductAttribute,
    ProductImage,
    ProductReview,
    Wishlist,
)


def _display_name(user) -> str:
    """A seller's public handle: real name, else the email handle.

    Never the phone — a phone is contact data the listing's ``contact_mode``
    decides whether to show, not a display name.
    """
    if user is None:
        return ""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    if user.email:
        return user.email.split("@")[0]
    return ""


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


class ListingActionSerializer(serializers.Serializer):
    """``{"action": "publish" | "renew" | …}`` — the lifecycle endpoint's body.

    Mirrors ``apps.products.lifecycle.ACTIONS``; a value outside it is a 400
    from the *serializer* for schema readers and from the *state machine*
    for everyone else — one source of choices either way.

    ``allow_duplicate`` is the wizard's "publish anyway" confirmation after a
    ``possible_duplicate`` warning. It skips the similarity gate only:
    completeness and the quota remain absolute.
    """

    action = serializers.ChoiceField(
        choices=[(name, name) for name in sorted(lifecycle_actions)],
        help_text="Lifecycle action to apply to the listing.",
    )
    allow_duplicate = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Publish despite a possible_duplicate warning (publish only).",
    )


class SellerMiniSerializer(serializers.Serializer):
    """``{id, name}`` — the listing's owner on a public page.

    Deliberately shapeless about contact data: the phone rides alongside the
    listing (``seller_phone``) only when the seller's ``contact_mode`` says
    so, never inside the seller object that pages cache and re-render.
    """

    id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        return _display_name(obj)


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""

    store = StoreSerializer(read_only=True)
    # Phase 12: the category is the nested catalog node (read); writes go
    # through ``category_id`` on ProductCreateUpdateSerializer. Null for
    # legacy rows the FK migration could not file.
    category = CategoryMiniSerializer(read_only=True)
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
    # Phase 13: the listing surface.
    seller = SellerMiniSerializer(read_only=True)
    seller_phone = serializers.SerializerMethodField()
    wilaya = WilayaSerializer(read_only=True)
    commune = CommuneSerializer(read_only=True)
    # No explicit ``source``: DRF *rejects* source == field name, and the
    # property is read straight off the instance by name.
    canonical_path = serializers.CharField(read_only=True)
    listing_type_label = serializers.SerializerMethodField()
    price_mode_label = serializers.SerializerMethodField()
    contact_mode_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "store",
            "seller",
            "seller_phone",
            "name",
            "description",
            "base_price",
            "old_price",
            "currency",
            "price_mode",
            "price_mode_label",
            "listing_type",
            "listing_type_label",
            "contact_mode",
            "contact_mode_label",
            "status",
            "status_label",
            "slug",
            "canonical_path",
            "category",
            "is_available",
            "low_stock_threshold",
            "attributes_json",
            "wilaya",
            "commune",
            "published_at",
            "expires_at",
            "sold_at",
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
        """The current user's review for this product.

        Reads the ``reviews`` prefetch cache when the view supplied one (the
        detail and seller-list paths do) — the old unconditional
        ``ProductReview.objects.filter(…).first()`` ran one query *per row*
        on the seller list, which is finding #15 this phase fixes. Paths
        without the prefetch fall back to the single query, correctly.
        """
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            return None
        cache = obj.__dict__.get("_prefetched_objects_cache", {})
        prefetched = cache.get("reviews")
        if prefetched is not None:
            review = next((r for r in prefetched if r.user_id == request.user.id), None)
        else:
            review = ProductReview.objects.filter(user=request.user, product=obj).first()
        if review:
            return ProductReviewSerializer(review, context=self.context).data
        return None

    def get_seller_phone(self, obj) -> str | None:
        """The seller's number when — and only when — they chose to show it.

        ``contact_mode`` *is* the consent: PHONE/WHATSAPP means "display my
        number on this listing", CHECKOUT/CHAT means don't. Only a verified
        number qualifies (unproven numbers are not worth publishing), and the
        phone never appears for inactive listings — this serializer runs on
        public paths that all go through ``QuerySet.public()``.
        """
        if obj.contact_mode not in (ContactMode.PHONE, ContactMode.WHATSAPP):
            return None
        seller = obj.seller
        if seller is None or not seller.phone_verified or not seller.phone_number:
            return None
        return seller.phone_number

    def get_listing_type_label(self, obj) -> str:
        return choice_label(ListingType.choices, obj.listing_type)

    def get_price_mode_label(self, obj) -> str:
        return choice_label(PriceMode.choices, obj.price_mode)

    def get_contact_mode_label(self, obj) -> str:
        return choice_label(ContactMode.choices, obj.contact_mode)

    def get_status_label(self, obj) -> str:
        return choice_label(ListingStatus.choices, obj.status)


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings"""

    # ``allow_null`` is load-bearing (Phase 13): a classified's ``store`` is
    # NULL, and a dotted source that walks through None raises AttributeError
    # → DRF's SkipField → the key would be *absent* from classified rows while
    # present for store SKUs. One shape for the whole catalogue: null.
    store_name = serializers.CharField(source="store.store_name", read_only=True, allow_null=True)
    store_slug = serializers.CharField(source="store.store_slug", read_only=True, allow_null=True)
    seller_name = serializers.SerializerMethodField()
    category = CategoryMiniSerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    is_wishlisted = serializers.SerializerMethodField()
    canonical_path = serializers.CharField(read_only=True)
    wilaya_name = serializers.SerializerMethodField()
    listing_type_label = serializers.SerializerMethodField()
    price_mode_label = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "base_price",
            "old_price",
            "currency",
            "price_mode",
            "price_mode_label",
            "listing_type",
            "listing_type_label",
            "slug",
            "canonical_path",
            "category",
            "is_available",
            "store_name",
            "store_slug",
            "seller_name",
            "wilaya_name",
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

    def get_seller_name(self, obj) -> str:
        """A classified has no store name; the seller carries the identity.

        Store products keep their store name (cards render store_name when
        present and fall back to this), so one field serves both halves of
        the catalogue without a per-row branch in the client.
        """
        return _display_name(obj.seller)

    def get_wilaya_name(self, obj) -> str | None:
        """Location by wilaya — a listing's address, not a filter code.

        Method field rather than ``source="wilaya.display_name"`` so a
        locationless row serializes to ``None`` instead of blowing up the
        whole page on one attribute error.
        """
        return obj.wilaya.display_name if obj.wilaya_id else None

    def get_listing_type_label(self, obj) -> str:
        return choice_label(ListingType.choices, obj.listing_type)

    def get_price_mode_label(self, obj) -> str:
        return choice_label(PriceMode.choices, obj.price_mode)


class ProductSearchPageSerializer(serializers.Serializer):
    """``{next, previous, results}`` — the page envelope of FeedCursorPagination.

    ``search_products`` is a ``@api_view``, so there is no view object for
    drf-spectacular to read ``pagination_class`` off; without this the docs
    would advertise a bare array for a body that is actually a page.

    The name is deliberately *not* ``PaginatedProductListSerializer``: drf-
    specticular auto-names pagination wrappers ``Paginated{Result}List``, so
    that class name collided with the generated ``PaginatedProductList``
    component (W001, two identities one name).
    """

    next = serializers.URLField(allow_null=True, read_only=True)
    previous = serializers.URLField(allow_null=True, read_only=True)
    results = ProductListSerializer(many=True, read_only=True)


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products *and* wizard draft listings.

    Phase 12 contract: write ``category_id`` (an active catalog node; required
    on create — a listing nobody can file is not publishable) and
    ``attributes_json``, validated against the category's *effective*
    attribute definitions (own + ancestors', deeper overriding) by
    :func:`apps.catalog.validation.validate_attributes`. Unknown keys, missing
    required keys and mistyped values are all rejected with per-key messages
    under ``attributes_json`` so the dynamic form can highlight its inputs.

    Phase 13 contract:
      * the wizard endpoint passes ``listing_wizard`` in context → the row is
        created as a **draft** owned directly by the requester (no store), the
        draft cap applies, and *required* attribute keys are deferred to
        publish — an autosave must never be rejected for being half-typed.
        Strictness follows the **status**, not the endpoint, so the detail
        PATCH of a draft stays lenient while any live listing stays strict;
      * price modes FREE/ON_REQUEST/EXCHANGE force ``base_price`` to 0 —
        "4500 DA or free" is not a price;
      * ``old_price`` only makes sense above the current price, and only for
        FIXED/NEGOTIABLE.
    """

    images = ProductImageSerializer(many=True, required=False)
    attributes = ProductAttributeSerializer(many=True, required=False)
    category = CategoryMiniSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        source="category",
        write_only=True,
        # Required on create is enforced in validate(): one message, one
        # place, and updates may legitimately leave the category alone.
        required=False,
    )
    wilaya_id = serializers.PrimaryKeyRelatedField(
        queryset=Wilaya.objects.filter(is_active=True),
        source="wilaya",
        write_only=True,
        required=False,
    )
    commune_id = serializers.PrimaryKeyRelatedField(
        queryset=Commune.objects.filter(is_active=True),
        source="commune",
        write_only=True,
        required=False,
    )
    listing_type = serializers.ChoiceField(choices=ListingType.choices, required=False)
    price_mode = serializers.ChoiceField(choices=PriceMode.choices, required=False)
    contact_mode = serializers.ChoiceField(choices=ContactMode.choices, required=False)
    old_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=0
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "base_price",
            "old_price",
            "currency",
            "price_mode",
            "listing_type",
            "contact_mode",
            "category",
            "category_id",
            "wilaya_id",
            "commune_id",
            "is_available",
            "low_stock_threshold",
            "attributes_json",
            "images",
            "attributes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get("listing_wizard"):
            # A draft may be as empty as the step the seller reached; the
            # publish gate (apps.products.lifecycle) is where completeness
            # becomes mandatory, once, with the list of what is missing.
            self.fields["name"].allow_blank = True
            self.fields["description"].required = False
            self.fields["description"].allow_blank = True
            self.fields["base_price"].required = False

    def _effective_status(self, attrs) -> str:
        """The status this row will have after the write, for validation
        strictness: drafts and rejected listings are checked for *shape*,
        published ones for *completeness* (required keys included)."""
        if self.instance is not None:
            return self.instance.status
        if self.context.get("listing_wizard"):
            return ListingStatus.DRAFT
        return ListingStatus.ACTIVE

    def validate(self, attrs):
        if self.instance is None and attrs.get("category") is None:
            raise serializers.ValidationError({"category_id": "A category is required."})

        category = attrs.get("category")
        if category is None and self.instance is not None:
            category = self.instance.category

        # --- a listing's type is decided at creation and never rewritten:
        # flipping STORE_PRODUCT → FOR_SALE on a stocked row would strand its
        # inventory and pull the rug from under anything already in carts.
        # An *unchanged* value is not a rewrite: the wizard autosave and any
        # PUT round-trip echo the type with every payload, and answering400
        # for a no-op would make those saves impossible.
        if (
            self.instance is not None
            and "listing_type" in attrs
            and attrs["listing_type"] != self.instance.listing_type
        ):
            raise serializers.ValidationError(
                {"listing_type": "A listing's type cannot change after creation."}
            )

        # --- geography: the wizard may send only commune_id; derive the
        # wilaya. A wilaya change that leaves a commune behind in the old
        # one silently clears the commune instead of storing an impossible
        # address (the form repopulates it).
        commune = attrs.get("commune")
        wilaya = attrs.get("wilaya")
        if commune is not None:
            if wilaya is None:
                attrs["wilaya"] = commune.wilaya
            elif commune.wilaya_id != wilaya.pk:
                raise serializers.ValidationError(
                    {"commune_id": "This commune does not belong to the selected wilaya."}
                )
        elif (
            wilaya is not None
            and self.instance is not None
            and self.instance.commune_id is not None
            and self.instance.commune.wilaya_id != wilaya.pk
        ):
            attrs["commune"] = None

        # --- price modes: unpriced means unpriced.
        price_mode = attrs.get(
            "price_mode",
            self.instance.price_mode if self.instance is not None else PriceMode.FIXED,
        )
        if price_mode in (PriceMode.FREE, PriceMode.ON_REQUEST, PriceMode.EXCHANGE):
            attrs["base_price"] = Decimal("0")
            if "price_mode" in attrs:
                # An old-price strikethrough on a free listing is nonsense.
                attrs.setdefault("old_price", None)
        if attrs.get("old_price") is not None:
            if price_mode not in (PriceMode.FIXED, PriceMode.NEGOTIABLE):
                raise serializers.ValidationError(
                    {
                        "old_price": "A previous price only makes sense for a fixed or negotiable price."
                    }
                )
            effective = attrs.get(
                "base_price",
                self.instance.base_price if self.instance is not None else None,
            )
            if effective is not None and attrs["old_price"] <= effective:
                raise serializers.ValidationError(
                    {"old_price": "The previous price must be higher than the current price."}
                )

        # --- image cap (Phase 14's upload pipeline enforces the same number)
        images = attrs.get("images")
        if images is not None and len(images) > settings.MAX_IMAGES_PER_LISTING:
            raise serializers.ValidationError(
                {"images": f"At most {settings.MAX_IMAGES_PER_LISTING} images per listing."}
            )

        if "attributes_json" in attrs:
            raw = attrs["attributes_json"]
        elif (
            self.instance is not None
            and attrs.get("category") is not None
            and attrs["category"] != self.instance.category
        ):
            # Re-filed without touching the attributes: what is stored must
            # still validate under the new category (its required/known keys),
            # or the listing would be quietly broken in its new subtree.
            raw = self.instance.attributes_json or {}
        else:
            raw = None

        if raw is not None:
            enforce_required = self._effective_status(attrs) not in (
                ListingStatus.DRAFT,
                ListingStatus.REJECTED,
            )
            try:
                attrs["attributes_json"] = validate_attributes(
                    category, raw, enforce_required=enforce_required
                )
            except DjangoValidationError as exc:
                if hasattr(exc, "message_dict"):
                    raise serializers.ValidationError(
                        {"attributes_json": exc.message_dict}
                    ) from exc
                raise serializers.ValidationError({"attributes_json": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        attributes_data = validated_data.pop("attributes", [])

        user = self.context["request"].user

        if self.context.get("listing_wizard"):
            # ---- Phase 13 classifieds path (apps/products/lifecycle.py is
            # the only thing that may take this row out of DRAFT).
            if validated_data.get("listing_type") == ListingType.STORE_PRODUCT:
                raise ApiError(
                    "Store products are posted from your seller dashboard.",
                    code="wrong_listing_type",
                    status_code=400,
                )
            drafts = Product.objects.filter(seller=user, status=ListingStatus.DRAFT).count()
            if drafts >= max_draft_listings():
                raise ApiError(
                    "You have too many saved drafts.",
                    code="draft_limit",
                    status_code=400,
                    details={"limit": max_draft_listings(), "drafts": drafts},
                )
            validated_data.setdefault("listing_type", ListingType.FOR_SALE)
            validated_data.setdefault("name", "")
            validated_data.setdefault("description", "")
            validated_data.setdefault("base_price", Decimal("0"))
            validated_data["seller"] = user
            validated_data["store"] = None
            validated_data["status"] = ListingStatus.DRAFT
        else:
            # ---- Store path (Phase 6/12 contract, unchanged except the
            # seller FK that Phase 13's ownership rules read).
            if not hasattr(user, "store"):
                raise serializers.ValidationError("You must have a store to create products")

            # Plan-based listing quota (free plan now; real plans in Phase 21)
            quota = get_product_quota(user)
            if quota is not None and user.store.products.count() >= quota:
                raise serializers.ValidationError(
                    f"You have reached the maximum limit of {quota} products for your plan"
                )

            validated_data["store"] = user.store
            validated_data["seller"] = user
            validated_data["listing_type"] = ListingType.STORE_PRODUCT

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

        name_changed = "name" in validated_data and validated_data["name"] != instance.name

        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if name_changed and instance.slug:
            # Canonical redirect when the slug changes: the slug follows the
            # name while the row is filed; old links keep resolving by id.
            _set_slug(instance)
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
