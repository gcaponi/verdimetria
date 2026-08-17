"""Entitlements di billing: unica fonte per "questo utente puo' usare X?".

`subscribed = True` per status Stripe in trialing/active, con bypass esplicito
per staff/superuser (operativita' interna, non clienti paganti) e per gli
utenti con `complimentary_access` (accesso omaggio, status/tier "comp"). I
tier di abbonamento mappano il price Stripe a un limite ettari CUMULATIVO
calcolato sui boundary correnti dei campi vivi dell'utente (ultima versione
per campo).
"""

from decimal import Decimal
from typing import Any

from django.conf import settings

from backend.accounts.models import User
from backend.billing.models import Subscription

ACTIVE_STATUSES = frozenset({"trialing", "active"})


class BillingGateError(Exception):
    """Accesso negato dal paywall: le view lo traducono in 402."""

    UNSUBSCRIBED = "unsubscribed"
    QUOTA = "quota"
    PUBLIC_MESSAGES = {
        UNSUBSCRIBED: "Abbonamento attivo richiesto per definire i confini",
        QUOTA: (
            "Limite del piano superato. Passa a un piano superiore "
            "per coprire piu' ettari"
        ),
    }

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(self.PUBLIC_MESSAGES[code])


def tier_for_price(price_id: str) -> str | None:
    """Chiave del tier (basic/pro/plus) per un price Stripe, None se ignoto."""
    if not price_id:
        return None
    for key, tier in settings.STRIPE_TIERS.items():
        if tier["price_id"] and tier["price_id"] == price_id:
            return key
    return None


def available_plans() -> list[dict[str, Any]]:
    """Catalogo piani esposto al frontend per le card di pricing."""
    return [
        {
            "tier": key,
            "label": tier["label"],
            "amount_eur_month": tier["amount_eur_month"],
            "max_hectares": tier["max_hectares"],
            "price_id": tier["price_id"],
        }
        for key, tier in settings.STRIPE_TIERS.items()
    ]


def get_entitlements(user: User) -> dict[str, object]:
    """Stato di accesso dell'utente, serializzabile direttamente in JSON."""
    if user.is_staff or user.is_superuser:
        return {
            "subscribed": True,
            "status": "staff",
            "current_period_end": None,
            "max_fields": settings.MAX_FIELDS_PER_ACCOUNT,
            "tier": "staff",
            "max_hectares": None,
            "plans": available_plans(),
        }
    if user.complimentary_access:
        return {
            "subscribed": True,
            "status": "comp",
            "current_period_end": None,
            "max_fields": settings.MAX_FIELDS_PER_ACCOUNT,
            "tier": "comp",
            "max_hectares": None,
            "plans": available_plans(),
        }
    subscription = Subscription.objects.filter(user=user).first()
    tier = tier_for_price(subscription.plan_id) if subscription is not None else None
    # Fail closed: an active Stripe status is insufficient when its price is
    # not one of the plans configured for this deployment. This prevents old
    # sandbox prices (or malformed webhook state) from granting unlimited use.
    subscribed = (
        subscription is not None
        and subscription.status in ACTIVE_STATUSES
        and tier is not None
    )
    return {
        "subscribed": subscribed,
        "status": subscription.status if subscription else "",
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription is not None and subscription.current_period_end is not None
            else None
        ),
        "max_fields": settings.MAX_FIELDS_PER_ACCOUNT,
        "tier": tier,
        "max_hectares": (
            settings.STRIPE_TIERS[tier]["max_hectares"] if tier is not None else None
        ),
        "plans": available_plans(),
    }


def current_total_hectares(owner: User, exclude_field_id: Any = None) -> Decimal:
    """Somma delle aree dei boundary correnti dei campi vivi dell'utente.

    Conta solo l'ultima versione di ogni campo (quella operativa) ed esclude
    i campi demo (gestiti dalla piattaforma). `exclude_field_id` salta il
    campo che sta ricevendo una nuova versione del confine.
    """
    from backend.fields.models import Field  # import pigro: evita cicli tra app

    fields = Field.objects.filter(owner=owner, is_demo=False)
    if exclude_field_id is not None:
        fields = fields.exclude(pk=exclude_field_id)
    total = Decimal("0")
    for field in fields.prefetch_related("boundaries"):
        latest = field.boundaries.first()  # Meta ordering: -version
        if latest is not None:
            total += latest.area_hectares
    return total


def enforce_hectare_quota(
    owner: User,
    additional_hectares: float | Decimal,
    *,
    exclude_field_id: Any = None,
) -> None:
    """Verifica il limite ettari CUMULATIVO del tier prima di un nuovo boundary.

    Solleva BillingGateError (402 lato view) se l'utente non e' abbonato o se
    il totale supererebbe il limite del piano. Tier con max_hectares None
    (plus, staff o accesso omaggio) non hanno limite.
    """
    entitlements = get_entitlements(owner)
    if not entitlements["subscribed"]:
        raise BillingGateError(BillingGateError.UNSUBSCRIBED)
    limit = entitlements["max_hectares"]
    if limit is None:
        return
    total = current_total_hectares(owner, exclude_field_id=exclude_field_id) + Decimal(
        str(additional_hectares)
    )
    if total > Decimal(str(limit)):
        raise BillingGateError(BillingGateError.QUOTA)
