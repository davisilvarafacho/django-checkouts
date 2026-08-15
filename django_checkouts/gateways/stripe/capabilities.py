"""Capacidades declaradas pelo gateway Stripe."""

from __future__ import annotations

from django_checkouts.capabilities import CheckoutCapabilities
from django_checkouts.capabilities import GatewayCapabilities
from django_checkouts.capabilities import InvoiceCapabilities
from django_checkouts.capabilities import ReconciliationCapabilities
from django_checkouts.capabilities import SubscriptionCapabilities
from django_checkouts.capabilities import WebhookCapabilities
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CancellationTiming
from django_checkouts.enums import ChangeTiming
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import ProrationBehavior

STRIPE_CAPABILITIES = GatewayCapabilities(
    checkouts=CheckoutCapabilities(
        modes=frozenset(CheckoutMode),
        payment_methods_by_mode={
            CheckoutMode.PAYMENT: frozenset(PaymentMethod),
            CheckoutMode.SUBSCRIPTION: frozenset({PaymentMethod.CARD}),
        },
        billing_cycles=frozenset(BillingCycle),
        supports_catalog_prices=True,
        supports_inline_prices=True,
        supports_expiration=True,
        supports_customer_prefill=True,
    ),
    subscriptions=SubscriptionCapabilities(
        retrieve=True,
        change_quantity=True,
        replace_price=True,
        add_remove_items=True,
        timings=frozenset(ChangeTiming),
        proration_behaviors=frozenset(ProrationBehavior),
        cancellation_timings=frozenset(CancellationTiming),
        resume_scheduled_cancellation=True,
        atomic_multi_change=True,
    ),
    invoices=InvoiceCapabilities(retrieve=True),
    webhooks=WebhookCapabilities(signed=True),
    reconciliation=ReconciliationCapabilities(events=True, maximum_page_size=100),
)

__all__ = ["STRIPE_CAPABILITIES"]
