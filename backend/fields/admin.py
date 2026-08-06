from django.contrib import admin

from backend.fields.models import AnalysisJob, BoundaryVersion, Field


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


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    """Costi AI per aggiornamento: visibilita' interna (non esposta in API)."""

    list_display = (
        "field",
        "owner",
        "status",
        "ai_cost_eur",
        "ai_tokens_in",
        "ai_tokens_out",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("field__name", "owner__email")
    readonly_fields = (
        "id",
        "field",
        "owner",
        "boundary_version",
        "status",
        "progress_step",
        "idempotency_key",
        "params",
        "result",
        "error",
        "celery_task_id",
        "attempts",
        "ai_tokens_in",
        "ai_tokens_out",
        "ai_cost_eur",
        "created_at",
        "started_at",
        "completed_at",
    )