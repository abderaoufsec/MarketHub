from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Category tree and dynamic attribute definitions (Phase 12)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    verbose_name = "Catalog"
