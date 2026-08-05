import stripe
from django.apps import AppConfig
from django.conf import settings


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.billing"

    def ready(self) -> None:
        # La SDK stripe-python richiede la chiave globale: senza, ogni call
        # (checkout/portal) fallisce con AuthenticationError -> 500. I test
        # mockano le call, quindi questo resta visibile solo in produzione.
        stripe.api_key = settings.STRIPE_SECRET_KEY
