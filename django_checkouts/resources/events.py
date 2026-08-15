"""Reconciliação de eventos remotos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_checkouts.gateways.commands import ListEvents

if TYPE_CHECKING:
    from datetime import datetime

    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types.events import EventPage


class EventResource:
    """Interface para listar eventos de reconciliação."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def list(
        self,
        *,
        occurred_since: datetime,
        occurred_before: datetime,
        cursor: str | None = None,
        limit: int = 100,
    ) -> EventPage:
        return self.gateway.execute(
            ListEvents(
                occurred_since=occurred_since,
                occurred_before=occurred_before,
                cursor=cursor,
                limit=limit,
            )
        )
