import json
from typing import Any, cast

from django.db import transaction
from rest_framework import serializers
from rest_framework.request import Request

from backend.accounts.models import User
from backend.fields.models import AnalysisJob, BoundaryVersion, Field, Intervention
from backend.fields.services import append_boundary, ensure_italy_coverage
from src.domain import AnalysisArea


class InterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intervention
        fields = ("id", "kind", "date", "notes", "created_at")
        read_only_fields = ("id", "created_at")


class AnalysisJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisJob
        fields = (
            "id",
            "field",
            "status",
            "progress_step",
            "boundary_version",
            "params",
            "result",
            "error",
            "attempts",
            "created_at",
            "started_at",
            "completed_at",
        )
        read_only_fields = fields


class BoundaryVersionSerializer(serializers.ModelSerializer):
    geometry = serializers.SerializerMethodField()
    area_hectares = serializers.FloatField(read_only=True)

    class Meta:
        model = BoundaryVersion
        fields = (
            "id",
            "version",
            "geometry",
            "area_hectares",
            "metric_crs",
            "source",
            "created_at",
        )

    def get_geometry(self, boundary: BoundaryVersion) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(boundary.geometry.geojson))


class FieldSerializer(serializers.ModelSerializer):
    boundary = serializers.JSONField(write_only=True)
    boundary_source = serializers.ChoiceField(
        choices=BoundaryVersion.Source,
        default=BoundaryVersion.Source.DRAW,
        write_only=True,
    )
    latest_boundary = serializers.SerializerMethodField()

    class Meta:
        model = Field
        fields = (
            "id",
            "name",
            "boundary",
            "boundary_source",
            "latest_boundary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_boundary(self, value: dict[str, Any]) -> AnalysisArea:
        try:
            area = AnalysisArea.from_geojson("Campo", value)
            ensure_italy_coverage(area)
            return area
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError(str(error)) from error

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Field:
        area = cast(AnalysisArea, validated_data.pop("boundary"))
        source = str(validated_data.pop("boundary_source"))
        request = cast(Request, self.context["request"])
        owner = cast(User, request.user)
        field = Field.objects.create(owner=owner, **validated_data)
        append_boundary(field, area, source)
        return field

    def get_latest_boundary(self, field: Field) -> dict[str, Any] | None:
        boundary = field.boundaries.first()
        if boundary is None:
            return None
        return cast(dict[str, Any], BoundaryVersionSerializer(boundary).data)


class BoundaryCreateSerializer(serializers.Serializer):
    geometry = serializers.JSONField(write_only=True)
    source = serializers.ChoiceField(
        choices=BoundaryVersion.Source,
        default=BoundaryVersion.Source.DRAW,
    )

    def validate_geometry(self, value: dict[str, Any]) -> AnalysisArea:
        field = cast(Field, self.context["field"])
        try:
            area = AnalysisArea.from_geojson(field.name, value)
            ensure_italy_coverage(area)
            return area
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError(str(error)) from error

    def create(self, validated_data: dict[str, Any]) -> BoundaryVersion:
        field = cast(Field, self.context["field"])
        area = cast(AnalysisArea, validated_data["geometry"])
        return append_boundary(field, area, str(validated_data["source"]))