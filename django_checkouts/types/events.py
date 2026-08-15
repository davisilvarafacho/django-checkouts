"""Eventos verificados e páginas de reconciliação normalizadas."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 - runtime hints
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # noqa: TC003 - runtime hints
from types import MappingProxyType

from django_checkouts.enums import EventType  # noqa: TC001 - runtime hints
from django_checkouts.enums import Gateway  # noqa: TC001 - runtime hints
from django_checkouts.enums import ResourceKind  # noqa: TC001 - runtime hints
from django_checkouts.types.checkouts import Checkout  # noqa: TC001 - runtime hints
from django_checkouts.types.common import normalize_required_utc
from django_checkouts.types.invoices import Invoice  # noqa: TC001 - runtime hints
from django_checkouts.types.subscriptions import (
    Subscription,  # noqa: TC001 - runtime hints
)


@dataclass(frozen=True, slots=True, kw_only=True)
class WebhookEvent:
    """Evento autenticado e convertido para o vocabulário da biblioteca."""

    gateway: Gateway | str
    variant: str
    event_id: str
    event_type: str
    type: EventType | None
    occurred_at: datetime
    resource_kind: ResourceKind | None
    resource_id: str | None
    resource: Checkout | Subscription | Invoice | None
    livemode: bool | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "occurred_at",
            normalize_required_utc(self.occurred_at, "occurred_at"),
        )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))


@dataclass(frozen=True, slots=True, kw_only=True)
class EventPage:
    """Página temporal de eventos para reconciliação."""

    items: tuple[WebhookEvent, ...]
    next_cursor: str | None
    occurred_since: datetime
    occurred_before: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "occurred_since",
            normalize_required_utc(self.occurred_since, "occurred_since"),
        )
        object.__setattr__(
            self,
            "occurred_before",
            normalize_required_utc(self.occurred_before, "occurred_before"),
        )
