from typing import Any

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import Field, Intervention

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
def field(api_client: APIClient, user: User) -> Field:
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo diario", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert response.status_code == 201
    return Field.objects.get(pk=response.data["id"])


@pytest.mark.django_db
def test_create_and_list_interventions(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)

    created = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "irrigation", "date": "2026-07-20", "notes": "2 ore goccia a goccia"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["kind"] == "irrigation"
    api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "harvest", "date": "2026-07-25"},
        format="json",
    )

    listing = api_client.get(f"/api/v1/fields/{field.pk}/interventions/")
    assert listing.status_code == 200
    assert len(listing.data) == 2
    assert listing.data[0]["date"] == "2026-07-25"  # ordinati per data decrescente
    assert listing.data[1]["notes"] == "2 ore goccia a goccia"


@pytest.mark.django_db
def test_intervention_rejects_invalid_kind(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)

    response = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "aratura-inventata", "date": "2026-07-20"},
        format="json",
    )

    assert response.status_code == 400
    assert Intervention.objects.count() == 0


@pytest.mark.django_db
def test_interventions_are_isolated_by_owner(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    created = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "note", "date": "2026-07-20", "notes": "privato"},
        format="json",
    )
    other = User.objects.create_user(email="other@example.com", password="StrongPass-2026!")
    api_client.force_authenticate(other)

    listing = api_client.get(f"/api/v1/fields/{field.pk}/interventions/")
    create = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "note", "date": "2026-07-21"},
        format="json",
    )
    delete = api_client.delete(f"/api/v1/interventions/{created.data['id']}/")

    assert listing.status_code == 404
    assert create.status_code == 404
    assert delete.status_code == 404
    assert Intervention.objects.count() == 1


@pytest.mark.django_db
def test_delete_intervention(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    created = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "treatment", "date": "2026-07-22"},
        format="json",
    )

    response = api_client.delete(f"/api/v1/interventions/{created.data['id']}/")

    assert response.status_code == 204
    assert Intervention.objects.count() == 0
