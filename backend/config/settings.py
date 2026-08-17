"""Django settings for the Verdimetria modular monolith."""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from importlib import import_module
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def env_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).lower() in {"1", "true", "yes", "on"}


def bundled_library_path(directory: str, pattern: str) -> str | None:
    site_packages = (
        Path(sys.prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    candidates = sorted((site_packages / directory).glob(pattern))
    return str(candidates[0]) if candidates else None


def preload_bundled_geospatial_libraries() -> None:
    import_module("rasterio")
    import_module("shapely.geometry")


DEBUG = env_bool("DJANGO_DEBUG", default=False)
UNSAFE_LOCAL_SECRET = "unsafe-local-development-secret-key-only"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", UNSAFE_LOCAL_SECRET)
if not DEBUG and SECRET_KEY == UNSAFE_LOCAL_SECRET:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY e' obbligatoria quando DEBUG=false")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

GDAL_LIBRARY_PATH = os.getenv("GDAL_LIBRARY_PATH") or bundled_library_path(
    "rasterio.libs", "libgdal*.so*"
)
GEOS_LIBRARY_PATH = os.getenv("GEOS_LIBRARY_PATH") or bundled_library_path(
    "shapely.libs", "libgeos_c*.so*"
)
if GDAL_LIBRARY_PATH or GEOS_LIBRARY_PATH:
    preload_bundled_geospatial_libraries()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "corsheaders",
    "rest_framework",
    "backend.accounts",
    "backend.fields",
    "backend.billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "backend.config.wsgi.application"
ASGI_APPLICATION = "backend.config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.getenv("POSTGRES_DB", "verdimetria"),
        "USER": os.getenv("POSTGRES_USER", "verdimetria"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "verdimetria-local"),
        "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.getenv("POSTGRES_PORT", "5433"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "120/min",
        "auth": "10/min",
        "jobs": "10/hour",
    },
    "COERCE_DECIMAL_TO_STRING": False,
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://verdimetria.cais.uno",
)

# Chiave di firma JWT separata dal SECRET_KEY (Fase sicurezza 3): ruotabile
# senza toccare il segreto Django. Obbligatoria in produzione.
JWT_SIGNING_KEY = os.getenv("DJANGO_JWT_SIGNING_KEY", "").strip()
if not DEBUG and not JWT_SIGNING_KEY:
    raise ImproperlyConfigured("DJANGO_JWT_SIGNING_KEY e' obbligatoria quando DEBUG=false")
SIMPLE_JWT = {
    "SIGNING_KEY": JWT_SIGNING_KEY or SECRET_KEY,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

if not DEBUG and os.getenv("REDIS_URL"):
    _redis = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")
    if _redis.rsplit("/", 1)[-1].isdigit():
        _cache_redis = f"{_redis.rsplit('/', 1)[0]}/2"
    else:
        _cache_redis = f"{_redis.rstrip('/')}/2"
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _cache_redis,
        }
    }

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # nginx already terminates TLS; enable Django redirect only when asked
    # so the test suite (DEBUG=false against SQLite/PostGIS) does not 301.
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "it-it"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
# Fail-closed: in produzione il backend va dichiarato esplicitamente, cosi' un
# env mancante non puo' degradare i reset token nel console log/journal.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "").strip()
if not EMAIL_BACKEND:
    if DEBUG:
        EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    else:
        raise ImproperlyConfigured("EMAIL_BACKEND e' obbligatoria quando DEBUG=false")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.postmarkapp.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", os.getenv("POSTMARK_SERVER_TOKEN", ""))
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", os.getenv("POSTMARK_SERVER_TOKEN", ""))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Verdimetria <noreply@localhost>")
OPS_ALERT_EMAIL = os.getenv("OPS_ALERT_EMAIL", "")
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

REPORT_CACHE_DIR = os.getenv("REPORT_CACHE_DIR", BASE_DIR / "report-cache")

MAX_FIELDS_PER_ACCOUNT = int(os.getenv("MAX_FIELDS_PER_ACCOUNT", "3"))

# Paywall abbonamenti (Stripe). Vuoti in locale: checkout/webhook falliscono
# con errore esplicito, il gate 402 resta attivo per tutti i non abbonati.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
# Tier di abbonamento (price_id Stripe -> limite ettari). Il limite e'
# CUMULATIVO: somma delle aree dei boundary correnti di tutti i campi vivi
# dell'utente (None = illimitato). Vuoti in locale.
STRIPE_TIERS = {
    "basic": {
        "price_id": os.getenv("STRIPE_PRICE_BASIC", ""),
        "label": "Basic",
        "amount_eur_month": 14.99,
        "max_hectares": 5.0,
    },
    "pro": {
        "price_id": os.getenv("STRIPE_PRICE_PRO", ""),
        "label": "Pro",
        "amount_eur_month": 34.99,
        "max_hectares": 15.0,
    },
    "plus": {
        "price_id": os.getenv("STRIPE_PRICE_PLUS", ""),
        "label": "Plus",
        "amount_eur_month": 54.99,
        "max_hectares": None,
    },
}

# Purge del cestino (Fase 2): il purge e' annullato se il marker del backup
# pgBackRest piu' recente e' assente o piu' vecchio di PURGE_BACKUP_MAX_AGE_HOURS.
PURGE_BACKUP_MARKER = os.getenv("PURGE_BACKUP_MARKER", "/tmp/last-verdimetria-backup.txt")
PURGE_BACKUP_MAX_AGE_HOURS = int(os.getenv("PURGE_BACKUP_MAX_AGE_HOURS", "48"))
