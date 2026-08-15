"""Checks locais para todas as variantes da fronteira de gateways."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error
from django.core.checks import Warning
from django.core.checks import register

from django_checkouts.exceptions import ConfigurationError
from django_checkouts.registry import _import_gateway_class
from django_checkouts.registry import get_variants


@register("django_checkouts")
def check_checkout_gateways(app_configs: Any = None, **kwargs: Any) -> list:
    """Importa, instancia e consulta gateways sem executar operações externas."""
    del app_configs
    del kwargs
    try:
        variants = get_variants()
    except ConfigurationError:
        return [_configuration_error("CHECKOUT_VARIANTS")]

    messages: list = []
    for variant, entry in variants.items():
        try:
            dotted_path, configuration = entry
            if not isinstance(dotted_path, str) or not isinstance(
                configuration, dict
            ):
                raise TypeError
            gateway_class = _import_gateway_class(dotted_path, str(variant))
            gateway = gateway_class(variant=str(variant), **configuration)
            messages.extend(gateway.check())
        except Exception:  # noqa: BLE001 - qualquer falha de config vira E001
            messages.append(_configuration_error(str(variant)))
            continue

        if getattr(gateway, "sandbox", False) and not settings.DEBUG:
            messages.append(
                Warning(
                    f"O gateway '{variant}' está em sandbox com DEBUG=False.",
                    hint="Use sandbox=False para credenciais de produção.",
                    id="django_checkouts.W002",
                )
            )
    return messages


def _configuration_error(variant: str) -> Error:
    return Error(
        f"A configuração da variante de checkout '{variant}' é inválida.",
        hint=(
            "Use o caminho de uma subclasse de BaseCheckoutGateway e uma "
            "configuração compatível com seu construtor."
        ),
        id="django_checkouts.E001",
    )


# Compatibilidade interna até a remoção da superfície pré-1.0 na Task 8.
check_checkout_providers = check_checkout_gateways

__all__ = ["check_checkout_gateways"]
