"""A interface orientada a recursos constrói os comandos corretos."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest

from django_checkouts.capabilities import CheckoutCapabilities
from django_checkouts.capabilities import GatewayCapabilities
from django_checkouts.capabilities import InvoiceCapabilities
from django_checkouts.capabilities import ReconciliationCapabilities
from django_checkouts.capabilities import SubscriptionCapabilities
from django_checkouts.capabilities import WebhookCapabilities
from django_checkouts.client import CheckoutClient
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CancellationTiming
from django_checkouts.enums import ChangeTiming
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import ProrationBehavior
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.commands import CancelCheckout
from django_checkouts.gateways.commands import CancelRemoteSubscription
from django_checkouts.gateways.commands import ChangeRemoteSubscription
from django_checkouts.gateways.commands import CreateCheckout
from django_checkouts.gateways.commands import ListEvents
from django_checkouts.gateways.commands import ResumeSubscription
from django_checkouts.gateways.commands import RetrieveCheckout
from django_checkouts.gateways.commands import RetrieveInvoice
from django_checkouts.gateways.commands import RetrieveSubscription
from django_checkouts.gateways.commands import VerifyWebhook
from django_checkouts.testing import FakeCheckoutGateway
from django_checkouts.types import ChangeSubscription
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import InlinePrice
from django_checkouts.types import SetQuantity


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
            supports_customer_prefill=False,
        ),
        subscriptions=SubscriptionCapabilities(
            retrieve=True,
            change_quantity=True,
            replace_price=True,
            add_remove_items=True,
            timings=frozenset({ChangeTiming.IMMEDIATELY}),
            proration_behaviors=frozenset({ProrationBehavior.NONE}),
            cancellation_timings=frozenset({CancellationTiming.IMMEDIATELY}),
            resume_scheduled_cancellation=True,
            atomic_multi_change=True,
        ),
        invoices=InvoiceCapabilities(retrieve=True),
        webhooks=WebhookCapabilities(signed=True),
        reconciliation=ReconciliationCapabilities(
            events=True,
            maximum_page_size=100,
        ),
    )


@pytest.fixture
def fake_gateway(capabilities: GatewayCapabilities) -> FakeCheckoutGateway:
    return FakeCheckoutGateway(
        results={
            CreateCheckout: "checkout",
            RetrieveCheckout: "checkout",
            CancelCheckout: "checkout",
            RetrieveSubscription: "subscription",
            ChangeRemoteSubscription: "subscription",
            CancelRemoteSubscription: "subscription",
            ResumeSubscription: "subscription",
            RetrieveInvoice: "invoice",
            VerifyWebhook: "event",
            ListEvents: "events",
        },
        capabilities=capabilities,
    )


@pytest.fixture
def checkout_create() -> CheckoutCreate:
    return CheckoutCreate(
        items=(
            CheckoutItem(
                quantity=1,
                price=InlinePrice(name="Plano", unit_amount=1000, currency="BRL"),
            ),
        ),
        success_url="https://example.test/success",
    )


def test_client_exposes_five_resources(fake_gateway: FakeCheckoutGateway) -> None:
    client = CheckoutClient(fake_gateway)
    assert (
        client.checkouts.gateway,
        client.subscriptions.gateway,
        client.invoices.gateway,
        client.webhooks.gateway,
        client.events.gateway,
    ) == (fake_gateway,) * 5


def test_create_builds_command(
    fake_gateway: FakeCheckoutGateway, checkout_create: CheckoutCreate
) -> None:
    CheckoutClient(fake_gateway).checkouts.create(
        checkout_create, idempotency_key="order-1:v1"
    )
    assert fake_gateway.commands == [
        CreateCheckout(request=checkout_create, idempotency_key="order-1:v1")
    ]


@pytest.mark.parametrize("idempotency_key", ["", "   "])
def test_empty_idempotency_key_fails(
    fake_gateway: FakeCheckoutGateway,
    checkout_create: CheckoutCreate,
    idempotency_key: str,
) -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        CheckoutClient(fake_gateway).checkouts.create(
            checkout_create, idempotency_key=idempotency_key
        )
    assert fake_gateway.commands == []


def test_resources_build_their_matching_commands(
    fake_gateway: FakeCheckoutGateway,
) -> None:
    client = CheckoutClient(fake_gateway)
    request = ChangeSubscription(changes=(SetQuantity(item_id="item_1", quantity=2),))
    since = datetime(2026, 1, 1, tzinfo=UTC)
    before = datetime(2026, 1, 2, tzinfo=UTC)

    assert client.checkouts.retrieve("co_1") == "checkout"
    assert client.checkouts.cancel("co_1", idempotency_key="cancel-1") == "checkout"
    assert client.subscriptions.retrieve("sub_1") == "subscription"
    assert client.subscriptions.change(
        "sub_1", request, idempotency_key="change-1"
    ) == "subscription"
    assert client.subscriptions.cancel(
        "sub_1",
        timing=CancellationTiming.IMMEDIATELY,
        idempotency_key="cancel-sub-1",
    ) == "subscription"
    assert (
        client.subscriptions.resume("sub_1", idempotency_key="resume-1")
        == "subscription"
    )
    assert client.invoices.retrieve("in_1") == "invoice"
    assert client.webhooks.verify(b"{}", {"X-Signature": "signature"}) == "event"
    assert client.events.list(
        occurred_since=since,
        occurred_before=before,
        cursor="next",
        limit=50,
    ) == "events"

    assert fake_gateway.commands == [
        RetrieveCheckout(external_id="co_1"),
        CancelCheckout(external_id="co_1", idempotency_key="cancel-1"),
        RetrieveSubscription(external_id="sub_1"),
        ChangeRemoteSubscription(
            external_id="sub_1", request=request, idempotency_key="change-1"
        ),
        CancelRemoteSubscription(
            external_id="sub_1",
            timing=CancellationTiming.IMMEDIATELY,
            idempotency_key="cancel-sub-1",
        ),
        ResumeSubscription(external_id="sub_1", idempotency_key="resume-1"),
        RetrieveInvoice(external_id="in_1"),
        VerifyWebhook(raw_body=b"{}", headers={"X-Signature": "signature"}),
        ListEvents(
            occurred_since=since,
            occurred_before=before,
            cursor="next",
            limit=50,
        ),
    ]
