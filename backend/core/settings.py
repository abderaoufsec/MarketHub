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
    for name in ('.env.local', '.env'):
        path = BASE_DIR / name
        if path.is_file():
            return Config(RepositoryEnv(path))
    return Config(RepositoryEmpty())


env = _load_env()


def env_str(name: str, default: str = '') -> str:
    return env(name, default=default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, default=default, cast=bool)


def env_int(name: str, default: int = 0) -> int:
    return env(name, default=default, cast=int)


def env_list(name: str, default: str = '') -> list:
    return [item.strip() for item in env_str(name, default).split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------
# No insecure defaults: an unset key is an *empty* string, which the
# production fail-fast below rejects. Development only works with an env file.
SECRET_KEY = env_str('DJANGO_SECRET_KEY')

# Safe default: the project must never be reachable on the internet with DEBUG on.
DEBUG = env_bool('DEBUG', default=False)

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', default='localhost,127.0.0.1')

# Placeholders that ship in .env.example / older commits and must never be
# accepted as a production secret.
_PLACEHOLDER_SECRETS = frozenset({
    'django-insecure-dev-key-change-in-production',
    'your-secret-key-here-change-in-production',
    'your-secret-key-here',
    'changeme',
    'change-me',
    'secret',
})


def _secret_is_usable(value: str) -> bool:
    """A production secret must exist, be long enough and not be a placeholder."""
    lowered = value.lower()
    return bool(value) and (
        value not in _PLACEHOLDER_SECRETS
        and len(value) >= 32
        and 'insecure' not in lowered
        and 'change' not in lowered
        and 'example' not in lowered
        and 'your-secret' not in lowered
    )


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',

    # Local apps
    'apps.users',
    'apps.stores',
    'apps.products',
    'apps.inventory',
    'apps.orders',
    'apps.payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env_str('DB_NAME', 'markethub'),
        'USER': env_str('DB_USER', 'postgres'),
        'PASSWORD': env_str('DB_PASSWORD'),
        'HOST': env_str('DB_HOST', 'localhost'),
        'PORT': env_str('DB_PORT', '5432'),
        'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 0),
    }
}

# Custom User Model (declared exactly once)
AUTH_USER_MODEL = 'users.User'

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
    if not DATABASES['default']['PASSWORD']:
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
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ---------------------------------------------------------------------------
# Internationalization — Algeria-ready defaults (Phase 2)
# ---------------------------------------------------------------------------
# USE_L10N is not set: it was removed in Django 5.0, localized formatting is
# always enabled.
LANGUAGE_CODE = env_str('LANGUAGE_CODE', 'fr')

TIME_ZONE = env_str('TIME_ZONE', 'Africa/Algiers')

USE_I18N = True
USE_TZ = True

# Languages supported by the platform (Phase 11 wires the frontend switcher).
LANGUAGES = [
    ('ar', 'العربية'),
    ('fr', 'Français'),
    ('en', 'English'),
]

# Translations live in backend/locale/<lang>/LC_MESSAGES/django.po
LOCALE_PATHS = [BASE_DIR / 'locale']

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# REST Framework Configuration
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# JWT Settings
# NOTE: no AUTH_COOKIE* keys — SimpleJWT has no built-in cookie support; those
# options did nothing. Cookie-based auth is implemented deliberately in Phase 7.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=env_int('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=env_int('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7)
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ---------------------------------------------------------------------------
# CORS Settings
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
)

CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Email Configuration — env-driven (development default: console backend)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env_str(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = env_str('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env_str('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env_str('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env_str('DEFAULT_FROM_EMAIL', 'noreply@markethub.com')
EMAIL_TIMEOUT = env_int('EMAIL_TIMEOUT', 10)

# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------
# Free-plan listing quota. Per-plan quotas are stubbed in apps.users.plans and
# become real, upgradeable plans in Phase 21.
MAX_PRODUCTS_PER_SELLER = env_int('MAX_PRODUCTS_PER_SELLER', 20)

PLATFORM_COMMISSION_RATE = float(env_str('PLATFORM_COMMISSION_RATE', '0.15'))
SITE_URL = env_str('SITE_URL', 'http://localhost:8000')
FRONTEND_URL = env_str('FRONTEND_URL', 'http://localhost:3000')

# ---------------------------------------------------------------------------
# Logging — structured, console-based; never log secrets or raw exceptions
# to HTTP responses (views must log server-side instead).
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': env_str('LOG_LEVEL', 'INFO').upper(),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env_str('DJANGO_LOG_LEVEL', 'INFO').upper(),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': env_str('APPS_LOG_LEVEL', 'INFO').upper(),
            'propagate': False,
        },
    },
}
