"""Checkout hospedado do Stripe (Checkout Sessions).

Instalação: ``pip install 'django-checkouts[stripe]'``.

O Stripe é o único dos três com catálogo de preços, então é o único que declara
``Capability.PROVIDER_CATALOG``. Sem ``provider_price_id``, a lib manda
``price_data`` inline — o que cria um Product novo a cada checkout. Para
catálogo estável, passe o ``price_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django_checkouts.base import BaseCheckoutProvider
from django_checkouts.credentials import TokenAuth
from django_checkouts.dto import CheckoutData
from django_checkouts.dto import Customer
from django_checkouts.dto import ProviderState
from django_checkouts.dto import WebhookPayload
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import Capability
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import EventType
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import Provider
from django_checkouts.exceptions import CheckoutNotFound
from django_checkouts.exceptions import ProviderPermanentError
from django_checkouts.exceptions import ProviderTemporaryError
from django_checkouts.exceptions import ValidationError
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.webhooks import BaseWebhookAuth

if TYPE_CHECKING:
    from collections.abc import Mapping
    from dataclasses import dataclass as _dataclass  # noqa: F401

    from django_checkouts.dto import CheckoutRequest

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime

# Fora de TYPE_CHECKING porque a conversão de ciclo é usada em runtime.
CYCLES: dict[BillingCycle, tuple[str, int]] = {
    BillingCycle.WEEKLY: ("week", 1),
    BillingCycle.BIWEEKLY: ("week", 2),
    BillingCycle.MONTHLY: ("month", 1),
    BillingCycle.BIMONTHLY: ("month", 2),
    BillingCycle.QUARTERLY: ("month", 3),
    BillingCycle.SEMIANNUALLY: ("month", 6),
    BillingCycle.YEARLY: ("year", 1),
}

PAYMENT_METHODS: dict[PaymentMethod, str] = {
    PaymentMethod.CARD: "card",
    PaymentMethod.PIX: "pix",
    PaymentMethod.BOLETO: "boleto",
}

#: O Stripe separa "a sessão terminou" (``status``) de "o dinheiro entrou"
#: (``payment_status``), e só o par diz o estado de verdade: uma sessão
#: ``complete`` com boleto emitido e não pago ainda é PENDING. Por isso o mapa é
#: chaveado por ``f"{status}/{payment_status}"``.
STATUS_MAP: dict[str, CheckoutStatus] = {
    "open/unpaid": CheckoutStatus.PENDING,
    "open/no_payment_required": CheckoutStatus.PENDING,
    "complete/paid": CheckoutStatus.PAID,
    "complete/no_payment_required": CheckoutStatus.PAID,
    "complete/unpaid": CheckoutStatus.PENDING,
    "expired/unpaid": CheckoutStatus.EXPIRED,
    "expired/no_payment_required": CheckoutStatus.EXPIRED,
    "expired/paid": CheckoutStatus.PAID,
}

EVENT_MAP: dict[str, EventType] = {
    "checkout.session.completed": EventType.CHECKOUT_PAID,
    "checkout.session.async_payment_succeeded": EventType.CHECKOUT_PAID,
    "checkout.session.async_payment_failed": EventType.CHECKOUT_FAILED,
    "checkout.session.expired": EventType.CHECKOUT_EXPIRED,
}


def _import_stripe():
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise ProviderPermanentError(
            "O SDK do Stripe não está instalado. Instale com "
            "pip install 'django-checkouts[stripe]'."
        ) from exc
    return stripe


@dataclass(frozen=True)
class StripeCheckoutState(ProviderState):
    """Visão tolerante do payload de Checkout Session do Stripe."""

    id: str | None = None
    status: str | None = None
    payment_status: str | None = None
    url: str | None = None
    amount_total: int | None = None
    currency: str | None = None
    customer: str | None = None
    customer_details: dict | None = None
    client_reference_id: str | None = None
    expires_at: int | None = None
    mode: str | None = None
    metadata: dict | None = None


@dataclass
class StripeWebhookAuth(BaseWebhookAuth):
    """Verificação de assinatura do Stripe, delegada ao SDK.

    O esquema ``v1`` do cabeçalho ``Stripe-Signature`` inclui timestamp e
    tolerância contra replay. Reimplementar isso à mão é fácil de errar, então
    usamos ``stripe.Webhook.construct_event``, que verifica e decodifica de uma
    vez só.
    """

    tolerance: int = 300
    header: str = field(default="stripe-signature")

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
        stripe = _import_stripe()
        secret = self._require_secret()
        signature = self._require_header(headers, self.header)
        try:
            event = stripe.Webhook.construct_event(
                payload=raw_body,
                sig_header=signature,
                secret=secret,
                tolerance=self.tolerance,
            )
        except ValueError as exc:
            raise WebhookVerificationError(
                f"O corpo do webhook do Stripe não é JSON válido: {exc}"
            ) from exc
        except stripe.SignatureVerificationError as exc:
            raise WebhookVerificationError(
                f"A assinatura do webhook do Stripe não confere: {exc}. Causa "
                f"mais comum: o corpo foi reserializado antes da verificação, "
                f"ou o webhook_secret é de outro endpoint."
            ) from exc
        return dict(event)


class StripeCheckoutProvider(BaseCheckoutProvider):
    """Checkout Sessions do Stripe."""

    name = Provider.STRIPE
    state_class = StripeCheckoutState

    STATUS_MAP = STATUS_MAP
    EVENT_MAP = EVENT_MAP

    CAPABILITIES = {
        Capability.SUBSCRIPTION,
        Capability.CANCEL,
        Capability.EXPIRATION,
        Capability.CUSTOMER_PREFILL,
        Capability.PROVIDER_CATALOG,
    }

    SUPPORTED_PAYMENT_METHODS = {
        PaymentMethod.CARD,
        PaymentMethod.PIX,
        PaymentMethod.BOLETO,
    }

    SUPPORTED_CYCLES = set(CYCLES)

    default_currency = "BRL"

    #: O Stripe recusa validade fora desta janela.
    MIN_EXPIRATION_SECONDS = 30 * 60
    MAX_EXPIRATION_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        api_key: str,
        webhook_secret: str = "",
        sandbox: bool = True,
        timeout: int = 20,
        **kwargs: Any,
    ) -> None:
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.sandbox = sandbox
        self.timeout = timeout
        self.auth = TokenAuth(
            token=api_key,
            expected_prefix="sk_test_" if sandbox else "sk_live_",
            sandbox=sandbox,
        )
        self.webhook_auth = StripeWebhookAuth(
            provider=self.name,
            secret=webhook_secret,
        )

    # --- infraestrutura ----------------------------------------------------

    def _call(self, func, *args: Any, **kwargs: Any):
        """Executa uma chamada do SDK traduzindo os erros para os nossos.

        A divisão temporário/permanente segue a taxonomia do Stripe: erro de
        conexão e rate limit valem retry; requisição inválida e falha de
        autenticação, não.
        """
        stripe = _import_stripe()
        kwargs.setdefault("api_key", self.api_key)
        try:
            return func(*args, **kwargs)
        except (stripe.APIConnectionError, stripe.RateLimitError) as exc:
            raise ProviderTemporaryError(str(exc)) from exc
        except stripe.InvalidRequestError as exc:
            message = str(exc)
            if "No such checkout.session" in message:
                raise CheckoutNotFound(
                    message, code=getattr(exc, "http_status", None)
                ) from exc
            raise ProviderPermanentError(
                message,
                code=getattr(exc, "http_status", None),
                gateway_message=message,
            ) from exc
        except stripe.AuthenticationError as exc:
            raise ProviderPermanentError(
                f"O Stripe recusou a credencial: {exc}",
                code=getattr(exc, "http_status", None),
            ) from exc
        except stripe.APIError as exc:
            status = getattr(exc, "http_status", None) or 500
            error_class = (
                ProviderTemporaryError if status >= 500 else ProviderPermanentError
            )
            raise error_class(str(exc), code=status) from exc

    # --- tradução ----------------------------------------------------------

    def map_status(self, gateway_status: str) -> CheckoutStatus:
        """Aceita a chave composta ``status/payment_status``."""
        return super().map_status(gateway_status)

    def _status_key(self, raw: Mapping) -> str:
        return f"{raw.get('status')}/{raw.get('payment_status')}"

    def _to_data(self, raw: Mapping) -> CheckoutData:
        details = raw.get("customer_details") or {}
        expires_at = raw.get("expires_at")
        return CheckoutData(
            external_id=raw["id"],
            status=self.map_status(self._status_key(raw)),
            provider=self.name,
            mode=CheckoutMode(raw.get("mode") or CheckoutMode.PAYMENT),
            url=raw.get("url"),
            amount_total=raw.get("amount_total") or 0,
            currency=(raw.get("currency") or self.default_currency).upper(),
            customer=Customer(
                name=details.get("name"),
                email=details.get("email"),
                phone=details.get("phone"),
                tax_id=self._tax_id(details),
                provider_customer_id=raw.get("customer"),
            ),
            reference_id=raw.get("client_reference_id"),
            expires_at=(
                datetime.fromtimestamp(expires_at, tz=UTC) if expires_at else None
            ),
            raw=dict(raw),
        )

    @staticmethod
    def _tax_id(details: Mapping) -> str | None:
        """Extrai CPF/CNPJ dos ``tax_ids`` do Stripe, se houver."""
        for entry in details.get("tax_ids") or []:
            if entry.get("type") in ("br_cpf", "br_cnpj"):
                return entry.get("value")
        return None

    # --- operações ---------------------------------------------------------

    def _line_item(self, item, request: CheckoutRequest) -> dict[str, Any]:
        if item.provider_price_id:
            return {"price": item.provider_price_id, "quantity": item.quantity}

        product_data: dict[str, Any] = {"name": item.name}
        if item.description:
            product_data["description"] = item.description
        if item.image_url:
            product_data["images"] = [item.image_url]

        price_data: dict[str, Any] = {
            "currency": request.currency.lower(),
            "unit_amount": item.amount,
            "product_data": product_data,
        }
        if request.mode == CheckoutMode.SUBSCRIPTION and request.recurrence:
            interval, interval_count = CYCLES[BillingCycle(request.recurrence.cycle)]
            price_data["recurring"] = {
                "interval": interval,
                "interval_count": interval_count,
            }
        return {"price_data": price_data, "quantity": item.quantity}

    def _create_checkout(self, request: CheckoutRequest) -> CheckoutData:
        stripe = _import_stripe()

        methods = [PAYMENT_METHODS[item] for item in request.payment_methods]
        if request.mode == CheckoutMode.SUBSCRIPTION and methods != ["card"]:
            raise ValidationError(
                "O Stripe só aceita cartão em assinatura; pix e boleto não são "
                "recorrentes na plataforma. Use payment_methods=[PaymentMethod.CARD]."
            )

        params: dict[str, Any] = {
            "mode": str(request.mode),
            "line_items": [self._line_item(item, request) for item in request.items],
            "success_url": request.success_url,
            "payment_method_types": methods,
        }
        if request.cancel_url:
            params["cancel_url"] = request.cancel_url
        if request.reference_id:
            params["client_reference_id"] = request.reference_id
        if request.metadata:
            params["metadata"] = request.metadata
        if request.customer:
            if request.customer.provider_customer_id:
                params["customer"] = request.customer.provider_customer_id
            elif request.customer.email:
                params["customer_email"] = request.customer.email
        if request.expires_at:
            params["expires_at"] = self._expires_at(request.expires_at)

        params.update(request.provider_options)

        raw = self._call(stripe.checkout.Session.create, **params)
        return self._to_data(raw)

    def _expires_at(self, expires_at: datetime) -> int:
        """Converte para timestamp, recusando fora da janela aceita pelo Stripe."""
        from django.utils import timezone

        delta = (expires_at - timezone.now()).total_seconds()
        if delta < self.MIN_EXPIRATION_SECONDS:
            raise ValidationError(
                f"O Stripe exige validade de no mínimo 30 minutos; "
                f"recebi {int(delta)}s."
            )
        if delta > self.MAX_EXPIRATION_SECONDS:
            raise ValidationError(
                f"O Stripe exige validade de no máximo 24 horas; "
                f"recebi {int(delta)}s."
            )
        return int(expires_at.timestamp())

    def _retrieve_checkout(self, external_id: str) -> CheckoutData:
        stripe = _import_stripe()
        raw = self._call(stripe.checkout.Session.retrieve, external_id)
        return self._to_data(raw)

    def _cancel_checkout(self, external_id: str) -> CheckoutData:
        """No Stripe, cancelar uma Checkout Session é expirá-la."""
        stripe = _import_stripe()
        raw = self._call(stripe.checkout.Session.expire, external_id)
        return self._to_data(raw)

    def _parse_webhook(self, payload: dict[str, Any]) -> WebhookPayload:
        event_type = payload.get("type", "")
        session = (payload.get("data") or {}).get("object") or {}

        data = None
        status = None
        if session.get("object") == "checkout.session":
            data = self._to_data(session)
            status = data.status

        return WebhookPayload(
            provider=self.name,
            event_id=str(payload.get("id", "")),
            event_type=event_type,
            type=self.map_event(event_type),
            external_id=session.get("id"),
            reference_id=session.get("client_reference_id"),
            status=status,
            data=data,
            raw=payload,
        )
