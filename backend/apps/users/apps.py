from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        # Side-effect import: registering the post_save receiver that sends
        # verification emails. Ruff's F401 autofix removed it once (Phase 5);
        # keep the noqa so it can never be "cleaned up" again.
        import apps.users.signals  # noqa: F401
