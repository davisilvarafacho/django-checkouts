"""Provider do Stripe. Nenhum teste toca a rede: o SDK é substituído."""

from __future__ import annotations

from datetime import timedelta

import pytest
import stripe
from django.utils import timezone

from django_checkouts.dto import Customer
from django_checkouts.dto import LineItem
from django_checkouts.dto import Recurrence
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import EventType
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import Provider
from django_checkouts.exceptions import CheckoutNotFound
from django_checkouts.exceptions import ProviderPermanentError
from django_checkouts.exceptions import ProviderTemporaryError
from django_checkouts.exceptions import ValidationError
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.providers.stripe import StripeCheckoutProvider

SUCCESS_URL = "https://exemplo.com.br/obrigado/"


@pytest.fixture
def provider():
    return StripeCheckoutProvider(
        api_key="sk_test_dummy",
        webhook_secret="whsec_dummy",
        sandbox=True,
    )


@pytest.fixture
def capture_create(monkeypatch, load_fixture):
    """Substitui Session.create e devolve os kwargs recebidos."""
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return load_fixture("session_open.json")

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(fake_create))
    return captured


def item(**kwargs):
    return LineItem(
        name=kwargs.pop("name", "Plano Pro"),
        amount=kwargs.pop("amount", 4990),
        **kwargs,
    )


class TestCreateCheckout:
    def test_builds_inline_price_data(self, provider, capture_create):
        provider.create_checkout(items=[item()], success_url=SUCCESS_URL)
        line = capture_create["line_items"][0]
        assert line["price_data"]["unit_amount"] == 4990
        assert line["price_data"]["currency"] == "brl"
        assert line["price_data"]["product_data"]["name"] == "Plano Pro"

    def test_uses_catalog_price_when_given(self, provider, capture_create):
        """Com price_id não se manda price_data — senão o Stripe cria Product novo."""
        provider.create_checkout(
            items=[LineItem(name="Plano", amount=0, provider_price_id="price_123")],
            success_url=SUCCESS_URL,
        )
        line = capture_create["line_items"][0]
        assert line == {"price": "price_123", "quantity": 1}

    def test_maps_payment_methods(self, provider, capture_create):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            payment_methods=[PaymentMethod.PIX, PaymentMethod.BOLETO],
        )
        assert capture_create["payment_method_types"] == ["pix", "boleto"]

    def test_reference_id_becomes_client_reference_id(self, provider, capture_create):
        provider.create_checkout(
            items=[item()], success_url=SUCCESS_URL, reference_id="pedido-123"
        )
        assert capture_create["client_reference_id"] == "pedido-123"

    def test_customer_email_prefills(self, provider, capture_create):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            customer=Customer(email="pagador@exemplo.com.br"),
        )
        assert capture_create["customer_email"] == "pagador@exemplo.com.br"

    def test_existing_customer_id_wins_over_email(self, provider, capture_create):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            customer=Customer(email="a@b.com", provider_customer_id="cus_1"),
        )
        assert capture_create["customer"] == "cus_1"
        assert "customer_email" not in capture_create

    def test_provider_options_override_last(self, provider, capture_create):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            provider_options={"submit_type": "pay", "locale": "pt-BR"},
        )
        assert capture_create["locale"] == "pt-BR"

    @pytest.mark.parametrize(
        ("cycle", "expected"),
        [
            (BillingCycle.WEEKLY, ("week", 1)),
            (BillingCycle.BIWEEKLY, ("week", 2)),
            (BillingCycle.MONTHLY, ("month", 1)),
            (BillingCycle.QUARTERLY, ("month", 3)),
            (BillingCycle.SEMIANNUALLY, ("month", 6)),
            (BillingCycle.YEARLY, ("year", 1)),
        ],
    )
    def test_translates_every_cycle(self, provider, capture_create, cycle, expected):
        provider.create_checkout(
            items=[item()],
            success_url=SUCCESS_URL,
            mode=CheckoutMode.SUBSCRIPTION,
            recurrence=Recurrence(cycle=cycle),
        )
        recurring = capture_create["line_items"][0]["price_data"]["recurring"]
        assert (recurring["interval"], recurring["interval_count"]) == expected

    def test_subscription_with_pix_is_refused(self, provider, capture_create):
        """Pix não é recorrente no Stripe; recusar é melhor que um 400 obscuro."""
        with pytest.raises(ValidationError, match="cartão"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                mode=CheckoutMode.SUBSCRIPTION,
                payment_methods=[PaymentMethod.PIX],
                recurrence=Recurrence(cycle=BillingCycle.MONTHLY),
            )

    def test_expiration_below_stripe_minimum_is_refused(self, provider, capture_create):
        with pytest.raises(ValidationError, match="30 minutos"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                expires_at=timezone.now() + timedelta(minutes=5),
            )

    def test_expiration_above_stripe_maximum_is_refused(self, provider, capture_create):
        with pytest.raises(ValidationError, match="24 horas"):
            provider.create_checkout(
                items=[item()],
                success_url=SUCCESS_URL,
                expires_at=timezone.now() + timedelta(days=3),
            )


