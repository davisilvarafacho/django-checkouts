"""Pedidos e resultados normalizados para coleta de forma de pagamento."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime  # noqa: TC003 - runtime hints
from types import MappingProxyType
from urllib.parse import urlparse

from django_checkouts.enums import Gateway
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import SetupStatus
from django_checkouts.gateways.options import GatewayOptions  # noqa: TC001
from django_checkouts.types.common import Customer
from django_checkouts.types.common import normalize_utc


@dataclass(frozen=True, slots=True, kw_only=True)
class SetupCreate:
    success_url: str
    cancel_url: str | None = None
    payment_methods: tuple[PaymentMethod, ...] = (PaymentMethod.CARD,)
    customer: Customer | None = None
    reference_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    gateway_options: GatewayOptions | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("success_url", self.success_url),
            ("cancel_url", self.cancel_url),
        ):
            if value is None and name == "cancel_url":
                continue
            if (
                not isinstance(value, str)
                or urlparse(value).scheme not in {"http", "https"}
                or not urlparse(value).netloc
            ):
                raise ValueError(f"{name} deve ser uma URL HTTP(S) absoluta.")
        if not isinstance(self.payment_methods, tuple) or not self.payment_methods:
            raise ValueError("payment_methods deve ser uma tupla não vazia.")
        if any(
            not isinstance(method, PaymentMethod) for method in self.payment_methods
        ):
            raise TypeError("payment_methods deve conter somente PaymentMethod.")
        if self.customer is not None and not isinstance(self.customer, Customer):
            raise TypeError("customer deve ser Customer ou None.")
        if self.reference_id is not None and (
            not isinstance(self.reference_id, str) or not self.reference_id.strip()
        ):
            raise ValueError("reference_id deve ser texto não vazio ou None.")
        if not isinstance(self.metadata, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.metadata.items()
        ):
            raise TypeError("metadata deve mapear strings para strings.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True, kw_only=True)
class Setup:
    external_id: str
    gateway: Gateway | str
    variant: str
    status: SetupStatus
    url: str | None
    customer: Customer | None
    reference_id: str | None
    expires_at: datetime | None
    created_at: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.external_id, str) or not self.external_id.strip():
            raise ValueError("external_id deve ser texto não vazio.")
        if (
            not isinstance(self.gateway, (Gateway, str))
            or not str(self.gateway).strip()
        ):
            raise ValueError("gateway deve ser identificado.")
        if not isinstance(self.variant, str) or not self.variant.strip():
            raise ValueError("variant deve ser texto não vazio.")
        if not isinstance(self.status, SetupStatus):
            object.__setattr__(self, "status", SetupStatus(self.status))
        if self.reference_id is not None and (
            not isinstance(self.reference_id, str) or not self.reference_id.strip()
        ):
            raise ValueError("reference_id deve ser texto não vazio ou None.")
        object.__setattr__(
            self, "expires_at", normalize_utc(self.expires_at, "expires_at")
        )
        object.__setattr__(
            self, "created_at", normalize_utc(self.created_at, "created_at")
        )
        object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
