"""Verificação de webhooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import VerifyWebhook

if TYPE_CHECKING:
    from collections.abc import Mapping

    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types.events import WebhookEvent


class WebhookResource:
    """Interface para verificar e normalizar webhooks recebidos."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> WebhookEvent:
        return self.gateway.execute(VerifyWebhook(raw_body=raw_body, headers=headers))
