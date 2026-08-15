"""Contratos compartilhados pelo despacho interno dos gateways."""

from __future__ import annotations

from collections.abc import Callable  # noqa: TC003 - runtime hints
from dataclasses import dataclass
from typing import Protocol
from typing import TypeVar

from django_checkouts.capabilities import (
    GatewayCapabilities,  # noqa: TC001 - runtime hints
)
from django_checkouts.enums import Gateway  # noqa: TC001 - runtime hints
from django_checkouts.gateways.commands import (
    GatewayCommand,  # noqa: TC001 - runtime hints
)

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionContext:
    """Dados de uma execução, sem reter estado entre comandos."""

    gateway: Gateway | str
    variant: str
    call: Callable[..., object]


class CommandHandler(Protocol[ResultT]):
    """Adaptador de um tipo exato de comando para um gateway concreto."""

    command_type: type[GatewayCommand[ResultT]]

    def validate(
        self,
        command: GatewayCommand[ResultT],
        capabilities: GatewayCapabilities,
    ) -> None:
        """Recusa comandos inviáveis antes de qualquer operação externa."""

    def handle(
        self,
        command: GatewayCommand[ResultT],
        context: ExecutionContext,
    ) -> ResultT:
        """Executa um comando previamente validado."""
