"""Operações de assinatura pela interface normalizada do Stripe."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from unittest.mock import Mock

import pytest
import stripe

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CancellationTiming
from django_checkouts.enums import ChangeTiming
from django_checkouts.enums import ProrationBehavior
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.stripe import StripeGateway
from django_checkouts.types import AddItem
from django_checkouts.types import CatalogPrice
from django_checkouts.types import ChangeSubscription
from django_checkouts.types import InlinePrice
from django_checkouts.types import RemoveItem
from django_checkouts.types import ReplacePrice
from django_checkouts.types import SetQuantity


@pytest.fixture
def stripe_mock(monkeypatch):
    for operation in ("retrieve", "modify", "cancel"):
        monkeypatch.setattr(stripe.Subscription, operation, Mock())
    for operation in ("create", "modify"):
        monkeypatch.setattr(stripe.SubscriptionSchedule, operation, Mock())
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


def stripe_subscription(payload: dict[str, object]) -> object:
    return stripe.Subscription.construct_from(payload, "sk_test")


def test_retrieve_normalizes_real_sdk_subscription(
    stripe_client, stripe_mock, load_fixture
):
    stripe_mock.Subscription.retrieve.return_value = stripe_subscription(
        load_fixture("subscription_active.json")
    )

    subscription = stripe_client.subscriptions.retrieve("sub_1")

    stripe_mock.Subscription.retrieve.assert_called_once_with(
        "sub_1",
        expand=["items.data.price", "latest_invoice"],
        api_key="sk_test_per_account",
    )
    assert subscription.external_id == "sub_1"
    assert subscription.status is SubscriptionStatus.ACTIVE
    assert subscription.customer_id == "cus_42"
    assert subscription.latest_invoice_id == "in_paid_1"
    assert subscription.reference_id == "contract-42"
    assert subscription.current_period_start == datetime.fromtimestamp(
        1785542400, tz=UTC
    )
    assert subscription.items[0].external_id == "si_1"
    assert subscription.items[0].price_id == "price_pro"
    assert subscription.items[0].quantity == 10
    assert subscription.items[0].unit_amount == 4900
    assert subscription.items[0].currency == "BRL"
    assert subscription.items[0].billing_cycle is BillingCycle.MONTHLY
    assert type(subscription.raw) is not dict
    assert type(subscription.raw["items"]) is dict


def test_change_sets_absolute_quantity(stripe_client, stripe_mock, load_fixture):
    stripe_mock.Subscription.modify.return_value = load_fixture(
        "subscription_active.json"
    )

    stripe_client.subscriptions.change(
        "sub_1",
        ChangeSubscription(
            changes=(SetQuantity(item_id="si_1", quantity=25),),
            proration=ProrationBehavior.INVOICE_IMMEDIATELY,
        ),
        idempotency_key="org-42:seats:25:v1",
    )

    kwargs = stripe_mock.Subscription.modify.call_args.kwargs
    assert kwargs["items"] == [{"id": "si_1", "quantity": 25}]
    assert kwargs["proration_behavior"] == "always_invoice"
    assert kwargs["idempotency_key"] == "org-42:seats:25:v1"
    assert kwargs["api_key"] == "sk_test_per_account"


def test_change_maps_every_item_operation(stripe_client, stripe_mock, load_fixture):
    stripe_mock.Subscription.modify.return_value = load_fixture(
        "subscription_active.json"
    )
    request = ChangeSubscription(
        changes=(
            ReplacePrice(
                item_id="si_1",
                price=CatalogPrice(external_id="price_enterprise"),
                quantity=30,
            ),
            RemoveItem(item_id="si_2"),
            AddItem(
                price=InlinePrice(
                    name="Suporte premium",
                    description="Atendimento prioritário",
                    unit_amount=7500,
                    currency="BRL",
                ),
                quantity=1,
            ),
        ),
        proration=ProrationBehavior.NONE,
        metadata={"tenant": "42"},
    )

    stripe_client.subscriptions.change(
        "sub_1", request, idempotency_key="sub_1:change:v1"
    )

    assert stripe_mock.Subscription.modify.call_args.kwargs["items"] == [
        {"id": "si_1", "price": "price_enterprise", "quantity": 30},
        {"id": "si_2", "deleted": True},
        {
            "price_data": {
                "currency": "brl",
                "unit_amount": 7500,
                "product_data": {
                    "name": "Suporte premium",
                    "description": "Atendimento prioritário",
                },
            },
            "quantity": 1,
        },
    ]
    assert stripe_mock.Subscription.modify.call_args.kwargs["metadata"] == {
        "tenant": "42"
    }


@pytest.mark.parametrize(
    ("behavior", "expected"),
    [
        (ProrationBehavior.CREATE_PRORATIONS, "create_prorations"),
        (ProrationBehavior.INVOICE_IMMEDIATELY, "always_invoice"),
        (ProrationBehavior.NONE, "none"),
    ],
)
def test_change_maps_every_proration_behavior(
    stripe_client, stripe_mock, load_fixture, behavior, expected
):
    stripe_mock.Subscription.modify.return_value = load_fixture(
        "subscription_active.json"
    )

    stripe_client.subscriptions.change(
        "sub_1",
        ChangeSubscription(
            changes=(SetQuantity(item_id="si_1", quantity=20),),
            proration=behavior,
        ),
        idempotency_key=f"sub_1:{behavior}:v1",
    )

    assert (
        stripe_mock.Subscription.modify.call_args.kwargs["proration_behavior"]
        == expected
    )


def test_next_cycle_uses_schedule_then_retrieves_subscription(
    stripe_client, stripe_mock, load_fixture
):
    current = load_fixture("subscription_active.json")
    stripe_mock.Subscription.retrieve.side_effect = [current, current]
    stripe_mock.SubscriptionSchedule.create.return_value = (
        stripe.SubscriptionSchedule.construct_from(
            {
                "id": "sub_sched_1",
                "phases": [
                    {
                        "start_date": 1785542400,
                        "end_date": 1788220800,
                        "items": [
                            {
                                "price": {"id": "price_pro"},
                                "quantity": 10,
                            },
                            {
                                "price": {"id": "price_addon"},
                                "quantity": 2,
                            },
                        ],
                    }
                ],
            },
            "sk_test",
        )
    )

    result = stripe_client.subscriptions.change(
        "sub_1",
        ChangeSubscription(
            changes=(SetQuantity(item_id="si_1", quantity=25),),
            timing=ChangeTiming.NEXT_CYCLE,
            proration=ProrationBehavior.NONE,
        ),
        idempotency_key="sub_1:next:v1",
    )

    stripe_mock.SubscriptionSchedule.create.assert_called_once_with(
        from_subscription="sub_1",
        idempotency_key="sub_1:next:v1",
        api_key="sk_test_per_account",
    )
    phases = stripe_mock.SubscriptionSchedule.modify.call_args.kwargs["phases"]
    assert phases[0] == {
        "start_date": 1785542400,
        "end_date": 1788220800,
        "items": [
            {"price": "price_pro", "quantity": 10},
            {"price": "price_addon", "quantity": 2},
        ],
    }
    assert phases[-1] == {
        "start_date": 1788220800,
        "duration": {"interval": "month", "interval_count": 1},
        "items": [
            {"price": "price_pro", "quantity": 25},
            {"price": "price_addon", "quantity": 2},
        ],
        "proration_behavior": "none",
    }
    assert (
        stripe_mock.SubscriptionSchedule.modify.call_args.kwargs["idempotency_key"]
        == "sub_1:next:v1"
    )
    assert stripe_mock.Subscription.retrieve.call_count == 2
    assert result.external_id == "sub_1"


def test_cancel_period_end_and_resume(stripe_client, stripe_mock, load_fixture):
    active = load_fixture("subscription_active.json")
    stripe_mock.Subscription.modify.return_value = active
    stripe_mock.Subscription.retrieve.return_value = load_fixture(
        "subscription_canceling.json"
    )

    stripe_client.subscriptions.cancel(
        "sub_1",
        timing=CancellationTiming.PERIOD_END,
        idempotency_key="sub_1:cancel:v1",
    )
    assert (
        stripe_mock.Subscription.modify.call_args.kwargs["cancel_at_period_end"]
        is True
    )
    assert (
        stripe_mock.Subscription.modify.call_args.kwargs["idempotency_key"]
        == "sub_1:cancel:v1"
    )

    stripe_client.subscriptions.resume(
        "sub_1", idempotency_key="sub_1:resume:v1"
    )
    assert (
        stripe_mock.Subscription.modify.call_args.kwargs["cancel_at_period_end"]
        is False
    )
    assert (
        stripe_mock.Subscription.modify.call_args.kwargs["idempotency_key"]
        == "sub_1:resume:v1"
    )


def test_cancel_immediately_uses_cancel_endpoint(
    stripe_client, stripe_mock, load_fixture
):
    canceled = load_fixture("subscription_active.json")
    canceled["status"] = "canceled"
    canceled["ended_at"] = 1786000000
    stripe_mock.Subscription.cancel.return_value = canceled

    result = stripe_client.subscriptions.cancel(
        "sub_1",
        timing=CancellationTiming.IMMEDIATELY,
        idempotency_key="sub_1:cancel-now:v1",
    )

    stripe_mock.Subscription.cancel.assert_called_once_with(
        "sub_1",
        idempotency_key="sub_1:cancel-now:v1",
        api_key="sk_test_per_account",
    )
    assert result.status is SubscriptionStatus.CANCELED


@pytest.mark.parametrize(
    ("status", "ended_at"),
    [("canceled", None), ("active", 1786000000)],
)
def test_resume_rejects_ended_or_canceled_subscription(
    stripe_client, stripe_mock, load_fixture, status, ended_at
):
    raw = load_fixture("subscription_canceling.json")
    raw.update(status=status, ended_at=ended_at)
    stripe_mock.Subscription.retrieve.return_value = raw

    with pytest.raises(ValidationError, match=r"encerrada|cancelada"):
        stripe_client.subscriptions.resume(
            "sub_1", idempotency_key="sub_1:resume:v1"
        )

    stripe_mock.Subscription.modify.assert_not_called()


def test_unknown_subscription_status_is_a_public_protocol_error(
    stripe_client, stripe_mock, load_fixture
):
    raw = load_fixture("subscription_active.json")
    raw["status"] = "future_status"
    stripe_mock.Subscription.retrieve.return_value = raw

    with pytest.raises(GatewayProtocolError):
        stripe_client.subscriptions.retrieve("sub_1")


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
def test_subscription_response_quantities_are_strict(
    stripe_client, stripe_mock, load_fixture, quantity
):
    raw = load_fixture("subscription_active.json")
    raw["items"]["data"][0]["quantity"] = quantity
    stripe_mock.Subscription.retrieve.return_value = raw

    with pytest.raises(GatewayProtocolError):
        stripe_client.subscriptions.retrieve("sub_1")
