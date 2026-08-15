"""Contratos públicos dos DTOs normalizados."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC
from datetime import datetime

import pytest

from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import Gateway
from django_checkouts.enums import RetryDisposition
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.exceptions import GatewayTemporaryError
from django_checkouts.exceptions import RetryAdvice
from django_checkouts.types import AddItem
from django_checkouts.types import CatalogPrice
from django_checkouts.types import ChangeSubscription
from django_checkouts.types import Checkout
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import InlinePrice
from django_checkouts.types import SetQuantity
from django_checkouts.types import Subscription


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
    advice = RetryAdvice(RetryDisposition.RETRY)
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
