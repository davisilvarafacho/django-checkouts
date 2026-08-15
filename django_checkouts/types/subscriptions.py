"""Pedidos e resultados normalizados de assinatura."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 - runtime hints
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # noqa: TC003 - runtime hints
from types import MappingProxyType

from django_checkouts.enums import BillingCycle
from django_checkouts.enums import ChangeTiming
from django_checkouts.enums import Gateway
from django_checkouts.enums import ProrationBehavior
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.gateways.options import (
    GatewayOptions,  # noqa: TC001 - runtime hints
)
from django_checkouts.types.common import Price
from django_checkouts.types.common import normalize_currency
from django_checkouts.types.common import normalize_utc
from django_checkouts.types.common import validate_integer
from django_checkouts.types.common import validate_positive_integer


@dataclass(frozen=True, slots=True, kw_only=True)
class SetQuantity:
    """Define a quantidade absoluta de um item remoto."""

    item_id: str
    quantity: int

    def __post_init__(self) -> None:
        validate_positive_integer(self.quantity, "quantity")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplacePrice:
    """Substitui o preço de um item remoto."""

    item_id: str
    price: Price
    quantity: int | None = None

    def __post_init__(self) -> None:
        if self.quantity is not None:
            validate_positive_integer(self.quantity, "quantity")


@dataclass(frozen=True, slots=True, kw_only=True)
class AddItem:
    """Adiciona um novo item à assinatura."""

    price: Price
    quantity: int = 1

    def __post_init__(self) -> None:
        validate_positive_integer(self.quantity, "quantity")


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveItem:
    """Remove um item remoto da assinatura."""

    item_id: str


SubscriptionChange = SetQuantity | ReplacePrice | AddItem | RemoveItem


def validate_subscription_changes(changes: tuple[SubscriptionChange, ...]) -> None:
    """Recusa mudanças vazias ou concorrentes sobre o mesmo item remoto."""
    if not changes:
        raise ValueError("changes deve conter pelo menos uma alteração.")

    targeted_item_ids: set[str] = set()
    for change in changes:
        item_id = getattr(change, "item_id", None)
        if item_id is None:
            continue
        if item_id in targeted_item_ids:
            raise ValueError(
                f"Duas alterações não podem atingir o mesmo item_id: {item_id!r}."
            )
        targeted_item_ids.add(item_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeSubscription:
    """Conjunto de mudanças portáveis de uma assinatura existente."""

    changes: tuple[SubscriptionChange, ...]
    timing: ChangeTiming = ChangeTiming.IMMEDIATELY
    proration: ProrationBehavior = ProrationBehavior.CREATE_PRORATIONS
    metadata: Mapping[str, str] | None = None
    gateway_options: GatewayOptions | None = None

    def __post_init__(self) -> None:
        validate_subscription_changes(self.changes)


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionItem:
    """Item normalizado pertencente a uma assinatura."""

    external_id: str
    price_id: str | None
    quantity: int
    unit_amount: int | None
    currency: str | None
    billing_cycle: BillingCycle | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        validate_positive_integer(self.quantity, "quantity")
        if self.unit_amount is not None:
            validate_integer(self.unit_amount, "unit_amount")
        if self.currency is not None:
            object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))


@dataclass(frozen=True, slots=True, kw_only=True)
class Subscription:
    """Estado normalizado de uma assinatura retornada pelo gateway."""

    external_id: str
    gateway: Gateway | str
    variant: str
    status: SubscriptionStatus
    customer_id: str | None
    items: tuple[SubscriptionItem, ...]
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_end: datetime | None
    cancel_at: datetime | None
    canceled_at: datetime | None
    ended_at: datetime | None
    latest_invoice_id: str | None
    reference_id: str | None
    metadata: Mapping[str, str]
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in (
            "current_period_start",
            "current_period_end",
            "trial_end",
            "cancel_at",
            "canceled_at",
            "ended_at",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
