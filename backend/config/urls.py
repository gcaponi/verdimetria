from django.contrib import admin
from django.urls import include, path

from backend.config.health import health, ready

urlpatterns = [
    path("health/", health, name="health"),
    path("ready/", ready, name="ready"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("backend.accounts.urls")),
    path("api/v1/billing/", include("backend.billing.urls")),
    path("api/v1/", include("backend.fields.urls")),
]
