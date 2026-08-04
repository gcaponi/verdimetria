from typing import Any

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import AnalysisJob, Field

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

SPAIN_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [-3.70, 40.41],
        [-3.69, 40.41],
        [-3.69, 40.42],
        [-3.70, 40.42],
        [-3.70, 40.41],
    ]],
}

ANALYSIS_RESULT: dict[str, Any] = {
    "status": "ready",
    "analysisId": "demo123",
    "vegetation": {"validObservations": 25},
    "terrain": {"slope": {"mean": 2.9}},
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_demo_endpoint_404_without_demo_field(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/demo/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_demo_endpoint_serves_completed_job_without_auth(
    api_client: APIClient, user: User
) -> None:
    api_client.force_authenticate(user)
    create = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo dimostrativo", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert create.status_code == 201
    field = Field.objects.get(pk=create.data["id"])
    field.is_demo = True
    field.save(update_fields=("is_demo",))
    AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=1,
        idempotency_key="demo-key",
        params={},
        status=AnalysisJob.Status.COMPLETED,
        result=ANALYSIS_RESULT,
    )

    api_client.force_authenticate(user=None)
    response = api_client.get("/api/v1/demo/")

    assert response.status_code == 200
    assert response.data["field"]["name"] == "Campo dimostrativo"
    assert response.data["field"]["boundary"]["geometry"]["type"] == "MultiPolygon"
    assert response.data["analysis"] == ANALYSIS_RESULT
    assert "generatedAt" in response.data


@pytest.mark.django_db
def test_demo_endpoint_404_when_demo_has_no_completed_job(
    api_client: APIClient, user: User
) -> None:
    api_client.force_authenticate(user)
    create = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo dimostrativo", "boundary": FIELD_POLYGON},
        format="json",
    )
    field = Field.objects.get(pk=create.data["id"])
    field.is_demo = True
    field.save(update_fields=("is_demo",))

    response = api_client.get("/api/v1/demo/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_create_field_rejects_outside_italy(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)

    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo Madrid", "boundary": SPAIN_POLYGON},
        format="json",
    )

    assert response.status_code == 400
    assert "copertura operativa" in str(response.data)
    assert Field.objects.count() == 0
