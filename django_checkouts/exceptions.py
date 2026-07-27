"""Hierarquia de erros da lib.

A divisão que importa é **temporário vs permanente**: ela carrega a semântica
de retry no próprio tipo. Um
`ProviderTemporaryError` (timeout, 5xx) pode ser repetido tal como está; um
`ProviderPermanentError` (400, status não mapeado) vai falhar de novo do mesmo
jeito e precisa de intervenção. Sem essa distinção, todo `except` vira
adivinhação sobre se vale a pena tentar de novo.

Regra de ouro: **todo** erro que sai de um provider herda de
:class:`CheckoutError`. Se `requests.Timeout` ou `KeyError` vazar, é bug da lib.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Iterable


class CheckoutError(Exception):
    """Base de tudo que a lib levanta."""

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


class ProviderTemporaryError(CheckoutError):
    """Falha transitória; repetir a mesma chamada é seguro.

    Timeout, erro de conexão, 5xx do provedor. Numa view de webhook, responda
    5xx para o provedor reenviar.
    """


class ProviderPermanentError(CheckoutError):
    """Falha definitiva; repetir sem mudar nada vai dar no mesmo.

    4xx do provedor, corpo não-JSON, status fora do ``STATUS_MAP``. Numa view de
    webhook, responda 4xx — um 5xx faria o provedor reenviar para sempre algo
    que nunca vai passar.
    """


class ConfigurationError(CheckoutError):
    """``settings.DJANGO_CHECKOUTS`` ausente, incompleto ou inconsistente.

    Sempre erro de deploy, nunca de runtime do pagador. O ideal é que os system
    checks peguem isso antes — veja :mod:`django_checkouts.checks`.
    """


class ValidationError(CheckoutError):
    """Argumentos inválidos passados para um método do provider.

    Levantado **antes** de qualquer I/O — falha barata e local.
    """


class CapabilityNotSupported(CheckoutError):
    """O provider não implementa a operação pedida."""

    def __init__(self, provider: str, capability: str) -> None:
        super().__init__(
            f"O provedor '{provider}' não suporta a capacidade '{capability}'."
        )
        self.provider = provider
        self.capability = capability


class UnsupportedPaymentMethod(CheckoutError):
    """O provider não oferece um dos meios de pagamento pedidos."""

    def __init__(
        self, provider: str, method: str, supported: Iterable[Any]
    ) -> None:
        super().__init__(
            f"O provedor '{provider}' não suporta o meio de pagamento "
            f"'{method}'. Suportados: {sorted(str(item) for item in supported)}."
        )
        self.provider = provider
        self.method = method
        self.supported = supported


class CheckoutNotFound(ProviderPermanentError):
    """Nenhum checkout com o id informado existe no provedor."""


class WebhookVerificationError(ProviderPermanentError):
    """A assinatura ou o token do webhook não confere.

    Herda de permanente de propósito: a requisição não veio do provedor (ou o
    segredo está errado), e reenviá-la nunca vai resolver.
    """