class TestStatusMapping:
    @pytest.mark.parametrize(
        ("status", "payment_status", "expected"),
        [
            ("open", "unpaid", CheckoutStatus.PENDING),
            ("complete", "paid", CheckoutStatus.PAID),
            ("complete", "unpaid", CheckoutStatus.PENDING),
            ("complete", "no_payment_required", CheckoutStatus.PAID),
            ("expired", "unpaid", CheckoutStatus.EXPIRED),
        ],
    )
    def test_pair_decides_status(self, provider, status, payment_status, expected):
        """`complete` sozinho não quer dizer pago: boleto emitido é PENDING."""
        assert provider.map_status(f"{status}/{payment_status}") == expected

    def test_unknown_pair_raises(self, provider):
        with pytest.raises(ProviderPermanentError, match="STATUS_MAP"):
            provider.map_status("complete/estorno_parcial")


class TestRetrieveAndCancel:
    def test_retrieve_normalizes_paid_session(
        self, provider, monkeypatch, load_fixture
    ):
        monkeypatch.setattr(
            stripe.checkout.Session,
            "retrieve",
            staticmethod(lambda *a, **k: load_fixture("session_paid.json")),
        )
        data = provider.retrieve_checkout("cs_test_a1b2c3")
        assert data.status == CheckoutStatus.PAID
        assert data.is_paid
        assert data.amount_total == 4990
        assert data.currency == "BRL"
        assert data.reference_id == "pedido-123"
        assert data.customer.email == "pagador@exemplo.com.br"
        assert data.customer.tax_id == "12345678909"
        assert data.raw["id"] == "cs_test_a1b2c3"

    def test_cancel_expires_the_session(self, provider, monkeypatch, load_fixture):
        called = {}

        def fake_expire(session_id, **kwargs):
            called["id"] = session_id
            payload = load_fixture("session_open.json")
            payload["status"] = "expired"
            return payload

        monkeypatch.setattr(
            stripe.checkout.Session, "expire", staticmethod(fake_expire)
        )
        data = provider.cancel_checkout("cs_test_a1b2c3")
        assert called["id"] == "cs_test_a1b2c3"
        assert data.status == CheckoutStatus.EXPIRED


class TestErrorTranslation:
    def test_connection_error_is_temporary(self, provider, monkeypatch):
        def boom(**kwargs):
            raise stripe.APIConnectionError("conexão caiu")

        monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(boom))
        with pytest.raises(ProviderTemporaryError):
            provider.create_checkout(items=[item()], success_url=SUCCESS_URL)

    def test_invalid_request_is_permanent(self, provider, monkeypatch):
        def boom(**kwargs):
            raise stripe.InvalidRequestError("parâmetro inválido", param="line_items")

        monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(boom))
        with pytest.raises(ProviderPermanentError):
            provider.create_checkout(items=[item()], success_url=SUCCESS_URL)

    def test_missing_session_becomes_checkout_not_found(self, provider, monkeypatch):
        def boom(*args, **kwargs):
            raise stripe.InvalidRequestError(
                "No such checkout.session: cs_x", param="id"
            )

        monkeypatch.setattr(stripe.checkout.Session, "retrieve", staticmethod(boom))
        with pytest.raises(CheckoutNotFound):
            provider.retrieve_checkout("cs_x")


class TestWebhook:
    def test_verified_event_is_normalized(
        self, provider, monkeypatch, load_fixture
    ):
        payload = load_fixture("webhook_completed.json")
        monkeypatch.setattr(
            stripe.Webhook, "construct_event", staticmethod(lambda **k: payload)
        )
        event = provider.verify_webhook(b"{}", {"stripe-signature": "t=1,v1=abc"})

        assert event.provider is Provider.STRIPE
        assert event.event_id == "evt_test_123"
        assert event.event_type == "checkout.session.completed"
        assert event.type == EventType.CHECKOUT_PAID
        assert event.external_id == "cs_test_a1b2c3"
        assert event.reference_id == "pedido-123"
        assert event.status == CheckoutStatus.PAID
        assert event.data.amount_total == 4990

    def test_missing_signature_header_is_refused(self, provider):
        with pytest.raises(WebhookVerificationError, match="stripe-signature"):
            provider.verify_webhook(b"{}", {})

    def test_bad_signature_is_refused(self, provider, monkeypatch):
        def boom(**kwargs):
            raise stripe.SignatureVerificationError("assinatura inválida", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(boom))
        with pytest.raises(WebhookVerificationError, match="não confere"):
            provider.verify_webhook(b"{}", {"stripe-signature": "t=1,v1=xxx"})

    def test_missing_webhook_secret_refuses_instead_of_accepting(self):
        """Sem segredo, aceitar seria pior do que recusar."""
        insecure = StripeCheckoutProvider(api_key="sk_test_x", webhook_secret="")
        with pytest.raises(WebhookVerificationError, match="não configurado"):
            insecure.verify_webhook(b"{}", {"stripe-signature": "t=1,v1=abc"})

    def test_unknown_event_type_survives(self, provider, monkeypatch):
        payload = {
            "id": "evt_x",
            "type": "invoice.paid",
            "data": {"object": {"object": "invoice"}},
        }
        monkeypatch.setattr(
            stripe.Webhook, "construct_event", staticmethod(lambda **k: payload)
        )
        event = provider.verify_webhook(b"{}", {"stripe-signature": "t=1,v1=abc"})
        assert event.type is None
        assert event.event_type == "invoice.paid"
        assert event.raw == payload
