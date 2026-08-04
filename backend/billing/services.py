"""Entitlements di billing: unica fonte per "questo utente puo' usare X?".

`subscribed = True` per status Stripe in trialing/active, con bypass esplicito
per staff/superuser (operativita' interna, non clienti paganti).
"""

from django.conf import settings

from backend.accounts.models import User
from backend.billing.models import Subscription

ACTIVE_STATUSES = frozenset({"trialing", "active"})


def get_entitlements(user: User) -> dict[str, object]:
    """Stato di accesso dell'utente, serializzabile direttamente in JSON."""
    if user.is_staff or user.is_superuser:
        return {
            "subscribed": True,
            "status": "staff",
            "current_period_end": None,
            "max_fields": settings.MAX_FIELDS_PER_ACCOUNT,
        }
    subscription = Subscription.objects.filter(user=user).first()
    subscribed = subscription is not None and subscription.status in ACTIVE_STATUSES
    return {
        "subscribed": subscribed,
        "status": subscription.status if subscription else "",
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription is not None and subscription.current_period_end is not None
            else None
        ),
        "max_fields": settings.MAX_FIELDS_PER_ACCOUNT,
    }
