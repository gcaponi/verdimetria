"""Test del paywall Stripe: checkout/portal/webhook/entitlement + gate 402.

La firma HMAC del webhook non viene verificata davvero: `construct_event` e'
mockato e i test validano routing, dedup e transizioni di stato. La fixture
`user` locale NON abbonata sovrascrive quella del conftest (baseline abbonata).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import json
import pytest
import stripe
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.billing.models import Subscription
from backend.billing.services import BillingGateError, enforce_hectare_quota, get_entitlements
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

PERIOD_END = 1893456000  # 2030-01-01T00:00:00Z


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> User:
    """Utente SENZA abbonamento: il paywall deve bloccarlo."""
    return User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")


def activate(user: User, status: str = "active", customer_id: str = "cus_test") -> Subscription:
    return Subscription.objects.create(
        user=user,
        stripe_customer_id=customer_id,
        stripe_subscription_id="sub_test",
        status=status,
        current_period_end=datetime.fromtimestamp(PERIOD_END, tz=timezone.utc),
    )


def create_field(api_client: APIClient, name: str = "Campo prova") -> Any:
    return api_client.post(
        "/api/v1/fields/",
        {"name": name, "boundary": FIELD_POLYGON},
        format="json",
    )


def subscription_event(
    event_id: str,
    status: str,
    subscription_id: str = "sub_test",
    customer_id: str = "cus_test",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": subscription_id,
                "customer": customer_id,
                "status": status,
                "cancel_at_period_end": False,
                "current_period_end": PERIOD_END,
                "items": {"data": [{"price": {"id": "price_test"}}]},
            }
        },
    }


def post_webhook(api_client: APIClient, event: dict[str, Any]) -> Any:
    with patch(
        "backend.billing.views.stripe.Webhook.construct_event", return_value=event
    ):
        return api_client.post(
            "/api/v1/billing/webhook/",
            data=json.dumps(event),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )


@pytest.mark.django_db
def test_checkout_requires_authentication(api_client: APIClient) -> None:
    response = api_client.post("/api/v1/billing/checkout/", {}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_checkout_creates_customer_and_returns_session_url(
    api_client: APIClient, user: User
) -> None:
    api_client.force_authenticate(user)
    with (
        patch(
            "backend.billing.views.stripe.Customer.create",
            return_value=SimpleNamespace(id="cus_new"),
        ) as customer_create,
        patch(
            "backend.billing.views.stripe.checkout.Session.create",
            return_value=SimpleNamespace(url="https://checkout.stripe.com/pay/test"),
        ) as session_create,
    ):
        response = api_client.post("/api/v1/billing/checkout/", {}, format="json")

    assert response.status_code == 200
    assert response.data["url"] == "https://checkout.stripe.com/pay/test"
    customer_create.assert_called_once_with(
        email=user.email, metadata={"user_id": str(user.pk)}
    )
    session_kwargs = session_create.call_args.kwargs
    assert session_kwargs["mode"] == "subscription"
    assert session_kwargs["customer"] == "cus_new"
    assert session_kwargs["line_items"] == [
        {"price": "", "quantity": 1}
    ]  # STRIPE_PRICE_ID vuoto in locale
    subscription = Subscription.objects.get(user=user)
    assert subscription.stripe_customer_id == "cus_new"


@pytest.mark.django_db
def test_checkout_reuses_existing_customer(api_client: APIClient, user: User) -> None:
    activate(user, customer_id="cus_esistente")
    api_client.force_authenticate(user)
    with (
        patch(
            "backend.billing.views.stripe.Customer.create",
            return_value=SimpleNamespace(id="cus_mai_usato"),
        ) as customer_create,
        patch(
            "backend.billing.views.stripe.checkout.Session.create",
            return_value=SimpleNamespace(url="https://checkout.stripe.com/pay/test"),
        ),
    ):
        response = api_client.post("/api/v1/billing/checkout/", {}, format="json")

    assert response.status_code == 200
    customer_create.assert_not_called()


@pytest.mark.django_db
def test_portal_requires_existing_customer(api_client: APIClient, user: User) -> None:
    api_client.force_authenticate(user)
    response = api_client.post("/api/v1/billing/portal/", {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_portal_returns_session_url(api_client: APIClient, user: User) -> None:
    activate(user, customer_id="cus_esistente")
    api_client.force_authenticate(user)
    with patch(
        "backend.billing.views.stripe.billing_portal.Session.create",
        return_value=SimpleNamespace(url="https://billing.stripe.com/p/session"),
    ) as portal_create:
        response = api_client.post("/api/v1/billing/portal/", {}, format="json")

    assert response.status_code == 200
    assert response.data["url"] == "https://billing.stripe.com/p/session"
    assert portal_create.call_args.kwargs["customer"] == "cus_esistente"


@pytest.mark.django_db
def test_webhook_rejects_invalid_signature(api_client: APIClient) -> None:
    with patch(
        "backend.billing.views.stripe.Webhook.construct_event",
        side_effect=stripe.error.SignatureVerificationError(
            "firma non valida", "t=1,v1=corrotta"
        ),
    ):
        response = api_client.post(
            "/api/v1/billing/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=corrotta",
        )

    assert response.status_code == 400


@pytest.mark.django_db
def test_webhook_checkout_completed_links_customer(
    api_client: APIClient, user: User
) -> None:
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(user.pk),
                "customer": "cus_checkout",
                "subscription": "sub_checkout",
            }
        },
    }
    response = post_webhook(api_client, event)

    assert response.status_code == 200
    subscription = Subscription.objects.get(user=user)
    assert subscription.stripe_customer_id == "cus_checkout"
    assert subscription.stripe_subscription_id == "sub_checkout"
    # Lo status attivo arriva solo dall'evento subscription.
    assert subscription.status == ""


@pytest.mark.django_db
def test_webhook_activates_subscription(api_client: APIClient, user: User) -> None:
    activate(user, status="incomplete")
    response = post_webhook(api_client, subscription_event("evt_1", "active"))

    assert response.status_code == 200
    subscription = Subscription.objects.get(user=user)
    assert subscription.status == "active"
    assert subscription.plan_id == "price_test"
    assert subscription.current_period_end == datetime.fromtimestamp(
        PERIOD_END, tz=timezone.utc
    )


@pytest.mark.django_db
def test_webhook_duplicate_event_is_ignored(api_client: APIClient, user: User) -> None:
    activate(user, status="active")
    first = post_webhook(api_client, subscription_event("evt_duplicato", "active"))
    assert first.status_code == 200

    # Replay di Stripe con lo stesso event_id ma stato diverso: non deve applicarsi.
    replay = subscription_event("evt_duplicato", "canceled")
    replay["data"]["object"]["current_period_end"] = None
    second = post_webhook(api_client, replay)

    assert second.status_code == 200
    assert second.data["duplicate"] is True
    assert Subscription.objects.get(user=user).status == "active"


@pytest.mark.django_db
def test_webhook_deleted_revokes_entitlement(api_client: APIClient, user: User) -> None:
    activate(user, status="active")
    event = subscription_event("evt_delete", "canceled")
    event["type"] = "customer.subscription.deleted"
    response = post_webhook(api_client, event)

    assert response.status_code == 200
    assert Subscription.objects.get(user=user).status == "canceled"

    api_client.force_authenticate(user)
    entitlement = api_client.get("/api/v1/billing/entitlement/")
    assert entitlement.status_code == 200
    assert entitlement.data["subscribed"] is False


@pytest.mark.django_db
def test_invoice_payment_failed_downgrades_active_subscription(
    api_client: APIClient, user: User
) -> None:
    activate(user, status="active")
    event = {
        "id": "evt_payment_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_test", "customer": "cus_test"}},
    }
    response = post_webhook(api_client, event)

    assert response.status_code == 200
    assert Subscription.objects.get(user=user).status == "past_due"


@pytest.mark.django_db
def test_entitlement_endpoint_reflects_subscription(
    api_client: APIClient, user: User
) -> None:
    api_client.force_authenticate(user)
    without = api_client.get("/api/v1/billing/entitlement/")
    assert without.status_code == 200
    assert without.data["subscribed"] is False
    assert without.data["status"] == ""
    assert without.data["max_fields"] == 3

    activate(user, status="active")
    with_subscription = api_client.get("/api/v1/billing/entitlement/")
    assert with_subscription.data["subscribed"] is True
    assert with_subscription.data["status"] == "active"
    assert with_subscription.data["current_period_end"] is not None


@pytest.mark.django_db
def test_create_field_requires_active_subscription(
    api_client: APIClient, user: User
) -> None:
    api_client.force_authenticate(user)
    response = create_field(api_client)

    assert response.status_code == 402
    assert "Abbonamento" in response.data["detail"]
    assert Field.objects.count() == 0


@pytest.mark.django_db
def test_create_field_allowed_with_active_subscription(
    api_client: APIClient, user: User
) -> None:
    activate(user)
    api_client.force_authenticate(user)
    assert create_field(api_client).status_code == 201


@pytest.mark.django_db
def test_create_job_requires_active_subscription(
    api_client: APIClient, user: User
) -> None:
    activate(user)
    api_client.force_authenticate(user)
    created = create_field(api_client)
    assert created.status_code == 201
    field_id = created.data["id"]

    subscription = Subscription.objects.get(user=user)
    subscription.status = "canceled"
    subscription.save(update_fields=("status",))

    response = api_client.post(f"/api/v1/fields/{field_id}/jobs/", {}, format="json")
    assert response.status_code == 402
    assert "Abbonamento" in response.data["detail"]


@pytest.mark.django_db
def test_demo_field_job_bypasses_paywall(
    api_client: APIClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    activate(user)
    api_client.force_authenticate(user)
    created = create_field(api_client)
    assert created.status_code == 201
    field = Field.objects.get(pk=created.data["id"])
    field.is_demo = True
    field.save(update_fields=("is_demo",))

    subscription = Subscription.objects.get(user=user)
    subscription.status = "canceled"
    subscription.save(update_fields=("status",))

    delay_spy = Mock()
    monkeypatch.setattr("backend.fields.views.run_analysis_job.delay", delay_spy)
    response = api_client.post(f"/api/v1/fields/{field.pk}/jobs/", {}, format="json")

    assert response.status_code == 201
    assert delay_spy.called


@pytest.mark.django_db
def test_staff_bypasses_paywall(api_client: APIClient, user: User) -> None:
    user.is_staff = True
    user.save(update_fields=("is_staff",))
    api_client.force_authenticate(user)
    assert create_field(api_client).status_code == 201


@pytest.mark.django_db
def test_webhook_reads_data_from_raw_body_not_sdk_object(
    api_client: APIClient, user: User
) -> None:
    """Regressione 2026-08-05: stripe-python v15 non espone .get() sugli
    StripeObject. Il webhook deve leggere i dati dal body JSON grezzo anche se
    construct_event restituisce un oggetto opaco."""
    activate(user, status="incomplete")
    event = subscription_event("evt_raw_body", "active")
    with patch(
        "backend.billing.views.stripe.Webhook.construct_event", return_value=object()
    ):
        response = api_client.post(
            "/api/v1/billing/webhook/",
            data=json.dumps(event),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )

    assert response.status_code == 200
    assert Subscription.objects.get(user=user).status == "active"


@pytest.mark.django_db
def test_complimentary_access_grants_entitlements(user: User) -> None:
    """Accesso omaggio: entitlement comp senza abbonamento Stripe."""
    user.complimentary_access = True
    user.save(update_fields=("complimentary_access",))

    entitlements = get_entitlements(user)

    assert entitlements["subscribed"] is True
    assert entitlements["status"] == "comp"
    assert entitlements["tier"] == "comp"
    assert entitlements["max_hectares"] is None


@pytest.mark.django_db
def test_complimentary_access_skips_hectare_quota(user: User) -> None:
    """Il tier comp non ha limite ettari: quota mai superata."""
    user.complimentary_access = True
    user.save(update_fields=("complimentary_access",))

    enforce_hectare_quota(user, 999999)


@pytest.mark.django_db
def test_user_without_flags_still_blocked_by_paywall(user: User) -> None:
    """Regressione: utente senza flag e senza abbonamento resta fuori."""
    entitlements = get_entitlements(user)

    assert entitlements["subscribed"] is False
    assert entitlements["status"] == ""
    with pytest.raises(BillingGateError):
        enforce_hectare_quota(user, 1)
