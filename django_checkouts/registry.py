"""Descoberta e instanciação dos providers configurados.

Cada provedor é uma variante nomeada, com a classe e a configuração dela::

    CHECKOUT_VARIANTS = {
        "stripe": (
            "django_checkouts.providers.stripe.StripeCheckoutProvider",
            {
                "api_key": env("STRIPE_API_KEY"),
                "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
            },
        ),
    }

A chave da variante é string em ``settings`` — um módulo de settings não deve
importar a lib —, mas **no código use o enum**:
``get_checkout_provider(Provider.STRIPE)``. ``Provider`` é ``TextChoices``, e
portanto subclasse de ``str``: os dois casam na mesma chave.

Quais variantes existem é regra da biblioteca, não detalhe de teste: os system
checks, a documentação e a suíte de contrato leem todos a mesma implementação
daqui.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from django_checkouts.exceptions import ConfigurationError

if TYPE_CHECKING:
    from django_checkouts.base import BaseCheckoutProvider
    from django_checkouts.enums import Provider

PROVIDER_CACHE: dict[str, BaseCheckoutProvider] = {}


def get_variants() -> dict[str, tuple[str, dict[str, Any]]]:
    """Devolve ``settings.CHECKOUT_VARIANTS`` já validado na forma."""
    variants = getattr(settings, "CHECKOUT_VARIANTS", {})
    if not isinstance(variants, dict):
        raise ConfigurationError(
            f"settings.CHECKOUT_VARIANTS deve ser um dict, e não "
            f"{type(variants).__name__}."
        )
    return variants


def get_checkout_provider(
    variant: Provider | str, **overrides: Any
) -> BaseCheckoutProvider:
    """Devolve o provider de uma variante.

    Args:
        variant: Chave em ``CHECKOUT_VARIANTS``. Prefira um membro de
            :class:`~django_checkouts.enums.Provider`; string crua só para
            variante com nome próprio (``"stripe-br"``, multi-tenant).
        **overrides: Configuração que sobrescreve a de settings
            (``api_key=...``). Quando você passa qualquer override, a instância
            **não** é cacheada — é o caso multi-tenant, em que cada chamada tem
            credencial própria.

    Raises:
        ConfigurationError: Variante inexistente, classe não importável, ou
            classe que não é um provider de checkout.
    """
    variants = get_variants()
    try:
        dotted_path, config = variants[variant]
    except KeyError:
        raise ConfigurationError(
            f"A variante de checkout '{variant}' não existe. Configuradas: "
            f"{sorted(variants) or 'nenhuma'}. Defina-a em "
            f"settings.CHECKOUT_VARIANTS."
        ) from None

    if overrides:
        return _import_provider_class(dotted_path, variant)(
            **{**config, **overrides}
        )

    if variant not in PROVIDER_CACHE:
        provider_class = _import_provider_class(dotted_path, variant)
        PROVIDER_CACHE[variant] = provider_class(**config)
    return PROVIDER_CACHE[variant]


def _import_provider_class(
    dotted_path: str, variant: str
) -> type[BaseCheckoutProvider]:
    from django_checkouts.base import BaseCheckoutProvider

    try:
        provider_class = import_string(dotted_path)
    except ImportError as exc:
        raise ConfigurationError(
            f"Não consegui importar '{dotted_path}' para a variante "
            f"'{variant}': {exc}. Se for um provedor embutido, confira se o "
            f"extra correspondente está instalado (ex.: "
            f"pip install 'django-checkouts[stripe]')."
        ) from exc

    if not (
        inspect.isclass(provider_class)
        and issubclass(provider_class, BaseCheckoutProvider)
    ):
        raise ConfigurationError(
            f"'{dotted_path}' precisa ser uma subclasse de BaseCheckoutProvider."
        )
    return provider_class


def iter_checkout_provider_classes() -> list[tuple[str, type[BaseCheckoutProvider]]]:
    """Devolve ``(variante, classe)`` para cada variante de checkout."""
    from django_checkouts.base import BaseCheckoutProvider

    found: list[tuple[str, type[BaseCheckoutProvider]]] = []
    for variant, entry in get_variants().items():
        try:
            dotted_path, _config = entry
            provider_class = import_string(dotted_path)
        except (ImportError, TypeError, ValueError):
            continue
        if inspect.isclass(provider_class) and issubclass(
            provider_class, BaseCheckoutProvider
        ):
            found.append((variant, provider_class))
    return found


def iter_checkout_providers() -> list[BaseCheckoutProvider]:
    """Instancia todos os providers de checkout configurados.

    Um provider que não constrói é ignorado: configuração quebrada é reportada
    pelos system checks, não por uma exceção durante a descoberta.
    """
    providers: list[BaseCheckoutProvider] = []
    for variant, _provider_class in iter_checkout_provider_classes():
        try:
            providers.append(get_checkout_provider(variant))
        except Exception:
            continue
    return providers
