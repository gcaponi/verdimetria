"""Django settings for the Verdimetria modular monolith."""

from __future__ import annotations

import os
import sys
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


DEBUG = env_bool("DJANGO_DEBUG", default=True)
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
    "COERCE_DECIMAL_TO_STRING": False,
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://verdimetria.cais.uno",
)

LANGUAGE_CODE = "it-it"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.postmarkapp.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", os.getenv("POSTMARK_SERVER_TOKEN", ""))
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", os.getenv("POSTMARK_SERVER_TOKEN", ""))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Verdimetria <noreply@localhost>")
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60