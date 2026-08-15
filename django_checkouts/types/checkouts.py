"""Pedidos e resultados normalizados de checkout."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from types import MappingProxyType
from typing import TYPE_CHECKING

from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import PaymentMethod
from django_checkouts.types.common import CheckoutItem
from django_checkouts.types.common import Customer
from django_checkouts.types.common import InlinePrice
from django_checkouts.types.common import Recurrence
from django_checkouts.types.common import normalize_currency
from django_checkouts.types.common import normalize_utc
from django_checkouts.types.common import validate_integer

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from django_checkouts.enums import Gateway
    from django_checkouts.gateways.options import GatewayOptions


def validate_checkout_create(checkout: CheckoutCreate) -> None:
    """Aplica invariantes que não pertencem a um item isolado."""
    if not checkout.items:
        raise ValueError("items deve conter pelo menos um item.")

    inline_currencies = {
        item.price.currency
        for item in checkout.items
        if isinstance(item.price, InlinePrice)
    }
    if len(inline_currencies) > 1:
        raise ValueError("Os preços inline de items devem usar a mesma currency.")
    if checkout.mode == CheckoutMode.PAYMENT and checkout.recurrence is not None:
        raise ValueError("recurrence só pode ser usada com mode=SUBSCRIPTION.")
    if (
        checkout.mode == CheckoutMode.SUBSCRIPTION
        and any(isinstance(item.price, InlinePrice) for item in checkout.items)
        and checkout.recurrence is None
    ):
        raise ValueError(
            "recurrence é obrigatória para preços inline em mode=SUBSCRIPTION."
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutCreate:
    """Pedido portável para iniciar um checkout hospedado."""

    items: tuple[CheckoutItem, ...]
    success_url: str
    mode: CheckoutMode = CheckoutMode.PAYMENT
    cancel_url: str | None = None
    payment_methods: tuple[PaymentMethod, ...] = (PaymentMethod.CARD,)
    customer: Customer | None = None
    recurrence: Recurrence | None = None
    reference_id: str | None = None
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    gateway_options: GatewayOptions | None = None

    def __post_init__(self) -> None:
        validate_checkout_create(self)
        object.__setattr__(
            self, "expires_at", normalize_utc(self.expires_at, "expires_at")
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Checkout:
    """Estado normalizado de um checkout retornado pelo gateway."""

    external_id: str
    gateway: Gateway | str
    variant: str
    status: CheckoutStatus
    mode: CheckoutMode
    url: str | None
    amount_total: int
    currency: str
    customer: Customer | None
    reference_id: str | None
    subscription_id: str | None
    expires_at: datetime | None
    created_at: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        validate_integer(self.amount_total, "amount_total")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(
            self, "expires_at", normalize_utc(self.expires_at, "expires_at")
        )
        object.__setattr__(
            self, "created_at", normalize_utc(self.created_at, "created_at")
        )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
