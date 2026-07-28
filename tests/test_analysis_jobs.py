from typing import Any
from unittest.mock import Mock

import pytest
from celery.exceptions import MaxRetriesExceededError
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.jobs import build_job_params, compute_idempotency_key
from backend.fields.models import AnalysisJob, Field
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
                }
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
                            }
                        }
                    }
                }
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
    "provider": "Verdimetria rules",
    "model": "evidence-rules-v1",
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


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> User:
    return User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")


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
    monkeypatch.setattr("backend.fields.tasks.generate_insights", lambda metrics: AI_RESULT)


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
