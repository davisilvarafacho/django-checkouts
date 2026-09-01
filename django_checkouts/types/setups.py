"""Pedidos e resultados normalizados para coleta de forma de pagamento."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 - runtime hints
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # noqa: TC003 - runtime hints
from types import MappingProxyType

from django_checkouts.enums import Gateway
from django_checkouts.enums import PaymentMethod
from django_checkouts.types.common import Customer  # noqa: TC001 - runtime hints


@dataclass(frozen=True, slots=True, kw_only=True)
class SetupCreate:
    success_url: str
    cancel_url: str | None = None
    payment_methods: tuple[PaymentMethod, ...] = (PaymentMethod.CARD,)
    customer: Customer | None = None
    reference_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class Setup:
    external_id: str
    gateway: Gateway | str
    variant: str
    status: str
    url: str | None
    customer: Customer | None
    reference_id: str | None
    expires_at: datetime | None
    created_at: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
