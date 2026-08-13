from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest
from celery.exceptions import MaxRetriesExceededError
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.jobs import build_job_params, compute_idempotency_key
from backend.fields.models import AnalysisJob, Field
from backend.fields.pipeline import (
    compute_vigor_variability,
    parse_statistics,
    summarize_ndmi,
)
from backend.fields.tasks import run_analysis_job
from src.ingestion.catalog_api import CatalogItem

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

STATISTICAL_PAYLOAD: dict[str, Any] = {
    "data": [
        {
            "interval": {"from": "2026-07-01T00:00:00Z", "to": "2026-07-06T00:00:00Z"},
            "outputs": {
                "ndvi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.42,
                                "min": 0.1,
                                "max": 0.7,
                                "stDev": 0.08,
                                "sampleCount": 1000,
                                "noDataCount": 50,
                                "percentiles": {"10.0": 0.3, "50.0": 0.42, "90.0": 0.6},
                            }
                        }
                    }
                },
                "ndmi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.28,
                                "min": 0.1,
                                "max": 0.45,
                                "stDev": 0.06,
                                "sampleCount": 1000,
                                "noDataCount": 50,
                                "percentiles": {"10.0": 0.15, "50.0": 0.28, "90.0": 0.4},
                            }
                        }
                    }
                },
            },
        },
        {
            "interval": {"from": "2026-07-06T00:00:00Z", "to": "2026-07-11T00:00:00Z"},
            "outputs": {
                "ndvi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.45,
                                "min": 0.12,
                                "max": 0.72,
                                "stDev": 0.07,
                                "sampleCount": 1000,
                                "noDataCount": 40,
                            },
                            "histogram": {
                                "bins": [
                                    {"lowEdge": 0.2, "highEdge": 0.3, "count": 96},
                                    {"lowEdge": 0.3, "highEdge": 0.4, "count": 288},
                                    {"lowEdge": 0.5, "highEdge": 0.6, "count": 576},
                                ],
                                "underflowCount": 0,
                                "overflowCount": 0,
                            },
                        }
                    }
                },
                "ndmi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.31,
                                "min": 0.12,
                                "max": 0.48,
                                "stDev": 0.05,
                                "sampleCount": 1000,
                                "noDataCount": 40,
                            }
                        }
                    }
                },
            },
        },
    ]
}

CATALOG_ITEMS = [
    CatalogItem(
        item_id="S2A_20260710",
        acquired_at="2026-07-10T09:30:00Z",
        cloud_cover=5.0,
        collection="sentinel-2-l2a",
        geometry={"type": "Polygon", "coordinates": []},
    )
]

AI_RESULT: dict[str, Any] = {
    "status": "fallback",
    "summary": "Sintesi di test",
    "insights": [],
}

TERRAIN_RESULT: dict[str, Any] = {
    "elevation": {"min": 10.0, "max": 25.0, "mean": 17.5},
    "slope": {"mean": 3.2, "max": 8.1},
    "aspectDominant": "SE",
    "resolutionMeters": 30,
    "validPixels": 30,
}

