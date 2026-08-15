"""Despacho tipado de comandos sem I/O antes das validações."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.base import BaseCheckoutGateway
from django_checkouts.gateways.commands import GatewayCommand
from django_checkouts.gateways.commands import RetrieveInvoice


@dataclass(frozen=True, slots=True, kw_only=True)
class Echo(GatewayCommand[str]):
    """Comando mínimo para exercitar o despacho."""

    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EchoChild(Echo):
    """Subtipo que não pode reutilizar o handler de ``Echo``."""


class EchoHandler:
    command_type = Echo

    def validate(self, command: Echo, capabilities: GatewayCapabilities) -> None:
        if not command.value:
            raise ValidationError("value é obrigatório.")

    def handle(self, command: Echo, context: Any) -> str:
        return f"{context.variant}:{command.value}"


class FailingHandler:
    command_type = Echo

    def validate(self, command: Echo, capabilities: GatewayCapabilities) -> None:
        return None

    def handle(self, command: Echo, context: Any) -> str:
        return context.call(self._raise_external_error, mutation=True)

    def _raise_external_error(self) -> str:
        raise RuntimeError("Bearer segredo-externo")


class FakeGateway(BaseCheckoutGateway):
    name = "fake"
    capabilities = GatewayCapabilities(
        checkouts=CheckoutCapabilities(
            modes=frozenset({CheckoutMode.PAYMENT}),
            payment_methods_by_mode={
                CheckoutMode.PAYMENT: frozenset({PaymentMethod.CARD}),
            },
            billing_cycles=frozenset({BillingCycle.MONTHLY}),
            supports_catalog_prices=True,
            supports_inline_prices=True,
            supports_expiration=False,
            supports_customer_prefill=False,
        ),
        subscriptions=SubscriptionCapabilities(
            retrieve=False,
            change_quantity=False,
            replace_price=False,
            add_remove_items=False,
            timings=frozenset({ChangeTiming.IMMEDIATELY}),
            proration_behaviors=frozenset({ProrationBehavior.NONE}),
            cancellation_timings=frozenset({CancellationTiming.IMMEDIATELY}),
            resume_scheduled_cancellation=False,
            atomic_multi_change=False,
        ),
        invoices=InvoiceCapabilities(retrieve=False),
        webhooks=WebhookCapabilities(signed=True),
        reconciliation=ReconciliationCapabilities(
            events=False,
            maximum_page_size=100,
        ),
    )
    handlers = (EchoHandler(),)

    def __init__(self, **configuration: object) -> None:
        super().__init__(variant="fake-br", **configuration)
        self.io_calls = 0


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


def test_validation_precedes_io(fake_gateway: FakeGateway) -> None:
    with pytest.raises(ValidationError):
        fake_gateway.execute(Echo(value=""))

    assert fake_gateway.io_calls == 0


def test_missing_handler_is_capability_error(fake_gateway: FakeGateway) -> None:
    with pytest.raises(CapabilityNotSupported):
        fake_gateway.execute(RetrieveInvoice(external_id="in_123"))

    assert fake_gateway.io_calls == 0


def test_dispatch_uses_the_exact_command_type(fake_gateway: FakeGateway) -> None:
    with pytest.raises(CapabilityNotSupported):
        fake_gateway.execute(EchoChild(value="olá"))


def test_dispatch_passes_the_variant_to_the_handler(fake_gateway: FakeGateway) -> None:
    assert fake_gateway.execute(Echo(value="olá")) == "fake-br:olá"


def test_call_translates_external_errors_without_exposing_the_message() -> None:
    class FailingGateway(FakeGateway):
        handlers = (FailingHandler(),)

    with pytest.raises(GatewayPermanentError) as caught:
        FailingGateway().execute(Echo(value="olá"))

    assert "segredo-externo" not in str(caught.value)
