from django.contrib import admin

from backend.billing.models import StripeEvent, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "plan_id", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "cancel_at_period_end")
    search_fields = ("user__email", "stripe_customer_id", "stripe_subscription_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "created_at")
    list_filter = ("event_type",)
    search_fields = ("event_id",)
