"""Test dei tier di abbonamento: scelta piano in checkout, entitlement con
limite ettari e gate CUMULATIVO sui boundary (creazione campo e nuova versione).

I price_id qui sono finti ("price_basic/pro/plus"): la mappa tier arriva da
`settings.STRIPE_TIERS` sovrascritta dalla fixture `tiers`.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.billing.models import Subscription
from backend.fields.models import Field

TEST_TIERS: dict[str, dict[str, Any]] = {
    "basic": {"price_id": "price_basic", "label": "Basic", "amount_eur_month": 14.99, "max_hectares": 5.0},
    "pro": {"price_id": "price_pro", "label": "Pro", "amount_eur_month": 34.99, "max_hectares": 15.0},
    "plus": {"price_id": "price_plus", "label": "Plus", "amount_eur_month": 54.99, "max_hectares": None},
}

PERIOD_END = 1893456000  # 2030-01-01T00:00:00Z

# ~0.99 ha (0.001° x 0.001° in Sicilia)
SMALL_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.600, 36.920],
        [14.601, 36.920],
        [14.601, 36.921],
        [14.600, 36.921],
        [14.600, 36.920],
    ]],
}

# ~98.8 ha (0.01° x 0.01°)
BIG_POLYGON: dict[str, Any] = {
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


@pytest.fixture
def tiers(settings: Any) -> dict[str, dict[str, Any]]:
    settings.STRIPE_TIERS = TEST_TIERS
    return TEST_TIERS


def activate(user: User, plan_id: str = "", status: str = "active") -> Subscription:
    return Subscription.objects.create(
        user=user,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status=status,
        plan_id=plan_id,
        current_period_end=datetime.fromtimestamp(PERIOD_END, tz=timezone.utc),
    )


def create_field(api_client: APIClient, polygon: dict[str, Any], name: str = "Campo prova") -> Any:
    return api_client.post("/api/v1/fields/", {"name": name, "boundary": polygon}, format="json")


# ---- checkout con scelta piano -------------------------------------------


@pytest.mark.django_db
def test_checkout_defaults_to_basic_tier(api_client: APIClient, user: User, tiers: Any) -> None:
    api_client.force_authenticate(user)
    with (
        patch("backend.billing.views.stripe.Customer.create", return_value=SimpleNamespace(id="cus_new")),
        patch(
            "backend.billing.views.stripe.checkout.Session.create",
            return_value=SimpleNamespace(url="https://checkout.stripe.com/pay/test"),
        ) as session_create,
    ):
        response = api_client.post("/api/v1/billing/checkout/", {}, format="json")

    assert response.status_code == 200
    assert session_create.call_args.kwargs["line_items"] == [{"price": "price_basic", "quantity": 1}]


@pytest.mark.django_db
def test_checkout_accepts_explicit_tier(api_client: APIClient, user: User, tiers: Any) -> None:
    api_client.force_authenticate(user)
    with (
        patch("backend.billing.views.stripe.Customer.create", return_value=SimpleNamespace(id="cus_new")),
        patch(
            "backend.billing.views.stripe.checkout.Session.create",
            return_value=SimpleNamespace(url="https://checkout.stripe.com/pay/test"),
        ) as session_create,
    ):
        response = api_client.post(
            "/api/v1/billing/checkout/", {"price_id": "price_pro"}, format="json"
        )

    assert response.status_code == 200
    assert session_create.call_args.kwargs["line_items"] == [{"price": "price_pro", "quantity": 1}]


@pytest.mark.django_db
def test_checkout_rejects_unknown_price(api_client: APIClient, user: User, tiers: Any) -> None:
    api_client.force_authenticate(user)
    with patch("backend.billing.views.stripe.Customer.create", return_value=SimpleNamespace(id="cus_new")):
        response = api_client.post(
            "/api/v1/billing/checkout/", {"price_id": "price_inesistente"}, format="json"
        )

    assert response.status_code == 400


# ---- entitlement con tier e limite ---------------------------------------


@pytest.mark.django_db
def test_entitlement_exposes_tier_limit_and_plans(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user, plan_id="price_pro")
    api_client.force_authenticate(user)
    response = api_client.get("/api/v1/billing/entitlement/")

    assert response.status_code == 200
    assert response.data["tier"] == "pro"
    assert response.data["max_hectares"] == 15.0
    assert [plan["tier"] for plan in response.data["plans"]] == ["basic", "pro", "plus"]


@pytest.mark.django_db
def test_entitlement_unknown_price_has_no_limit(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    # Piani storici/ignoti: abbonamento valido, nessuna enforcement ettari.
    activate(user, plan_id="price_storico")
    api_client.force_authenticate(user)
    response = api_client.get("/api/v1/billing/entitlement/")

    assert response.data["subscribed"] is True
    assert response.data["tier"] is None
    assert response.data["max_hectares"] is None


# ---- gate ettari cumulativo ----------------------------------------------


@pytest.mark.django_db
def test_basic_tier_blocks_oversized_first_field(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user, plan_id="price_basic")
    api_client.force_authenticate(user)
    response = create_field(api_client, BIG_POLYGON)

    assert response.status_code == 402
    assert "Limite del piano" in response.data["detail"]
    assert Field.objects.count() == 0


@pytest.mark.django_db
def test_cumulative_limit_sums_boundaries_across_fields(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user, plan_id="price_basic")
    api_client.force_authenticate(user)

    assert create_field(api_client, SMALL_POLYGON, name="Campo 1").status_code == 201
    assert create_field(api_client, SMALL_POLYGON, name="Campo 2").status_code == 201
    # ~2 ha esistenti + ~98.8 ha nuovi: il totale cumulativo supera i 5 ha.
    response = create_field(api_client, BIG_POLYGON, name="Campo 3")

    assert response.status_code == 402
    assert Field.objects.count() == 2


@pytest.mark.django_db
def test_new_boundary_version_excludes_the_replaced_field(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user, plan_id="price_basic")
    api_client.force_authenticate(user)
    created = create_field(api_client, SMALL_POLYGON)
    assert created.status_code == 201
    field_id = created.data["id"]

    # Nuova versione dello stesso campo: sostituisce la precedente, il totale
    # resta ~1 ha (non si somma alla versione sostituita).
    response = api_client.post(
        f"/api/v1/fields/{field_id}/boundaries/",
        {"geometry": SMALL_POLYGON, "source": "draw"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["version"] == 2


@pytest.mark.django_db
def test_boundary_creation_requires_subscription(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user)  # senza plan_id: abbonato, nessun limite ettari
    api_client.force_authenticate(user)
    created = create_field(api_client, SMALL_POLYGON)
    assert created.status_code == 201
    field_id = created.data["id"]

    subscription = Subscription.objects.get(user=user)
    subscription.status = "canceled"
    subscription.save(update_fields=("status",))

    response = api_client.post(
        f"/api/v1/fields/{field_id}/boundaries/",
        {"geometry": SMALL_POLYGON, "source": "draw"},
        format="json",
    )

    assert response.status_code == 402
    assert "Abbonamento" in response.data["detail"]


@pytest.mark.django_db
def test_demo_field_boundaries_bypass_quota(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user)
    api_client.force_authenticate(user)
    created = create_field(api_client, SMALL_POLYGON)
    field = Field.objects.get(pk=created.data["id"])
    field.is_demo = True
    field.save(update_fields=("is_demo",))

    subscription = Subscription.objects.get(user=user)
    subscription.status = "canceled"
    subscription.save(update_fields=("status",))

    response = api_client.post(
        f"/api/v1/fields/{field.pk}/boundaries/",
        {"geometry": BIG_POLYGON, "source": "draw"},
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_plus_tier_has_no_hectare_limit(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    activate(user, plan_id="price_plus")
    api_client.force_authenticate(user)
    assert create_field(api_client, BIG_POLYGON).status_code == 201


@pytest.mark.django_db
def test_billing_app_ready_sets_stripe_api_key(settings: Any) -> None:
    """Regressione 2026-08-05: senza stripe.api_key ogni call reale dava 500,
    ma i test (tutti mockati) restavano verdi."""
    import stripe as stripe_lib
    from django.apps import apps

    settings.STRIPE_SECRET_KEY = "sk_test_regression"
    apps.get_app_config("billing").ready()
    assert stripe_lib.api_key == "sk_test_regression"


@pytest.mark.django_db
def test_webhook_subscription_created_out_of_order_links_via_customer_metadata(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    """Regressione 2026-08-05 (bug E2E reale): Stripe NON garantisce l'ordine
    di consegna. subscription.created puo' arrivare prima di
    checkout.session.completed, quando la riga locale non esiste ancora:
    il handler deve risalire all'utente dai metadata del customer."""
    event = {
        "id": "evt_ooo",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_ooo",
                "customer": "cus_ooo",
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": PERIOD_END,
                "items": {"data": [{"price": {"id": "price_basic"}}]},
            }
        },
    }
    with (
        patch("backend.billing.views.stripe.Webhook.construct_event", return_value=event),
        patch(
            "backend.billing.views.stripe.Customer.retrieve",
            return_value=SimpleNamespace(metadata={"user_id": str(user.pk)}),
        ) as retrieve,
    ):
        response = api_client.post(
            "/api/v1/billing/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )

    assert response.status_code == 200
    retrieve.assert_called_once_with("cus_ooo")
    subscription = Subscription.objects.get(user=user)
    assert subscription.status == "active"
    assert subscription.plan_id == "price_basic"
    assert subscription.stripe_subscription_id == "sub_ooo"
    assert subscription.stripe_customer_id == "cus_ooo"


@pytest.mark.django_db
def test_webhook_reads_period_end_from_items_basil_shape(
    api_client: APIClient, user: User, tiers: Any
) -> None:
    """API Stripe basil: current_period_end vive in items.data[], non nella
    root della Subscription. Il webhook deve leggerlo da li'."""
    activate(user)
    event = {
        "id": "evt_basil",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_test",
                "customer": "cus_test",
                "status": "active",
                "cancel_at_period_end": False,
                "items": {
                    "data": [{
                        "price": {"id": "price_pro"},
                        "current_period_end": PERIOD_END,
                    }]
                },
            }
        },
    }
    with patch("backend.billing.views.stripe.Webhook.construct_event", return_value=event):
        response = api_client.post(
            "/api/v1/billing/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )

    assert response.status_code == 200
    subscription = Subscription.objects.get(user=user)
    assert subscription.plan_id == "price_pro"
    assert subscription.current_period_end == datetime.fromtimestamp(
        PERIOD_END, tz=timezone.utc
    )
