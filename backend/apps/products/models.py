from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import (
    Avg,
    Count,
    Exists,
    FloatField,
    IntegerField,
    OuterRef,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from apps.stores.models import Store


class ProductQuerySet(models.QuerySet):
    """Query helpers that keep a page of products a *fixed* number of queries.

    The three numbers the API exposes for every product — total stock, rating
    average, review count — used to be model properties, so rendering a list
    of 20 rows ran 60 extra aggregate queries on top of the page itself. They
    are annotations now, and the properties are gone rather than left as a
    fallback: a list that silently degrades to per-row work is exactly the
    defect this exists to remove, so reading an un-annotated instance should
    fail loudly at ``AttributeError`` instead of quietly costing a query.

    Use ``Product.objects.with_catalog_stats()`` wherever
    :class:`~apps.products.serializers.ProductSerializer` or
    :class:`~apps.products.serializers.ProductListSerializer` will read them.
    """

    def with_stock(self):
        """Annotate ``total_stock``: the sum of every inventory row.

        A correlated **subquery**, not a join: ``with_catalog_stats`` also
        aggregates reviews, and joining both would cross-multiply the rows
        (stock x reviews) and inflate the sum.
        """
        # Imported here because apps.inventory imports Product at module level.
        from apps.inventory.models import Inventory

        totals = (
            Inventory.objects.filter(product=OuterRef("pk"))
            .order_by()
            .values("product")
            .annotate(total=Sum("stock_quantity"))
            .values("total")
        )
        return self.annotate(
            total_stock=Coalesce(Subquery(totals, output_field=IntegerField()), Value(0))
        )

    def with_ratings(self):
        """Annotate ``average_rating`` and ``review_count``.

        Counted over every review, matching the properties this replaces (the
        approved-only filter is the review *list* endpoint's business, not the
        aggregate's). Two subqueries rather than joins for the same
        cross-multiplication reason as :meth:`with_stock`.
        """
        reviews = ProductReview.objects.filter(product=OuterRef("pk")).order_by().values("product")
        return self.annotate(
            review_count=Coalesce(
                Subquery(reviews.annotate(n=Count("id")).values("n"), output_field=IntegerField()),
                Value(0),
            ),
            average_rating=Coalesce(
                Subquery(
                    reviews.annotate(avg=Avg("rating")).values("avg"),
                    output_field=FloatField(),
                ),
                Value(0.0),
            ),
        )

    def with_catalog_stats(self):
        """Every per-row number the product serializers expose, in one query."""
        return self.with_stock().with_ratings()

    def for_user(self, user):
        """Annotate ``is_wishlisted`` for one user.

        ``Exists`` rather than ``prefetch_related``: the wishlist can hold
        thousands of rows for an active user, and this only needs to know
        about the products on this page. Anonymous callers get a constant
        ``False`` so the serializer's shape does not depend on who asked.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return self.annotate(is_wishlisted=Value(False))
        return self.annotate(
            is_wishlisted=Exists(Wishlist.objects.filter(user=user, product=OuterRef("pk")))
        )


class Product(models.Model):
    """
    Core product model managed by sellers

    Per-row numbers (stock, rating, review count) come from
    :class:`ProductQuerySet`, never from a loop over instances.
    """

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=255)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Phase 12: the free-text ``category`` CharField became a FK into the
    # catalog tree. Nullable at the DB level only so rows migrated from the
    # legacy free text survive; the API requires it on create.
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
    )
    is_available = models.BooleanField(default=True)
    low_stock_threshold = models.IntegerField(default=5)
    # Dynamic per-category attributes (Phase 12), validated against the
    # category's effective AttributeDefinitions by
    # apps.catalog.validation.validate_attributes.
    attributes_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        indexes = [
            # The two real feeds: "available, newest first" (the catalogue)
            # and "in this category, newest first". Each also covers the bare
            # single-column filter it replaces, so those are gone — a write
            # pays for one index instead of two.
            models.Index(fields=["is_available", "-created_at"], name="products_available_newest"),
            models.Index(fields=["category", "-created_at"], name="products_category_newest"),
            # Ordering only: the admin and any unfiltered page of the feed.
            models.Index(fields=["-created_at"], name="products_newest"),
            # Phase 12: the dynamic attribute filters (?attr_<key>=…). GIN
            # over the jsonb keys/values; numeric min/max filters cast the
            # value and cannot use it (Phase 15's search work owns that
            # scale), but exact enum/boolean/text filters can.
            GinIndex(fields=["attributes_json"], name="products_attributes_gin"),
        ]

    def __str__(self):
        return self.name

    def is_low(self, total_stock=None):
        """Whether stock is at or below the product's own threshold.

        A business rule, so it is deliberately not an ORM expression: it is
        ``total_stock`` (whatever the caller already has) against this row's
        ``low_stock_threshold``. Pass the annotated total to avoid a query.
        """
        stock = self.total_stock if total_stock is None else total_stock
        return stock <= self.low_stock_threshold


def nested_product_queryset(user=None):
    """The queryset for a Product embedded inside another object.

    An order line and a cart line expose the same product fields the
    catalogue does, so they need the same annotations and the same image
    prefetch — only a ``Prefetch`` can supply them, because the nested
    object's own queryset is the one being evaluated::

        Order.objects.prefetch_related(
            Prefetch("items__product", queryset=nested_product_queryset(user))
        )

    Leaving it out costs three aggregates, one image query and one wishlist
    check *per line*, which is the shape of every N+1 this phase removed.
    """
    return (
        Product.objects.with_catalog_stats()
        .for_user(user)
        .select_related("store", "category")
        .prefetch_related("images")
    )


class ProductAttribute(models.Model):
    """
    Defines specific product variations like size, color
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attributes")
    attribute_name = models.CharField(max_length=100)
    attribute_value = models.CharField(max_length=100)
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_attributes"
        unique_together = ["product", "attribute_name", "attribute_value"]

    def __str__(self):
        return f"{self.product.name} - {self.attribute_name}: {self.attribute_value}"


class ProductImage(models.Model):
    """
    Stores URLs for product images
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField()
    is_primary = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_images"
        ordering = ["-is_primary", "sort_order"]

    def __str__(self):
        return f"{self.product.name} - Image {self.id}"

    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(
                is_primary=False
            )
        super().save(*args, **kwargs)


class ProductReview(models.Model):
    """
    Model for product reviews and ratings
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5 stars
    comment = models.TextField()
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_reviews"
        unique_together = ["product", "user"]  # One review per user per product
        ordering = ["-created_at"]
        indexes = [
            # The review list: filter by product, newest first. The unique
            # (product, user) constraint indexes a different pair and cannot
            # serve this ordering.
            models.Index(fields=["product", "-created_at"], name="reviews_product_newest"),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.product.name} ({self.rating} stars)"


class Wishlist(models.Model):
    """
    Model for user wishlists
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wishlists"
        unique_together = ["user", "product"]
        ordering = ["-added_at"]
        indexes = [
            # The wishlist list: this user's entries, newest first. The unique
            # (user, product) constraint indexes a different pair.
            models.Index(fields=["user", "-added_at"], name="wishlists_user_newest"),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.product.name}"
