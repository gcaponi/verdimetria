import uuid
from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import AnalysisJob, Field, Intervention

FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.61, 36.92],
        [14.61, 36.93],
        [14.60, 36.93],
        [14.60, 36.92],
    ]],
}

NDVI_POINTS: list[dict[str, Any]] = [
    {
        "date": "2026-07-06",
        "from": "2026-07-01T00:00:00Z",
        "to": "2026-07-06T00:00:00Z",
        "mean": 0.42,
        "min": 0.1,
        "max": 0.7,
        "stDev": 0.08,
        "p10": 0.3,
        "p50": 0.42,
        "p90": 0.6,
        "validPixels": 950,
    },
    {
        "date": "2026-07-11",
        "from": "2026-07-06T00:00:00Z",
        "to": "2026-07-11T00:00:00Z",
        "mean": 0.45,
        "min": 0.12,
        "max": 0.72,
        "stDev": 0.07,
        "p10": 0.32,
        "p50": 0.45,
        "p90": 0.62,
        "validPixels": 960,
    },
]

FULL_RESULT: dict[str, Any] = {
    "status": "ready",
    "analysisId": "0123456789abcdef",
    "generatedAt": "2026-07-28T10:15:00+00:00",
    "period": {"from": "2026-04-01", "to": "2026-07-28"},
    "area": {
        "hectares": 2.63,
        "centroid": [14.605, 36.925],
        "utmCrs": "EPSG:32633",
        "resolutionMeters": 10,
    },
    "catalog": {
        "sceneCount": 12,
        "latestAcquisition": "2026-07-26T09:50:00Z",
        "meanCloudCover": 8.4,
        "items": [],
    },
    "vegetation": {
        "points": NDVI_POINTS,
        "current": 0.45,
        "average": 0.435,
        "min": 0.42,
        "max": 0.45,
        "trend": 0.03,
        "validObservations": 2,
        "totalValidPixels": 1910,
    },
    "ndmi": {
        "points": NDVI_POINTS,
        "current": 0.31,
        "average": 0.295,
        "min": 0.28,
        "max": 0.31,
        "trend": 0.03,
        "validObservations": 2,
        "totalValidPixels": 1910,
    },
    "variability": {
        "date": "2026-07-11",
        "validPixels": 960,
        "weak": 10.0,
        "intermediate": 30.0,
        "vigorous": 60.0,
        "method": "histogram",
        "thresholds": {"weakMax": 0.3, "vigorousMin": 0.5},
        "note": "Classi di vigore da soglie NDVI convenzionali MVP: non sono una verita' agronomica.",
    },
    "terrain": {
        "elevation": {"min": 185.0, "max": 206.0, "mean": 195.5},
        "slope": {"mean": 6.4, "max": 9.6},
        "aspectDominant": "S",
        "resolutionMeters": 10,
        "source": "TINITALY 1.1 (INGV, CC BY 4.0)",
        "validPixels": 260,
    },
    "landCover": {
        "year": 2021,
        "source": "CLC+ Backbone",
        "resolutionMeters": 10,
        "dominantClass": 7,
        "classes": [
            {"code": 7, "label": "Erbacee periodiche (seminativi)", "share": 0.8, "hectares": 2.1},
            {"code": 4, "label": "Bosco di latifoglie sempreverdi", "share": 0.2, "hectares": 0.5},
        ],
        "validPixels": 260,
    },
    "ai": {
        "provider": "Verdimetria rules",
        "model": "evidence-rules-v1",
        "status": "fallback",
        "summary": "Sintesi di test con caratteri accentati àèéìòù.",
        "insights": [
            {
                "tone": "warn",
                "title": "Vigore disomogeneo <bozza> & note",
                "text": "Il 30% del campo e' in classe intermedia.",
                "evidence": "Variabilita' NDVI del 2026-07-11",
            }
        ],
    },
    "provenance": [
        {
            "provider": "Copernicus Data Space Ecosystem",
            "dataset": "Sentinel-2 L2A",
            "services": ["Catalog API", "Statistical API"],
            "quality": "SCL cloud/shadow mask + dataMask su NDVI e NDMI",
        },
        {
            "provider": "TINITALY 1.1 (INGV, CC BY 4.0)",
            "dataset": "Digital Elevation Model 10 m",
            "services": ["Download tile lazy"],
            "quality": "Feature morfometriche calcolate localmente sul poligono",
        },
    ],
    "disclaimer": (
        "Analisi osservativa da satellite: evidenzia pattern da verificare sul campo "
        "e non sostituisce sopralluogo, laboratorio o consulenza agronomica."
    ),
}

