"""
Store Admin Configuration
"""

from django.contrib import admin
from django.db.models import Avg, Sum
from django.urls import reverse
from django.utils.html import format_html, mark_safe

from .models import Store


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """Professional Store Admin"""

    list_display = [
        "store_badge",
        "owner_link",
        "category_badge",
        "status_badge",
        "stats_display",
        "created_display",
    ]
    list_filter = ["category", "is_active", "created_at"]
    search_fields = ["store_name", "store_slug", "owner__email", "description"]
    ordering = ["-created_at"]
    readonly_fields = ["store_slug", "created_at", "updated_at", "detailed_stats", "preview_link"]

    fieldsets = (
        ("Store Information", {"fields": ("store_name", "store_slug", "description", "category")}),
        ("Owner", {"fields": ("owner",)}),
        ("Branding", {"fields": ("logo_url", "banner_image_url"), "classes": ["collapse"]}),
        ("Status", {"fields": ("is_active",)}),
        ("Dates", {"fields": ("created_at", "updated_at"), "classes": ["collapse"]}),
        ("Statistics & Analytics", {"fields": ("detailed_stats",), "classes": ["collapse"]}),
        ("Preview", {"fields": ("preview_link",)}),
    )

    actions = ["activate_stores", "deactivate_stores"]

    def store_badge(self, obj):
        """Display store name with icon"""
        if obj:
            icon = "🏪"
            return format_html(
                '<div style="font-weight: 600; color: #2c3e50;">{} {}</div>'
                '<div style="font-size: 11px; color: #7f8c8d; margin-top: 2px;">{}</div>',
                icon,
                obj.store_name,
                obj.store_slug,
            )
        return "-"

    store_badge.short_description = "Store"
    store_badge.admin_order_field = "store_name"

    def owner_link(self, obj):
        """Link to owner"""
        if obj and obj.owner:
            url = reverse("admin:users_user_change", args=[obj.owner.id])
            owner_name = obj.owner.get_full_name() or "No name"
            return format_html(
                '<a href="{}" style="color: #3498db; text-decoration: none;">'
                '<div style="font-weight: 500;">{}</div>'
                '<div style="font-size: 11px; color: #7f8c8d;">{}</div>'
                "</a>",
                url,
                owner_name,
                obj.owner.email,
            )
        return "-"

    owner_link.short_description = "Owner"

    def category_badge(self, obj):
        """Display category with color"""
        if not obj:
            return "-"

        colors = {
            "electronics": "#3498db",
            "fashion": "#e91e63",
            "home": "#27ae60",
            "books": "#f39c12",
            "sports": "#1abc9c",
            "toys": "#9b59b6",
            "food": "#e67e22",
            "beauty": "#ff6b9d",
            "other": "#95a5a6",
        }
        color = colors.get(obj.category, "#95a5a6")
        display = (
            obj.get_category_display() if hasattr(obj, "get_category_display") else obj.category
        )
        return format_html(
            '<span style="background: {}; color: white; padding: 5px 12px; '
            "border-radius: 12px; font-size: 11px; font-weight: 600; "
            'text-transform: uppercase;">{}</span>',
            color,
            display,
        )

    category_badge.short_description = "Category"
    category_badge.admin_order_field = "category"

    def status_badge(self, obj):
        """Display active status"""
        if not obj:
            return "-"

        if obj.is_active:
            return mark_safe(
                '<span style="background: #27ae60; color: white; padding: 5px 12px; '
                'border-radius: 12px; font-size: 11px; font-weight: 600;">'
                "✓ ACTIVE</span>"
            )
        return mark_safe(
            '<span style="background: #e74c3c; color: white; padding: 5px 12px; '
            'border-radius: 12px; font-size: 11px; font-weight: 600;">'
            "✗ INACTIVE</span>"
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "is_active"

    def stats_display(self, obj):
        """Quick stats display"""
        if not obj:
            return "-"

        try:
            product_count = obj.products.count() if hasattr(obj, "products") else 0
            order_count = obj.orders.count() if hasattr(obj, "orders") else 0

            return format_html(
                '<div style="font-size: 12px;">'
                '<div style="margin: 2px 0;">📦 <strong>{}</strong> products</div>'
                '<div style="margin: 2px 0;">🛒 <strong>{}</strong> orders</div>'
                "</div>",
                product_count,
                order_count,
            )
        except Exception:
            return mark_safe('<span style="color: #95a5a6;">—</span>')

    stats_display.short_description = "Quick Stats"

    def created_display(self, obj):
        """Format creation date"""
        if obj and obj.created_at:
            return obj.created_at.strftime("%b %d, %Y")
        return "-"

    created_display.short_description = "Created"
    created_display.admin_order_field = "created_at"

    def detailed_stats(self, obj):
        """Detailed statistics"""
        if not obj:
            return "-"

        try:
            product_count = obj.products.count() if hasattr(obj, "products") else 0
            active_products = (
                obj.products.filter(is_available=True).count() if hasattr(obj, "products") else 0
            )
            order_count = obj.orders.count() if hasattr(obj, "orders") else 0

            # Revenue calculation
            revenue = 0
            avg_order = 0
            if hasattr(obj, "orders"):
                revenue_data = obj.orders.filter(payment_status="SUCCESSFUL").aggregate(
                    total=Sum("total_amount")
                )
                revenue = revenue_data["total"] or 0

                avg_data = obj.orders.filter(payment_status="SUCCESSFUL").aggregate(
                    avg=Avg("total_amount")
                )
                avg_order = avg_data["avg"] or 0

            html = f"""
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;
                        border-left: 4px solid #3498db;">
                <h3 style="margin-top: 0; color: #2c3e50;">📊 Store Analytics</h3>

                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <div style="color: #7f8c8d; font-size: 12px;">TOTAL PRODUCTS</div>
                        <div style="font-size: 24px; font-weight: bold; color: #3498db;">
                            {product_count}
                        </div>
                        <div style="color: #27ae60; font-size: 11px; margin-top: 4px;">
                            {active_products} active
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <div style="color: #7f8c8d; font-size: 12px;">TOTAL ORDERS</div>
                        <div style="font-size: 24px; font-weight: bold; color: #9b59b6;">
                            {order_count}
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <div style="color: #7f8c8d; font-size: 12px;">TOTAL REVENUE</div>
                        <div style="font-size: 24px; font-weight: bold; color: #27ae60;">
                            ${revenue:,.2f}
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <div style="color: #7f8c8d; font-size: 12px;">AVG ORDER VALUE</div>
                        <div style="font-size: 24px; font-weight: bold; color: #e67e22;">
                            ${avg_order:,.2f}
                        </div>
                    </div>
                </div>
            </div>
            """

            return mark_safe(html)
        except Exception as e:
            return format_html('<div style="color: #e74c3c;">Error loading stats: {}</div>', str(e))

    detailed_stats.short_description = "Detailed Analytics"

    def preview_link(self, obj):
        """Link to frontend store"""
        if obj:
            url = f"http://localhost:3000/stores/{obj.store_slug}"
            return format_html(
                '<a href="{}" target="_blank" style="display: inline-block; '
                "background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); "
                "color: white; padding: 10px 20px; border-radius: 6px; "
                'text-decoration: none; font-weight: 600;">'
                "🌐 View Store on Website</a>",
                url,
            )
        return "-"

    preview_link.short_description = "Preview"

    # Actions
    def activate_stores(self, request, queryset):
        """Activate selected stores"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} store(s) activated.")

    activate_stores.short_description = "✓ Activate selected stores"

    def deactivate_stores(self, request, queryset):
        """Deactivate selected stores"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} store(s) deactivated.")

    deactivate_stores.short_description = "✗ Deactivate selected stores"
