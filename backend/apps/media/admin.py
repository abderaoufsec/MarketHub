from django.contrib import admin
from django.utils.html import format_html

from .models import Image


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "preview",
        "owner",
        "original_name",
        "dimensions",
        "size_bytes",
        "phash",
        "status",
        "created_at",
    )
    list_filter = ("status", "mime_type")
    search_fields = ("original_name", "owner__email", "phash", "checksum")
    readonly_fields = (
        "preview",
        "file",
        "original_name",
        "mime_type",
        "size_bytes",
        "width",
        "height",
        "checksum",
        "phash",
        "dominant_color",
        "lqip",
        "variants",
        "status",
        "created_at",
    )
    date_hierarchy = "created_at"

    @admin.display(description="Preview")
    def preview(self, obj):
        url = obj.url_for("thumb")
        if not url:
            return "—"
        return format_html('<img src="{}" alt="" style="height:48px;border-radius:4px;" />', url)

    @admin.display(description="Dimensions")
    def dimensions(self, obj):
        return f"{obj.width}x{obj.height}"
