"""Discovery and construction of configured checkout gateways."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from django_checkouts.exceptions import ConfigurationError

if TYPE_CHECKING:
    from django_checkouts.client import CheckoutClient
    from django_checkouts.enums import Gateway
    from django_checkouts.gateways.base import BaseCheckoutGateway

GATEWAY_CACHE: dict[str, CheckoutClient] = {}


def get_variants() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return ``CHECKOUT_VARIANTS`` after validating its outer shape."""
    variants = getattr(settings, "CHECKOUT_VARIANTS", {})
    if not isinstance(variants, dict):
        raise ConfigurationError(
            f"settings.CHECKOUT_VARIANTS deve ser um dict, e não "
            f"{type(variants).__name__}."
        )
    return variants


def get_checkout_gateway(
    variant: Gateway | str, **credential_overrides: object
) -> CheckoutClient:
    """Return a resource-oriented client for a configured gateway variant.

    Clients without credential overrides are cached by variant. Credential
    overrides are intended for account-specific calls and are never cached.
    """
    from django_checkouts.client import CheckoutClient

    variants = get_variants()
    try:
        dotted_path, config = variants[variant]
    except KeyError:
        raise ConfigurationError(
            f"A variante de checkout '{variant}' não existe. Configuradas: "
            f"{sorted(variants) or 'nenhuma'}. Defina-a em "
            f"settings.CHECKOUT_VARIANTS."
        ) from None

    if credential_overrides:
        gateway = _import_gateway_class(dotted_path, str(variant))(
            variant=str(variant), **{**config, **credential_overrides}
        )
        return CheckoutClient(gateway)

    if variant not in GATEWAY_CACHE:
        gateway = _import_gateway_class(dotted_path, str(variant))(
            variant=str(variant), **config
        )
        GATEWAY_CACHE[variant] = CheckoutClient(gateway)
    return GATEWAY_CACHE[variant]


def _import_gateway_class(
    dotted_path: str, variant: str
) -> type[BaseCheckoutGateway]:
    """Import and validate a configured gateway class."""
    from django_checkouts.gateways.base import BaseCheckoutGateway

    try:
        gateway_class = import_string(dotted_path)
    except ImportError as exc:
        raise ConfigurationError(
            f"Não consegui importar '{dotted_path}' para a variante "
            f"'{variant}': {exc}."
        ) from exc

    if not (
        inspect.isclass(gateway_class)
        and issubclass(gateway_class, BaseCheckoutGateway)
    ):
        raise ConfigurationError(
            f"'{dotted_path}' precisa ser uma subclasse de BaseCheckoutGateway."
        )
    return gateway_class


__all__ = ["get_checkout_gateway"]
