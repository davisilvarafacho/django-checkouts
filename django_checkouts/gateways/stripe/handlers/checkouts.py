"""Handlers de criação, consulta e cancelamento de Checkout Sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.utils import timezone

from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import Gateway
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import ConfigurationError
from django_checkouts.exceptions import UnsupportedPaymentMethod
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.commands import CancelCheckout
from django_checkouts.gateways.commands import CreateCheckout
from django_checkouts.gateways.commands import CreateSetup
from django_checkouts.gateways.commands import RetrieveCheckout
from django_checkouts.gateways.stripe.mapping import build_checkout_params
from django_checkouts.gateways.stripe.mapping import build_setup_params
from django_checkouts.gateways.stripe.mapping import checkout_from_stripe
from django_checkouts.gateways.stripe.mapping import setup_from_stripe
from django_checkouts.gateways.stripe.options import StripeCheckoutOptions
from django_checkouts.types import CatalogPrice
from django_checkouts.types import InlinePrice

if TYPE_CHECKING:
    from django_checkouts.capabilities import CheckoutCapabilities
    from django_checkouts.capabilities import GatewayCapabilities
    from django_checkouts.gateways.contracts import ExecutionContext
    from django_checkouts.types import Checkout
    from django_checkouts.types import CheckoutCreate

MIN_EXPIRATION_SECONDS = 30 * 60
MAX_EXPIRATION_SECONDS = 24 * 60 * 60


class StripeCreateCheckoutHandler:
    """Cria uma Checkout Session depois da validação de capabilities."""

    command_type = CreateCheckout

    def validate(
        self, command: CreateCheckout, capabilities: GatewayCapabilities
    ) -> None:
        validate_checkout_create(
            command.request,
            capabilities.checkouts,
            Gateway.STRIPE,
        )
        _validate_stripe_options(command.request)
        _validate_stripe_expiration(command.request)

    def handle(self, command: CreateCheckout, context: ExecutionContext) -> Checkout:
        stripe = _import_stripe()
        raw = context.call(
            stripe.checkout.Session.create,
            **build_checkout_params(command.request),
            idempotency_key=command.idempotency_key,
            mutation=True,
        )
        return checkout_from_stripe(raw, variant=context.variant)


class StripeCreateSetupHandler:
    command_type = CreateSetup

    def validate(self, command: CreateSetup, capabilities: GatewayCapabilities) -> None:
        if not capabilities.checkouts.supports_setup:
            raise CapabilityNotSupported(str(Gateway.STRIPE), "setup")
        supported = capabilities.checkouts.payment_methods_for(CheckoutMode.PAYMENT)
        for method in command.request.payment_methods:
            if method not in supported:
                raise UnsupportedPaymentMethod(
                    str(Gateway.STRIPE), str(method), supported
                )

    def handle(self, command: CreateSetup, context: ExecutionContext):
        stripe = _import_stripe()
        raw = context.call(
            stripe.checkout.Session.create,
            **build_setup_params(command.request),
            idempotency_key=command.idempotency_key,
            mutation=True,
        )
        return setup_from_stripe(raw, variant=context.variant)


class StripeRetrieveCheckoutHandler:
    """Consulta e normaliza uma Checkout Session."""

    command_type = RetrieveCheckout

    def validate(
        self, command: RetrieveCheckout, capabilities: GatewayCapabilities
    ) -> None:
        del command
        del capabilities

    def handle(self, command: RetrieveCheckout, context: ExecutionContext) -> Checkout:
        stripe = _import_stripe()
        raw = context.call(stripe.checkout.Session.retrieve, command.external_id)
        return checkout_from_stripe(raw, variant=context.variant)


class StripeCancelCheckoutHandler:
    """Expira somente a sessão; uma assinatura criada não é cancelada."""

    command_type = CancelCheckout

    def validate(
        self, command: CancelCheckout, capabilities: GatewayCapabilities
    ) -> None:
        del command
        del capabilities

    def handle(self, command: CancelCheckout, context: ExecutionContext) -> Checkout:
        stripe = _import_stripe()
        raw = context.call(
            stripe.checkout.Session.expire,
            command.external_id,
            idempotency_key=command.idempotency_key,
            mutation=True,
        )
        return checkout_from_stripe(raw, variant=context.variant)


def validate_checkout_create(
    request: CheckoutCreate,
    capabilities: CheckoutCapabilities,
    gateway: Gateway | str,
) -> None:
    """Recusa opções fora das capabilities antes do I/O externo."""
    gateway_name = str(gateway)
    if request.mode not in capabilities.modes:
        raise CapabilityNotSupported(gateway_name, f"checkout:{request.mode}")

    supported_methods = capabilities.payment_methods_for(request.mode)
    for method in request.payment_methods:
        if method not in supported_methods:
            raise UnsupportedPaymentMethod(
                gateway_name,
                str(method),
                supported_methods,
            )

    for item in request.items:
        if (
            isinstance(item.price, CatalogPrice)
            and not capabilities.supports_catalog_prices
        ):
            raise CapabilityNotSupported(gateway_name, "catalog_prices")
        if (
            isinstance(item.price, InlinePrice)
            and not capabilities.supports_inline_prices
        ):
            raise CapabilityNotSupported(gateway_name, "inline_prices")

    if (
        request.recurrence is not None
        and request.recurrence.cycle not in capabilities.billing_cycles
    ):
        raise CapabilityNotSupported(
            gateway_name,
            f"billing_cycle:{request.recurrence.cycle}",
        )
    if request.expires_at is not None and not capabilities.supports_expiration:
        raise CapabilityNotSupported(gateway_name, "expiration")
    if request.customer is not None and not capabilities.supports_customer_prefill:
        raise CapabilityNotSupported(gateway_name, "customer_prefill")


def _validate_stripe_options(request: CheckoutCreate) -> None:
    options = request.gateway_options
    if options is not None and not isinstance(options, StripeCheckoutOptions):
        raise ValidationError(
            "gateway_options deve ser StripeCheckoutOptions para o gateway Stripe."
        )


def _validate_stripe_expiration(request: CheckoutCreate) -> None:
    if request.expires_at is None:
        return
    delta = (request.expires_at - timezone.now()).total_seconds()
    if delta < MIN_EXPIRATION_SECONDS:
        raise ValidationError("O Stripe exige validade de no mínimo 30 minutos.")
    if delta > MAX_EXPIRATION_SECONDS:
        raise ValidationError("O Stripe exige validade de no máximo 24 horas.")


def _import_stripe() -> Any:
    try:
        import stripe
    except ImportError as error:  # pragma: no cover - depende do extra instalado
        raise ConfigurationError(
            "O SDK do Stripe não está instalado. Instale django-checkouts[stripe]."
        ) from error
    return stripe


__all__ = [
    "StripeCancelCheckoutHandler",
    "StripeCreateCheckoutHandler",
    "StripeCreateSetupHandler",
    "StripeRetrieveCheckoutHandler",
    "validate_checkout_create",
]
