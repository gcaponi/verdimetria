import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone


class AliveManager(models.Manager):
    """Manager di default: solo record non cestinati (Fase 2 — cestino)."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteMixin(models.Model):
    """Tombstone: il DELETE applicativo diventa UPDATE con marca temporale.

    `objects` vede solo i record vivi; `all_objects` tutto (per trash/restore).
    Il purge definitivo dopo 30 giorni e' un job separato (management command).
    """

    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    delete_reason = models.CharField(max_length=200, blank=True, default="")

    objects = AliveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, actor=None, reason: str = "") -> None:
        self.deleted_at = timezone.now()
        self.deleted_by = actor
        self.delete_reason = reason
        update_fields = ["deleted_at", "deleted_by", "delete_reason"]
        if hasattr(self, "updated_at"):
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)

    def restore(self) -> None:
        self.deleted_at = None
        self.deleted_by = None
        self.delete_reason = ""
        update_fields = ["deleted_at", "deleted_by", "delete_reason"]
        if hasattr(self, "updated_at"):
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)


class AuditEntry(models.Model):
    """Traccia append-only delle operazioni sensibili (Fase 2).

    L'applicazione scrive soltanto; UPDATE/DELETE sono bloccati a livello DB
    dal guard (nessuna eccezione, nemmeno postgres).
    """

    class Action(models.TextChoices):
        DELETE = "delete", "Cestino"
        RESTORE = "restore", "Ripristino"
        PURGE = "purge", "Eliminazione definitiva"

    id = models.BigAutoField(primary_key=True)
    action = models.CharField(max_length=16, choices=Action)
    entity_type = models.CharField(max_length=32)
    entity_id = models.CharField(max_length=64)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reason = models.CharField(max_length=200, blank=True, default="")
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("entity_type", "entity_id"))]

    def __str__(self) -> str:
        return f"{self.action} · {self.entity_type} · {self.entity_id}"


class Field(SoftDeleteMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fields",
    )
    name = models.CharField(max_length=160)
    # Optional user-declared crop: interpretation metadata only, never required.
    crop = models.CharField(max_length=120, blank=True, default="")
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
    # Telemetria costo AI: valorizzata solo se DeepSeek ha risposto con
    # output valido; il fallback rule-based lascia i valori di default.
    ai_tokens_in = models.PositiveIntegerField(default=0)
    ai_tokens_out = models.PositiveIntegerField(default=0)
    ai_cost_eur = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("owner", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.field.name} · {self.status}"


class Intervention(SoftDeleteMixin):
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