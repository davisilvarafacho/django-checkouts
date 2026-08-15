"""Primitivas compartilhadas pelos comandos e resultados normalizados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django_checkouts.enums import BillingCycle


def validate_positive_integer(value: int, field_name: str) -> None:
    """Recusa booleanos, frações e valores não positivos para uma quantidade."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} deve ser um inteiro positivo.")
    if value <= 0:
        raise ValueError(f"{field_name} deve ser um inteiro positivo.")


def normalize_currency(currency: str) -> str:
    """Normaliza um código ISO 4217 simples para maiúsculas."""
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency deve ter exatamente três letras ISO 4217.")
    return currency.upper()


def normalize_utc(value: datetime | None, field_name: str) -> datetime | None:
    """Exige datas conscientes de fuso e devolve-as convertidas para UTC."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} deve ser datetime timezone-aware ou None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} deve ter timezone-aware para ser normalizado em UTC."
        )
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class InlinePrice:
    """Preço informado diretamente para criação de checkout, em centavos."""

    name: str
    unit_amount: int
    currency: str = "BRL"
    description: str | None = None
    image_url: str | None = None

    def __post_init__(self) -> None:
        validate_positive_integer(self.unit_amount, "unit_amount")
        object.__setattr__(self, "currency", normalize_currency(self.currency))


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogPrice:
    """Preço previamente cadastrado no catálogo remoto do gateway."""

    external_id: str


Price = InlinePrice | CatalogPrice


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutItem:
    """Um preço e sua quantidade absoluta em um checkout."""

    price: Price
    quantity: int = 1
    reference_id: str | None = None

    def __post_init__(self) -> None:
        validate_positive_integer(self.quantity, "quantity")


@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    """Dados portáveis do cliente, quando conhecidos."""

    name: str | None = None
    email: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    external_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Recurrence:
    """Periodicidade de uma assinatura."""

    cycle: BillingCycle
    description: str | None = None
