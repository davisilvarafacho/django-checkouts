"""Autenticação opcional de webhooks para Django REST Framework."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication

from django_checkouts.registry import get_checkout_gateway

if TYPE_CHECKING:
    from django_checkouts.enums import Gateway
    from django_checkouts.types import WebhookEvent


class CheckoutWebhookAuthentication(BaseAuthentication):
    """Verifica o corpo cru e expõe o evento normalizado em ``request.auth``."""

    variant: Gateway | str = ""

    def authenticate(self, request) -> tuple[AnonymousUser, WebhookEvent]:
        event = get_checkout_gateway(self.variant).webhooks.verify(
            bytes(request.body), request.headers
        )
        return AnonymousUser(), event


def checkout_webhook_authentication(
    variant: Gateway | str,
) -> type[CheckoutWebhookAuthentication]:
    """Cria uma authentication class concreta vinculada a uma variante."""
    name = str(variant)
    class_name = f"{name.title().replace('-', '')}CheckoutWebhookAuthentication"
    return type(
        class_name,
        (CheckoutWebhookAuthentication,),
        {"variant": variant, "__module__": __name__},
    )


__all__ = ["CheckoutWebhookAuthentication", "checkout_webhook_authentication"]
