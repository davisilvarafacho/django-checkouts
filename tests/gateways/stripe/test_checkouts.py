"""Operações de Checkout Session pela interface normalizada do Stripe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import stripe
from django.utils import timezone

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import Gateway
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import RetryDisposition
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.exceptions import GatewayTemporaryError
from django_checkouts.exceptions import ResourceNotFound
from django_checkouts.exceptions import UnsupportedPaymentMethod
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways import GatewayOptions
from django_checkouts.gateways.stripe import StripeCheckoutOptions
from django_checkouts.gateways.stripe import StripeGateway
from django_checkouts.types import CatalogPrice
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import Customer
from django_checkouts.types import InlinePrice
from django_checkouts.types import Recurrence

if TYPE_CHECKING:
    from collections.abc import Mapping

SUCCESS_URL = "https://example.test/success"


@pytest.fixture
def stripe_mock(monkeypatch):
    monkeypatch.setattr(stripe.checkout.Session, "create", Mock())
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", Mock())
    monkeypatch.setattr(stripe.checkout.Session, "expire", Mock())
    monkeypatch.setattr(stripe.Subscription, "cancel", Mock())
    monkeypatch.setattr(stripe, "api_key", "global-key-must-not-change")
    return stripe


@pytest.fixture
def stripe_client() -> CheckoutClient:
    return CheckoutClient(
        StripeGateway(
            api_key="sk_test_per_account",
            webhook_secret="whsec_test",
            sandbox=True,
            variant="stripe-br",
        )
    )


def subscription_checkout(
    *, quantity: int = 1, method: PaymentMethod = PaymentMethod.CARD
) -> CheckoutCreate:
    return CheckoutCreate(
        mode=CheckoutMode.SUBSCRIPTION,
        items=(
            CheckoutItem(
                price=CatalogPrice(external_id="price_pro"),
                quantity=quantity,
            ),
        ),
        payment_methods=(method,),
        success_url=SUCCESS_URL,
    )


def payment_checkout(
    *,
    mode: CheckoutMode = CheckoutMode.PAYMENT,
    items: tuple[CheckoutItem, ...] | None = None,
    success_url: str = SUCCESS_URL,
    cancel_url: str | None = None,
    payment_methods: tuple[PaymentMethod, ...] = (
        PaymentMethod.PIX,
        PaymentMethod.BOLETO,
    ),
    customer: Customer | None = None,
    recurrence: Recurrence | None = None,
    reference_id: str | None = None,
    expires_at: datetime | None = None,
    metadata: Mapping[str, str] | None = None,
    gateway_options: GatewayOptions | None = None,
) -> CheckoutCreate:
    return CheckoutCreate(
        mode=mode,
        items=items
        or (
            CheckoutItem(
                price=InlinePrice(
                    name="Plano Pro",
                    description="Acesso completo",
                    image_url="https://example.test/pro.png",
                    unit_amount=4990,
                    currency="BRL",
                ),
                quantity=2,
            ),
        ),
        success_url=success_url,
        cancel_url=cancel_url,
        payment_methods=payment_methods,
        customer=customer,
        recurrence=recurrence,
        reference_id=reference_id,
        expires_at=expires_at,
        metadata=metadata or {},
        gateway_options=gateway_options,
    )


def test_subscription_checkout_sends_quantity_and_key(
    stripe_client, stripe_mock, load_fixture
):
    stripe_mock.checkout.Session.create.return_value = load_fixture(
        "session_open.json"
    )

    stripe_client.checkouts.create(
        subscription_checkout(quantity=10), idempotency_key="org-42:v1"
    )

    kwargs = stripe_mock.checkout.Session.create.call_args.kwargs
    assert kwargs["line_items"] == [{"price": "price_pro", "quantity": 10}]
    assert kwargs["idempotency_key"] == "org-42:v1"
    assert kwargs["api_key"] == "sk_test_per_account"
    assert stripe_mock.api_key == "global-key-must-not-change"


def test_subscription_pix_fails_before_sdk(stripe_client, stripe_mock):
    with pytest.raises(UnsupportedPaymentMethod):
        stripe_client.checkouts.create(
            subscription_checkout(method=PaymentMethod.PIX),
            idempotency_key="x:v1",
        )

    stripe_mock.checkout.Session.create.assert_not_called()


def test_inline_checkout_maps_portable_fields_and_typed_options(
    stripe_client, stripe_mock, load_fixture
):
    stripe_mock.checkout.Session.create.return_value = load_fixture(
        "session_open.json"
    )
    expires_at = timezone.now() + timedelta(hours=1)
    request = payment_checkout(
        cancel_url="https://example.test/cancel",
        reference_id="order-42",
        expires_at=expires_at,
        metadata={"tenant": "42"},
        customer=Customer(
            email="buyer@example.test", external_id="cus_existing"
        ),
        gateway_options=StripeCheckoutOptions(
            allow_promotion_codes=True,
            automatic_tax=True,
            billing_address_required=True,
        ),
    )

    stripe_client.checkouts.create(request, idempotency_key="order-42:v1")

    kwargs = stripe_mock.checkout.Session.create.call_args.kwargs
    assert kwargs["mode"] == "payment"
    assert kwargs["success_url"] == SUCCESS_URL
    assert kwargs["cancel_url"] == "https://example.test/cancel"
    assert kwargs["payment_method_types"] == ["pix", "boleto"]
    assert kwargs["client_reference_id"] == "order-42"
    assert kwargs["expires_at"] == int(expires_at.timestamp())
    assert kwargs["metadata"] == {"tenant": "42"}
    assert kwargs["customer"] == "cus_existing"
    assert "customer_email" not in kwargs
    assert kwargs["allow_promotion_codes"] is True
    assert kwargs["automatic_tax"] == {"enabled": True}
    assert kwargs["billing_address_collection"] == "required"
    assert kwargs["line_items"] == [
        {
            "price_data": {
                "currency": "brl",
                "unit_amount": 4990,
                "product_data": {
                    "name": "Plano Pro",
                    "description": "Acesso completo",
                    "images": ["https://example.test/pro.png"],
                },
            },
            "quantity": 2,
        }
    ]


@pytest.mark.parametrize(
    ("cycle", "expected"),
    [
        (BillingCycle.WEEKLY, {"interval": "week", "interval_count": 1}),
        (BillingCycle.BIWEEKLY, {"interval": "week", "interval_count": 2}),
        (BillingCycle.MONTHLY, {"interval": "month", "interval_count": 1}),
        (BillingCycle.BIMONTHLY, {"interval": "month", "interval_count": 2}),
        (BillingCycle.QUARTERLY, {"interval": "month", "interval_count": 3}),
        (BillingCycle.SEMIANNUALLY, {"interval": "month", "interval_count": 6}),
        (BillingCycle.YEARLY, {"interval": "year", "interval_count": 1}),
    ],
)
def test_subscription_inline_price_maps_every_billing_cycle(
    stripe_client, stripe_mock, load_fixture, cycle, expected
):
    stripe_mock.checkout.Session.create.return_value = load_fixture(
        "session_open.json"
    )
    request = payment_checkout(
        mode=CheckoutMode.SUBSCRIPTION,
        payment_methods=(PaymentMethod.CARD,),
        recurrence=Recurrence(cycle=cycle),
    )

    stripe_client.checkouts.create(request, idempotency_key=f"cycle:{cycle}")

    price_data = stripe_mock.checkout.Session.create.call_args.kwargs["line_items"][
        0
    ]["price_data"]
    assert price_data["recurring"] == expected


def test_customer_email_is_used_without_external_customer(
    stripe_client, stripe_mock, load_fixture
):
    stripe_mock.checkout.Session.create.return_value = load_fixture(
        "session_open.json"
    )

    stripe_client.checkouts.create(
        payment_checkout(customer=Customer(email="buyer@example.test")),
        idempotency_key="email:v1",
    )

    kwargs = stripe_mock.checkout.Session.create.call_args.kwargs
    assert kwargs["customer_email"] == "buyer@example.test"
    assert "customer" not in kwargs


@dataclass(frozen=True, slots=True, kw_only=True)
class OtherGatewayOptions(GatewayOptions):
    gateway = Gateway.ASAAS


def test_options_for_another_gateway_fail_before_sdk(stripe_client, stripe_mock):
    with pytest.raises(ValidationError, match="gateway_options"):
        stripe_client.checkouts.create(
            payment_checkout(gateway_options=OtherGatewayOptions()),
            idempotency_key="wrong-options:v1",
        )

    stripe_mock.checkout.Session.create.assert_not_called()


@pytest.mark.parametrize(
    "expires_at",
    [
        pytest.param(
            lambda: timezone.now() + timedelta(minutes=5), id="below-minimum"
        ),
        pytest.param(
            lambda: timezone.now() + timedelta(days=2), id="above-maximum"
        ),
    ],
)
def test_invalid_stripe_expiration_fails_before_sdk(
    stripe_client, stripe_mock, expires_at
):
    with pytest.raises(ValidationError, match=r"30 minutos|24 horas"):
        stripe_client.checkouts.create(
            payment_checkout(expires_at=expires_at()),
            idempotency_key="expiration:v1",
        )

    stripe_mock.checkout.Session.create.assert_not_called()


def test_retrieve_strictly_normalizes_session(
    stripe_client, stripe_mock, load_fixture
):
    raw = load_fixture("session_paid.json")
    raw["subscription"] = "sub_123"
    raw["created"] = 1_785_000_000
    stripe_mock.checkout.Session.retrieve.return_value = raw

    checkout = stripe_client.checkouts.retrieve("cs_test_a1b2c3")

    stripe_mock.checkout.Session.retrieve.assert_called_once_with(
        "cs_test_a1b2c3", api_key="sk_test_per_account"
    )
    assert checkout.gateway is Gateway.STRIPE
    assert checkout.variant == "stripe-br"
    assert checkout.status is CheckoutStatus.PAID
    assert checkout.mode is CheckoutMode.PAYMENT
    assert checkout.amount_total == 4990
    assert checkout.currency == "BRL"
    assert checkout.reference_id == "pedido-123"
    assert checkout.subscription_id == "sub_123"
    assert checkout.created_at == datetime.fromtimestamp(1_785_000_000, tz=UTC)
    assert checkout.expires_at == datetime.fromtimestamp(1_785_000_000, tz=UTC)
    assert checkout.customer == Customer(
        name="Maria Souza",
        email="pagador@exemplo.com.br",
        phone="+5511999999999",
        tax_id="12345678909",
        external_id="cus_ABC123",
    )
    assert checkout.raw["id"] == "cs_test_a1b2c3"


def test_cancel_expires_only_the_checkout_session(
    stripe_client, stripe_mock, load_fixture
):
    raw = load_fixture("session_open.json")
    raw["status"] = "expired"
    stripe_mock.checkout.Session.expire.return_value = raw

    checkout = stripe_client.checkouts.cancel(
        "cs_test_a1b2c3", idempotency_key="cancel:v1"
    )

    stripe_mock.checkout.Session.expire.assert_called_once_with(
        "cs_test_a1b2c3",
        idempotency_key="cancel:v1",
        api_key="sk_test_per_account",
    )
    stripe_mock.Subscription.cancel.assert_not_called()
    assert checkout.status is CheckoutStatus.EXPIRED


@pytest.mark.parametrize(
    ("status", "payment_status", "expected"),
    [
        ("open", "unpaid", CheckoutStatus.PENDING),
        ("complete", "paid", CheckoutStatus.PAID),
        ("complete", "unpaid", CheckoutStatus.PENDING),
        ("complete", "no_payment_required", CheckoutStatus.PAID),
        ("expired", "unpaid", CheckoutStatus.EXPIRED),
        ("expired", "paid", CheckoutStatus.PAID),
    ],
)
def test_status_mapping_uses_session_and_payment_status(
    stripe_client, stripe_mock, load_fixture, status, payment_status, expected
):
    raw = load_fixture("session_open.json")
    raw.update(status=status, payment_status=payment_status)
    stripe_mock.checkout.Session.retrieve.return_value = raw

    assert stripe_client.checkouts.retrieve("cs_1").status is expected


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "unexpected"), ("mode", "setup")],
)
def test_unknown_status_or_mode_is_a_protocol_error(
    stripe_client, stripe_mock, load_fixture, field, value
):
    raw = load_fixture("session_open.json")
    raw[field] = value
    stripe_mock.checkout.Session.retrieve.return_value = raw

    with pytest.raises(GatewayProtocolError):
        stripe_client.checkouts.retrieve("cs_1")


@pytest.mark.parametrize(
    ("sdk_error", "public_error"),
    [
        (stripe.APIConnectionError("connection failed"), GatewayTemporaryError),
        (
            stripe.InvalidRequestError("invalid request", param="line_items"),
            GatewayPermanentError,
        ),
    ],
)
def test_sdk_checkout_errors_are_translated(
    stripe_client, stripe_mock, sdk_error, public_error
):
    stripe_mock.checkout.Session.create.side_effect = sdk_error

    with pytest.raises(public_error):
        stripe_client.checkouts.create(
            payment_checkout(), idempotency_key="error:v1"
        )


def test_missing_checkout_is_resource_not_found(stripe_client, stripe_mock):
    stripe_mock.checkout.Session.retrieve.side_effect = stripe.InvalidRequestError(
        "No such checkout.session: cs_missing", param="id"
    )

    with pytest.raises(ResourceNotFound):
        stripe_client.checkouts.retrieve("cs_missing")


@pytest.mark.parametrize("operation", ["create", "cancel"])
@pytest.mark.parametrize(
    "sdk_error",
    [
        stripe.APIConnectionError("connection dropped"),
        stripe.APIError("server failed", http_status=500),
        stripe.APIError("server failed without status"),
    ],
)
def test_uncertain_mutation_error_requires_the_same_key(
    stripe_client, stripe_mock, operation, sdk_error
):
    if operation == "create":
        stripe_mock.checkout.Session.create.side_effect = sdk_error
    else:
        stripe_mock.checkout.Session.expire.side_effect = sdk_error

    def perform_mutation():
        if operation == "create":
            return stripe_client.checkouts.create(
                payment_checkout(), idempotency_key="retry:v1"
            )
        return stripe_client.checkouts.cancel(
            "cs_1", idempotency_key="retry:v1"
        )

    with pytest.raises(GatewayTemporaryError) as caught:
        perform_mutation()

    assert caught.value.retry_advice.disposition is RetryDisposition.RETRY_SAME_KEY


def test_read_connection_error_uses_generic_retry(stripe_client, stripe_mock):
    stripe_mock.checkout.Session.retrieve.side_effect = stripe.APIConnectionError(
        "connection dropped"
    )

    with pytest.raises(GatewayTemporaryError) as caught:
        stripe_client.checkouts.retrieve("cs_1")

    assert caught.value.retry_advice.disposition is RetryDisposition.RETRY


def test_statusless_api_error_is_temporary_for_read(stripe_client, stripe_mock):
    stripe_mock.checkout.Session.retrieve.side_effect = stripe.APIError(
        "server failed without status"
    )

    with pytest.raises(GatewayTemporaryError) as caught:
        stripe_client.checkouts.retrieve("cs_1")

    assert caught.value.code == 500
    assert caught.value.retry_advice.disposition is RetryDisposition.RETRY
