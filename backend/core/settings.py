"""
Django settings for MarketHub project.

Configuration is environment-driven (Phase 2 of docs/todo.md):

    1. real process environment variables   (highest priority)
    2. ``backend/.env.local``               (developer overrides, git-ignored)
    3. ``backend/.env``                     (shared defaults, git-ignored)

Copy ``backend/.env.example`` to ``backend/.env.local`` and edit the values.
With ``DEBUG=False`` the project refuses to boot until the production secrets
are present (see ``_check_production_secrets`` below).
"""

from datetime import timedelta
from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env() -> Config:
    """Return a config object for the first env file found, else env vars only."""
    for name in (".env.local", ".env"):
        path = BASE_DIR / name
        if path.is_file():
            return Config(RepositoryEnv(path))
    return Config(RepositoryEmpty())


env = _load_env()


def env_str(name: str, default: str = "") -> str:
    return env(name, default=default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, default=default, cast=bool)


def env_int(name: str, default: int = 0) -> int:
    return env(name, default=default, cast=int)


def env_list(name: str, default: str = "") -> list:
    return [item.strip() for item in env_str(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------
# No insecure defaults: an unset key is an *empty* string, which the
# production fail-fast below rejects. Development only works with an env file.
SECRET_KEY = env_str("DJANGO_SECRET_KEY")

# Safe default: the project must never be reachable on the internet with DEBUG on.
DEBUG = env_bool("DEBUG", default=False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default="localhost,127.0.0.1")

# Placeholders that ship in .env.example / older commits and must never be
# accepted as a production secret.
_PLACEHOLDER_SECRETS = frozenset(
    {
        "django-insecure-dev-key-change-in-production",
        "your-secret-key-here-change-in-production",
        "your-secret-key-here",
        "changeme",
        "change-me",
        "secret",
    }
)


def _secret_is_usable(value: str) -> bool:
    """A production secret must exist, be long enough and not be a placeholder."""
    lowered = value.lower()
    return bool(value) and (
        value not in _PLACEHOLDER_SECRETS
        and len(value) >= 32
        and "insecure" not in lowered
        and "change" not in lowered
        and "example" not in lowered
        and "your-secret" not in lowered
    )


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # GinIndex over Product.attributes_json (Phase 12) needs the postgres
    # app registered; it contributes no models of its own.
    "django.contrib.postgres",
    # Third party apps
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    # Local apps
    # "core" is the project config package: installing it puts its shared
    # helpers (and their management commands, e.g. compile_api_messages) on
    # Django's path. It defines no models, so it contributes no migrations.
    "core",
    # Geography first: apps.users.Address references its Wilaya/Commune.
    "apps.geography",
    "apps.catalog",
    "apps.users",
    "apps.stores",
    "apps.products",
    "apps.inventory",
    "apps.orders",
    "apps.payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # Phase 9: the request id + the error envelope. It must wrap the whole
    # stack so a failure raised in *any* inner middleware still carries the
    # contract, and so the id exists before the view (or the exception
    # handler) runs.
    "core.middleware.ApiContractMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # After Session, before Common — the documented placement. Without it
    # Accept-Language is ignored and every response would speak LANGUAGE_CODE.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("DB_NAME", "markethub"),
        "USER": env_str("DB_USER", "postgres"),
        "PASSWORD": env_str("DB_PASSWORD"),
        "HOST": env_str("DB_HOST", "localhost"),
        "PORT": env_str("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 0),
    }
}

# Custom User Model (declared exactly once)
AUTH_USER_MODEL = "users.User"

# ---------------------------------------------------------------------------
# Production fail-fast
# ---------------------------------------------------------------------------
if not DEBUG:
    _production_problems = []
    if not _secret_is_usable(SECRET_KEY):
        _production_problems.append(
            "DJANGO_SECRET_KEY is missing, shorter than 32 characters, or a "
            "placeholder from .env.example."
        )
    if not DATABASES["default"]["PASSWORD"]:
        _production_problems.append(
            "DB_PASSWORD is empty (database credentials are required when DEBUG=False)."
        )
    if _production_problems:
        raise ImproperlyConfigured(
            "MarketHub refuses to start with DEBUG=False and incomplete secrets:\n  - "
            + "\n  - ".join(_production_problems)
            + "\n\nFix it by copying backend/.env.example to backend/.env.local and "
            "setting real values, or by exporting the variables in the environment."
        )

# ---------------------------------------------------------------------------
# HTTPS posture (Phase 7 of docs/todo.md)
# ---------------------------------------------------------------------------
# Enabled whenever DEBUG is off; every value can be overridden per environment
# (e.g. a staging box behind plain HTTP, or a proxy that terminates TLS).
# `manage.py check --deploy` must be clean with these defaults.


def _https_settings(debug: bool) -> dict:
    if debug:
        # Development over plain HTTP: secure-only cookies and redirects would
        # break http://localhost:3000 -> http://localhost:8000.
        return {
            "SECURE_SSL_REDIRECT": env_bool("SECURE_SSL_REDIRECT", default=False),
            "SESSION_COOKIE_SECURE": env_bool("SESSION_COOKIE_SECURE", default=False),
            "CSRF_COOKIE_SECURE": env_bool("CSRF_COOKIE_SECURE", default=False),
            "SECURE_HSTS_SECONDS": env_int("SECURE_HSTS_SECONDS", default=0),
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
            "SECURE_HSTS_PRELOAD": False,
            "AUTH_COOKIE_SECURE": env_bool("AUTH_COOKIE_SECURE", default=False),
        }
    return {
        "SECURE_SSL_REDIRECT": env_bool("SECURE_SSL_REDIRECT", default=True),
        "SESSION_COOKIE_SECURE": env_bool("SESSION_COOKIE_SECURE", default=True),
        "CSRF_COOKIE_SECURE": env_bool("CSRF_COOKIE_SECURE", default=True),
        "SECURE_HSTS_SECONDS": env_int("SECURE_HSTS_SECONDS", default=31536000),
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True),
        "SECURE_HSTS_PRELOAD": env_bool("SECURE_HSTS_PRELOAD", default=True),
        "AUTH_COOKIE_SECURE": env_bool("AUTH_COOKIE_SECURE", default=True),
    }


