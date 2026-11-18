"""
Products Admin Configuration - Safe Version
"""

from django.contrib import admin

from .models import Product, ProductAttribute, ProductImage, ProductReview


class ProductAttributeInline(admin.TabularInline):
    """Inline for product attributes"""

    model = ProductAttribute
    extra = 1
    fields = ["attribute_name", "attribute_value", "sku"]


class ProductImageInline(admin.TabularInline):
    """Inline for product images"""

    model = ProductImage
    extra = 1
    fields = ["upload", "image_url", "is_primary", "sort_order"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Product Admin — Phase 13 exposes the listing surface.

    ``seller`` belongs to the *add* form on purpose: the column is NOT NULL
    and only the form supplies it, so leaving it out would turn every admin
    add into an IntegrityError.
    """

    list_display = [
        "id",
        "name",
        "listing_type",
        "status",
        "store",
        "seller",
        "base_price",
        "category",
        "is_available",
        "created_at",
    ]
    list_filter = ["status", "listing_type", "is_available", "category", "created_at"]
    search_fields = ["name", "description", "store__store_name", "seller__email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Product Information", {"fields": ("name", "description", "category")}),
        ("Listing", {"fields": ("seller", "listing_type", "status", "contact_mode", "slug")}),
        ("Store", {"fields": ("store",)}),
        (
            "Pricing",
            {"fields": ("base_price", "price_mode", "old_price", "currency")},
        ),
        ("Location", {"fields": ("wilaya", "commune")}),
        ("Inventory", {"fields": ("is_available", "low_stock_threshold")}),
        (
            "Lifecycle",
            {"fields": ("published_at", "expires_at", "sold_at"), "classes": ["collapse"]},
        ),
        (
            "Moderation (Phase 17)",
            {
                "fields": (
                    "rejection_reason",
                    "moderation_flags",
                    "moderated_at",
                    "moderated_by",
                ),
                "classes": ["collapse"],
            },
        ),
        ("Additional Attributes", {"fields": ("attributes_json",), "classes": ["collapse"]}),
        ("Dates", {"fields": ("created_at", "updated_at"), "classes": ["collapse"]}),
    )

    inlines = [ProductImageInline, ProductAttributeInline]

    actions = ["make_available", "make_unavailable"]

    def make_available(self, request, queryset):
        """Make products available"""
        updated = queryset.update(is_available=True)
        self.message_user(request, f"{updated} product(s) made available.")

    make_available.short_description = "Make available"

    def make_unavailable(self, request, queryset):
        """Make products unavailable"""
        updated = queryset.update(is_available=False)
        self.message_user(request, f"{updated} product(s) made unavailable.")

    make_unavailable.short_description = "Make unavailable"


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    """Product Attribute Admin"""

    list_display = ["id", "product", "attribute_name", "attribute_value", "sku"]
    list_filter = ["attribute_name"]
    search_fields = ["product__name", "attribute_name", "attribute_value", "sku"]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Product Image Admin"""

    list_display = ["id", "product", "is_primary", "sort_order", "created_at"]
    list_filter = ["is_primary"]
    search_fields = ["product__name"]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """Phase 17: reviews are moderated, so they need a queue of their own."""

    list_display = (
        "id",
        "product",
        "user",
        "rating",
        "is_approved",
        "is_verified_purchase",
        "created_at",
    )
    list_filter = ("is_approved", "is_verified_purchase", "rating")
    search_fields = ("product__name", "user__email", "comment")
    raw_id_fields = ("product", "user")
    actions = ["approve_reviews", "reject_reviews"]

    def approve_reviews(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(
            is_approved=True,
            moderated_at=timezone.now(),
            moderation_note="approved in admin",
        )
        self.message_user(request, f"{updated} review(s) approved.")

    approve_reviews.short_description = "Approve selected reviews"

    def reject_reviews(self, request, queryset):
        updated = queryset.update(
            is_approved=False,
            moderation_note="rejected in admin",
        )
        self.message_user(request, f"{updated} review(s) hidden.")

    reject_reviews.short_description = "Hide selected reviews"
