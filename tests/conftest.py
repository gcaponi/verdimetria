import pytest

from backend.accounts.models import User
from backend.billing.models import Subscription


@pytest.fixture
def user() -> User:
    """Utente abbonato di default: la baseline API assume il paywall attivo.

    I test del paywall (tests/test_billing.py) definiscono una propria fixture
    `user` NON abbonata per verificare il gate 402.
    """
    user = User.objects.create_user(email="farmer@example.com", password="StrongPass-2026!")
    Subscription.objects.create(user=user, status="active")
    return user
