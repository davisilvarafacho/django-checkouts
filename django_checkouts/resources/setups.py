"""Operações de coleta de forma de pagamento sem cobrança."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import CancelSetup
from django_checkouts.gateways.commands import CreateSetup
from django_checkouts.gateways.commands import RetrieveSetup
from django_checkouts.resources._validation import require_idempotency_key

if TYPE_CHECKING:
    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types import Setup
    from django_checkouts.types import SetupCreate


class SetupResource:
    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def create(self, request: SetupCreate, *, idempotency_key: str) -> Setup:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            CreateSetup(request=request, idempotency_key=idempotency_key)
        )

    def retrieve(self, external_id: str) -> Setup:
        return self.gateway.execute(RetrieveSetup(external_id=external_id))

    def cancel(self, external_id: str, *, idempotency_key: str) -> Setup:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            CancelSetup(external_id=external_id, idempotency_key=idempotency_key)
        )
