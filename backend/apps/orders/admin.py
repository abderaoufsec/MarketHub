"""
Orders Admin Configuration - Safe Version
"""

from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """Inline for order items"""

    model = OrderItem
    extra = 0
    readonly_fields = ["product", "quantity", "unit_price_at_purchase"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Order Admin"""

    list_display = [
        "id",
        "user",
        "store",
        "total_amount",
        "order_status",
        "payment_status",
        "order_date",
    ]
    list_filter = ["order_status", "payment_status", "order_date"]
    search_fields = ["id", "user__email", "store__store_name"]
    ordering = ["-order_date"]
    readonly_fields = ["id", "order_date", "total_amount"]

    fieldsets = (
        ("Order Information", {"fields": ("id", "user", "store", "order_date")}),
        ("Order Details", {"fields": ("total_amount", "shipping_address", "shipping_method")}),
        ("Status", {"fields": ("order_status", "payment_status")}),
    )

    inlines = [OrderItemInline]

    actions = ["mark_processing", "mark_shipped", "mark_completed", "mark_cancelled"]

    def mark_processing(self, request, queryset):
        updated = queryset.update(order_status="PROCESSING")
        self.message_user(request, f"{updated} order(s) marked as processing.")

    mark_processing.short_description = "Mark as Processing"

    def mark_shipped(self, request, queryset):
        updated = queryset.update(order_status="SHIPPED")
        self.message_user(request, f"{updated} order(s) marked as shipped.")

    mark_shipped.short_description = "Mark as Shipped"

    def mark_completed(self, request, queryset):
        updated = queryset.update(order_status="COMPLETED")
        self.message_user(request, f"{updated} order(s) marked as completed.")

    mark_completed.short_description = "Mark as Completed"

    def mark_cancelled(self, request, queryset):
        updated = queryset.update(order_status="CANCELLED")
        self.message_user(request, f"{updated} order(s) cancelled.")

    mark_cancelled.short_description = "Cancel Orders"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Order Item Admin"""

    list_display = ["id", "order", "product", "quantity", "unit_price_at_purchase"]
    list_filter = ["order__order_date"]
    search_fields = ["order__id", "product__name"]
