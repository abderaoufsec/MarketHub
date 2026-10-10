"""
Products Admin Configuration - Safe Version
"""

from django.contrib import admin

from .models import Product, ProductAttribute, ProductImage


class ProductAttributeInline(admin.TabularInline):
    """Inline for product attributes"""

    model = ProductAttribute
    extra = 1
    fields = ["attribute_name", "attribute_value", "sku"]


class ProductImageInline(admin.TabularInline):
    """Inline for product images"""

    model = ProductImage
    extra = 1
    fields = ["image_url", "is_primary", "sort_order"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Product Admin"""

    list_display = ["id", "name", "store", "base_price", "category", "is_available", "created_at"]
    list_filter = ["is_available", "category", "created_at"]
    search_fields = ["name", "description", "store__store_name"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Product Information", {"fields": ("name", "description", "category")}),
        ("Store", {"fields": ("store",)}),
        ("Pricing", {"fields": ("base_price",)}),
        ("Inventory", {"fields": ("is_available", "low_stock_threshold")}),
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
