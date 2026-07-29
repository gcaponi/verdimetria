import uuid

from django.conf import settings
from django.contrib.gis.db import models


class Field(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fields",
    )
    name = models.CharField(max_length=160)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("owner", "-created_at"))]

    def __str__(self) -> str:
        return self.name


class BoundaryVersion(models.Model):
    class Source(models.TextChoices):
        DRAW = "draw", "Disegno mappa"
        UPLOAD = "upload", "Caricamento file"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name="boundaries",
    )
    version = models.PositiveIntegerField()
    geometry = models.MultiPolygonField(srid=4326)
    area_hectares = models.DecimalField(max_digits=14, decimal_places=4)
    metric_crs = models.CharField(max_length=16)
    source = models.CharField(max_length=16, choices=Source, default=Source.DRAW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=("field", "version"),
                name="fields_unique_boundary_version",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="fields_boundary_version_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.field.name} v{self.version}"


class AnalysisJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "In attesa"
        RUNNING = "running", "In esecuzione"
        COMPLETED = "completed", "Completato"
        FAILED = "failed", "Fallito"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name="analysis_jobs",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analysis_jobs",
    )
    boundary_version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status,
        default=Status.PENDING,
    )
    progress_step = models.CharField(max_length=32, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, unique=True)
    params = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=64, blank=True, default="")
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("owner", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.field.name} · {self.status}"


class Intervention(models.Model):
    """Voce del diario degli interventi agricoli sul campo (PRD: quaderno)."""

    class Kind(models.TextChoices):
        IRRIGATION = "irrigation", "Irrigazione"
        FERTILIZATION = "fertilization", "Concimazione"
        TREATMENT = "treatment", "Trattamento"
        SOWING = "sowing", "Semina"
        HARVEST = "harvest", "Raccolta"
        NOTE = "note", "Nota"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name="interventions",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interventions",
    )
    kind = models.CharField(max_length=16, choices=Kind)
    date = models.DateField()
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-date", "-created_at",)
        indexes = [models.Index(fields=("field", "-date"))]

    def __str__(self) -> str:
        return f"{self.field.name} · {self.get_kind_display()} · {self.date}"