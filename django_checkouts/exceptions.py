"""Erros públicos e instruções seguras de repetição."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from django_checkouts.enums import RetryDisposition

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import timedelta

    from django_checkouts.enums import Gateway


def _sanitize_gateway_message(message: str | None) -> str | None:
    """Keep external diagnostics useful without retaining untrusted secrets."""
    if message is None:
        return None
    return "O gateway retornou uma mensagem de erro externa."


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryAdvice:
    """Orientação que o consumidor pode aplicar após uma falha."""

    disposition: RetryDisposition
    retry_after: timedelta | None = None


class CheckoutError(Exception):
    """Base de todos os erros que atravessam a interface pública."""

    def __init__(
        self,
        message: str = "",
        code: str | int | None = None,
        gateway_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.gateway_message = gateway_message
        self.retry_advice = RetryAdvice(disposition=RetryDisposition.NEVER)


class ConfigurationError(CheckoutError):
    """Configuração ausente ou inconsistente, a ser corrigida no deploy."""


class ValidationError(CheckoutError):
    """Argumentos inválidos, recusados antes de qualquer I/O."""


class CapabilityNotSupported(CheckoutError):
    """O gateway não implementa a operação solicitada."""

    def __init__(self, gateway: str, capability: str) -> None:
        super().__init__(
            f"O gateway '{gateway}' não suporta a capacidade '{capability}'."
        )
        self.gateway = gateway
        self.capability = capability


class UnsupportedPaymentMethod(CheckoutError):
    """O gateway não oferece um dos meios de pagamento pedidos."""

    def __init__(self, gateway: str, method: str, supported: Iterable[Any]) -> None:
        super().__init__(
            f"O gateway '{gateway}' não suporta o meio de pagamento '{method}'. "
            f"Suportados: {sorted(str(item) for item in supported)}."
        )
        self.gateway = gateway
        self.method = method
        self.supported = supported


class WebhookVerificationError(CheckoutError):
    """A assinatura ou o token do webhook não confere."""


class GatewayError(CheckoutError):
    """Falha já traduzida da API externa, sem expor segredos ao consumidor."""

    default_retry_advice = RetryAdvice(disposition=RetryDisposition.NEVER)

    def __init__(
        self,
        message: str = "",
        *,
        gateway: Gateway | str,
        variant: str,
        code: str | int | None = None,
        gateway_message: str | None = None,
        retry_advice: RetryAdvice | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            gateway_message=_sanitize_gateway_message(gateway_message),
        )
        self.gateway = gateway
        self.variant = variant
        self.retry_advice = retry_advice or self.default_retry_advice


class GatewayTemporaryError(GatewayError):
    """Falha transitória que pode ser repetida segundo ``retry_advice``."""

    default_retry_advice = RetryAdvice(disposition=RetryDisposition.RETRY)


class GatewayPermanentError(GatewayError):
    """Falha definitiva que não deve ser repetida sem conciliação ou mudança."""


class GatewayProtocolError(GatewayPermanentError):
    """Resposta externa incompatível com o contrato normalizado."""

    def __init__(
        self,
        message: str = "",
        *,
        gateway: Gateway | str,
        variant: str,
        code: str | int | None = None,
        gateway_message: str | None = None,
        retry_advice: RetryAdvice | None = None,
    ) -> None:
        GatewayError.__init__(
            self,
            message,
            gateway=gateway,
            variant=variant,
            code=code,
            gateway_message=gateway_message,
            retry_advice=retry_advice,
        )


class ResourceNotFound(GatewayPermanentError):
    """O recurso solicitado não existe no gateway."""
