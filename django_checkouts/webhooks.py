"""Verificação **de entrada**: provar que um webhook veio mesmo do gateway.

O sentido aqui é gateway → aplicação. Para o caminho contrário — a credencial
enviada ao chamar a API — veja :mod:`django_checkouts.credentials`.

A lib não traz view nem rota de webhook: roteamento, transação, fila e o que
fazer com um pagamento confirmado são decisões do seu projeto, e qualquer default
seria engessado. Ela cobre a parte que é idêntica em todo projeto e fácil de
errar em silêncio — provar a origem da requisição e normalizar o payload. Para
usar isso como authentication class de DRF, veja
:mod:`django_checkouts.integrations.drf`.

Toda comparação de segredo usa :func:`hmac.compare_digest`, nunca ``==``, para
não vazar o segredo por timing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from django.core.checks import Error

from django_checkouts.exceptions import WebhookVerificationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from django.core.checks import CheckMessage

    from django_checkouts.enums import Gateway


def normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Baixa as chaves para minúsculas e desfaz o prefixo ``HTTP_``.

    Cabeçalho HTTP é case-insensitive, e cada camada entrega de um jeito:
    ``request.headers`` do Django já normaliza, ``request.META`` vira
    ``HTTP_X_FOO``, e um dict escrito à mão num teste vem como veio. Normalizar
    na entrada evita o clássico "funciona em produção, falha no teste".
    """
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        name = key.lower().replace("_", "-")
        if name.startswith("http-"):
            name = name.removeprefix("http-")
        normalized[name] = value
    return normalized


@dataclass
class BaseWebhookAuth:
    """Prova que um webhook veio mesmo do gateway.

    ``verify`` devolve o payload já decodificado em vez de só validar: o Stripe
    verifica e constrói o evento na mesma passada, e decodificar duas vezes
    seria desperdício.
    """

    gateway: Gateway | str = ""
    """Quem assina o webhook."""

    secret: str = field(default="", repr=False)

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
        """Verifica a requisição e devolve o payload decodificado.

        Args:
            raw_body: Corpo **cru**, em bytes, exatamente como chegou.
                Reserializar o JSON quebra qualquer verificação por hash.
            headers: Cabeçalhos da requisição. Case-insensitive.

        Raises:
            WebhookVerificationError: A requisição não veio do gateway, ou o
                corpo está ilegível.
        """
        raise NotImplementedError

    def validate(self) -> list[CheckMessage]:
        if not self.secret:
            return [
                Error(
                    f"Segredo de webhook ausente para '{self.gateway}'; sem ele "
                    f"não há como autenticar as notificações recebidas.",
                    id="django_checkouts.E002",
                )
            ]
        return []

    # --- utilidades para as subclasses -------------------------------------

    def _require_header(self, headers: Mapping[str, str], name: str) -> str:
        value = normalize_headers(headers).get(name)
        if not value:
            raise WebhookVerificationError(
                f"Webhook de {self.gateway} sem o cabeçalho '{name}'. Ou a "
                f"requisição não veio do gateway, ou um proxy à frente da "
                f"aplicação está removendo o cabeçalho."
            )
        return value

    def _require_secret(self) -> str:
        if not self.secret:
            raise WebhookVerificationError(
                f"Segredo de webhook não configurado para '{self.gateway}'; "
                f"recusando a notificação por segurança."
            )
        return self.secret

    def _decode(self, raw_body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw_body or b"{}")
        except (ValueError, UnicodeDecodeError) as exc:
            raise WebhookVerificationError(
                f"O corpo do webhook de {self.gateway} não é JSON válido: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise WebhookVerificationError(
                f"Esperava um objeto JSON no webhook de {self.gateway}, "
                f"e recebi {type(payload).__name__}."
            )
        return payload


@dataclass
class HeaderTokenWebhookAuth(BaseWebhookAuth):
    """Compara um token estático enviado num cabeçalho.

    É o modelo do Asaas: você cadastra um token no painel e ele reenvia esse
    mesmo token em todo webhook. Mais fraco que assinatura do corpo — prova a
    origem, mas não a integridade do payload —, então trate o token como senha.
    """

    header: str = ""

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
        expected = self._require_secret()
        received = self._require_header(headers, self.header)
        if not hmac.compare_digest(expected, received):
            raise WebhookVerificationError(
                f"O token em '{self.header}' não confere com o configurado para "
                f"'{self.gateway}'."
            )
        return self._decode(raw_body)


@dataclass
class Sha256BodyWebhookAuth(BaseWebhookAuth):
    """Confere o SHA-256 hexadecimal de ``<token>-<corpo>``.

    É o modelo do PagBank. Diferente do token estático, também prova que o corpo
    não foi alterado no caminho — desde que você passe o corpo **cru**.
    """

    header: str = ""

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
        token = self._require_secret()
        received = self._require_header(headers, self.header)
        expected = hashlib.sha256(token.encode() + b"-" + raw_body).hexdigest()
        if not hmac.compare_digest(expected, received.lower()):
            raise WebhookVerificationError(
                f"O hash em '{self.header}' não confere para '{self.gateway}'. "
                f"Causa mais comum: o corpo foi reserializado antes da "
                f"verificação — passe request.body cru, não "
                f"json.dumps(request.data)."
            )
        return self._decode(raw_body)
