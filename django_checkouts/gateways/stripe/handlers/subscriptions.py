"""Handlers do ciclo de vida de assinaturas do Stripe."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from django_checkouts.enums import CancellationTiming
from django_checkouts.enums import ChangeTiming
from django_checkouts.enums import Gateway
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.commands import CancelRemoteSubscription
from django_checkouts.gateways.commands import ChangeRemoteSubscription
from django_checkouts.gateways.commands import ResumeSubscription
from django_checkouts.gateways.commands import RetrieveSubscription
from django_checkouts.gateways.stripe.mapping import PRORATION_MAP
from django_checkouts.gateways.stripe.mapping import build_subscription_change_items
from django_checkouts.gateways.stripe.mapping import scheduled_subscription_phases
from django_checkouts.gateways.stripe.mapping import subscription_from_stripe
from django_checkouts.types import InlinePrice

if TYPE_CHECKING:
    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.contracts import ExecutionContext
    from django_checkouts.types import Subscription

SUBSCRIPTION_EXPANSIONS = ["items.data.price", "latest_invoice"]


class StripeRetrieveSubscriptionHandler:
    """Consulta e normaliza uma assinatura."""

    command_type = RetrieveSubscription

    def validate(
        self, command: RetrieveSubscription, capabilities: GatewayCapabilities
    ) -> None:
        del command
        del capabilities

    def handle(
        self, command: RetrieveSubscription, context: ExecutionContext
    ) -> Subscription:
        raw = _retrieve(command.external_id, context)
        return subscription_from_stripe(raw, variant=context.variant)


class StripeChangeSubscriptionHandler:
    """Aplica mudanças agora ou agenda o conjunto do próximo ciclo."""

    command_type = ChangeRemoteSubscription

    def validate(
        self,
        command: ChangeRemoteSubscription,
        capabilities: GatewayCapabilities,
    ) -> None:
        del capabilities
        if any(
            isinstance(getattr(change, "price", None), InlinePrice)
            for change in command.request.changes
        ):
            raise CapabilityNotSupported(
                str(Gateway.STRIPE), "subscription_inline_prices"
            )

    def handle(
        self, command: ChangeRemoteSubscription, context: ExecutionContext
    ) -> Subscription:
        if command.request.timing is ChangeTiming.NEXT_CYCLE:
            return _schedule_change(command, context)

        import stripe

        params: dict[str, object] = {
            "items": build_subscription_change_items(command.request.changes),
            "proration_behavior": PRORATION_MAP[command.request.proration],
            "idempotency_key": command.idempotency_key,
        }
        if command.request.metadata is not None:
            params["metadata"] = dict(command.request.metadata)
        raw = context.call(
            stripe.Subscription.modify,
            command.external_id,
            **params,
            mutation=True,
        )
        return subscription_from_stripe(raw, variant=context.variant)


class StripeCancelSubscriptionHandler:
    """Cancela imediatamente ou agenda o cancelamento no fim do período."""

    command_type = CancelRemoteSubscription

    def validate(
        self,
        command: CancelRemoteSubscription,
        capabilities: GatewayCapabilities,
    ) -> None:
        del command
        del capabilities

    def handle(
        self, command: CancelRemoteSubscription, context: ExecutionContext
    ) -> Subscription:
        import stripe

        operation = (
            stripe.Subscription.cancel
            if command.timing is CancellationTiming.IMMEDIATELY
            else stripe.Subscription.modify
        )
        params: dict[str, object] = {"idempotency_key": command.idempotency_key}
        if command.timing is CancellationTiming.PERIOD_END:
            params["cancel_at_period_end"] = True
        raw = context.call(
            operation,
            command.external_id,
            **params,
            mutation=True,
        )
        return subscription_from_stripe(raw, variant=context.variant)


class StripeResumeSubscriptionHandler:
    """Retoma somente uma assinatura cujo cancelamento ainda não terminou."""

    command_type = ResumeSubscription

    def validate(
        self, command: ResumeSubscription, capabilities: GatewayCapabilities
    ) -> None:
        del command
        del capabilities

    def handle(
        self, command: ResumeSubscription, context: ExecutionContext
    ) -> Subscription:
        import stripe

        current = subscription_from_stripe(
            _retrieve(command.external_id, context), variant=context.variant
        )
        if (
            current.status is SubscriptionStatus.CANCELED
            or current.ended_at is not None
        ):
            raise ValidationError(
                "Uma assinatura encerrada ou cancelada não pode ser retomada."
            )
        raw = context.call(
            stripe.Subscription.modify,
            command.external_id,
            cancel_at_period_end=False,
            idempotency_key=command.idempotency_key,
            mutation=True,
        )
        return subscription_from_stripe(raw, variant=context.variant)


def _schedule_change(
    command: ChangeRemoteSubscription, context: ExecutionContext
) -> Subscription:
    import stripe

    current = subscription_from_stripe(
        _retrieve(command.external_id, context), variant=context.variant
    )
    schedule = context.call(
        stripe.SubscriptionSchedule.create,
        from_subscription=command.external_id,
        idempotency_key=command.idempotency_key,
        mutation=True,
    )
    schedule_id = _schedule_id(schedule, variant=context.variant)
    phases = scheduled_subscription_phases(
        current,
        schedule,
        command.request.changes,
        proration=command.request.proration,
        metadata=command.request.metadata,
        variant=context.variant,
    )
    context.call(
        stripe.SubscriptionSchedule.modify,
        schedule_id,
        phases=phases,
        idempotency_key=command.idempotency_key,
        mutation=True,
    )
    return subscription_from_stripe(
        _retrieve(command.external_id, context), variant=context.variant
    )


def _retrieve(external_id: str, context: ExecutionContext) -> object:
    import stripe

    return context.call(
        stripe.Subscription.retrieve,
        external_id,
        expand=SUBSCRIPTION_EXPANSIONS,
    )


def _schedule_id(schedule: object, *, variant: str) -> str:
    value = (
        schedule.get("id")
        if isinstance(schedule, Mapping)
        else getattr(schedule, "id", None)
    )
    if not isinstance(value, str) or not value:
        raise GatewayProtocolError(
            "O Stripe não informou o id do agendamento da assinatura.",
            gateway="stripe",
            variant=variant,
        )
    return value


__all__ = [
    "StripeCancelSubscriptionHandler",
    "StripeChangeSubscriptionHandler",
    "StripeResumeSubscriptionHandler",
    "StripeRetrieveSubscriptionHandler",
]
