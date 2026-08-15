"""Contrato da BaseCheckoutProvider: o que ela recusa antes de tocar a rede.

Estes testes usam um provider de mentira. Se algum deles fizer I/O, é bug: toda
validação aqui precisa acontecer antes de qualquer chamada ao gateway.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from django_checkouts.base import BaseCheckoutProvider
from django_checkouts.dto import CheckoutData
from django_checkouts.dto import LineItem
from django_checkouts.dto import Recurrence
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import Capability
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import PaymentMethod
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.exceptions import UnsupportedPaymentMethod
from django_checkouts.exceptions import ValidationError

SUCCESS_URL = "https://exemplo.com.br/obrigado/"


class FakeProvider(BaseCheckoutProvider):
    name = "fake"
    STATUS_MAP = {"ok": CheckoutStatus.PAID}
    CAPABILITIES = {
        Capability.SUBSCRIPTION,
        Capability.EXPIRATION,
        Capability.CUSTOMER_PREFILL,
    }
    SUPPORTED_PAYMENT_METHODS = {PaymentMethod.CARD, PaymentMethod.PIX}
    SUPPORTED_CYCLES = {BillingCycle.MONTHLY}

    def __init__(self):
        self.received = None

    def _create_checkout(self, request):
        self.received = request
        return CheckoutData(
            external_id="fake-1",
            status=CheckoutStatus.PENDING,
            provider=self.name,
            mode=request.mode,
            url="https://pagar.exemplo/fake-1",
        )


@pytest.fixture
def provider():
    return FakeProvider()


def item(**kwargs):
    return LineItem(
        name=kwargs.pop("name", "Plano Pro"),
        amount=kwargs.pop("amount", 4990),
        **kwargs,
    )


class TestLineItem:
    def test_rejects_zero_amount(self):
        with pytest.raises(ValidationError, match="centavos"):
            LineItem(name="Plano", amount=0)

    def test_rejects_blank_name(self):
        with pytest.raises(ValidationError, match="name"):
            LineItem(name="   ", amount=100)

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValidationError, match="quantity"):
            LineItem(name="Plano", amount=100, quantity=0)

    def test_allows_zero_amount_with_provider_price_id(self):
        """Com preço do catálogo, o valor vem do provedor e não daqui."""
        assert LineItem(name="Plano", amount=0, provider_price_id="price_1").amount == 0

    def test_total_multiplies_quantity(self):
        assert LineItem(name="Plano", amount=4990, quantity=3).total == 14970


class TestCreateCheckoutValidation:
    def test_requires_items(self, provider):
        with pytest.raises(ValidationError, match="pelo menos um item"):
            provider.create_checkout(items=[], success_url=SUCCESS_URL)

    def test_rejects_relative_success_url(self, provider):
        with pytest.raises(ValidationError, match="URL absoluta"):
            provider.create_checkout(items=[item()], success_url="/obrigado/")

    def test_rejects_unsupported_payment_method(self, provider):
        with pytest.raises(UnsupportedPaymentMethod, match="boleto"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                payment_methods=[PaymentMethod.BOLETO],
            )

    def test_rejects_unsupported_cycle(self, provider):
        with pytest.raises(ValidationError, match="ciclo"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                mode=CheckoutMode.SUBSCRIPTION,
                recurrence=Recurrence(cycle=BillingCycle.YEARLY),
            )

    def test_subscription_requires_recurrence(self, provider):
        with pytest.raises(ValidationError, match="recurrence"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                mode=CheckoutMode.SUBSCRIPTION,
            )

    def test_recurrence_without_subscription_is_rejected(self, provider):
        """Falhar é melhor que ignorar em silêncio uma cobrança recorrente."""
        with pytest.raises(ValidationError, match="SUBSCRIPTION"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                recurrence=Recurrence(cycle=BillingCycle.MONTHLY),
            )

    def test_rejects_naive_expires_at(self, provider):
        with pytest.raises(ValidationError, match="timezone-aware"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                expires_at=timezone.now().replace(tzinfo=None) + timedelta(hours=1),
            )

    def test_rejects_past_expires_at(self, provider):
        with pytest.raises(ValidationError, match="futuro"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                expires_at=timezone.now() - timedelta(hours=1),
            )

    def test_rejects_non_string_metadata(self, provider):
        with pytest.raises(ValidationError, match="string"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                metadata={"pedido": 123},
            )

    def test_deduplicates_payment_methods_preserving_order(self, provider):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            payment_methods=[PaymentMethod.PIX, PaymentMethod.CARD, PaymentMethod.PIX],
        )
        assert provider.received.payment_methods == (
            PaymentMethod.PIX,
            PaymentMethod.CARD,
        )

    def test_uppercases_currency(self, provider):
        provider.create_checkout(
            items=[item()], success_url=SUCCESS_URL, currency="brl"
        )
        assert provider.received.currency == "BRL"

    def test_amount_total_sums_items(self, provider):
        provider.create_checkout(
            items=[item(amount=1000, quantity=2), item(name="Extra", amount=500)],
            success_url=SUCCESS_URL,
        )
        assert provider.received.amount_total == 2500


class TestCapabilities:
    def test_cancel_without_capability_is_refused(self, provider):
        with pytest.raises(CapabilityNotSupported, match="cancel"):
            provider.cancel_checkout("fake-1")

    def test_provider_price_id_without_catalog_is_refused(self, provider):
        """Melhor recusar do que ignorar o price_id e cobrar o valor errado."""
        with pytest.raises(CapabilityNotSupported, match="provider_catalog"):
            provider.create_checkout(
                items=[LineItem(name="Plano", amount=100, provider_price_id="price_1")],
                success_url=SUCCESS_URL,
            )


class TestStatusMapping:
    def test_maps_known_status(self, provider):
        assert provider.map_status("ok") == CheckoutStatus.PAID

    def test_unknown_status_raises_with_actionable_message(self, provider):
        with pytest.raises(GatewayProtocolError, match="STATUS_MAP"):
            provider.map_status("estado_novo_do_gateway")

    def test_unknown_event_returns_none_instead_of_raising(self, provider):
        """Evento fora do escopo não pode derrubar a fila de webhooks."""
        assert provider.map_event("invoice.created") is None


class TestEmptyId:
    def test_retrieve_rejects_blank_id(self, provider):
        with pytest.raises(ValidationError, match="external_id"):
            provider.retrieve_checkout("   ")
