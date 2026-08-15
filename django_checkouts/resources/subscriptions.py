"""Operações de assinaturas remotas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import CancelRemoteSubscription
from django_checkouts.gateways.commands import ChangeRemoteSubscription
from django_checkouts.gateways.commands import ResumeSubscription
from django_checkouts.gateways.commands import RetrieveSubscription
from django_checkouts.resources._validation import require_idempotency_key

if TYPE_CHECKING:
    from django_checkouts.enums import CancellationTiming
    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types.subscriptions import ChangeSubscription
    from django_checkouts.types.subscriptions import Subscription


class SubscriptionResource:
    """Interface de consultas e mutações de assinaturas."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def retrieve(self, external_id: str) -> Subscription:
        return self.gateway.execute(RetrieveSubscription(external_id=external_id))

    def change(
        self,
        external_id: str,
        request: ChangeSubscription,
        *,
        idempotency_key: str,
    ) -> Subscription:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            ChangeRemoteSubscription(
                external_id=external_id,
                request=request,
                idempotency_key=idempotency_key,
            )
        )

    def cancel(
        self,
        external_id: str,
        *,
        timing: CancellationTiming,
        idempotency_key: str,
    ) -> Subscription:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            CancelRemoteSubscription(
                external_id=external_id,
                timing=timing,
                idempotency_key=idempotency_key,
            )
        )

    def resume(self, external_id: str, *, idempotency_key: str) -> Subscription:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            ResumeSubscription(
                external_id=external_id,
                idempotency_key=idempotency_key,
            )
        )
