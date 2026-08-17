import uuid
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.accounts.models import User
from backend.billing.services import BillingGateError, get_entitlements
from backend.fields.jobs import build_job_params, compute_idempotency_key
from backend.fields.models import AnalysisJob, AuditEntry, Field, Intervention
from backend.fields.report import build_report_pdf, cached_report_path
from backend.fields.serializers import (
    AnalysisJobSerializer,
    BoundaryCreateSerializer,
    BoundaryVersionSerializer,
    FieldSerializer,
    InterventionSerializer,
)
from backend.fields.tasks import run_analysis_job


class FieldViewSet(viewsets.ModelViewSet):
    serializer_class = FieldSerializer
    http_method_names = ("get", "post", "delete", "head", "options")

    def get_queryset(self) -> QuerySet[Field]:
        if self.request.user.is_anonymous:
            return Field.objects.none()
        return Field.objects.filter(owner=self.request.user).prefetch_related("boundaries")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        owner = cast(User, request.user)
        # Paywall pay-to-use: i campi sono un diritto di abbonamento.
        if not get_entitlements(owner)["subscribed"]:
            return Response(
                {"detail": "Abbonamento attivo richiesto per creare campi"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        # Demo fields are platform-managed and must not consume the user quota.
        owned_count = Field.objects.filter(owner=owner, is_demo=False).count()
        if owned_count >= settings.MAX_FIELDS_PER_ACCOUNT:
            return Response(
                {
                    "detail": (
                        f"Limite massimo di {settings.MAX_FIELDS_PER_ACCOUNT} "
                        "campi per account raggiunto"
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            return super().create(request, *args, **kwargs)
        except BillingGateError as error:
            # Quota ettari cumulativa del tier superata (vedi serializers).
            return Response(
                {"detail": BillingGateError.PUBLIC_MESSAGES[error.code]},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

    @action(detail=True, methods=("post",), url_path="boundaries")
    def create_boundary(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        serializer = BoundaryCreateSerializer(
            data=request.data,
            context={"request": request, "field": field},
        )
        serializer.is_valid(raise_exception=True)
        try:
            boundary = serializer.save()
        except BillingGateError as error:
            return Response(
                {"detail": BillingGateError.PUBLIC_MESSAGES[error.code]},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        return Response(BoundaryVersionSerializer(boundary).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"), url_path="jobs")
    def jobs(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        if request.method == "GET":
            queryset = field.analysis_jobs.all()
            return Response(AnalysisJobSerializer(queryset, many=True).data)
        return self._create_job(request, field)

    def _create_job(self, request: Request, field: Field) -> Response:
        # Paywall pay-to-use: l'analisi e' un diritto di abbonamento. I campi
        # demo restano interamente usabili (demo pubblica e interni).
        if not field.is_demo and not get_entitlements(cast(User, request.user))["subscribed"]:
            return Response(
                {"detail": "Abbonamento attivo richiesto per avviare analisi"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        data = request.data if isinstance(request.data, dict) else {}
        try:
            params = build_job_params(
                field,
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
            )
        except ValueError:
            return Response(
                {"detail": "Parametri analisi non validi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

    @action(detail=True, methods=("get", "post"), url_path="interventions")
    def interventions(self, request: Request, **kwargs: Any) -> Response:
        field = self.get_object()
        if request.method == "GET":
            queryset = field.interventions.all()
            return Response(InterventionSerializer(queryset, many=True).data)
        serializer = InterventionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(field=field, owner=cast(User, request.user))
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Cestino (Fase 2): tombstone, non hard delete. Recuperabile 30 giorni."""
        field = self.get_object()
        if field.is_demo:
            return Response(
                {"detail": "Il campo dimostrativo non e' cancellabile"},
                status=status.HTTP_409_CONFLICT,
            )
        actor = cast(User, request.user)
        reason = ""
        if isinstance(request.data, dict):
            reason = str(request.data.get("reason", ""))
        with transaction.atomic():
            field.soft_delete(actor=actor, reason=reason)
            AuditEntry.objects.create(
                action=AuditEntry.Action.DELETE,
                entity_type="field",
                entity_id=str(field.pk),
                actor=actor,
                reason=reason,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("get",), url_path="trash")
    def trash(self, request: Request) -> Response:
        """Campi cestinati dell'utente (recuperabili entro 30 giorni)."""
        queryset = Field.all_objects.filter(
            owner=request.user, deleted_at__isnull=False
        ).order_by("-deleted_at")
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=True, methods=("post",), url_path="restore")
    def restore(self, request: Request, **kwargs: Any) -> Response:
        """Ripristino controllato (Fase 2): solo owner, registrato nell'audit."""
        actor = cast(User, request.user)
        field = Field.all_objects.filter(owner=actor, pk=kwargs.get("pk")).first()
        if field is None:
            return Response(
                {"detail": "Campo non trovato"}, status=status.HTTP_404_NOT_FOUND
            )
        if field.deleted_at is None:
            return Response(
                {"detail": "Il campo non e' nel cestino"},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            field.restore()
            AuditEntry.objects.create(
                action=AuditEntry.Action.RESTORE,
                entity_type="field",
                entity_id=str(field.pk),
                actor=actor,
            )
        return Response(self.get_serializer(field).data)


class AnalysisJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnalysisJobSerializer
    http_method_names = ("get", "head", "options")

    def get_queryset(self) -> QuerySet[AnalysisJob]:
        if self.request.user.is_anonymous:
            return AnalysisJob.objects.none()
        # I job di campi cestinati scompaiono dalle viste ordinarie (Fase 2).
        return AnalysisJob.objects.filter(
            owner=self.request.user, field__deleted_at__isnull=True
        )


class InterventionViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """DELETE /api/v1/interventions/:id/ — cestino (Fase 2), solo proprietario."""
    serializer_class = InterventionSerializer
    http_method_names = ("delete", "head", "options")

    def get_queryset(self) -> QuerySet[Intervention]:
        if self.request.user.is_anonymous:
            return Intervention.objects.none()
        return Intervention.objects.filter(owner=self.request.user)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        intervention = self.get_object()
        actor = cast(User, request.user)
        reason = ""
        if isinstance(request.data, dict):
            reason = str(request.data.get("reason", ""))
        with transaction.atomic():
            intervention.soft_delete(actor=actor, reason=reason)
            AuditEntry.objects.create(
                action=AuditEntry.Action.DELETE,
                entity_type="intervention",
                entity_id=str(intervention.pk),
                actor=actor,
                reason=reason,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobReportView(APIView):
    """GET /api/v1/jobs/<id>/report.pdf — A4 agronomic report of a completed job.

    The PDF is generated server-side (reportlab) from the job result and cached
    on disk under settings.REPORT_CACHE_DIR; the cache key embeds completed_at,
    so a retried job re-completing with a new result invalidates it.
    """

    def get(self, request: Request, job_id: uuid.UUID, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            job = AnalysisJob.objects.select_related("field").get(pk=job_id)
        except AnalysisJob.DoesNotExist:
            return Response({"detail": "Job non trovato"}, status=status.HTTP_404_NOT_FOUND)
        if job.owner_id != request.user.pk:
            return Response(
                {"detail": "Non sei il proprietario di questo job"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if job.status != AnalysisJob.Status.COMPLETED or not job.result:
            return Response(
                {"detail": "Report disponibile solo per analisi completate"},
                status=status.HTTP_409_CONFLICT,
            )
        report_path = cached_report_path(job)
        if not report_path.exists():
            report_path.parent.mkdir(parents=True, exist_ok=True)
            for stale in report_path.parent.glob(f"{job.pk}-*.pdf"):
                stale.unlink()
            report_path.write_bytes(build_report_pdf(job))
        response = HttpResponse(report_path.read_bytes(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="verdimetria-report-{job.pk.hex[:16]}.pdf"'
        )
        return response


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
