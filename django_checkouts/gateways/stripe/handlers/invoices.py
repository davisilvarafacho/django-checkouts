"""Handler de consulta de faturas do Stripe."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import RetrieveInvoice
from django_checkouts.gateways.stripe.mapping import invoice_from_stripe

if TYPE_CHECKING:
    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.contracts import ExecutionContext
    from django_checkouts.types import Invoice


class StripeRetrieveInvoiceHandler:
    """Consulta a fatura expandindo o preço de cada linha."""

    command_type = RetrieveInvoice

    def validate(
        self, command: RetrieveInvoice, capabilities: GatewayCapabilities
    ) -> None:
        del command
        del capabilities

    def handle(
        self, command: RetrieveInvoice, context: ExecutionContext
    ) -> Invoice:
        import stripe

        raw = context.call(
            stripe.Invoice.retrieve,
            command.external_id,
            expand=["lines.data.price"],
        )
        return invoice_from_stripe(raw, variant=context.variant)


__all__ = ["StripeRetrieveInvoiceHandler"]
