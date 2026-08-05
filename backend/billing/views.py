"""Endpoint billing: checkout, customer portal, webhook Stripe, entitlement.

Il webhook e' AllowAny perche' Stripe non invia JWT: la sicurezza e' la
verifica della firma HMAC (`STRIPE_WEBHOOK_SECRET`). Ogni evento e' registrato
una sola volta in `StripeEvent` per idempotenza sui replay.
"""

from datetime import UTC, datetime
from typing import Any, Callable, cast

import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.accounts.models import User
from backend.billing.models import StripeEvent, Subscription
from backend.billing.services import ACTIVE_STATUSES, get_entitlements


class CheckoutView(APIView):
    """POST /api/v1/billing/checkout/ -> URL Stripe Checkout (mode subscription)."""

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        subscription = Subscription.objects.filter(user=user).first()
        customer_id = subscription.stripe_customer_id if subscription else ""

        if not customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={"user_id": str(user.pk)},
            )
            customer_id = str(customer.id)
            Subscription.objects.update_or_create(
                user=user,
                defaults={"stripe_customer_id": customer_id},
            )

        requested_price = ""
        if isinstance(request.data, dict):
            requested_price = str(request.data.get("price_id") or "").strip()
        if not requested_price:
            requested_price = str(settings.STRIPE_TIERS["basic"]["price_id"])
        allowed_prices = {
            str(tier["price_id"])
            for tier in settings.STRIPE_TIERS.values()
            if tier["price_id"]
        }
        if allowed_prices and requested_price not in allowed_prices:
            return Response(
                {"detail": "Piano non valido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": requested_price, "quantity": 1}],
            success_url=f"{settings.FRONTEND_URL.rstrip('/')}/account?checkout=success",
            cancel_url=f"{settings.FRONTEND_URL.rstrip('/')}/account?checkout=cancelled",
            client_reference_id=str(user.pk),
            metadata={"user_id": str(user.pk)},
        )
        return Response({"url": session.url})


class PortalView(APIView):
    """POST /api/v1/billing/portal/ -> URL del customer portal Stripe."""

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        subscription = (
            Subscription.objects.filter(user=user).exclude(stripe_customer_id="").first()
        )
        if subscription is None:
            return Response(
                {"detail": "Nessun cliente Stripe associato a questo account"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL.rstrip('/')}/account",
        )
        return Response({"url": session.url})


class EntitlementView(APIView):
    """GET /api/v1/billing/entitlement/ -> stato abbonamento dell'utente."""

    def get(self, request: Request) -> Response:
        return Response(get_entitlements(cast(User, request.user)))


class WebhookView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        signature = request.headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                signature,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return Response(
                {"detail": "Firma del webhook non valida"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_id = str(event["id"])
        if StripeEvent.objects.filter(event_id=event_id).exists():
            # Replay di Stripe: gia' processato, nessuna azione.
            return Response({"received": True, "duplicate": True})

        StripeEvent.objects.create(event_id=event_id, event_type=str(event["type"]))
        handler = HANDLERS.get(str(event["type"]))
        if handler is not None:
            handler(event["data"]["object"])
        return Response({"received": True})


def _handle_checkout_completed(checkout_session: dict[str, Any]) -> None:
    """checkout.session.completed: collega customer/subscription all'utente.

    Lo status di abbonamento arriva dagli eventi customer.subscription.*:
    qui registriamo solo i riferimenti Stripe, senza assumere l'attivazione.
    """
    user_id = checkout_session.get("client_reference_id") or (
        checkout_session.get("metadata") or {}
    ).get("user_id")
    if not user_id:
        return
    try:
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        return
    Subscription.objects.update_or_create(
        user=user,
        defaults={
            "stripe_customer_id": checkout_session.get("customer") or "",
            "stripe_subscription_id": checkout_session.get("subscription") or "",
        },
    )


def _handle_subscription_event(subscription_object: dict[str, Any]) -> None:
    """customer.subscription.created/updated/deleted: sincronizza lo stato."""
    customer_id = subscription_object.get("customer") or ""
    subscription_id = subscription_object.get("id") or ""
    subscription = None
    if customer_id:
        subscription = Subscription.objects.filter(
            stripe_customer_id=customer_id
        ).first()
    if subscription is None and subscription_id:
        subscription = Subscription.objects.filter(
            stripe_subscription_id=subscription_id
        ).first()
    if subscription is None:
        # Stripe NON garantisce l'ordine di consegna: subscription.created puo'
        # arrivare prima di checkout.session.completed, quando la riga locale
        # non esiste ancora. Risalgo all'utente dai metadata del customer
        # (impostati da CheckoutView alla creazione).
        user_id = _user_id_from_customer_metadata(customer_id)
        if not user_id:
            return
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError):
            return
        subscription, _ = Subscription.objects.update_or_create(
            user=user,
            defaults={"stripe_customer_id": customer_id},
        )

    period_end = subscription_object.get("current_period_end")
    plan_id = ""
    items = (subscription_object.get("items") or {}).get("data") or []
    if items and items[0].get("price"):
        plan_id = (items[0]["price"].get("id") or "")

    subscription.stripe_subscription_id = subscription_id
    subscription.status = subscription_object.get("status") or ""
    subscription.plan_id = plan_id
    subscription.cancel_at_period_end = bool(
        subscription_object.get("cancel_at_period_end", False)
    )
    subscription.current_period_end = (
        datetime.fromtimestamp(float(period_end), tz=UTC) if period_end else None
    )
    subscription.save(
        update_fields=(
            "stripe_subscription_id",
            "status",
            "plan_id",
            "cancel_at_period_end",
            "current_period_end",
            "updated_at",
        )
    )


def _user_id_from_customer_metadata(customer_id: str) -> str | None:
    """user_id dai metadata del customer Stripe (fallback per consegne fuori ordine)."""
    if not customer_id:
        return None
    try:
        customer = stripe.Customer.retrieve(customer_id)
    except stripe.error.StripeError:
        return None
    metadata = getattr(customer, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return None
    user_id = metadata.get("user_id")
    return str(user_id) if user_id else None


def _handle_invoice_payment_failed(invoice: dict[str, Any]) -> None:
    """invoice.payment_failed: declassa un abbonamento attivo a past_due."""
    subscription_id = invoice.get("subscription") or ""
    subscription = Subscription.objects.filter(
        stripe_subscription_id=subscription_id
    ).first()
    if subscription is not None and subscription.status in ACTIVE_STATUSES:
        subscription.status = "past_due"
        subscription.save(update_fields=("status", "updated_at"))


HANDLERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.created": _handle_subscription_event,
    "customer.subscription.updated": _handle_subscription_event,
    "customer.subscription.deleted": _handle_subscription_event,
    "invoice.payment_failed": _handle_invoice_payment_failed,
}
