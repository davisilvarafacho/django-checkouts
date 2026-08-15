from __future__ import annotations

import pytest
from django.test import override_settings

from django_checkouts.exceptions import ConfigurationError
from django_checkouts.gateways.base import BaseCheckoutGateway
from django_checkouts.registry import get_checkout_gateway


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


@override_settings(CHECKOUT_VARIANTS={})
def test_unknown_variant_lists_the_configured_ones() -> None:
    with pytest.raises(ConfigurationError, match="nenhuma"):
        get_checkout_gateway("missing")


@override_settings(CHECKOUT_VARIANTS={"broken": ("not.a.real.Gateway", {})})
def test_unimportable_gateway_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Não consegui importar"):
        get_checkout_gateway("broken")


@override_settings(
    CHECKOUT_VARIANTS={"wrong": ("django.http.HttpResponse", {})}
)
def test_class_that_is_not_a_gateway_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="BaseCheckoutGateway"):
        get_checkout_gateway("wrong")
