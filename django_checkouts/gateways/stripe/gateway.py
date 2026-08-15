"""Composição e fronteira de I/O do gateway Stripe."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import TypeVar
from typing import cast

from django_checkouts.enums import Gateway
from django_checkouts.enums import RetryDisposition
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
from django_checkouts.gateways.stripe.handlers import StripeResumeSubscriptionHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveCheckoutHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveInvoiceHandler
from django_checkouts.gateways.stripe.handlers import StripeRetrieveSubscriptionHandler

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

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
            StripeRetrieveCheckoutHandler(),
            StripeCancelCheckoutHandler(),
            StripeRetrieveSubscriptionHandler(),
            StripeChangeSubscriptionHandler(),
            StripeCancelSubscriptionHandler(),
            StripeResumeSubscriptionHandler(),
            StripeRetrieveInvoiceHandler(),
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

    def translate_error(self, error: Exception, *, mutation: bool) -> GatewayError:
        """Traduz as falhas de checkout do SDK para a taxonomia pública."""
        import stripe

        code = getattr(error, "http_status", None)
        if isinstance(error, stripe.APIConnectionError):
            return GatewayTemporaryError(
                "O Stripe não concluiu a operação temporariamente.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=str(error),
                retry_advice=_retry_advice(mutation),
            )
        if isinstance(error, stripe.RateLimitError):
            return GatewayTemporaryError(
                "O Stripe limitou temporariamente as requisições.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=str(error),
            )
        if isinstance(error, stripe.InvalidRequestError):
            if "No such checkout.session" in str(error):
                return ResourceNotFound(
                    "O checkout solicitado não existe no Stripe.",
                    gateway=self.name,
                    variant=self.variant,
                    code=code,
                    gateway_message=str(error),
                )
            return GatewayPermanentError(
                "O Stripe recusou os parâmetros da operação.",
                gateway=self.name,
                variant=self.variant,
                code=code,
                gateway_message=str(error),
            )
        if isinstance(error, stripe.AuthenticationError):
            return GatewayPermanentError(
                "O Stripe recusou a credencial configurada.",
                gateway=self.name,
                variant=self.variant,
                code=code,
            )
        if isinstance(error, stripe.APIError):
            api_error_code = 500 if code is None else code
            error_class = (
                GatewayTemporaryError
                if isinstance(api_error_code, int) and api_error_code >= 500
                else GatewayPermanentError
            )
            return error_class(
                "O Stripe não concluiu a operação solicitada.",
                gateway=self.name,
                variant=self.variant,
                code=api_error_code,
                gateway_message=str(error),
                retry_advice=(
                    _retry_advice(mutation)
                    if error_class is GatewayTemporaryError
                    else None
                ),
            )
        return super().translate_error(error, mutation=mutation)


def _retry_advice(mutation: bool) -> RetryAdvice:
    disposition = (
        RetryDisposition.RETRY_SAME_KEY
        if mutation
        else RetryDisposition.RETRY
    )
    return RetryAdvice(disposition=disposition)


__all__ = ["StripeGateway"]
