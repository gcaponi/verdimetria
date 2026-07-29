from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.accounts.models import User
from backend.fields.jobs import build_job_params, compute_idempotency_key
from backend.fields.models import AnalysisJob, Field
from backend.fields.serializers import (
    AnalysisJobSerializer,
    BoundaryCreateSerializer,
    BoundaryVersionSerializer,
    FieldSerializer,
)
from backend.fields.tasks import run_analysis_job


class FieldViewSet(viewsets.ModelViewSet):
    serializer_class = FieldSerializer
    http_method_names = ("get", "post", "delete", "head", "options")

    def get_queryset(self) -> QuerySet[Field]:
        if self.request.user.is_anonymous:
            return Field.objects.none()
        return Field.objects.filter(owner=self.request.user).prefetch_related("boundaries")

    @action(detail=True, methods=("post",), url_path="boundaries")
    def create_boundary(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        serializer = BoundaryCreateSerializer(
            data=request.data,
            context={"request": request, "field": field},
        )
        serializer.is_valid(raise_exception=True)
        boundary = serializer.save()
        return Response(BoundaryVersionSerializer(boundary).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"), url_path="jobs")
    def jobs(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        if request.method == "GET":
            queryset = field.analysis_jobs.all()
            return Response(AnalysisJobSerializer(queryset, many=True).data)
        return self._create_job(request, field)

    def _create_job(self, request: Request, field: Field) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        try:
            params = build_job_params(
                field,
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        idempotency_key = compute_idempotency_key(field, params)
        with transaction.atomic():
            existing = (
                AnalysisJob.objects.select_for_update()
                .filter(idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                if existing.status == AnalysisJob.Status.FAILED:
                    # Il retry riusa lo stesso job: la chiave idempotente identifica
                    # l'analisi logica, il fallimento e' uno stato transitorio.
                    existing.status = AnalysisJob.Status.PENDING
                    existing.error = ""
                    existing.progress_step = ""
                    existing.completed_at = None
                    existing.save(
                        update_fields=("status", "error", "progress_step", "completed_at")
                    )
                    run_analysis_job.delay(str(existing.pk))
                return Response(
                    AnalysisJobSerializer(existing).data, status=status.HTTP_200_OK
                )

            owner = cast(User, request.user)
            try:
                job = AnalysisJob.objects.create(
                    field=field,
                    owner=owner,
                    boundary_version=params["boundary_version"],
                    idempotency_key=idempotency_key,
                    params=params,
                )
            except IntegrityError:
                # Race con una creazione concorrente: vince la richiesta arrivata prima.
                job = AnalysisJob.objects.get(idempotency_key=idempotency_key)
                return Response(AnalysisJobSerializer(job).data, status=status.HTTP_200_OK)

        run_analysis_job.delay(str(job.pk))
        return Response(
            AnalysisJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )


class AnalysisJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnalysisJobSerializer
    http_method_names = ("get", "head", "options")

    def get_queryset(self) -> QuerySet[AnalysisJob]:
        if self.request.user.is_anonymous:
            return AnalysisJob.objects.none()
        return AnalysisJob.objects.filter(owner=self.request.user)


class DemoAnalysisView(APIView):
    """Campo dimostrativo pubblico (PRD 9.2): read-only, nessuna autenticazione.

    Serve l'ultimo job completato del campo marcato `is_demo`, con il confine
    per la visualizzazione su mappa. Mai dati di campi utente reali.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        field = Field.objects.filter(is_demo=True).order_by("-created_at").first()
        if field is None:
            return Response(
                {"detail": "Campo dimostrativo non configurato"},
                status=status.HTTP_404_NOT_FOUND,
            )
        job = (
            field.analysis_jobs.filter(status=AnalysisJob.Status.COMPLETED)
            .order_by("-completed_at")
            .first()
        )
        if job is None:
            return Response(
                {"detail": "Analisi dimostrativa non ancora disponibile"},
                status=status.HTTP_404_NOT_FOUND,
            )
        boundary = field.boundaries.first()
        return Response({
            "field": {
                "id": str(field.pk),
                "name": field.name,
                "boundary": BoundaryVersionSerializer(boundary).data if boundary else None,
            },
            "analysis": job.result,
            "generatedAt": job.completed_at,
        })
