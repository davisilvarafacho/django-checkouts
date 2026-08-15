"""Operações de checkout hospedado."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import CancelCheckout
from django_checkouts.gateways.commands import CreateCheckout
from django_checkouts.gateways.commands import RetrieveCheckout
from django_checkouts.resources._validation import require_idempotency_key

if TYPE_CHECKING:
    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types.checkouts import Checkout
    from django_checkouts.types.checkouts import CheckoutCreate


class CheckoutResource:
    """Interface de consultas e mutações de checkouts."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def create(
        self, request: CheckoutCreate, *, idempotency_key: str
    ) -> Checkout:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            CreateCheckout(request=request, idempotency_key=idempotency_key)
        )

    def retrieve(self, external_id: str) -> Checkout:
        return self.gateway.execute(RetrieveCheckout(external_id=external_id))

    def cancel(self, external_id: str, *, idempotency_key: str) -> Checkout:
        require_idempotency_key(idempotency_key)
        return self.gateway.execute(
            CancelCheckout(
                external_id=external_id,
                idempotency_key=idempotency_key,
            )
        )
