from typing import Any

import pytest

from backend.accounts.models import User
from backend.billing.models import Subscription


@pytest.fixture
def user(settings: Any) -> User:
    """Utente abbonato di default: la baseline API assume il paywall attivo.

    I test del paywall (tests/test_billing.py) definiscono una propria fixture
    `user` NON abbonata per verificare il gate 402.
    """
    tiers = {key: dict(value) for key, value in settings.STRIPE_TIERS.items()}
    if not tiers["plus"]["price_id"]:
        tiers["plus"]["price_id"] = "price_test_plus"
    settings.STRIPE_TIERS = tiers
    user = User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")
    Subscription.objects.create(
        user=user,
        status="active",
        plan_id=tiers["plus"]["price_id"],
    )
    return user
