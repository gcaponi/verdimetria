from django.conf import settings
from django.db import models


class Subscription(models.Model):
    """Legame OneToOne tra utente e abbonamento Stripe (paywall pay-to-use).

    Lo `status` conserva il valore grezzo di Stripe ("trialing", "active",
    "past_due", "canceled", ...): la semantica di "abbonato" e' decisa in
    `services.get_entitlements`, non qui.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_subscription",
    )
    stripe_customer_id = models.CharField(max_length=128, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    plan_id = models.CharField(max_length=128, blank=True, default="")
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("stripe_customer_id",))]

    def __str__(self) -> str:
        return f"{self.user.email} · {self.status or 'mai abbonato'}"


class StripeEvent(models.Model):
    """Evento webhook gia' processato: idempotenza sul replay di Stripe."""

    event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.event_type} · {self.event_id}"
