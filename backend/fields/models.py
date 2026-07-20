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