"""Operações de faturas remotas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import RetrieveInvoice

if TYPE_CHECKING:
    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types.invoices import Invoice


class InvoiceResource:
    """Interface de consultas de faturas."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def retrieve(self, external_id: str) -> Invoice:
        return self.gateway.execute(RetrieveInvoice(external_id=external_id))
