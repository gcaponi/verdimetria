from typing import Any

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import Field
from backend.fields.serializers import FieldSerializer

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


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> User:
    return User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")


def _create_field(api_client: APIClient, user: User, payload: dict[str, Any]) -> Any:
    api_client.force_authenticate(user)
    return api_client.post("/api/v1/fields/", payload, format="json")


@pytest.mark.django_db
def test_create_field_without_crop_defaults_to_blank(api_client: APIClient, user: User) -> None:
    response = _create_field(api_client, user, {"name": "Campo base", "boundary": FIELD_POLYGON})

    assert response.status_code == 201
    assert response.data["crop"] == ""
    assert Field.objects.get(pk=response.data["id"]).crop == ""


@pytest.mark.django_db
def test_create_field_with_crop_is_persisted_and_returned(api_client: APIClient, user: User) -> None:
    response = _create_field(
        api_client, user, {"name": "Vigneto Etna", "crop": "Vigneto", "boundary": FIELD_POLYGON}
    )

    assert response.status_code == 201
    assert response.data["crop"] == "Vigneto"
    field = Field.objects.get(pk=response.data["id"])
    assert field.crop == "Vigneto"

    listing = api_client.get("/api/v1/fields/")
    assert listing.status_code == 200
    assert listing.data[0]["crop"] == "Vigneto"


@pytest.mark.django_db
def test_create_field_accepts_blank_crop(api_client: APIClient, user: User) -> None:
    response = _create_field(
        api_client, user, {"name": "Campo vuoto", "crop": "", "boundary": FIELD_POLYGON}
    )

    assert response.status_code == 201
    assert response.data["crop"] == ""


@pytest.mark.django_db
def test_crop_is_included_in_serializer_output(api_client: APIClient, user: User) -> None:
    response = _create_field(
        api_client, user, {"name": "Oliveto", "crop": "Oliveto", "boundary": FIELD_POLYGON}
    )
    assert response.status_code == 201
    field = Field.objects.get(pk=response.data["id"])

    data = FieldSerializer(field).data

    assert data["crop"] == "Oliveto"
