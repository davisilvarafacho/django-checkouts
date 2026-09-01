"""Handler de reconciliação dos eventos do Stripe."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.commands import ListEvents
from django_checkouts.gateways.stripe.mapping import event_page_from_stripe

if TYPE_CHECKING:
    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.contracts import ExecutionContext
    from django_checkouts.types import EventPage


class StripeListEventsHandler:
    """Lista uma janela semifechada e devolve eventos cronológicos."""

    command_type = ListEvents

    def validate(self, command: ListEvents, capabilities: GatewayCapabilities) -> None:
        maximum = capabilities.reconciliation.maximum_page_size
        if (
            isinstance(command.limit, bool)
            or not isinstance(command.limit, int)
            or not 1 <= command.limit <= maximum
        ):
            raise ValidationError(f"limit deve ser um inteiro entre 1 e {maximum}.")
        if not _is_aware(command.occurred_since) or not _is_aware(
            command.occurred_before
        ):
            raise ValidationError(
                "occurred_since e occurred_before devem ser datetime timezone-aware."
            )
        if command.occurred_since >= command.occurred_before:
            raise ValidationError("occurred_since deve ser anterior a occurred_before.")

    def handle(self, command: ListEvents, context: ExecutionContext) -> EventPage:
        import stripe

        raw = context.call(
            stripe.Event.list,
            created={
                "gte": int(command.occurred_since.timestamp()),
                "lt": int(command.occurred_before.timestamp()),
            },
            starting_after=command.cursor,
            limit=command.limit,
        )
        return event_page_from_stripe(
            raw,
            variant=context.variant,
            occurred_since=command.occurred_since,
            occurred_before=command.occurred_before,
        )


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = ["StripeListEventsHandler"]
