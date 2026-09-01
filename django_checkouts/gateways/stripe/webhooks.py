"""Autenticação de webhooks do Stripe antes da normalização."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.gateways.commands import VerifyWebhook
from django_checkouts.gateways.stripe.mapping import event_from_stripe

if TYPE_CHECKING:
    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.contracts import ExecutionContext
    from django_checkouts.types import WebhookEvent


@dataclass(frozen=True, slots=True)
class StripeVerifyWebhookHandler:
    """Verifica o corpo cru com o segredo do endpoint configurado."""

    webhook_secret: str
    command_type = VerifyWebhook

    def validate(
        self, command: VerifyWebhook, capabilities: GatewayCapabilities
    ) -> None:
        del capabilities
        if not self.webhook_secret:
            raise WebhookVerificationError(
                "O webhook_secret do Stripe não está configurado."
            )
        if _signature_header(command.headers) is None:
            raise WebhookVerificationError(
                "O cabeçalho Stripe-Signature não foi informado."
            )

    def handle(self, command: VerifyWebhook, context: ExecutionContext) -> WebhookEvent:
        import stripe

        signature = _signature_header(command.headers)
        if signature is None:  # protegido por validate
            raise WebhookVerificationError(
                "O cabeçalho Stripe-Signature não foi informado."
            )
        try:
            raw = stripe.Webhook.construct_event(
                payload=command.raw_body,
                sig_header=signature,
                secret=self.webhook_secret,
            )
        except (ValueError, stripe.SignatureVerificationError):
            raise WebhookVerificationError(
                "O corpo ou a assinatura do webhook do Stripe não confere."
            ) from None
        return event_from_stripe(raw, variant=context.variant)


def _signature_header(headers: object) -> str | None:
    items = getattr(headers, "items", None)
    if not callable(items):
        return None
    for key, value in items():
        if (
            isinstance(key, str)
            and key.lower() == "stripe-signature"
            and isinstance(value, str)
            and value
        ):
            return value
    return None


__all__ = ["StripeVerifyWebhookHandler"]