globals().update(_https_settings(DEBUG))

# Hardened regardless of DEBUG — none of these break plain-HTTP development.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = env_str("SECURE_REFERRER_POLICY", "same-origin")
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = env_str("SESSION_COOKIE_SAMESITE", "Lax")
# The frontend must be able to read `csrftoken` to echo it as X-CSRFToken
# (double-submit). Only the JWT cookies below are HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = env_str("CSRF_COOKIE_SAMESITE", "Lax")

# Set when TLS terminates at a reverse proxy in front of the app.
if env_bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cross-origin cookie auth (Phase 7): the Next.js origin must be trusted for
# Django's Origin/Referer CSRF check on unsafe requests.
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
)

# SameSite policy for the HttpOnly JWT cookies. `Lax` covers same-site setups
# (www + api on one domain); a split-site deployment must set `None` (+ secure).
AUTH_COOKIE_SAMESITE = env_str("AUTH_COOKIE_SAMESITE", "Lax")

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization — Algeria-ready defaults (Phase 2)
# ---------------------------------------------------------------------------
# USE_L10N is not set: it was removed in Django 5.0, localized formatting is
# always enabled.
LANGUAGE_CODE = env_str("LANGUAGE_CODE", "fr")

TIME_ZONE = env_str("TIME_ZONE", "Africa/Algiers")

USE_I18N = True
USE_TZ = True

# Languages supported by the platform (Phase 11 wires the frontend switcher).
LANGUAGES = [
    ("ar", "العربية"),
    ("fr", "Français"),
    ("en", "English"),
]

