"""A suíte pública de contratos pode ser reutilizada por gateways."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from unittest.mock import Mock

import pytest

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.commands import CreateCheckout
from django_checkouts.gateways.stripe import StripeGateway
from django_checkouts.testing import FakeCheckoutGateway
from django_checkouts.testing import GatewayContractSuite
from django_checkouts.types import Checkout
from django_checkouts.types import WebhookEvent


@pytest.fixture
def gateway() -> StripeGateway:
    return StripeGateway(
        api_key="sk_test_contract",
        webhook_secret="whsec_contract",
        variant="stripe-contract",
    )


@pytest.fixture
def suite(gateway) -> GatewayContractSuite:
    return GatewayContractSuite(gateway)


def checkout_result() -> Checkout:
    return Checkout(
        external_id="cs_1",
        gateway="fake",
        variant="fake",
        status=CheckoutStatus.PAID,
        mode=CheckoutMode.PAYMENT,
        url=None,
        amount_total=1000,
        currency="brl",
        customer=None,
        reference_id=None,
        subscription_id=None,
        expires_at=None,
        created_at=datetime(2026, 8, 15, tzinfo=UTC),
        raw={"id": "cs_1", "currency": "brl"},
    )


def webhook_event(*, known: bool = True) -> WebhookEvent:
    return WebhookEvent(
        gateway="fake",
        variant="fake",
        event_id="evt_1",
        event_type="checkout.paid" if known else "future.event",
        type=None,
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        resource_kind=None,
        resource_id=None,
        resource=None,
        livemode=False,
        raw={"id": "evt_1"},
    )


def test_asserts_unique_exact_handlers_and_capability_agreement(suite) -> None:
    suite.assert_unique_exact_handlers()
    suite.assert_capability_handler_agreement()


def test_detects_duplicate_handler_types(gateway) -> None:
    gateway.handlers = (*gateway.handlers, gateway.handlers[0])

    with pytest.raises(AssertionError, match="handler"):
        GatewayContractSuite(gateway).assert_unique_exact_handlers()


def test_asserts_validation_happens_before_io(suite) -> None:
    io = Mock()

    suite.assert_validation_before_io(
        lambda: (_ for _ in ()).throw(ValidationError("invalid")),
        io,
    )


def test_asserts_idempotency_key_is_forwarded_unchanged(suite) -> None:
    operation = Mock(return_value=checkout_result())
    key = "tenant:checkout:v1"

    suite.assert_unchanged_idempotency_key(
        lambda: operation(idempotency_key=key), operation, key
    )


def test_asserts_normalized_types_utc_currency_and_hidden_immutable_raw(
    suite,
) -> None:
    suite.assert_normalized_result(checkout_result(), Checkout)


def test_asserts_only_public_sanitized_errors_escape(suite) -> None:
    suite.assert_public_errors_only(
        lambda: (_ for _ in ()).throw(
            GatewayPermanentError(
                "public",
                gateway="fake",
                variant="fake",
                gateway_message="secret",
            )
        ),
        forbidden_values=("secret",),
    )


def test_asserts_verified_ids_and_unknown_event_shape(suite) -> None:
    event = webhook_event(known=False)

    suite.assert_verified_event_ids((event,))
    suite.assert_unknown_event(event)


def test_fake_gateway_remains_exported_and_records_commands() -> None:
    result = checkout_result()
    command = CreateCheckout(request=Mock(), idempotency_key="same-key")
    fake = FakeCheckoutGateway(
        results={CreateCheckout: result},
        capabilities=Mock(),
    )

    assert CheckoutClient(fake)._gateway.execute(command) is result
    assert fake.commands == [command]
