"""Gateway determinístico para testes de clientes consumidores."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django_checkouts.gateways.base import BaseCheckoutGateway

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping

    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.commands import GatewayCommand


class FakeCheckoutGateway(BaseCheckoutGateway):
    """Captura comandos e retorna o resultado configurado para o tipo exato."""

    name = "fake"

    def __init__(
        self,
        *,
        results: Mapping[
            type[GatewayCommand[Any]], Any | Callable[[GatewayCommand[Any]], Any]
        ],
        capabilities: GatewayCapabilities,
        variant: str = "fake",
    ) -> None:
        super().__init__(variant=variant)
        self.results = dict(results)
        self.capabilities = capabilities
        self.commands: list[GatewayCommand[Any]] = []

    def execute(self, command: GatewayCommand[Any]) -> Any:
        self.commands.append(command)
        result = self.results[type(command)]
        return result(command) if callable(result) else result