# Translations live in backend/locale/<lang>/LC_MESSAGES/django.po
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# REST Framework Configuration
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Bearer header (API/mobile clients) *and* HttpOnly cookie + CSRF (web).
        "apps.users.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticatedOrReadOnly",),
    # Page numbers, which is what an order history or an audit trail needs
    # (people jump to page 3). The endless feeds opt into keyset pagination
    # per view instead — see core/pagination.py (Phase 10).
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Phase 9 — one error shape for every failure the DRF views raise
    # (core/exceptions.py renders {code, message, details, request_id}).
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    # Phase 9 — routes live under /api/v1/ (core/versioning.py).
    "VERSIONING_CLASS": "core.versioning.PathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # Phase 9 — OpenAPI generation (drf-spectacular renders /api/docs/).
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Phase 7 throttling: strict rates on the auth endpoints, a scoped
    # anti-scraping rate on endpoints that expose phone numbers. Only views
    # that opt in (throttle_classes) are throttled — there is deliberately no
    # global default, so ordinary API traffic is unaffected.
    # Phase 8 adds the OTP/social scopes (the per-number budgets that make
    # SMS pumping unprofitable live in apps.users.otp, on top of these).
    "DEFAULT_THROTTLE_RATES": {
        "login": env_str("THROTTLE_RATE_LOGIN", "10/min"),
        "register": env_str("THROTTLE_RATE_REGISTER", "10/hour"),
        "verify_email": env_str("THROTTLE_RATE_VERIFY_EMAIL", "20/hour"),
        "change_password": env_str("THROTTLE_RATE_CHANGE_PASSWORD", "5/hour"),
        "token_refresh": env_str("THROTTLE_RATE_TOKEN_REFRESH", "30/min"),
        "reveal_phone": env_str("THROTTLE_RATE_REVEAL_PHONE", "30/min"),
        "otp_request": env_str("THROTTLE_RATE_OTP_REQUEST", "30/hour"),
        "otp_verify": env_str("THROTTLE_RATE_OTP_VERIFY", "30/min"),
        "forgot_password": env_str("THROTTLE_RATE_FORGOT_PASSWORD", "10/hour"),
        "resend_verification": env_str("THROTTLE_RATE_RESEND_VERIFICATION", "10/hour"),
        "social_login": env_str("THROTTLE_RATE_SOCIAL_LOGIN", "10/hour"),
    },
}

# JWT Settings
# NOTE: no AUTH_COOKIE* keys here — SimpleJWT has no built-in cookie support
# (those options never did anything). The HttpOnly cookie flow is implemented
# deliberately in apps/users (CookieJWTAuthentication + set_auth_cookies).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# Cache — backs DRF throttling and the failed-login backoff (Phase 7).
# LocMem is per-process; Phase 22 swaps in Redis for shared/production use.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": env_str("CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": env_str("CACHE_LOCATION", "markethub"),
    }
}

# ---------------------------------------------------------------------------
# django-debug-toolbar (Phase 10) — opt-in, dev-only
# ---------------------------------------------------------------------------
# The SQL panel is how the query ceilings in tests/test_query_performance.py
# get *explained*: it lists every query a request made, with timings and the
# stack trace that issued each one. Off unless asked for (DEBUG_TOOLBAR=1) and
# even then it only renders when DEBUG is on and the request comes from
# INTERNAL_IPS, so tests, CI and production never import it — the app starts
# the same whether or not the package is installed.
# Install with: pip install -r requirements-dev.txt
if DEBUG and env_bool("DEBUG_TOOLBAR", default=False):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]
    INTERNAL_IPS = ["127.0.0.1", "localhost"]

# ---------------------------------------------------------------------------
# CORS Settings
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
)
# Cross-origin clients can only read response headers listed here. These are
# the Phase 9 contract: the correlation id, the throttle hint, the API version.
CORS_EXPOSE_HEADERS = env_list(
    "CORS_EXPOSE_HEADERS",
    # Idempotency-Replayed lets a browser client tell "created" from
    # "replayed" on the endpoints that take an Idempotency-Key.
    default="X-Request-ID, Retry-After, X-API-Version, Idempotency-Replayed, Location",
)

# ---------------------------------------------------------------------------
# OpenAPI (Phase 9) — /api/docs/ (Swagger UI), /api/redoc/, /api/schema/
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "MarketHub API",
    "DESCRIPTION": (
        "MarketHub is a classifieds/marketplace for Algeria.\n\n"
        "Every endpoint under `/api/v1/` answers a failure with the same envelope:\n\n"
        "```json\n"
        '{"code": "insufficient_stock", "message": "...", "details": null, "request_id": "..."}\n'
        "```\n\n"
        "`code` is stable and machine-readable (catalogue: `docs/error-codes.md`), "
        "`message` is translated according to `Accept-Language`, `details` carries "
        "field errors or structured extras, and `request_id` matches the "
        "`X-Request-ID` response header."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # One request schema per operation keeps the "Try it out" panel usable.
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    # Tags come from the URL (core/schema.py) so no route can ship untagged.
    "POSTPROCESSING_HOOKS": ["core.schema.tag_operations"],
}

CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Email Configuration — env-driven (development default: console backend)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env_str(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env_str("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "noreply@markethub.com")
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

# ---------------------------------------------------------------------------
# SMS / Phone OTP (Phase 8) — phone is the primary identity in Algeria.
# ---------------------------------------------------------------------------
# The transport is pluggable (apps.users.sms). Default mirrors the email
# console backend: the message is logged + appended to `outbox`, so dev and
# tests never pay for an SMS. Production sets a real gateway:
#   SMS_BACKEND=apps.users.sms.HttpJsonSmsBackend  (+ SMS_API_URL / SMS_API_KEY)
# A WhatsApp/Viber business API plugs in behind the same one-method class.
SMS_BACKEND = env_str("SMS_BACKEND", "apps.users.sms.ConsoleSmsBackend")
SMS_API_URL = env_str("SMS_API_URL")
SMS_API_KEY = env_str("SMS_API_KEY")
SMS_FROM = env_str("SMS_FROM", "MarketHub")
SMS_TIMEOUT = env_int("SMS_TIMEOUT", 10)

# OTP hardening: short, single-use, attempt-capped, budgeted per number/IP.
OTP_LENGTH = env_int("OTP_LENGTH", 6)
OTP_TTL_SECONDS = env_int("OTP_TTL_SECONDS", 300)
OTP_MAX_ATTEMPTS = env_int("OTP_MAX_ATTEMPTS", 5)
OTP_RESEND_COOLDOWN_SECONDS = env_int("OTP_RESEND_COOLDOWN_SECONDS", 60)
OTP_MAX_PER_PHONE_PER_DAY = env_int("OTP_MAX_PER_PHONE_PER_DAY", 5)
OTP_MAX_PER_IP_PER_DAY = env_int("OTP_MAX_PER_IP_PER_DAY", 20)

# ---------------------------------------------------------------------------
# Social login (Phase 8, optional) — empty means the provider answers 503.
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = env_str("GOOGLE_CLIENT_ID")
FACEBOOK_APP_ID = env_str("FACEBOOK_APP_ID")
FACEBOOK_APP_SECRET = env_str("FACEBOOK_APP_SECRET")
SOCIAL_HTTP_TIMEOUT = env_int("SOCIAL_HTTP_TIMEOUT", 10)

# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------
# Free-plan listing quota. Per-plan quotas are stubbed in apps.users.plans and
# become real, upgradeable plans in Phase 21.
MAX_PRODUCTS_PER_SELLER = env_int("MAX_PRODUCTS_PER_SELLER", 20)

# Phase 13 — listings lifecycle. The wizard's publish path reads these; the
# moderation flag routes publish through PENDING_REVIEW until an admin acts
# (Phase 17 turns it on and fills the queue).
LISTING_VALID_DAYS = env_int("LISTING_VALID_DAYS", 30)
LISTINGS_REQUIRE_MODERATION = env_bool("LISTINGS_REQUIRE_MODERATION", False)
MAX_ACTIVE_LISTINGS_PER_USER = env_int("MAX_ACTIVE_LISTINGS_PER_USER", 10)
MAX_DRAFT_LISTINGS = env_int("MAX_DRAFT_LISTINGS", 20)
MAX_IMAGES_PER_LISTING = env_int("MAX_IMAGES_PER_LISTING", 15)

PLATFORM_COMMISSION_RATE = float(env_str("PLATFORM_COMMISSION_RATE", "0.15"))
SITE_URL = env_str("SITE_URL", "http://localhost:8000")
FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:3000")

# ---------------------------------------------------------------------------
# Logging — structured, console-based; never log secrets or raw exceptions
# to HTTP responses (views must log server-side instead).
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env_str("LOG_LEVEL", "INFO").upper(),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env_str("DJANGO_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": env_str("APPS_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
    },
}
