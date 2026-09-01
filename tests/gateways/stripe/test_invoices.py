"""Consulta de faturas pela interface normalizada do Stripe."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from unittest.mock import Mock

import pytest
import stripe

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import InvoiceReason
from django_checkouts.enums import InvoiceStatus
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.gateways.stripe import StripeGateway


@pytest.fixture
def stripe_mock(monkeypatch):
    monkeypatch.setattr(stripe.Invoice, "retrieve", Mock())
    monkeypatch.setattr(stripe, "api_key", "global-key-must-not-change")
    return stripe


@pytest.fixture
def stripe_client() -> CheckoutClient:
    return CheckoutClient(
        StripeGateway(
            api_key="sk_test_per_account",
            webhook_secret="whsec_test",
            variant="stripe-br",
        )
    )


def stripe_invoice(payload: dict[str, object]) -> object:
    return stripe.Invoice.construct_from(payload, "sk_test")


def test_retrieve_normalizes_real_sdk_invoice(stripe_client, stripe_mock, load_fixture):
    stripe_mock.Invoice.retrieve.return_value = stripe_invoice(
        load_fixture("invoice_paid.json")
    )

    invoice = stripe_client.invoices.retrieve("in_paid_1")

    stripe_mock.Invoice.retrieve.assert_called_once_with(
        "in_paid_1",
        expand=["lines.data.price"],
        api_key="sk_test_per_account",
    )
    assert invoice.external_id == "in_paid_1"
    assert invoice.status is InvoiceStatus.PAID
    assert invoice.reason is InvoiceReason.RENEWAL
    assert invoice.subscription_id == "sub_1"
    assert invoice.customer_id == "cus_42"
    assert invoice.amount_due == 7300
    assert invoice.amount_paid == 7300
    assert invoice.amount_remaining == 0
    assert invoice.currency == "BRL"
    assert invoice.paid_at == datetime.fromtimestamp(1785542500, tz=UTC)
    assert invoice.reference_id == "renewal-42"
    assert invoice.lines[1].quantity == 2
    assert invoice.lines[1].unit_amount == 1200
    assert invoice.lines[1].subscription_item_id == "si_2"
    assert invoice.lines[1].period_end == datetime.fromtimestamp(1788220800, tz=UTC)
    assert type(invoice.raw) is not dict
    assert type(invoice.raw["lines"]) is dict


def test_failed_invoice_maps_retry_details(stripe_client, stripe_mock, load_fixture):
    stripe_mock.Invoice.retrieve.return_value = load_fixture("invoice_failed.json")

    invoice = stripe_client.invoices.retrieve("in_failed_1")

    assert invoice.status is InvoiceStatus.OPEN
    assert invoice.reason is InvoiceReason.INITIAL_SUBSCRIPTION
    assert invoice.attempt_count == 2
    assert invoice.next_payment_attempt_at == datetime.fromtimestamp(1785628800, tz=UTC)
    assert invoice.hosted_url == "https://invoice.stripe.test/in_failed_1"


def test_retrieve_normalizes_current_sdk_invoice_shape(
    stripe_client, stripe_mock, load_fixture
):
    raw = load_fixture("invoice_paid.json")
    raw.pop("subscription")
    raw["parent"] = {
        "type": "subscription_details",
        "subscription_details": {"subscription": {"id": "sub_1"}},
    }
    line = raw["lines"]["data"][0]
    price = line.pop("price")
    line.pop("subscription_item")
    line["parent"] = {
        "type": "subscription_item_details",
        "subscription_item_details": {"subscription_item": "si_1"},
    }
    line["pricing"] = {
        "type": "price_details",
        "price_details": {"price": price, "product": "prod_1"},
        "unit_amount_decimal": "4900",
    }
    stripe_mock.Invoice.retrieve.return_value = stripe_invoice(raw)

    invoice = stripe_client.invoices.retrieve("in_paid_1")

    assert invoice.subscription_id == "sub_1"
    assert invoice.lines[0].subscription_item_id == "si_1"
    assert invoice.lines[0].unit_amount == 4900


@pytest.mark.parametrize(
    ("billing_reason", "expected"),
    [
        ("subscription_create", InvoiceReason.INITIAL_SUBSCRIPTION),
        ("subscription_cycle", InvoiceReason.RENEWAL),
        ("subscription_update", InvoiceReason.SUBSCRIPTION_UPDATE),
        ("manual", InvoiceReason.MANUAL),
        ("upcoming", InvoiceReason.UNKNOWN),
        (None, InvoiceReason.UNKNOWN),
    ],
)
def test_invoice_reason_mapping(
    stripe_client, stripe_mock, load_fixture, billing_reason, expected
):
    raw = load_fixture("invoice_paid.json")
    raw["billing_reason"] = billing_reason
    stripe_mock.Invoice.retrieve.return_value = raw

    assert stripe_client.invoices.retrieve("in_1").reason is expected


@pytest.mark.parametrize("status", [None, "future_status"])
def test_unknown_invoice_status_is_a_public_protocol_error(
    stripe_client, stripe_mock, load_fixture, status
):
    raw = load_fixture("invoice_paid.json")
    raw["status"] = status
    stripe_mock.Invoice.retrieve.return_value = raw

    with pytest.raises(GatewayProtocolError):
        stripe_client.invoices.retrieve("in_1")


@pytest.mark.parametrize(
    "quantity",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="bool"),
        pytest.param(1.5, id="fraction"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
    ],
)
def test_invoice_response_quantities_are_strict(
    stripe_client, stripe_mock, load_fixture, quantity
):
    raw = load_fixture("invoice_paid.json")
    raw["lines"]["data"][0]["quantity"] = quantity
    stripe_mock.Invoice.retrieve.return_value = raw

    with pytest.raises(GatewayProtocolError):
        stripe_client.invoices.retrieve("in_1")
