"""Comandos internos tipados para a fronteira com os gateways."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 - runtime hints
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - runtime hints
from typing import Generic
from typing import TypeVar

from django_checkouts.enums import CancellationTiming  # noqa: TC001 - runtime hints
from django_checkouts.types.checkouts import Checkout
from django_checkouts.types.checkouts import CheckoutCreate
from django_checkouts.types.events import EventPage
from django_checkouts.types.events import WebhookEvent
from django_checkouts.types.invoices import Invoice
from django_checkouts.types.setups import Setup
from django_checkouts.types.setups import SetupCreate
from django_checkouts.types.subscriptions import ChangeSubscription
from django_checkouts.types.subscriptions import Subscription

ResultT = TypeVar("ResultT")


class GatewayCommand(Generic[ResultT]):
    """Intenção tipada a ser executada por um handler de gateway."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateCheckout(GatewayCommand[Checkout]):
    """Cria um checkout hospedado."""

    request: CheckoutCreate
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSetup(GatewayCommand[Setup]):
    """Coleta uma forma de pagamento sem efetuar cobrança."""

    request: SetupCreate
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveSetup(GatewayCommand[Setup]):
    external_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelSetup(GatewayCommand[Setup]):
    external_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveCheckout(GatewayCommand[Checkout]):
    """Busca um checkout pelo identificador externo."""

    external_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelCheckout(GatewayCommand[Checkout]):
    """Cancela um checkout pelo identificador externo."""

    external_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveSubscription(GatewayCommand[Subscription]):
    """Busca uma assinatura pelo identificador externo."""

    external_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeRemoteSubscription(GatewayCommand[Subscription]):
    """Altera uma assinatura existente."""

    external_id: str
    request: ChangeSubscription
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelRemoteSubscription(GatewayCommand[Subscription]):
    """Cancela uma assinatura imediatamente ou no fim do período."""

    external_id: str
    timing: CancellationTiming
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeSubscription(GatewayCommand[Subscription]):
    """Retoma um cancelamento agendado."""

    external_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveInvoice(GatewayCommand[Invoice]):
    """Busca uma fatura pelo identificador externo."""

    external_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyWebhook(GatewayCommand[WebhookEvent]):
    """Verifica e normaliza um webhook recebido."""

    raw_body: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ListEvents(GatewayCommand[EventPage]):
    """Lista uma página temporal de eventos para conciliação."""

    occurred_since: datetime
    occurred_before: datetime
    cursor: str | None = None
    limit: int = 100
