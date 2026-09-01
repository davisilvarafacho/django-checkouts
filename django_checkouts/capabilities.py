"""Capacidades imutáveis declaradas por cada gateway."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 - runtime hints
from dataclasses import dataclass
from types import MappingProxyType

from django_checkouts.enums import BillingCycle  # noqa: TC001 - runtime hints
from django_checkouts.enums import CancellationTiming  # noqa: TC001 - runtime hints
from django_checkouts.enums import ChangeTiming  # noqa: TC001 - runtime hints
from django_checkouts.enums import CheckoutMode  # noqa: TC001 - runtime hints
from django_checkouts.enums import PaymentMethod  # noqa: TC001 - runtime hints
from django_checkouts.enums import ProrationBehavior  # noqa: TC001 - runtime hints


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutCapabilities:
    """Operações e opções suportadas na criação de checkouts."""

    modes: frozenset[CheckoutMode]
    payment_methods_by_mode: Mapping[CheckoutMode, frozenset[PaymentMethod]]
    billing_cycles: frozenset[BillingCycle]
    supports_catalog_prices: bool
    supports_inline_prices: bool
    supports_expiration: bool
    supports_customer_prefill: bool
    supports_setup: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "modes", frozenset(self.modes))
        object.__setattr__(
            self,
            "payment_methods_by_mode",
            MappingProxyType(
                {
                    mode: frozenset(methods)
                    for mode, methods in self.payment_methods_by_mode.items()
                }
            ),
        )
        object.__setattr__(self, "billing_cycles", frozenset(self.billing_cycles))

    def payment_methods_for(self, mode: CheckoutMode) -> frozenset[PaymentMethod]:
        """Devolve meios do modo ou o conjunto vazio quando ele não é suportado."""
        return self.payment_methods_by_mode.get(mode, frozenset())


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionCapabilities:
    """Operações portáveis disponíveis para assinaturas remotas."""

    retrieve: bool
    change_quantity: bool
    replace_price: bool
    add_remove_items: bool
    timings: frozenset[ChangeTiming]
    proration_behaviors: frozenset[ProrationBehavior]
    cancellation_timings: frozenset[CancellationTiming]
    resume_scheduled_cancellation: bool
    atomic_multi_change: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "timings", frozenset(self.timings))
        object.__setattr__(
            self,
            "proration_behaviors",
            frozenset(self.proration_behaviors),
        )
        object.__setattr__(
            self,
            "cancellation_timings",
            frozenset(self.cancellation_timings),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceCapabilities:
    """Operações portáveis disponíveis para faturas."""

    retrieve: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class WebhookCapabilities:
    """Garantias oferecidas na verificação de webhooks."""

    signed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationCapabilities:
    """Operações para conciliação de eventos remotos."""

    events: bool
    maximum_page_size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayCapabilities:
    """Conjunto completo de capacidades de uma implementação de gateway."""

    checkouts: CheckoutCapabilities
    subscriptions: SubscriptionCapabilities
    invoices: InvoiceCapabilities
    webhooks: WebhookCapabilities
    reconciliation: ReconciliationCapabilities