LAND_COVER_RESULT: dict[str, Any] = {
    "year": 2021,
    "source": "CLC+ Backbone",
    "resolutionMeters": 10,
    "dominantClass": 7,
    "classes": [
        {"code": 7, "label": "Erbacee periodiche (seminativi)", "share": 0.8, "hectares": 2.1},
        {"code": 4, "label": "Bosco di latifoglie sempreverdi", "share": 0.2, "hectares": 0.5},
    ],
    "validPixels": 260,
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def field(api_client: APIClient, user: User) -> Field:
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo Vittoria", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert response.status_code == 201
    return Field.objects.get(pk=response.data["id"])


@pytest.fixture
def delay_spy(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Evita la connessione a Redis: il task non parte davvero nei test API."""
    spy = Mock()
    monkeypatch.setattr("backend.fields.views.run_analysis_job.delay", spy)
    return spy


def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.fields.tasks.get_oauth_session", lambda: Mock())
    monkeypatch.setattr(
        "backend.fields.tasks.fetch_catalog_items", lambda *a, **k: CATALOG_ITEMS
    )
    monkeypatch.setattr(
        "backend.fields.tasks.fetch_ndvi_statistics", lambda *a, **k: STATISTICAL_PAYLOAD
    )
    monkeypatch.setattr("backend.fields.tasks.fetch_dem", lambda *a, **k: b"dem")
    monkeypatch.setattr(
        "backend.fields.tasks.compute_morphometry", lambda *a, **k: TERRAIN_RESULT
    )
    monkeypatch.setattr(
        "backend.fields.tasks.generate_insights", lambda metrics: (AI_RESULT, None)
    )


@pytest.mark.django_db
def test_create_job_uses_defaults_and_enqueues_task(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)

    response = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", {}, format="json")

    assert response.status_code == 201
    assert response.data["status"] == "pending"
    params = response.data["params"]
    assert params["boundary_version"] == 1
    assert params["max_cloud_cover"] == 20
    assert params["resolution_m"] == 10
    assert params["start_date"] < params["end_date"]
    job = AnalysisJob.objects.get(pk=response.data["id"])
    assert job.owner == user
    assert job.field == field
    delay_spy.assert_called_once_with(str(job.pk))


@pytest.mark.django_db
def test_create_job_is_idempotent_on_same_params(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)
    payload = {"start_date": "2026-01-01", "end_date": "2026-06-30"}

    first = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", payload, format="json")
    second = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert AnalysisJob.objects.count() == 1
    delay_spy.assert_called_once()


@pytest.mark.django_db
def test_failed_job_is_reenqueued_on_repost(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)
    payload = {"start_date": "2026-01-01", "end_date": "2026-06-30"}
    first = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", payload, format="json")
    AnalysisJob.objects.filter(pk=first.data["id"]).update(
        status=AnalysisJob.Status.FAILED, error="errore precedente"
    )

    second = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", payload, format="json")

    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert second.data["status"] == "pending"
    assert second.data["error"] == ""
    assert AnalysisJob.objects.count() == 1
    assert delay_spy.call_count == 2


@pytest.mark.django_db
def test_create_job_rejects_invalid_dates(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)

    bad_format = api_client.post(
        f"/api/v1/fields/{field.pk}/jobs/",
        {"start_date": "01/01/2026", "end_date": "2026-06-30"},
        format="json",
    )
    inverted = api_client.post(
        f"/api/v1/fields/{field.pk}/jobs/",
        {"start_date": "2026-06-30", "end_date": "2026-01-01"},
        format="json",
    )

    assert bad_format.status_code == 400
    assert inverted.status_code == 400
    assert AnalysisJob.objects.count() == 0
    delay_spy.assert_not_called()


@pytest.mark.django_db
def test_create_job_requires_boundary(api_client: APIClient, user: User, delay_spy: Mock) -> None:
    api_client.force_authenticate(user)
    empty_field = Field.objects.create(owner=user, name="Campo senza confine")

    response = api_client.post(f"/api/v1/fields/{empty_field.pk}/jobs/", {}, format="json")

    assert response.status_code == 400
    delay_spy.assert_not_called()


@pytest.mark.django_db
def test_jobs_are_isolated_by_owner(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)
    created = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", {}, format="json")
    other_user = User.objects.create_user(email="other@example.com", password="StrongPass-2026!")
    api_client.force_authenticate(other_user)

    list_response = api_client.get("/api/v1/jobs/")
    detail_response = api_client.get(f"/api/v1/jobs/{created.data['id']}/")
    field_jobs_response = api_client.get(f"/api/v1/fields/{field.pk}/jobs/")

    assert list_response.status_code == 200
    assert list_response.data == []
    assert detail_response.status_code == 404
    assert field_jobs_response.status_code == 404


@pytest.mark.django_db
def test_job_detail_is_readable_by_owner(
    api_client: APIClient,
    user: User,
    field: Field,
    delay_spy: Mock,
) -> None:
    api_client.force_authenticate(user)
    created = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", {}, format="json")

    detail = api_client.get(f"/api/v1/jobs/{created.data['id']}/")

    assert detail.status_code == 200
    assert detail.data["id"] == created.data["id"]
    assert detail.data["status"] == "pending"


@pytest.mark.django_db
def test_task_completes_job_with_field_analysis(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.progress_step == "done"
    assert job.attempts == 1
    assert job.started_at is not None
    assert job.completed_at is not None
    result = job.result
    assert result["status"] == "ready"
    assert result["vegetation"]["validObservations"] == 2
    assert result["catalog"]["sceneCount"] == 1
    assert result["terrain"] == TERRAIN_RESULT
    assert result["ai"] == AI_RESULT
    assert result["provenance"]
    # Fallback rule-based (usage None): nessun costo AI tracciato.
    assert job.ai_tokens_in == 0
    assert job.ai_tokens_out == 0
    assert job.ai_cost_eur == Decimal("0")

    # NDMI block mirrors the vegetation one (single Statistical request).
    ndmi = result["ndmi"]
    assert ndmi["current"] == 0.31
    assert ndmi["validObservations"] == 2
    assert ndmi["average"] == 0.295
    assert ndmi["totalValidPixels"] == 1910
    assert len(ndmi["points"]) == 2

    # Vigor variability from the latest observation's NDVI histogram.
    variability = result["variability"]
    assert variability["date"] == "2026-07-11"
    assert variability["method"] == "histogram"
    assert variability["validPixels"] == 960
    assert variability["weak"] == 10.0
    assert variability["intermediate"] == 30.0
    assert variability["vigorous"] == 60.0
    assert variability["thresholds"] == {"weakMax": 0.3, "vigorousMin": 0.5}
    assert "convenzionali" in variability["note"]

    # Aux point keys used for the derived blocks stay out of the contract.
    first_point = result["vegetation"]["points"][0]
    assert "ndmi" not in first_point
    assert "histogram" not in first_point
    assert "NDMI" in result["provenance"][0]["quality"]


AI_USAGE: dict[str, Any] = {"tokens_in": 1000, "tokens_out": 500, "model": "deepseek-v4-pro"}


@pytest.mark.django_db
def test_task_records_ai_usage_and_cost(
    monkeypatch: pytest.MonkeyPatch,
    api_client: APIClient,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(
        "backend.fields.tasks.generate_insights", lambda metrics: (AI_RESULT, AI_USAGE)
    )
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.ai_tokens_in == 1000
    assert job.ai_tokens_out == 500
    # (1000 + 500) token * 2.24 EUR/1M = 0.00336 EUR.
    assert job.ai_cost_eur == Decimal("0.003360")
    # Contratto API: i costi NON sono esposti all'utente (solo admin Django).
    api_client.force_authenticate(user)
    detail = api_client.get(f"/api/v1/jobs/{job.pk}/")
    assert "ai_tokens_in" not in detail.data
    assert "ai_tokens_out" not in detail.data
    assert "ai_cost_eur" not in detail.data


@pytest.mark.django_db
def test_task_fallback_leaves_ai_cost_fields_at_zero(
    monkeypatch: pytest.MonkeyPatch,
    api_client: APIClient,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)  # generate_insights ritorna usage None
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.ai_tokens_in == 0
    assert job.ai_tokens_out == 0
    assert job.ai_cost_eur == Decimal("0")
    # Anche nel fallback, token e costi restano dati operativi solo-admin.
    api_client.force_authenticate(user)
    detail = api_client.get(f"/api/v1/jobs/{job.pk}/")
    assert "ai_tokens_in" not in detail.data
    assert "ai_tokens_out" not in detail.data
    assert "ai_cost_eur" not in detail.data


@pytest.mark.django_db
def test_task_fails_without_retry_on_definitive_errors(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    # Statistical senza punti validi → ValueError definitivo, niente retry.
    monkeypatch.setattr("backend.fields.tasks.fetch_ndvi_statistics", lambda *a, **k: {"data": []})
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.FAILED
    assert "Nessuna osservazione NDVI" in job.error
    assert job.attempts == 1


@pytest.mark.django_db
def test_task_marks_failed_after_max_retries_on_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    import requests

    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(
        "backend.fields.tasks.fetch_catalog_items",
        Mock(side_effect=requests.Timeout("connessione scaduta")),
    )
    monkeypatch.setattr(
        run_analysis_job, "retry", Mock(side_effect=MaxRetriesExceededError())
    )
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.FAILED
    assert "non raggiungibile" in job.error


@pytest.mark.django_db
def test_completed_task_is_not_reexecuted(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )
    run_analysis_job.run(str(job.pk))
    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED

    # Seconda consegna dello stesso task (es. retry broker): deve essere un no-op.
    catalog_mock = Mock(return_value=CATALOG_ITEMS)
    monkeypatch.setattr("backend.fields.tasks.fetch_catalog_items", catalog_mock)
    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.attempts == 1
    catalog_mock.assert_not_called()


@pytest.mark.django_db
def test_task_includes_land_cover_when_raster_configured(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    monkeypatch.setenv("CLC_PLUS_RASTER_PATH", "/tmp/clc-plus.tif")
    monkeypatch.setattr(
        "backend.fields.tasks.compute_land_cover", lambda *a, **k: LAND_COVER_RESULT
    )
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.result["landCover"] == LAND_COVER_RESULT
    providers = [p["provider"] for p in job.result["provenance"]]
    assert "Copernicus Land Monitoring Service" in providers


@pytest.mark.django_db
def test_task_omits_land_cover_when_raster_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    monkeypatch.delenv("CLC_PLUS_RASTER_PATH", raising=False)
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert "landCover" not in job.result


TINITALY_RESULT: dict[str, Any] = {
    "elevation": {"min": 185.0, "max": 206.0, "mean": 195.5},
    "slope": {"mean": 6.4, "max": 9.6},
    "aspectDominant": "S",
    "resolutionMeters": 10,
    "source": "TINITALY 1.1 (INGV, CC BY 4.0)",
    "validPixels": 260,
}


@pytest.mark.django_db
def test_task_uses_tinitaly_when_cache_configured(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    monkeypatch.setenv("TINITALY_CACHE_DIR", "/tmp/tinitaly-cache")
    tinitaly_mock = Mock(return_value=TINITALY_RESULT)
    monkeypatch.setattr(
        "src.ingestion.tinitaly.compute_morphometry_tinitaly", tinitaly_mock
    )
    dem_mock = Mock(side_effect=AssertionError("non deve chiamare il DEM CDSE"))
    monkeypatch.setattr("backend.fields.tasks.fetch_dem", dem_mock)
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.result["terrain"] == TINITALY_RESULT
    tinitaly_mock.assert_called_once()
    providers = [p["provider"] for p in job.result["provenance"]]
    assert any("TINITALY" in p for p in providers)


@pytest.mark.django_db
def test_task_falls_back_to_cdse_dem_when_tinitaly_fails(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    _mock_pipeline(monkeypatch)
    monkeypatch.setenv("TINITALY_CACHE_DIR", "/tmp/tinitaly-cache")
    monkeypatch.setattr(
        "src.ingestion.tinitaly.compute_morphometry_tinitaly",
        Mock(side_effect=ValueError("tile non disponibile")),
    )
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.result["terrain"] == TERRAIN_RESULT


# --- Pure pipeline tests: NDMI block and vigor variability -------------------


def test_parse_statistics_extracts_ndmi_and_histogram() -> None:
    points = parse_statistics(STATISTICAL_PAYLOAD)

    assert len(points) == 2
    latest = points[-1]
    assert latest["mean"] == 0.45
    assert latest["ndmi"] == {
        "mean": 0.31,
        "min": 0.12,
        "max": 0.48,
        "stDev": 0.05,
        "p10": None,
        "p50": None,
        "p90": None,
        "validPixels": 960,
    }
    assert latest["histogram"]["bins"][0] == {"lowEdge": 0.2, "highEdge": 0.3, "count": 96}
    assert points[0]["histogram"] is None  # first interval carries no histogram


def test_summarize_ndmi_mirrors_vegetation_block() -> None:
    points = parse_statistics(STATISTICAL_PAYLOAD)

    ndmi = summarize_ndmi(points)

    assert ndmi is not None
    assert ndmi["current"] == 0.31
    assert ndmi["validObservations"] == 2
    assert ndmi["average"] == 0.295
    assert ndmi["min"] == 0.28
    assert ndmi["max"] == 0.31
    assert ndmi["totalValidPixels"] == 1910
    assert ndmi["points"][0]["date"] == "2026-07-06"
    assert ndmi["points"][0]["p50"] == 0.28
    assert ndmi["points"][1]["p50"] is None


def test_summarize_ndmi_returns_none_without_ndmi_output() -> None:
    payload = {
        "data": [
            {
                "interval": {"from": "2026-07-01T00:00:00Z", "to": "2026-07-06T00:00:00Z"},
                "outputs": {"ndvi": STATISTICAL_PAYLOAD["data"][0]["outputs"]["ndvi"]},
            }
        ]
    }

    points = parse_statistics(payload)

    assert points[0]["ndmi"] is None
    assert summarize_ndmi(points) is None


def test_variability_from_histogram_uses_real_pixel_counts() -> None:
    points = parse_statistics(STATISTICAL_PAYLOAD)

    variability = compute_vigor_variability(points)

    assert variability is not None
    assert variability["method"] == "histogram"
    assert variability["date"] == "2026-07-11"
    assert variability["validPixels"] == 960
    assert variability["weak"] == 10.0
    assert variability["intermediate"] == 30.0
    assert variability["vigorous"] == 60.0
    assert variability["thresholds"] == {"weakMax": 0.3, "vigorousMin": 0.5}
    assert "convenzionali" in variability["note"]


def test_variability_histogram_counts_underflow_and_overflow() -> None:
    point = _variability_point(
        histogram={
            "bins": [{"lowEdge": 0.5, "highEdge": 0.6, "count": 50}],
            "underflowCount": 40,
            "overflowCount": 10,
        }
    )

    variability = compute_vigor_variability([point])

    assert variability is not None
    assert variability["weak"] == 40.0
    assert variability["intermediate"] == 0.0
    assert variability["vigorous"] == 60.0


def test_variability_falls_back_to_percentile_approximation() -> None:
    # CDF through (0.1,0)-(0.3,10)-(0.42,50)-(0.6,90)-(0.7,100):
    # F(0.3)=10 -> weak 10%; F(0.5)=67.8 -> intermediate 57.8%, vigorous 32.2%.
    point = _variability_point(p10=0.3, p50=0.42, p90=0.6)

    variability = compute_vigor_variability([point])

    assert variability is not None
    assert variability["method"] == "percentile-approximation"
    assert variability["weak"] == 10.0
    assert variability["intermediate"] == 57.8
    assert variability["vigorous"] == 32.2


def test_variability_is_none_without_histogram_and_percentiles() -> None:
    point = _variability_point()

    assert compute_vigor_variability([point]) is None
    assert compute_vigor_variability([]) is None


def _variability_point(
    histogram: dict[str, Any] | None = None,
    p10: float | None = None,
    p50: float | None = None,
    p90: float | None = None,
) -> dict[str, Any]:
    return {
        "date": "2026-07-11",
        "from": "2026-07-06T00:00:00Z",
        "to": "2026-07-11T00:00:00Z",
        "mean": 0.42,
        "min": 0.1,
        "max": 0.7,
        "stDev": 0.08,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "validPixels": 950,
        "ndmi": None,
        "histogram": histogram,
    }
