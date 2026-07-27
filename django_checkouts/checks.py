"""System checks — configuração quebrada aparece no ``manage.py check``.

Cada provider expõe ``auth`` e ``webhook_auth``, e o ``validate()`` deles vira
``CheckMessage``. Credencial faltando é erro de deploy e deve ser detectada antes
do primeiro 401 em produção.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from django_checkouts.registry import iter_checkout_providers


@register("django_checkouts")
def check_checkout_providers(app_configs: Any = None, **kwargs: Any) -> list:
    """Valida as credenciais dos gateways na subida do processo."""
    messages: list = []
    for provider in iter_checkout_providers():
        for attr in ("auth", "webhook_auth"):
            auth = getattr(provider, attr, None)
            if auth is not None:
                messages.extend(auth.validate())

        if getattr(provider, "sandbox", False) and not settings.DEBUG:
            messages.append(
                CheckWarning(
                    f"O provider '{provider.name}' está com credenciais de "
                    f"sandbox e DEBUG=False.",
                    hint="Use sandbox=False para credenciais de produção.",
                    id="django_checkouts.W002",
                )
            )
    return messages
