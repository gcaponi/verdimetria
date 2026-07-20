from typing import Any

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import BoundaryVersion, Field
from src.domain import AnalysisArea


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

UPDATED_FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.612, 36.92],
        [14.612, 36.932],
        [14.60, 36.932],
        [14.60, 36.92],
    ]],
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> User:
    return User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")


@pytest.mark.django_db
def test_register_and_obtain_jwt(api_client: APIClient) -> None:
    register_response = api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "Farmer@example.com",
            "password": "StrongPass-2026!",
            "first_name": "Ada",
        },
        format="json",
    )

    assert register_response.status_code == 201
    assert register_response.data["email"] == "farmer@example.com"
    assert "password" not in register_response.data

    token_response = api_client.post(
        "/api/v1/auth/token/",
        {"email": "farmer@example.com", "password": "StrongPass-2026!"},
        format="json",
    )

    assert token_response.status_code == 200
    assert set(token_response.data) == {"access", "refresh"}


@pytest.mark.django_db
def test_register_rejects_case_insensitive_duplicate_email(api_client: APIClient) -> None:
    User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")

    response = api_client.post(
        "/api/v1/auth/register/",
        {"email": "FARMER@example.com", "password": "StrongPass-2026!"},
        format="json",
    )

    assert response.status_code == 400
    assert "email" in response.data


@pytest.mark.django_db
def test_create_field_persists_validated_boundary(
    api_client: APIClient,
    user: User,
) -> None:
    api_client.force_authenticate(user)

    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo Vittoria", "boundary": FIELD_POLYGON},
        format="json",
    )

    assert response.status_code == 201
    boundary_data = response.data["latest_boundary"]
    assert boundary_data["version"] == 1
    assert boundary_data["geometry"]["type"] == "MultiPolygon"
    assert boundary_data["metric_crs"] == "EPSG:32633"

    analysis_area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)
    expected_area = analysis_area.area_hectares(analysis_area.local_utm_crs())
    assert boundary_data["area_hectares"] == pytest.approx(expected_area, abs=0.0001)

    field = Field.objects.get(pk=response.data["id"])
    boundary = BoundaryVersion.objects.get(field=field)
    assert field.owner == user
    assert boundary.geometry.geom_type == "MultiPolygon"
    assert boundary.geometry.srid == 4326


@pytest.mark.django_db
def test_field_api_rejects_invalid_geometry(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    invalid_geometry = {
        "type": "Polygon",
        "coordinates": [[
            [14.60, 36.92],
            [14.61, 36.93],
            [14.61, 36.92],
            [14.60, 36.93],
            [14.60, 36.92],
        ]],
    }

    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo invalido", "boundary": invalid_geometry},
        format="json",
    )

    assert response.status_code == 400
    assert "Geometria non valida" in str(response.data["boundary"][0])
    assert Field.objects.count() == 0


@pytest.mark.django_db
def test_fields_are_isolated_by_owner(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    create_response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo privato", "boundary": FIELD_POLYGON},
        format="json",
    )
    other_user = User.objects.create_user(
        email="other@example.com",
        password="StrongPass-2026!",
    )
    api_client.force_authenticate(other_user)

    list_response = api_client.get("/api/v1/fields/")
    boundary_response = api_client.post(
        f"/api/v1/fields/{create_response.data['id']}/boundaries/",
        {"geometry": UPDATED_FIELD_POLYGON},
        format="json",
    )

    assert list_response.status_code == 200
    assert list_response.data == []
    assert boundary_response.status_code == 404


@pytest.mark.django_db
def test_add_boundary_creates_next_version(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    field_response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo versionato", "boundary": FIELD_POLYGON},
        format="json",
    )

    response = api_client.post(
        f"/api/v1/fields/{field_response.data['id']}/boundaries/",
        {"geometry": UPDATED_FIELD_POLYGON, "source": "draw"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["version"] == 2
    assert response.data["area_hectares"] > field_response.data["latest_boundary"]["area_hectares"]
    assert BoundaryVersion.objects.filter(field_id=field_response.data["id"]).count() == 2