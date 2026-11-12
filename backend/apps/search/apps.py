from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"
    verbose_name = "Search & discovery"

    def ready(self):
        from . import signals  # noqa: F401 - registers the publish alert hook
