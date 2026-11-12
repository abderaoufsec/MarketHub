from django.contrib import admin

from .models import SavedSearch, SearchQuery


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "frequency",
        "is_active",
        "notify_email",
        "notify_sms",
        "notify_whatsapp",
        "last_notified_at",
        "created_at",
    )
    list_filter = ("frequency", "is_active", "notify_email", "notify_sms", "notify_whatsapp")
    search_fields = ("name", "user__email", "user__phone_number")
    readonly_fields = ("created_at", "updated_at", "last_notified_at")
    raw_id_fields = ("user",)


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    """Analytics rows: read-only, small, and the synonym backlog."""

    list_display = ("query", "normalized", "result_count", "zero_results", "user", "created_at")
    list_filter = ("zero_results", "created_at")
    search_fields = ("query", "normalized")
    readonly_fields = [field.name for field in SearchQuery._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