# Old demo-job format: no ndmi/variability/landCover optional blocks.
LEGACY_RESULT: dict[str, Any] = {
    key: value
    for key, value in FULL_RESULT.items()
    if key not in ("ndmi", "variability", "landCover")
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def field(api_client: APIClient, user: User) -> Field:
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo Vittoria", "crop": "Grano duro", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert response.status_code == 201
    return Field.objects.get(pk=response.data["id"])


def _completed_job(user: User, field: Field, result: dict[str, Any]) -> AnalysisJob:
    return AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=1,
        idempotency_key=uuid.uuid4().hex,
        params={},
        status=AnalysisJob.Status.COMPLETED,
        result=result,
        completed_at=timezone.now(),
    )


@pytest.mark.django_db
def test_report_pdf_served_for_completed_job(
    api_client: APIClient,
    user: User,
    field: Field,
    settings: Any,
    tmp_path: Any,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    job = _completed_job(user, field, FULL_RESULT)
    Intervention.objects.create(
        field=field,
        owner=user,
        kind="irrigation",
        date=date(2026, 7, 20),
        notes="2 ore goccia a goccia",
    )
    api_client.force_authenticate(user)

    response = api_client.get(f"/api/v1/jobs/{job.pk}/report.pdf")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert "verdimetria-report-" in response["Content-Disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 5_000
    assert len(list(tmp_path.glob("*.pdf"))) == 1


@pytest.mark.django_db
def test_report_pdf_forbidden_for_other_user(
    api_client: APIClient,
    user: User,
    field: Field,
    settings: Any,
    tmp_path: Any,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    job = _completed_job(user, field, FULL_RESULT)
    other = User.objects.create_user(email="other@example.com", password="StrongPass-2026!")
    api_client.force_authenticate(other)

    response = api_client.get(f"/api/v1/jobs/{job.pk}/report.pdf")

    assert response.status_code == 403


@pytest.mark.django_db
def test_report_pdf_unknown_job_returns_404(
    api_client: APIClient,
    user: User,
    settings: Any,
    tmp_path: Any,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    api_client.force_authenticate(user)

    response = api_client.get(f"/api/v1/jobs/{uuid.uuid4()}/report.pdf")

    assert response.status_code == 404


@pytest.mark.django_db
def test_report_pdf_conflict_when_job_not_completed(
    api_client: APIClient,
    user: User,
    field: Field,
    settings: Any,
    tmp_path: Any,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    api_client.force_authenticate(user)
    pending = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=1,
        idempotency_key=uuid.uuid4().hex,
        params={},
    )

    response = api_client.get(f"/api/v1/jobs/{pending.pk}/report.pdf")

    assert response.status_code == 409

    # A completed job without a result payload is not reportable either.
    pending.status = AnalysisJob.Status.COMPLETED
    pending.result = None
    pending.save(update_fields=("status", "result"))

    response = api_client.get(f"/api/v1/jobs/{pending.pk}/report.pdf")

    assert response.status_code == 409


@pytest.mark.django_db
def test_report_pdf_second_call_serves_from_cache(
    api_client: APIClient,
    user: User,
    field: Field,
    settings: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    builder = Mock(return_value=b"%PDF-1.4 fake-cached-bytes")
    monkeypatch.setattr("backend.fields.views.build_report_pdf", builder)
    job = _completed_job(user, field, FULL_RESULT)
    api_client.force_authenticate(user)

    first = api_client.get(f"/api/v1/jobs/{job.pk}/report.pdf")
    second = api_client.get(f"/api/v1/jobs/{job.pk}/report.pdf")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == b"%PDF-1.4 fake-cached-bytes"
    assert second.content == b"%PDF-1.4 fake-cached-bytes"
    builder.assert_called_once()
    assert len(list(tmp_path.glob("*.pdf"))) == 1


@pytest.mark.django_db
def test_report_pdf_handles_legacy_result_without_optional_blocks(
    api_client: APIClient,
    user: User,
    field: Field,
    settings: Any,
    tmp_path: Any,
) -> None:
    settings.REPORT_CACHE_DIR = str(tmp_path)
    job = _completed_job(user, field, LEGACY_RESULT)
    api_client.force_authenticate(user)

    response = api_client.get(f"/api/v1/jobs/{job.pk}/report.pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
