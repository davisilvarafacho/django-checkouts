"""Credenciais **de saída**: como o provider se autentica no gateway.

O sentido aqui é aplicação → gateway. Para o caminho contrário — provar que um
webhook que chegou veio mesmo do gateway — veja :mod:`django_checkouts.webhooks`.

O ganho não está em montar o cabeçalho, que é trivial, e sim no
:meth:`BaseAuth.validate`: ele devolve ``CheckMessage``, e
:mod:`django_checkouts.checks` transforma isso em saída do ``manage.py check``.
Credencial ausente ou chave de produção em ambiente de sandbox aparecem no
deploy, e não como 401 no primeiro cliente real.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from django.core.checks import Error
from django.core.checks import Warning as CheckWarning

if TYPE_CHECKING:
    import requests
    from django.core.checks import CheckMessage


@dataclass
class BaseAuth:
    """Aplica credenciais do gateway numa sessão de requests."""

    sandbox: bool = False

    def apply(self, session: requests.Session) -> None:
        raise NotImplementedError

    def validate(self) -> list[CheckMessage]:
        return []


@dataclass
class TokenAuth(BaseAuth):
    """Credencial estática num cabeçalho de requisição.

    Cobre os três provedores do MVP: ``Authorization: Bearer <token>`` no Stripe
    e no PagBank, ``access_token: <token>`` sem esquema no Asaas.

    O token é ``repr=False``: objetos vão parar em log de exceção e em
    rastreadores de erro, e o segredo não pode ir junto.
    """

    token: str = field(default="", repr=False)
    header: str = "Authorization"
    scheme: str | None = "Bearer"
    expected_prefix: str | None = None

    def apply(self, session: requests.Session) -> None:
        value = f"{self.scheme} {self.token}" if self.scheme else self.token
        session.headers[self.header] = value

    def validate(self) -> list[CheckMessage]:
        messages: list[CheckMessage] = []
        if not self.token:
            messages.append(
                Error("Token de API ausente.", id="django_checkouts.E001")
            )
        elif self.expected_prefix and not self.token.startswith(self.expected_prefix):
            messages.append(
                CheckWarning(
                    f"O token de API não começa com '{self.expected_prefix}'.",
                    id="django_checkouts.W001",
                )
            )
        return messages
