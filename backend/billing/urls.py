from django.urls import path

from backend.billing.views import (
    CheckoutView,
    EntitlementView,
    PortalView,
    WebhookView,
)

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", PortalView.as_view(), name="billing-portal"),
    path("webhook/", WebhookView.as_view(), name="billing-webhook"),
    path("entitlement/", EntitlementView.as_view(), name="billing-entitlement"),
]
