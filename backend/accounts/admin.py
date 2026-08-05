from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import connection

from backend.accounts.models import User


@admin.register(User)
class VerdimetriaUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "complimentary_access")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profilo", {"fields": ("first_name", "last_name")}),
        (
            "Permessi",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "complimentary_access",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Date", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )

    def _enable_purge(self) -> None:
        """Abilita il purge SOLO per la transazione corrente.

        La guardia DB `verdimetria_guard` blocca i DELETE fuori da una sessione
        con `verdimetria.allow_purge=on`. L'eliminazione dall'admin e'
        esplicita e riservata a staff/superuser, quindi il bypass vale solo
        per questa transazione (SET LOCAL decade al commit/rollback).
        """
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL verdimetria.allow_purge = 'on'")

    def delete_model(self, request, obj):
        self._enable_purge()
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        self._enable_purge()
        super().delete_queryset(request, queryset)