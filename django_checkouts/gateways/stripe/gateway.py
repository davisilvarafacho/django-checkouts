"""Composição e fronteira de I/O do gateway Stripe."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import TypeVar
from typing import cast

from django_checkouts.enums import Gateway
from django_checkouts.enums import RetryDisposition
from django_checkouts.exceptions import CheckoutError
from django_checkouts.exceptions import ConfigurationError
from django_checkouts.exceptions import GatewayError
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.exceptions import GatewayTemporaryError
from django_checkouts.exceptions import ResourceNotFound
from django_checkouts.exceptions import RetryAdvice
from django_checkouts.gateways.base import BaseCheckoutGateway
from django_checkouts.gateways.stripe.capabilities import STRIPE_CAPABILITIES
from django_checkouts.gateways.stripe.handlers import StripeCancelCheckoutHandler
from django_checkouts.gateways.stripe.handlers import StripeCancelSubscriptionHandler
from django_checkouts.gateways.stripe.handlers import StripeChangeSubscriptionHandler
from django_checkouts.gateways.stripe.handlers import StripeCreateCheckoutHandler
from django_checkouts.gateways.stripe.handlers import StripeCreateSetupHandler
from django_checkouts.gateways.stripe.handlers import StripeListEventsHandler
from django_checkouts.gateways.stripe.handlers import StripeResumeSubscriptionHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveCheckoutHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveInvoiceHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveSubscriptionHandler
from django_checkouts.gateways.stripe.webhooks import StripeVerifyWebhookHandler

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence
    from typing import Any

    from django.core.checks import CheckMessage

    from django_checkouts.gateways.contracts import CommandHandler

ResultT = TypeVar("ResultT")


class StripeGateway(BaseCheckoutGateway):
    """Implementação Stripe sem estado global de credencial no SDK."""

    name = Gateway.STRIPE
    capabilities = STRIPE_CAPABILITIES
    handlers = cast(
        "tuple[CommandHandler[Any], ...]",
        (
            StripeCreateCheckoutHandler(),
            StripeCreateSetupHandler(),
            StripeRetrieveCheckoutHandler(),
            StripeCancelCheckoutHandler(),
            StripeRetrieveSubscriptionHandler(),
            StripeChangeSubscriptionHandler(),
            StripeCancelSubscriptionHandler(),
            StripeResumeSubscriptionHandler(),
            StripeRetrieveInvoiceHandler(),
            StripeListEventsHandler(),
        ),
    )

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str = "",
        sandbox: bool = True,
        variant: str = str(Gateway.STRIPE),
    ) -> None:
        self.handlers = cast(
            "tuple[CommandHandler[Any], ...]",
            (*self.handlers, StripeVerifyWebhookHandler(webhook_secret)),
        )
        super().__init__(variant=variant)
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.sandbox = sandbox

    def call(
        self,
        func: Callable[..., ResultT],
        *args: object,
        mutation: bool = False,
        **kwargs: object,
    ) -> ResultT:
        """Fornece a chave por chamada, sem alterar ``stripe.api_key``."""
        kwargs["api_key"] = self.api_key
        return super().call(func, *args, mutation=mutation, **kwargs)

    def translate_error(self, error: Exception, *, mutation: bool) -> CheckoutError:
        """Traduz as falhas de checkout do SDK para a taxonomia pública."""
        import stripe

        code = _external_error_code(error)
        gateway_message = getattr(error, "user_message", None)
        if isinstance(error, stripe.APIConnectionError):
            return GatewayTemporaryError(
                "O Stripe não concluiu a operação temporariamente.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=gateway_message,
                retry_advice=_retry_advice(mutation),
            )
        if isinstance(error, stripe.RateLimitError):
            return GatewayTemporaryError(
                "O Stripe limitou temporariamente as requisições.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=gateway_message,
            )
        if isinstance(error, stripe.IdempotencyError):
            return GatewayPermanentError(
                "O Stripe recusou a reutilização da chave de idempotência.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=gateway_message,
                retry_advice=RetryAdvice(
                    disposition=RetryDisposition.RECONCILE_FIRST
                ),
            )
        if isinstance(error, stripe.InvalidRequestError):
            if _is_missing_resource(error):
                return ResourceNotFound(
                    "O recurso solicitado não existe no Stripe.",
                    gateway=self.name,
                    variant=self.variant,
                    code=code,
                    gateway_message=gateway_message,
                )
            return GatewayPermanentError(
                "O Stripe recusou os parâmetros da operação.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=gateway_message,
            )
        if isinstance(error, stripe.AuthenticationError):
            return ConfigurationError(
                "O Stripe recusou a credencial configurada.",
                code=code,
            )
        if isinstance(error, stripe.APIError):
            if mutation:
                return GatewayPermanentError(
                    "O Stripe não confirmou o resultado da operação.",
                    gateway=self.name,
                    variant=self.variant,
                    code=code,
                    gateway_message=gateway_message,
                    retry_advice=RetryAdvice(
                        disposition=RetryDisposition.RECONCILE_FIRST
                    ),
                )
            http_status = getattr(error, "http_status", None)
            error_class: type[GatewayError] = GatewayTemporaryError
            if isinstance(http_status, int) and http_status < 500:
                error_class = GatewayPermanentError
            return error_class(
                "O Stripe não concluiu a operação solicitada.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=gateway_message,
            )
        return super().translate_error(error, mutation=mutation)

    def check(self) -> Sequence[CheckMessage]:
        """Valida credenciais localmente, sem inicializar o cliente Stripe."""
        from django.core.checks import Error
        from django.core.checks import Warning

        messages: list[CheckMessage] = []
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            messages.append(
                Error(
                    "A chave de API do gateway Stripe não foi configurada.",
                    id="django_checkouts.E001",
                )
            )
        if (
            self.capabilities.webhooks.signed
            and (
                not isinstance(self.webhook_secret, str)
                or not self.webhook_secret.strip()
            )
        ):
            messages.append(
                Error(
                    "O segredo de webhook do gateway Stripe não foi configurado.",
                    id="django_checkouts.E001",
                )
            )
        if (
            isinstance(self.api_key, str)
            and self.api_key.startswith("sk_live_")
            and self.sandbox
        ):
            messages.append(
                Warning(
                    "O gateway Stripe está em sandbox com uma chave live.",
                    id="django_checkouts.W001",
                )
            )
        return messages


def _retry_advice(mutation: bool) -> RetryAdvice:
    disposition = (
        RetryDisposition.RETRY_SAME_KEY
        if mutation
        else RetryDisposition.RETRY
    )
    return RetryAdvice(disposition=disposition)


def _external_error_code(error: Exception) -> str | int | None:
    """Mantém somente identificadores escalares seguros do SDK."""
    for attribute in ("code", "request_id", "http_status"):
        value = getattr(error, attribute, None)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and value:
            return value
    return None


def _is_missing_resource(error: Exception) -> bool:
    return (
        getattr(error, "code", None) == "resource_missing"
        or getattr(error, "http_status", None) == 404
        or "No such checkout.session" in str(error)
    )


__all__ = ["StripeGateway"]
