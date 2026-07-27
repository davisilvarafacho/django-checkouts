"""Checkout hospedado para Django com uma interface única e tipada.

Uso mínimo::

    from django_checkouts import get_checkout_provider
    from django_checkouts.dto import LineItem
    from django_checkouts.enums import Provider

    provider = get_checkout_provider(Provider.STRIPE)
    data = provider.create_checkout(
        items=[LineItem(name="Plano Pro", amount=4990)],
        success_url="https://exemplo.com.br/obrigado/",
        reference_id=str(pedido.pk),
    )
    return redirect(data.url)
"""

from __future__ import annotations

from django_checkouts.registry import get_checkout_provider

__all__ = ["get_checkout_provider"]

default_app_config = "django_checkouts.apps.DjangoCheckoutsConfig"
