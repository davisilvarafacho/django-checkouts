"""Despacho seguro e tipado para implementações de gateway."""

from __future__ import annotations

from collections.abc import Callable  # noqa: TC003 - runtime hints
from collections.abc import Sequence  # noqa: TC003 - runtime hints
from typing import Any
from typing import TypeVar
from typing import cast

from django.core.checks import CheckMessage  # noqa: TC002 - runtime hints

from django_checkouts.capabilities import (
    GatewayCapabilities,  # noqa: TC001 - runtime hints
)
from django_checkouts.enums import Gateway  # noqa: TC001 - runtime hints
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import CheckoutError
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.gateways.commands import (
    GatewayCommand,  # noqa: TC001 - runtime hints
)
from django_checkouts.gateways.contracts import CommandHandler
from django_checkouts.gateways.contracts import ExecutionContext

ResultT = TypeVar("ResultT")


class BaseCheckoutGateway:
    """Base para gateways que despacham comandos por seu tipo exato."""

    name: Gateway | str
    capabilities: GatewayCapabilities
    handlers: tuple[CommandHandler[Any], ...] = ()

    def __init__(self, *, variant: str, **configuration: object) -> None:
        """Inicializa a variante e o índice imutável dos handlers declarados."""
        del configuration
        self.variant = variant
        self._handlers = {handler.command_type: handler for handler in self.handlers}

    def execute(self, command: GatewayCommand[ResultT]) -> ResultT:
        """Valida e despacha um comando sem aceitar subclasses implicitamente."""
        handler = self._handlers.get(type(command))
        if handler is None:
            raise CapabilityNotSupported(str(self.name), type(command).__name__)

        typed_handler = cast("CommandHandler[ResultT]", handler)
        typed_handler.validate(command, self.capabilities)
        context = ExecutionContext(
            gateway=self.name,
            variant=self.variant,
            call=self.call,
        )
        return typed_handler.handle(command, context)

    def call(
        self,
        func: Callable[..., ResultT],
        *args: object,
        mutation: bool = False,
        **kwargs: object,
    ) -> ResultT:
        """Executa I/O e converte falhas externas para erros públicos."""
        try:
            return func(*args, **kwargs)
        except CheckoutError:
            raise
        except Exception as error:  # noqa: BLE001 - fronteira traduz erros externos
            raise self.translate_error(error, mutation=mutation) from None

    def translate_error(self, error: Exception, *, mutation: bool) -> CheckoutError:
        """Converte falhas externas sem propagar detalhes não confiáveis."""
        del error
        del mutation
        return GatewayPermanentError(
            "O gateway recusou ou não concluiu a operação solicitada.",
            gateway=self.name,
            variant=self.variant,
        )

    def check(self) -> Sequence[CheckMessage]:
        """Devolve avisos de configuração adicionais do gateway, quando houver."""
        return ()
