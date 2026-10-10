"""
Custom Django Admin Configuration for MarketHub
Professional styling and enhanced functionality
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, mark_safe

from .models import Address, User


class AddressInline(admin.TabularInline):
    """Inline for user addresses"""

    model = Address
    extra = 0
    fields = ["address_line1", "city", "country", "is_default"]
    classes = ["collapse"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Enhanced User Admin"""

    list_display = [
        "email_display",
        "name_display",
        "role_badge",
        "status_badge",
        "store_link",
        "joined_date",
        "last_login_display",
    ]
    list_filter = ["is_seller", "is_verified", "is_active", "is_staff", "date_joined"]
    search_fields = ["email", "first_name", "last_name", "phone_number"]
    ordering = ["-date_joined"]
    readonly_fields = ["date_joined", "last_login", "id", "statistics_display"]

    fieldsets = (
        ("Account Information", {"fields": ("email", "password", "id")}),
        ("Personal Information", {"fields": ("first_name", "last_name", "phone_number")}),
        (
            "Permissions & Status",
            {
                "fields": ("is_seller", "is_verified", "is_active", "is_staff", "is_superuser"),
                "classes": ["collapse"],
            },
        ),
        ("Important Dates", {"fields": ("date_joined", "last_login"), "classes": ["collapse"]}),
        ("Statistics", {"fields": ("statistics_display",), "classes": ["collapse"]}),
    )

    inlines = [AddressInline]

    actions = ["verify_users", "unverify_users", "make_seller", "remove_seller"]

    def email_display(self, obj):
        """Display email with icon"""
        if obj and obj.email:
            icon = "📧"
            return format_html('<span style="font-weight: 500;">{} {}</span>', icon, obj.email)
        return "-"

    email_display.short_description = "Email"
    email_display.admin_order_field = "email"

    def name_display(self, obj):
        """Display full name"""
        if obj:
            name = obj.get_full_name() or "No name"
            return format_html('<span style="color: #2c3e50;">{}</span>', name)
        return "-"

    name_display.short_description = "Name"

    def role_badge(self, obj):
        """Display role with color badge"""
        if not obj:
            return "-"

        if obj.is_superuser:
            return mark_safe(
                '<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
                "color: white; padding: 4px 12px; border-radius: 12px; "
                'font-size: 11px; font-weight: 600;">👑 SUPERUSER</span>'
            )
        elif obj.is_staff:
            return mark_safe(
                '<span style="background: #3498db; color: white; padding: 4px 12px; '
                'border-radius: 12px; font-size: 11px; font-weight: 600;">🛡️ STAFF</span>'
            )
        elif obj.is_seller:
            return mark_safe(
                '<span style="background: #27ae60; color: white; padding: 4px 12px; '
                'border-radius: 12px; font-size: 11px; font-weight: 600;">🏪 SELLER</span>'
            )
        else:
            return mark_safe(
                '<span style="background: #95a5a6; color: white; padding: 4px 12px; '
                'border-radius: 12px; font-size: 11px; font-weight: 600;">👤 BUYER</span>'
            )

    role_badge.short_description = "Role"

    def status_badge(self, obj):
        """Display verification and active status"""
        if not obj:
            return "-"

        statuses = []

        if obj.is_verified:
            statuses.append(
                '<span style="background: #27ae60; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 10px; margin-right: 4px;">✓ Verified</span>'
            )
        else:
            statuses.append(
                '<span style="background: #e74c3c; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 10px; margin-right: 4px;">✗ Not Verified</span>'
            )

        if obj.is_active:
            statuses.append(
                '<span style="background: #2ecc71; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 10px;">● Active</span>'
            )
        else:
            statuses.append(
                '<span style="background: #95a5a6; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 10px;">○ Inactive</span>'
            )

        return mark_safe("".join(statuses))

    status_badge.short_description = "Status"

    def store_link(self, obj):
        """Link to store if seller"""
        if not obj:
            return "-"

        if obj.is_seller and hasattr(obj, "store") and obj.store:
            url = reverse("admin:stores_store_change", args=[obj.store.id])
            return format_html(
                '<a href="{}" style="color: #3498db; text-decoration: none; '
                'font-weight: 500;">🏪 {}</a>',
                url,
                obj.store.store_name,
            )
        elif obj.is_seller:
            return mark_safe(
                '<span style="color: #e67e22; font-style: italic;">No store created</span>'
            )
        return mark_safe('<span style="color: #95a5a6;">—</span>')

    store_link.short_description = "Store"

    def joined_date(self, obj):
        """Format join date"""
        if obj and obj.date_joined:
            return obj.date_joined.strftime("%b %d, %Y")
        return "-"

    joined_date.short_description = "Joined"
    joined_date.admin_order_field = "date_joined"

    def last_login_display(self, obj):
        """Format last login"""
        if obj and obj.last_login:
            return obj.last_login.strftime("%b %d, %Y %I:%M %p")
        return mark_safe('<span style="color: #95a5a6;">Never</span>')

    last_login_display.short_description = "Last Login"
    last_login_display.admin_order_field = "last_login"

    def statistics_display(self, obj):
        """Display user statistics"""
        if not obj:
            return "-"

        stats = []

        try:
            # Address count
            address_count = obj.addresses.count()
            stats.append(
                f'<div style="margin: 10px 0;"><strong>📍 Addresses:</strong> {address_count}</div>'
            )

            # If seller, show store stats
            if obj.is_seller and hasattr(obj, "store") and obj.store:
                store = obj.store
                product_count = store.products.count()
                order_count = store.orders.count() if hasattr(store, "orders") else 0

                stats.append(
                    f'<div style="margin: 10px 0;"><strong>📦 Products:</strong> {product_count}</div>'
                )
                stats.append(
                    f'<div style="margin: 10px 0;"><strong>🛒 Orders:</strong> {order_count}</div>'
                )
        except Exception as e:
            stats.append(f'<div style="color: #e74c3c;">Error: {e!s}</div>')

        return mark_safe("".join(stats))

    statistics_display.short_description = "Statistics"

    # Custom actions
    def verify_users(self, request, queryset):
        """Verify selected users"""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} user(s) verified successfully.")

    verify_users.short_description = "✓ Verify selected users"

    def unverify_users(self, request, queryset):
        """Unverify selected users"""
        updated = queryset.update(is_verified=False)
        self.message_user(request, f"{updated} user(s) unverified.")

    unverify_users.short_description = "✗ Unverify selected users"

    def make_seller(self, request, queryset):
        """Make users sellers"""
        updated = queryset.update(is_seller=True)
        self.message_user(request, f"{updated} user(s) made sellers.")

    make_seller.short_description = "🏪 Make selected users sellers"

    def remove_seller(self, request, queryset):
        """Remove seller status"""
        updated = queryset.update(is_seller=False)
        self.message_user(request, f"Seller status removed from {updated} user(s).")

    remove_seller.short_description = "❌ Remove seller status"


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Address Admin"""

    list_display = ["id", "user_link", "address_display", "city", "country", "default_badge"]
    list_filter = ["country", "is_default"]
    search_fields = ["user__email", "city", "address_line1"]
    ordering = ["-is_default", "user__email"]

    def user_link(self, obj):
        """Link to user"""
        if obj and obj.user:
            url = reverse("admin:users_user_change", args=[obj.user.id])
            return format_html('<a href="{}" style="color: #3498db;">{}</a>', url, obj.user.email)
        return "-"

    user_link.short_description = "User"

    def address_display(self, obj):
        """Format address"""
        if obj and obj.address_line1:
            return format_html('<div style="max-width: 300px;">{}</div>', obj.address_line1)
        return "-"

    address_display.short_description = "Address"

    def default_badge(self, obj):
        """Show if default"""
        if obj and obj.is_default:
            return mark_safe(
                '<span style="background: #27ae60; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 10px;">⭐ Default</span>'
            )
        return mark_safe('<span style="color: #95a5a6;">—</span>')

    default_badge.short_description = "Default"
