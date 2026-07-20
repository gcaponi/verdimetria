from django.contrib import admin

from backend.fields.models import BoundaryVersion, Field


class BoundaryVersionInline(admin.TabularInline):
    model = BoundaryVersion
    extra = 0
    readonly_fields = ("version", "area_hectares", "metric_crs", "source", "created_at")


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("name", "owner__email")
    inlines = (BoundaryVersionInline,)


@admin.register(BoundaryVersion)
class BoundaryVersionAdmin(admin.ModelAdmin):
    list_display = ("field", "version", "area_hectares", "metric_crs", "source", "created_at")
    list_filter = ("source", "metric_crs")
    search_fields = ("field__name", "field__owner__email")