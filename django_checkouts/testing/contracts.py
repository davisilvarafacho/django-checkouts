"""Asserções reutilizáveis para implementações de gateway."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import fields
from dataclasses import is_dataclass
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from django_checkouts.exceptions import CheckoutError
from django_checkouts.gateways.commands import CancelCheckout
from django_checkouts.gateways.commands import CancelRemoteSubscription
from django_checkouts.gateways.commands import CancelSetup
from django_checkouts.gateways.commands import ChangeRemoteSubscription
from django_checkouts.gateways.commands import CreateCheckout
from django_checkouts.gateways.commands import CreateSetup
from django_checkouts.gateways.commands import ListEvents
from django_checkouts.gateways.commands import ResumeSubscription
from django_checkouts.gateways.commands import RetrieveCheckout
from django_checkouts.gateways.commands import RetrieveInvoice
from django_checkouts.gateways.commands import RetrieveSetup
from django_checkouts.gateways.commands import RetrieveSubscription
from django_checkouts.gateways.commands import VerifyWebhook

if TYPE_CHECKING:
    from unittest.mock import Mock

    from django_checkouts.gateways.base import BaseCheckoutGateway
    from django_checkouts.types import WebhookEvent


class GatewayContractSuite:
    """Valida invariantes observáveis exigidas de qualquer gateway."""

    def __init__(self, gateway: BaseCheckoutGateway) -> None:
        self.gateway = gateway

    def assert_unique_exact_handlers(self) -> None:
        """Exige um único handler por tipo exato de comando."""
        command_types = tuple(handler.command_type for handler in self.gateway.handlers)
        assert all(type(command_type) is type for command_type in command_types), (
            "cada handler deve declarar um tipo exato de comando"
        )
        assert len(command_types) == len(set(command_types)), (
            "cada tipo de comando deve ter um único handler"
        )
        assert set(self.gateway._handlers) == set(command_types), (
            "o índice interno deve preservar exatamente os handlers declarados"
        )

    def assert_capability_handler_agreement(self) -> None:
        """Compara capabilities operacionais com os handlers publicados."""
        capabilities = self.gateway.capabilities
        expected: set[type[Any]] = {VerifyWebhook}
        if capabilities.checkouts.modes:
            expected.update({CreateCheckout, RetrieveCheckout, CancelCheckout})
        if capabilities.checkouts.supports_setup:
            expected.update({CreateSetup, RetrieveSetup, CancelSetup})
        subscriptions = capabilities.subscriptions
        if subscriptions.retrieve:
            expected.add(RetrieveSubscription)
        if (
            subscriptions.change_quantity
            or subscriptions.replace_price
            or subscriptions.add_remove_items
        ):
            expected.add(ChangeRemoteSubscription)
        if subscriptions.cancellation_timings:
            expected.add(CancelRemoteSubscription)
        if subscriptions.resume_scheduled_cancellation:
            expected.add(ResumeSubscription)
        if capabilities.invoices.retrieve:
            expected.add(RetrieveInvoice)
        if capabilities.reconciliation.events:
            expected.add(ListEvents)

        actual = {handler.command_type for handler in self.gateway.handlers}
        assert actual == expected, (
            "capabilities e handlers divergem: "
            f"faltando={expected - actual}, excedentes={actual - expected}"
        )

    @staticmethod
    def assert_validation_before_io(
        operation: Callable[[], object], *external_operations: Mock
    ) -> None:
        """Exige recusa pública antes de qualquer chamada externa observada."""
        try:
            operation()
        except CheckoutError:
            pass
        else:
            raise AssertionError("a operação inválida deve falhar publicamente")
        assert all(call.call_count == 0 for call in external_operations), (
            "a validação deve acontecer antes de I/O"
        )

    @staticmethod
    def assert_unchanged_idempotency_key(
        operation: Callable[[], object],
        external_operation: Mock,
        idempotency_key: str,
    ) -> None:
        """Exige que a chave pública chegue intacta à fronteira externa."""
        operation()
        forwarded = [
            call.kwargs["idempotency_key"]
            for call in external_operation.call_args_list
            if "idempotency_key" in call.kwargs
        ]
        assert forwarded, "a mutação deve encaminhar uma chave de idempotência"
        assert all(value == idempotency_key for value in forwarded), (
            "a chave de idempotência não pode ser alterada"
        )

    @staticmethod
    def assert_normalized_result(result: object, expected_type: type[Any]) -> None:
        """Exige tipo exato, UTC, currency maiúscula e ``raw`` oculto/imutável."""
        assert type(result) is expected_type, (
            f"resultado deve ser {expected_type.__name__}, não {type(result).__name__}"
        )
        for value in _walk_values(result):
            if isinstance(value, datetime):
                assert value.tzinfo is UTC, "todas as datas devem estar em UTC"
            if is_dataclass(value):
                currency = getattr(value, "currency", None)
                if isinstance(currency, str):
                    assert currency == currency.upper(), (
                        "currency normalizada deve estar em maiúsculas"
                    )
                _assert_hidden_immutable_raw(value)

    @staticmethod
    def assert_public_errors_only(
        operation: Callable[[], object],
        *,
        forbidden_values: Iterable[str] = (),
    ) -> None:
        """Exige erro público e ausência de segredos na representação."""
        error = _capture_error(operation)
        assert isinstance(error, CheckoutError), (
            f"erro externo escapou da interface: {type(error).__name__}"
        )
        rendered = f"{error!s} {error!r} {getattr(error, 'gateway_message', '')}"
        for value in forbidden_values:
            assert value not in rendered, "um valor externo sensível vazou no erro"

    @staticmethod
    def assert_verified_event_ids(events: Iterable[WebhookEvent]) -> None:
        """Exige IDs remotos não vazios, preservados e sem duplicidade."""
        events = tuple(events)
        ids = tuple(event.event_id for event in events)
        assert events, "ao menos um evento verificado deve ser informado"
        assert all(ids), "eventos verificados devem ter event_id"
        assert len(ids) == len(set(ids)), "event_id deve ser único na página"
        assert all(event.raw.get("id") == event.event_id for event in events), (
            "event_id deve preservar o identificador do evento verificado"
        )

    @staticmethod
    def assert_unknown_event(event: WebhookEvent) -> None:
        """Exige preservação segura de um tipo remoto ainda desconhecido."""
        assert event.event_type, "o tipo externo desconhecido deve ser preservado"
        assert event.type is None
        assert event.resource_kind is None
        assert event.resource_id is None
        assert event.resource is None
        _assert_hidden_immutable_raw(event)


def _walk_values(value: object) -> Iterable[object]:
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            yield from _walk_values(getattr(value, item.name))
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_values(item)


def _capture_error(operation: Callable[[], object]) -> Exception:
    try:
        operation()
    except Exception as error:  # noqa: BLE001 - o contrato detecta erros externos
        return error
    raise AssertionError("a operação de falha deve levantar uma exceção")


def _assert_hidden_immutable_raw(value: object) -> None:
    marker = object()
    raw = getattr(value, "raw", marker)
    if raw is marker:
        return
    assert isinstance(raw, Mapping), "raw deve ser um mapping somente de leitura"
    assert "raw=" not in repr(value), "raw não deve aparecer em repr"
    try:
        raw["__contract_mutation__"] = True  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("raw deve ser imutável")


__all__ = ["GatewayContractSuite"]
