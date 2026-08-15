"""Cliente público composto pelos recursos de checkout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.resources import CheckoutResource
from django_checkouts.resources import EventResource
from django_checkouts.resources import InvoiceResource
from django_checkouts.resources import SubscriptionResource
from django_checkouts.resources import WebhookResource

if TYPE_CHECKING:
    from django_checkouts.gateways.base import BaseCheckoutGateway


class CheckoutClient:
    """Entrada pública para as operações de uma variante de gateway."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self._gateway = gateway
        self.gateway, self.variant = gateway.name, gateway.variant
        self.capabilities = gateway.capabilities
        self.checkouts = CheckoutResource(gateway)
        self.subscriptions = SubscriptionResource(gateway)
        self.invoices = InvoiceResource(gateway)
        self.webhooks = WebhookResource(gateway)
        self.events = EventResource(gateway)
