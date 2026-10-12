from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    # No ready() side-effect import any more: the post_save receiver that
    # duplicated the verification email (docs/todo.md Phase 8) was deleted
    # with signals.py — registration now has exactly one flow, in views.py.
