from __future__ import annotations

import pytest
from django.test import override_settings

from django_checkouts.enums import Provider
from django_checkouts.exceptions import ConfigurationError
from django_checkouts.gateways.base import BaseCheckoutGateway
from django_checkouts.registry import PROVIDER_CACHE
from django_checkouts.registry import get_checkout_gateway
from django_checkouts.registry import get_checkout_provider
from django_checkouts.registry import iter_checkout_providers

STRIPE_PATH = "django_checkouts.providers.stripe.StripeCheckoutProvider"


class ConfiguredGateway(BaseCheckoutGateway):
    name = "configured"
    capabilities = object()


@override_settings(
    CHECKOUT_VARIANTS={
        "configured": ("tests.test_registry.ConfiguredGateway", {"region": "br"})
    }
)
def test_gateway_clients_are_cached_without_overrides() -> None:
    assert get_checkout_gateway("configured") is get_checkout_gateway("configured")


@override_settings(
    CHECKOUT_VARIANTS={
        "configured": ("tests.test_registry.ConfiguredGateway", {"region": "br"})
    }
)
def test_gateway_overrides_bypass_client_cache() -> None:
    first_override = get_checkout_gateway("configured", region="us")
    second_override = get_checkout_gateway("configured", region="us")

    assert first_override is not second_override
    assert first_override is not get_checkout_gateway("configured")
    assert first_override.variant == "configured"


def test_resolves_configured_variant():
    provider = get_checkout_provider(Provider.STRIPE)
    assert provider.name is Provider.STRIPE


def test_caches_instances_between_calls():
    assert get_checkout_provider(Provider.STRIPE) is get_checkout_provider(
        Provider.STRIPE
    )


def test_overrides_bypass_the_cache():
    """Multi-tenant: cada chamada com credencial própria precisa ser distinta."""
    tenant = get_checkout_provider(Provider.STRIPE, api_key="sk_test_outro")
    assert tenant is not get_checkout_provider(Provider.STRIPE)
    assert tenant.api_key == "sk_test_outro"
    assert PROVIDER_CACHE[Provider.STRIPE].api_key == "sk_test_dummy"


def test_overrides_merge_with_settings_config():
    tenant = get_checkout_provider(Provider.STRIPE, api_key="sk_test_outro")
    assert tenant.webhook_secret == "whsec_dummy"


def test_unknown_variant_lists_the_configured_ones():
    with pytest.raises(ConfigurationError, match="stripe"):
        get_checkout_provider("mercadopago")


@override_settings(CHECKOUT_VARIANTS={"quebrado": ("nao.existe.Classe", {})})
def test_unimportable_class_mentions_the_extra():
    with pytest.raises(ConfigurationError, match="extra"):
        get_checkout_provider("quebrado")


@override_settings(CHECKOUT_VARIANTS={"errado": ("django.http.HttpResponse", {})})
def test_class_that_is_not_a_provider_is_refused():
    with pytest.raises(ConfigurationError, match="BaseCheckoutProvider"):
        get_checkout_provider("errado")


@override_settings(CHECKOUT_VARIANTS={Provider.STRIPE: (STRIPE_PATH, {})})
def test_discovery_skips_providers_that_fail_to_build():
    """Configuração quebrada é assunto dos system checks, não da descoberta."""
    assert iter_checkout_providers() == []
