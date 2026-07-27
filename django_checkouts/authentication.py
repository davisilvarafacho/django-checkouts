"""Authentication classes de DRF para endpoints de webhook.

Import opcional: só funciona se ``djangorestframework`` estiver instalado.

A lib não traz view de webhook — o que fazer com um pagamento confirmado é
decisão do seu projeto, e qualquer default aqui seria engessado. O que ela traz
é a autenticação, que é idêntica em todo projeto e fácil de errar em silêncio.
A verificação acontece **antes** de o DRF parsear o corpo, e o payload já
normalizado chega em ``request.auth``::

    from django_checkouts.authentication import StripeWebhookAuthentication
    from rest_framework.views import APIView

    class StripeWebhookView(APIView):
        authentication_classes = [StripeWebhookAuthentication]
        permission_classes = []

        def post(self, request):
            payload = request.auth       # WebhookPayload verificado
            ...                          # a view é sua
            return Response(status=200)

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from django_checkouts.enums import Provider
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.registry import get_checkout_provider

if TYPE_CHECKING:
    from django_checkouts.dto import WebhookPayload


class FakeGatewayUser:
    """Usuário falso que representa o gateway num webhook verificado.

    Não é um usuário de verdade e nunca toca o banco: o DRF exige um par
    ``(user, auth)``, e o "usuário" de um webhook é o próprio gateway. Implementa
    o suficiente da interface de user para as permissions do DRF não estourarem,
    e nada além disso.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.pk = None
        self.is_active = True
        self.is_staff = False
        self.is_superuser = False

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"gateway:{self.provider}"


class BaseCheckoutWebhookAuthentication(BaseAuthentication):
    """Verifica um webhook de checkout antes de o corpo ser parseado."""

    provider_name: Provider | str = ""
    """Chave da variante em ``CHECKOUT_VARIANTS``. Use um membro de
    :class:`~django_checkouts.enums.Provider` nos provedores da lib; string crua
    só para variante com nome próprio (``"stripe-br"``, multi-tenant)."""

    def authenticate(self, request) -> tuple[FakeGatewayUser, WebhookPayload]:
        provider = get_checkout_provider(self.provider_name)
        try:
            payload = provider.verify_webhook(
                raw_body=request.body,
                headers=request.headers,
            )
        except WebhookVerificationError as exc:
            raise AuthenticationFailed(str(exc)) from exc
        return FakeGatewayUser(self.provider_name), payload

    def authenticate_header(self, request) -> str:
        return f'Webhook realm="{self.provider_name}"'


def webhook_auth_for(
    provider_name: Provider | str,
) -> type[BaseCheckoutWebhookAuthentication]:
    """Monta uma authentication class amarrada a uma variante.

    Args:
        provider_name: Membro de :class:`~django_checkouts.enums.Provider` para
            os provedores da lib; string só quando a variante tem nome próprio
            (``webhook_auth_for("stripe-br")``).
    """
    name = str(provider_name)
    class_name = f"{name.title().replace('-', '')}WebhookAuthentication"
    return type(
        class_name,
        (BaseCheckoutWebhookAuthentication,),
        {"provider_name": provider_name},
    )


StripeWebhookAuthentication = webhook_auth_for(Provider.STRIPE)
PagSeguroWebhookAuthentication = webhook_auth_for(Provider.PAGSEGURO)
AsaasWebhookAuthentication = webhook_auth_for(Provider.ASAAS)
