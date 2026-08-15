"""System checks da fronteira configurável de gateways."""

from __future__ import annotations

from unittest.mock import Mock

import stripe
from django.core.checks import Warning
from django.test import override_settings

from django_checkouts.checks import check_checkout_gateways
from django_checkouts.gateways.base import BaseCheckoutGateway
from django_checkouts.gateways.stripe.capabilities import STRIPE_CAPABILITIES

STRIPE_PATH = "django_checkouts.gateways.stripe.StripeGateway"
LEGACY_PATH = "django_checkouts.providers.stripe.StripeCheckoutProvider"


def variants(**config):
    base = {"api_key": "sk_test_ok", "webhook_secret": "whsec_ok", "sandbox": True}
    return {"stripe": (STRIPE_PATH, {**base, **config})}


class CheckedGateway(BaseCheckoutGateway):
    name = "checked"
    capabilities = STRIPE_CAPABILITIES

    def check(self):
        return [Warning("custom", id="django_checkouts.W900")]


def test_healthy_gateway_configuration_is_silent() -> None:
    with override_settings(CHECKOUT_VARIANTS=variants(), DEBUG=True):
        assert check_checkout_gateways() == []


def test_each_gateway_is_instantiated_and_its_messages_are_appended() -> None:
    configured: dict[str, tuple[str, dict[str, object]]] = {
        "checked": ("tests.test_checks.CheckedGateway", {"region": "br"})
    }
    with override_settings(CHECKOUT_VARIANTS=configured):
        messages = check_checkout_gateways()

    assert [message.id for message in messages] == ["django_checkouts.W900"]


def test_missing_api_key_is_reported() -> None:
    with override_settings(CHECKOUT_VARIANTS=variants(api_key="")):
        messages = check_checkout_gateways()

    assert "django_checkouts.E001" in [message.id for message in messages]


def test_signed_webhook_requires_secret() -> None:
    with override_settings(CHECKOUT_VARIANTS=variants(webhook_secret="")):
        messages = check_checkout_gateways()

    assert "django_checkouts.E001" in [message.id for message in messages]


def test_bad_path_or_configuration_is_reported() -> None:
    configurations: tuple[dict[str, object], ...] = (
        {"broken": ("not.a.real.Gateway", {})},
        {"broken": (STRIPE_PATH, {"unknown": True})},
        {"broken": "malformed"},
    )
    for configured in configurations:
        with override_settings(CHECKOUT_VARIANTS=configured):
            messages = check_checkout_gateways()

        assert [message.id for message in messages] == ["django_checkouts.E001"]


def test_legacy_provider_path_is_rejected() -> None:
    configured = {
        "stripe": (
            LEGACY_PATH,
            {"api_key": "sk_test_ok", "webhook_secret": "whsec_ok"},
        )
    }
    with override_settings(CHECKOUT_VARIANTS=configured):
        messages = check_checkout_gateways()

    assert [message.id for message in messages] == ["django_checkouts.E001"]


def test_checks_never_call_stripe(monkeypatch) -> None:
    mocks = [Mock(), Mock(), Mock()]
    monkeypatch.setattr(stripe.checkout.Session, "create", mocks[0])
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", mocks[1])
    monkeypatch.setattr(stripe.Event, "list", mocks[2])

    with override_settings(CHECKOUT_VARIANTS=variants()):
        check_checkout_gateways()

    assert all(mock.call_count == 0 for mock in mocks)


def test_production_sandbox_configuration_warns() -> None:
    with override_settings(CHECKOUT_VARIANTS=variants(), DEBUG=False):
        messages = check_checkout_gateways()

    assert "django_checkouts.W002" in [message.id for message in messages]
