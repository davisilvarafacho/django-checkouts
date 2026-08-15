"""Resultados normalizados de faturas."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from types import MappingProxyType
from typing import TYPE_CHECKING

from django_checkouts.types.common import normalize_currency
from django_checkouts.types.common import normalize_utc
from django_checkouts.types.common import validate_positive_integer

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from django_checkouts.enums import Gateway
    from django_checkouts.enums import InvoiceReason
    from django_checkouts.enums import InvoiceStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceLine:
    """Linha normalizada de uma fatura."""

    external_id: str
    description: str | None
    quantity: int
    unit_amount: int | None
    amount: int
    currency: str
    subscription_item_id: str | None
    period_start: datetime | None
    period_end: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        validate_positive_integer(self.quantity, "quantity")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(
            self, "period_start", normalize_utc(self.period_start, "period_start")
        )
        object.__setattr__(
            self, "period_end", normalize_utc(self.period_end, "period_end")
        )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))


@dataclass(frozen=True, slots=True, kw_only=True)
class Invoice:
    """Estado normalizado de uma fatura retornada pelo gateway."""

    external_id: str
    gateway: Gateway | str
    variant: str
    status: InvoiceStatus
    reason: InvoiceReason
    subscription_id: str | None
    customer_id: str | None
    amount_due: int
    amount_paid: int
    amount_remaining: int
    currency: str
    lines: tuple[InvoiceLine, ...]
    due_at: datetime | None
    paid_at: datetime | None
    next_payment_attempt_at: datetime | None
    attempt_count: int
    hosted_url: str | None
    reference_id: str | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        for field_name in ("due_at", "paid_at", "next_payment_attempt_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
