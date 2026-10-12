from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        # Side-effect import: subclassing registers the extension in
        # drf-spectacular's registry at class-definition time, so the module
        # must be imported before /api/docs/ is generated — otherwise every
        # operation logs "could not resolve authenticator …".
        # This app deliberately has no *other* ready() imports: the post_save
        # receiver that duplicated the verification email (docs/todo.md
        # Phase 8) was deleted with signals.py. Keep the noqa on F401 — Ruff's
        # autofix once removed exactly this kind of import from ready()
        # (docs/todo.md Phase 5: the F401 fix "removed import
        # apps.users.signals from UsersConfig.ready()" and had to be restored
        # with an explicit suppression and a comment so it could not be
        # "cleaned up" a second time).
        from . import schema  # noqa: F401
