"""
Inventory Admin Configuration - Safe Version
"""

from django.contrib import admin

from .models import Inventory, InventoryAuditLog


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    """Inventory Management Admin"""

    list_display = ["id", "product", "stock_quantity", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["product__name", "product__store__store_name"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]


@admin.register(InventoryAuditLog)
class InventoryAuditLogAdmin(admin.ModelAdmin):
    """Inventory Audit Log Admin"""

    list_display = ["id", "product", "action_type", "quantity_delta", "timestamp"]
    list_filter = ["action_type", "timestamp"]
    search_fields = ["product__name", "reason"]
    ordering = ["-timestamp"]
    readonly_fields = ["timestamp"]
