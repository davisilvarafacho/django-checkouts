"""Contrato das capacidades declarativas de cada gateway."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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


@pytest.fixture
def capabilities() -> GatewayCapabilities:
    return GatewayCapabilities(
        checkouts=CheckoutCapabilities(
            modes=frozenset({CheckoutMode.PAYMENT}),
            payment_methods_by_mode={
                CheckoutMode.PAYMENT: frozenset({PaymentMethod.CARD}),
            },
            billing_cycles=frozenset({BillingCycle.MONTHLY}),
            supports_catalog_prices=True,
            supports_inline_prices=True,
            supports_expiration=False,
            supports_customer_prefill=True,
        ),
        subscriptions=SubscriptionCapabilities(
            retrieve=True,
            change_quantity=False,
            replace_price=False,
            add_remove_items=False,
            timings=frozenset({ChangeTiming.IMMEDIATELY}),
            proration_behaviors=frozenset({ProrationBehavior.NONE}),
            cancellation_timings=frozenset({CancellationTiming.IMMEDIATELY}),
            resume_scheduled_cancellation=False,
            atomic_multi_change=False,
        ),
        invoices=InvoiceCapabilities(retrieve=True),
        webhooks=WebhookCapabilities(signed=True),
        reconciliation=ReconciliationCapabilities(
            events=True,
            maximum_page_size=100,
        ),
    )


def test_payment_methods_for_returns_empty_frozenset_for_unsupported_mode(
    capabilities: GatewayCapabilities,
) -> None:
    assert (
        capabilities.checkouts.payment_methods_for(CheckoutMode.SUBSCRIPTION)
        == frozenset()
    )


def test_capabilities_are_immutable(capabilities: GatewayCapabilities) -> None:
    with pytest.raises(FrozenInstanceError):
        capabilities.invoices.retrieve = False
