"""Settings regression tests for the audit findings fixed in Phase 2.

docs/todo.md §0.3 #5/#6: dead AUTH_COOKIE* options, a duplicated
AUTH_USER_MODEL declaration, and insecure ``DB_PASSWORD``/``SECRET_KEY``
defaults baked into the source.
"""

from pathlib import Path

import pytest
from django.conf import settings

from core.settings import _secret_is_usable

SETTINGS_SOURCE = Path(__file__).with_name("settings.py").read_text(encoding="utf-8")


def test_secret_key_validation_rejects_placeholders():
    assert _secret_is_usable("") is False
    assert _secret_is_usable("django-insecure-dev-key-change-in-production") is False
    assert _secret_is_usable("your-secret-key-here-change-in-production") is False
    assert _secret_is_usable("short") is False


def test_secret_key_validation_accepts_a_real_key():
    assert _secret_is_usable("a" * 50) is True
    assert _secret_is_usable("Xk9$2mQ7pL0vR4tY8wN1bC6dF3gH5jS2aE") is True


def test_no_hardcoded_database_password():
    """§0.3 #6: DB_PASSWORD must never default to '12345' again."""
    assert "'12345'" not in SETTINGS_SOURCE
    assert '"12345"' not in SETTINGS_SOURCE


def test_auth_user_model_declared_exactly_once():
    """§0.3 #6: the duplicate AUTH_USER_MODEL line was removed."""
    assert SETTINGS_SOURCE.count("AUTH_USER_MODEL =") == 1
    assert settings.AUTH_USER_MODEL == "users.User"


def test_simple_jwt_has_no_dead_cookie_options():
    """§0.3 #5: AUTH_COOKIE* keys are not SimpleJWT options — they did nothing."""
    assert not [key for key in settings.SIMPLE_JWT if key.startswith("AUTH_COOKIE")]


def test_jwt_defaults_are_present():
    assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
    assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True


def test_algeria_locale_defaults():
    assert settings.LANGUAGE_CODE == "fr"
    assert settings.TIME_ZONE == "Africa/Algiers"
    assert [code for code, _ in settings.LANGUAGES] == ["ar", "fr", "en"]
    assert settings.LOCALE_PATHS
    assert settings.USE_I18N is True
    assert settings.USE_TZ is True


def test_email_backend_is_env_driven():
    assert isinstance(settings.EMAIL_BACKEND, str)
    assert "EMAIL_BACKEND" in SETTINGS_SOURCE


def test_logging_is_configured():
    assert settings.LOGGING["version"] == 1
    assert "console" in settings.LOGGING["handlers"]
    assert "django" in settings.LOGGING["loggers"]
    assert "apps" in settings.LOGGING["loggers"]


def test_cors_origins_are_a_list():
    assert isinstance(settings.CORS_ALLOWED_ORIGINS, list)
    assert settings.CORS_ALLOWED_ORIGINS


@pytest.mark.parametrize("app", ["users", "stores", "products", "inventory", "orders", "payments"])
def test_all_apps_installed(app):
    assert f"apps.{app}" in settings.INSTALLED_APPS
