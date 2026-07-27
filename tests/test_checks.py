"""System checks: credencial errada precisa aparecer no `manage.py check`."""

from __future__ import annotations

from django.test import override_settings

from django_checkouts.checks import check_checkout_providers
from django_checkouts.enums import Provider

STRIPE_PATH = "django_checkouts.providers.stripe.StripeCheckoutProvider"


def variants(**config):
    base = {"api_key": "sk_test_ok", "webhook_secret": "whsec_ok", "sandbox": True}
    return {Provider.STRIPE: (STRIPE_PATH, {**base, **config})}


def test_healthy_configuration_is_silent():
    with override_settings(CHECKOUT_VARIANTS=variants(), DEBUG=True):
        assert check_checkout_providers() == []


def test_production_configuration_is_silent():
    config = variants(api_key="sk_live_ok", sandbox=False)
    with override_settings(CHECKOUT_VARIANTS=config, DEBUG=False):
        assert check_checkout_providers() == []


def test_missing_webhook_secret_is_reported():
    with override_settings(CHECKOUT_VARIANTS=variants(webhook_secret="")):
        ids = [message.id for message in check_checkout_providers()]
    assert "django_checkouts.E002" in ids


def test_live_key_in_sandbox_is_reported():
    with override_settings(CHECKOUT_VARIANTS=variants(api_key="sk_live_x")):
        ids = [message.id for message in check_checkout_providers()]
    assert "django_checkouts.W001" in ids


def test_sandbox_with_debug_off_is_reported():
    """Sandbox em produção significa cobrar dinheiro que não existe."""
    with override_settings(CHECKOUT_VARIANTS=variants(), DEBUG=False):
        ids = [message.id for message in check_checkout_providers()]
    assert "django_checkouts.W002" in ids
