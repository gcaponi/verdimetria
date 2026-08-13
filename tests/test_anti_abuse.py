from typing import Any

import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.billing.models import Subscription
from backend.fields.models import Field

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


def create_field(api_client: APIClient, name: str = "Campo prova") -> Response:
    return api_client.post(
        "/api/v1/fields/",
        {"name": name, "boundary": FIELD_POLYGON},
        format="json",
    )


@pytest.mark.django_db
def test_user_can_create_up_to_three_fields(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)

    for _ in range(3):
        response = create_field(api_client)
        assert response.status_code == 201

    assert Field.objects.filter(owner=user).count() == 3


@pytest.mark.django_db
def test_fourth_field_is_rejected_with_403(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    for _ in range(3):
        assert create_field(api_client).status_code == 201

    response = create_field(api_client, name="Campo di troppo")

    assert response.status_code == 403
    assert "Limite massimo di 3 campi per account" in response.data["detail"]
    assert Field.objects.filter(owner=user).count() == 3


@pytest.mark.django_db
def test_field_cap_does_not_affect_other_users(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    for _ in range(3):
        assert create_field(api_client).status_code == 201
    assert create_field(api_client).status_code == 403

    other_user = User.objects.create_user(
        email="other@example.com",
        password="StrongPass-2026!",
    )
    Subscription.objects.create(
        user=other_user,
        status="active",
        plan_id=user.billing_subscription.plan_id,
    )
    api_client.force_authenticate(other_user)

    response = create_field(api_client)

    assert response.status_code == 201
    assert Field.objects.filter(owner=other_user).count() == 1


@pytest.mark.django_db
def test_demo_fields_do_not_count_toward_cap(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    for _ in range(3):
        assert create_field(api_client).status_code == 201
    demo_field = Field.objects.filter(owner=user).first()
    assert demo_field is not None
    demo_field.is_demo = True
    demo_field.save(update_fields=("is_demo",))

    response = create_field(api_client, name="Campo extra")

    assert response.status_code == 201
    assert Field.objects.filter(owner=user, is_demo=False).count() == 3
    # The cap applies again once three non-demo fields exist.
    assert create_field(api_client).status_code == 403
