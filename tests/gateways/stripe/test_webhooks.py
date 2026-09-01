"""Autenticação e normalização de webhooks do Stripe."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest
import stripe

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import EventType
from django_checkouts.enums import Gateway
from django_checkouts.enums import InvoiceReason
from django_checkouts.enums import ResourceKind
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.gateways.stripe import StripeGateway


@pytest.fixture
def stripe_mock(monkeypatch):
    monkeypatch.setattr(stripe.Webhook, "construct_event", Mock())
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


@pytest.fixture
def signed_payload(load_fixture):
    return (
        b'{"untrusted":"bytes must remain unchanged"}',
        {"Stripe-Signature": "t=1785542500,v1=signature"},
        load_fixture("event_invoice_paid.json"),
    )


def test_verifies_original_bytes_before_mapping(
    stripe_client, stripe_mock, signed_payload
):
    body, headers, payload = signed_payload
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(body, headers)

    stripe_mock.Webhook.construct_event.assert_called_once_with(
        payload=body,
        sig_header=headers["Stripe-Signature"],
        secret="whsec_test",
    )
    assert event.gateway == Gateway.STRIPE
    assert event.variant == "stripe-br"
    assert event.event_id == "evt_invoice_paid_1"
    assert event.type == EventType.INVOICE_PAID
    assert event.resource_kind == ResourceKind.INVOICE
    assert event.resource_id == "in_paid_1"
    assert event.resource.reason == InvoiceReason.RENEWAL


def test_unknown_event_is_preserved(stripe_client, stripe_mock, load_fixture):
    payload = load_fixture("event_unknown.json")
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    assert event.type is None
    assert event.event_type == "customer.tax_id.updated"
    assert event.resource_kind is None
    assert event.resource_id is None
    assert event.resource is None
    assert dict(event.raw) == payload


@pytest.mark.parametrize(
    ("remote_type", "expected"),
    [
        ("invoice.created", EventType.INVOICE_OPENED),
        ("invoice.finalized", EventType.INVOICE_OPENED),
        ("invoice.paid", EventType.INVOICE_PAID),
        ("invoice.payment_failed", EventType.INVOICE_PAYMENT_FAILED),
        ("invoice.voided", EventType.INVOICE_VOIDED),
        ("invoice.marked_uncollectible", EventType.INVOICE_UNCOLLECTIBLE),
    ],
)
def test_normalizes_invoice_event_taxonomy(
    stripe_client, stripe_mock, load_fixture, remote_type, expected
):
    payload = load_fixture("event_invoice_paid.json")
    payload["type"] = remote_type
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    assert event.type == expected
    assert event.type != "subscription.renewed"


@pytest.mark.parametrize(
    ("remote_type", "expected"),
    [
        ("checkout.session.created", EventType.CHECKOUT_PENDING),
        ("checkout.session.completed", EventType.CHECKOUT_PAID),
        ("checkout.session.async_payment_succeeded", EventType.CHECKOUT_PAID),
        ("checkout.session.async_payment_failed", EventType.CHECKOUT_FAILED),
        ("checkout.session.expired", EventType.CHECKOUT_EXPIRED),
        ("checkout.session.canceled", EventType.CHECKOUT_CANCELED),
    ],
)
def test_normalizes_checkout_event_taxonomy(
    stripe_client, stripe_mock, load_fixture, remote_type, expected
):
    payload = load_fixture("event_invoice_paid.json")
    payload["type"] = remote_type
    payload["data"]["object"] = load_fixture("session_paid.json")
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    assert event.type == expected
    assert event.resource_kind == ResourceKind.CHECKOUT


def test_completed_checkout_with_delayed_payment_remains_pending(
    stripe_client, stripe_mock, load_fixture
):
    payload = load_fixture("event_invoice_paid.json")
    session = load_fixture("session_paid.json")
    session["payment_status"] = "unpaid"
    payload["type"] = "checkout.session.completed"
    payload["data"]["object"] = session
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    assert event.type == EventType.CHECKOUT_PENDING


@pytest.mark.parametrize(
    ("remote_type", "expected"),
    [
        ("customer.subscription.created", EventType.SUBSCRIPTION_CREATED),
        ("customer.subscription.updated", EventType.SUBSCRIPTION_UPDATED),
        ("customer.subscription.deleted", EventType.SUBSCRIPTION_CANCELED),
    ],
)
def test_normalizes_subscription_event_taxonomy(
    stripe_client, stripe_mock, load_fixture, remote_type, expected
):
    payload = load_fixture("event_invoice_paid.json")
    payload["type"] = remote_type
    payload["data"]["object"] = load_fixture("subscription_active.json")
    stripe_mock.Webhook.construct_event.return_value = payload

    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    assert event.type == expected
    assert event.resource_kind == ResourceKind.SUBSCRIPTION


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid JSON"),
        stripe.SignatureVerificationError("invalid signature", "signature"),
    ],
)
def test_translates_invalid_body_or_signature(stripe_client, stripe_mock, error):
    stripe_mock.Webhook.construct_event.side_effect = error

    with pytest.raises(WebhookVerificationError):
        stripe_client.webhooks.verify(b"altered", {"Stripe-Signature": "signature"})


def test_rejects_missing_signature_before_stripe(stripe_client, stripe_mock):
    with pytest.raises(WebhookVerificationError, match="Stripe-Signature"):
        stripe_client.webhooks.verify(b"{}", {})

    stripe_mock.Webhook.construct_event.assert_not_called()


def test_rejects_missing_secret_before_stripe(stripe_mock):
    client = CheckoutClient(StripeGateway(api_key="sk_test", webhook_secret=""))

    with pytest.raises(WebhookVerificationError, match="webhook_secret"):
        client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})

    stripe_mock.Webhook.construct_event.assert_not_called()


def test_rejects_incomplete_known_event(stripe_client, stripe_mock, load_fixture):
    payload = deepcopy(load_fixture("event_invoice_paid.json"))
    del payload["data"]["object"]["status"]
    stripe_mock.Webhook.construct_event.return_value = payload

    with pytest.raises(GatewayProtocolError):
        stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "signature"})
