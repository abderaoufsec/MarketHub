from django.contrib import admin
from mptt.admin import DraggableMPTTAdmin

from .models import AttributeDefinition, Category


class AttributeDefinitionInline(admin.TabularInline):
    """Edit a category's dynamic fields inline — the whole point of Phase 12:
    adding a category + its attributes in admin instantly yields the posting
    form and the filters, no deploy."""

    model = AttributeDefinition
    extra = 1
    fields = [
        "key",
        "type",
        "label_fr",
        "label_ar",
        "label_en",
        "required",
        "filterable",
        "unit",
        "order",
        "is_active",
    ]


@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin):
    """Drag-and-drop tree editing; ``list_display`` shows the indented name.

    ``AttributeDefinitionInline`` keeps the dynamic form's fields one click
    from the tree. Deactivating a node (``is_active``) hides it and its
    subtree publicly without touching anyone's data — prefer it to deletion,
    which is protected while products reference the category.
    """

    list_display = ["tree_actions", "indented_title", "slug", "order", "is_active"]
    list_editable = ["order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["slug", "name_fr", "name_ar", "name_en"]
    prepopulated_fields = {"slug": ("name_fr",)}
    inlines = [AttributeDefinitionInline]
    mptt_level_indent = 20


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    """Standalone listing for search/triage; day-to-day editing is the
    inline under the category."""

    list_display = ["key", "category", "type", "required", "filterable", "order", "is_active"]
    list_filter = ["type", "required", "filterable", "is_active", "category"]
    search_fields = ["key", "label_fr", "label_ar", "label_en"]
