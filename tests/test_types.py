"""Contratos públicos dos DTOs normalizados."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC
from datetime import datetime
from inspect import isclass
from typing import get_type_hints

import pytest

from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import Gateway
from django_checkouts.enums import InvoiceReason
from django_checkouts.enums import InvoiceStatus
from django_checkouts.enums import RetryDisposition
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.exceptions import GatewayError
from django_checkouts.exceptions import GatewayTemporaryError
from django_checkouts.exceptions import RetryAdvice
from django_checkouts.gateways import GatewayOptions
from django_checkouts.types import AddItem
from django_checkouts.types import CatalogPrice
from django_checkouts.types import ChangeSubscription
from django_checkouts.types import Checkout
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import EventPage
from django_checkouts.types import InlinePrice
from django_checkouts.types import Invoice
from django_checkouts.types import InvoiceLine
from django_checkouts.types import SetQuantity
from django_checkouts.types import Subscription
from django_checkouts.types import SubscriptionItem
from django_checkouts.types import WebhookEvent


def test_money_rejects_float_and_bool():
    with pytest.raises(TypeError, match="unit_amount"):
        InlinePrice(name="Pro", unit_amount=49.90)
    with pytest.raises(TypeError, match="unit_amount"):
        InlinePrice(name="Pro", unit_amount=True)


def test_checkout_is_immutable_and_hides_raw():
    checkout = Checkout(
        external_id="cs_123",
        gateway=Gateway.STRIPE,
        variant="stripe-br",
        status=CheckoutStatus.PENDING,
        mode=CheckoutMode.PAYMENT,
        url=None,
        amount_total=4990,
        currency="brl",
        customer=None,
        reference_id="order-1",
        subscription_id=None,
        expires_at=None,
        created_at=datetime(2026, 8, 7, tzinfo=UTC),
        raw={"secret": "value"},
    )
    assert checkout.currency == "BRL"
    assert "secret" not in repr(checkout)
    with pytest.raises(FrozenInstanceError):
        checkout.status = CheckoutStatus.PAID


def test_quantity_is_absolute_and_positive():
    with pytest.raises(ValueError, match="quantity"):
        CheckoutItem(price=CatalogPrice(external_id="price_123"), quantity=0)


def test_public_dto_and_gateway_option_annotations_resolve_at_runtime():
    import django_checkouts.types as public_types

    dto_classes = [
        getattr(public_types, name)
        for name in public_types.__all__
        if isclass(getattr(public_types, name))
    ]

    assert all(get_type_hints(dto_class) for dto_class in dto_classes)
    assert get_type_hints(GatewayOptions)


@pytest.mark.parametrize(
    ("factory", "field_name"),
    [
        (
            lambda: WebhookEvent(
                gateway=Gateway.STRIPE,
                variant="stripe",
                event_id="evt_123",
                event_type="checkout.completed",
                type=None,
                occurred_at=None,
                resource_kind=None,
                resource_id=None,
                resource=None,
                livemode=True,
                raw={},
            ),
            "occurred_at",
        ),
        (
            lambda: EventPage(
                items=(),
                next_cursor=None,
                occurred_since=None,
                occurred_before=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            "occurred_since",
        ),
        (
            lambda: EventPage(
                items=(),
                next_cursor=None,
                occurred_since=datetime(2026, 1, 1, tzinfo=UTC),
                occurred_before=None,
            ),
            "occurred_before",
        ),
    ],
)
def test_required_event_datetimes_reject_none(factory, field_name):
    with pytest.raises(TypeError, match=field_name):
        factory()


def test_checkout_create_rejects_incompatible_items_and_recurrence():
    pro_brl = CheckoutItem(price=InlinePrice(name="Pro", unit_amount=4990))
    pro_usd = CheckoutItem(
        price=InlinePrice(name="Pro internacional", unit_amount=1000, currency="usd")
    )

    with pytest.raises(ValueError, match="items"):
        CheckoutCreate(items=(), success_url="https://example.test/success")
    with pytest.raises(ValueError, match="currency"):
        CheckoutCreate(
            items=(pro_brl, pro_usd),
            success_url="https://example.test/success",
        )
    with pytest.raises(ValueError, match="recurrence"):
        CheckoutCreate(
            items=(pro_brl,),
            success_url="https://example.test/success",
            recurrence=None,
            mode=CheckoutMode.SUBSCRIPTION,
        )


def test_checkout_create_rejects_recurrence_for_one_time_payment():
    from django_checkouts.enums import BillingCycle
    from django_checkouts.types import Recurrence

    with pytest.raises(ValueError, match="recurrence"):
        CheckoutCreate(
            items=(CheckoutItem(price=CatalogPrice(external_id="price_123")),),
            success_url="https://example.test/success",
            recurrence=Recurrence(cycle=BillingCycle.MONTHLY),
        )


def test_subscription_changes_reject_conflicts_and_invalid_quantity():
    with pytest.raises(TypeError, match="quantity"):
        AddItem(price=CatalogPrice(external_id="price_123"), quantity=True)
    with pytest.raises(ValueError, match="changes"):
        ChangeSubscription(changes=())
    with pytest.raises(ValueError, match="item_id"):
        ChangeSubscription(
            changes=(
                SetQuantity(item_id="si_123", quantity=2),
                SetQuantity(item_id="si_123", quantity=3),
            )
        )


def test_resources_normalize_dates_currency_and_defensively_copy_raw():
    raw = {"customer": {"email": "payer@example.test"}}
    subscription = Subscription(
        external_id="sub_123",
        gateway=Gateway.STRIPE,
        variant="stripe-br",
        status=SubscriptionStatus.ACTIVE,
        customer_id=None,
        items=(),
        current_period_start=datetime(2026, 8, 7, tzinfo=UTC),
        current_period_end=None,
        trial_end=None,
        cancel_at=None,
        canceled_at=None,
        ended_at=None,
        latest_invoice_id=None,
        reference_id=None,
        metadata={},
        raw=raw,
    )

    raw["customer"]["email"] = "changed@example.test"
    assert subscription.current_period_start.tzinfo is UTC
    assert subscription.raw["customer"]["email"] == "payer@example.test"
    with pytest.raises(TypeError):
        subscription.raw["new"] = "value"


def test_resources_reject_naive_dates_and_invalid_currency():
    with pytest.raises(ValueError, match="timezone"):
        Checkout(
            external_id="cs_123",
            gateway=Gateway.STRIPE,
            variant="stripe-br",
            status=CheckoutStatus.PENDING,
            mode=CheckoutMode.PAYMENT,
            url=None,
            amount_total=4990,
            currency="BRL",
            customer=None,
            reference_id=None,
            subscription_id=None,
            expires_at=None,
            created_at=datetime(2026, 8, 7),  # noqa: DTZ001 - entrada inválida testada
            raw={},
        )
    with pytest.raises(ValueError, match="currency"):
        InlinePrice(name="Pro", unit_amount=4990, currency="BR")


def test_gateway_error_carries_explicit_retry_advice():
    advice = RetryAdvice(disposition=RetryDisposition.RETRY)
    error = GatewayTemporaryError(
        "Gateway temporariamente indisponível.",
        gateway=Gateway.STRIPE,
        variant="stripe-br",
        code="rate_limit",
        gateway_message="Too many requests",
        retry_advice=advice,
    )

    assert error.gateway is Gateway.STRIPE
    assert error.variant == "stripe-br"
    assert error.code == "rate_limit"
    assert error.retry_advice is advice


def test_retry_advice_is_keyword_only_frozen_and_slotted():
    with pytest.raises(TypeError):
        RetryAdvice(RetryDisposition.RETRY)
    with pytest.raises(FrozenInstanceError):
        RetryAdvice(
            disposition=RetryDisposition.RETRY
        ).disposition = RetryDisposition.NEVER
    assert not hasattr(RetryAdvice(disposition=RetryDisposition.RETRY), "__dict__")


def test_gateway_error_redacts_external_secrets_from_message_and_repr():
    error = GatewayError(
        "Gateway recusou a solicitação.",
        gateway=Gateway.STRIPE,
        variant="stripe-br",
        gateway_message="Authorization: Bearer sk_live_verysecret token=abc123",
    )

    assert "sk_live_verysecret" not in error.gateway_message
    assert "abc123" not in error.gateway_message
    assert "sk_live_verysecret" not in repr(error)
    assert "abc123" not in str(error)


@pytest.mark.parametrize("invalid_amount", [True, 49.9])
def test_result_money_fields_reject_bool_and_float(invalid_amount):
    checkout_kwargs = {
        "external_id": "cs_123",
        "gateway": Gateway.STRIPE,
        "variant": "stripe-br",
        "status": CheckoutStatus.PENDING,
        "mode": CheckoutMode.PAYMENT,
        "url": None,
        "amount_total": invalid_amount,
        "currency": "BRL",
        "customer": None,
        "reference_id": None,
        "subscription_id": None,
        "expires_at": None,
        "created_at": None,
        "raw": {},
    }
    with pytest.raises(TypeError, match="amount_total"):
        Checkout(**checkout_kwargs)

    with pytest.raises(TypeError, match="unit_amount"):
        SubscriptionItem(
            external_id="si_123", price_id=None, quantity=1, unit_amount=invalid_amount,
            currency=None, billing_cycle=None, raw={},
        )
    with pytest.raises(TypeError, match="unit_amount"):
        InvoiceLine(
            external_id="il_123",
            description=None,
            quantity=1,
            unit_amount=invalid_amount,
            amount=100, currency="BRL", subscription_item_id=None,
            period_start=None, period_end=None, raw={},
        )
    with pytest.raises(TypeError, match="amount"):
        InvoiceLine(
            external_id="il_123", description=None, quantity=1, unit_amount=None,
            amount=invalid_amount, currency="BRL", subscription_item_id=None,
            period_start=None, period_end=None, raw={},
        )
    for field_name in ("amount_due", "amount_paid", "amount_remaining"):
        kwargs = {
            "external_id": "in_123",
            "gateway": Gateway.STRIPE,
            "variant": "stripe-br",
            "status": InvoiceStatus.OPEN,
            "reason": InvoiceReason.RENEWAL,
            "subscription_id": None,
            "customer_id": None,
            "amount_due": 100,
            "amount_paid": 0,
            "amount_remaining": 100,
            "currency": "BRL",
            "lines": (),
            "due_at": None,
            "paid_at": None,
            "next_payment_attempt_at": None,
            "attempt_count": 0,
            "hosted_url": None,
            "reference_id": None,
            "raw": {},
        }
        kwargs[field_name] = invalid_amount
        with pytest.raises(TypeError, match=field_name):
            Invoice(**kwargs)
