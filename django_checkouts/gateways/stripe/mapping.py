"""Mapeamento estrito entre Checkout Sessions e tipos normalizados."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from datetime import datetime
from typing import Any

from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import Gateway
from django_checkouts.enums import PaymentMethod
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.gateways.stripe.options import StripeCheckoutOptions
from django_checkouts.types import CatalogPrice
from django_checkouts.types import Checkout
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import Customer

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

STATUS_MAP: dict[tuple[str, str], CheckoutStatus] = {
    ("open", "unpaid"): CheckoutStatus.PENDING,
    ("open", "no_payment_required"): CheckoutStatus.PENDING,
    ("complete", "paid"): CheckoutStatus.PAID,
    ("complete", "no_payment_required"): CheckoutStatus.PAID,
    ("complete", "unpaid"): CheckoutStatus.PENDING,
    ("expired", "unpaid"): CheckoutStatus.EXPIRED,
    ("expired", "no_payment_required"): CheckoutStatus.EXPIRED,
    ("expired", "paid"): CheckoutStatus.PAID,
}

MODE_MAP: dict[str, CheckoutMode] = {
    "payment": CheckoutMode.PAYMENT,
    "subscription": CheckoutMode.SUBSCRIPTION,
}


def build_checkout_params(request: CheckoutCreate) -> dict[str, Any]:
    """Traduz somente os campos portáveis e options tipadas para o SDK."""
    params: dict[str, Any] = {
        "mode": request.mode.value,
        "line_items": [_line_item(item, request) for item in request.items],
        "success_url": request.success_url,
        "payment_method_types": [
            PAYMENT_METHODS[method] for method in request.payment_methods
        ],
    }
    if request.cancel_url is not None:
        params["cancel_url"] = request.cancel_url
    if request.reference_id is not None:
        params["client_reference_id"] = request.reference_id
    if request.expires_at is not None:
        params["expires_at"] = int(request.expires_at.timestamp())
    if request.metadata:
        params["metadata"] = dict(request.metadata)
    if request.customer is not None:
        if request.customer.external_id:
            params["customer"] = request.customer.external_id
        elif request.customer.email:
            params["customer_email"] = request.customer.email

    options = request.gateway_options
    if isinstance(options, StripeCheckoutOptions):
        if options.allow_promotion_codes:
            params["allow_promotion_codes"] = True
        if options.automatic_tax:
            params["automatic_tax"] = {"enabled": True}
        if options.billing_address_required:
            params["billing_address_collection"] = "required"
    return params


def checkout_from_stripe(raw: object, *, variant: str) -> Checkout:
    """Normaliza uma sessão, recusando estados financeiros desconhecidos."""
    raw = _response_mapping(raw, variant=variant)

    external_id = _optional_string(raw.get("id"), variant, "id")
    if not external_id:
        raise _protocol_error(variant, "O checkout do Stripe não informou id.")

    status_key = (raw.get("status"), raw.get("payment_status"))
    try:
        status = STATUS_MAP[status_key]  # type: ignore[index]
    except (KeyError, TypeError):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou um estado financeiro desconhecido.",
        ) from None

    try:
        mode = MODE_MAP[raw.get("mode")]  # type: ignore[index]
    except (KeyError, TypeError):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou um modo desconhecido.",
        ) from None

    amount_total = raw.get("amount_total")
    if amount_total is None:
        amount_total = 0
    if isinstance(amount_total, bool) or not isinstance(amount_total, int):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou amount_total inválido.",
        )

    currency = raw.get("currency")
    if not isinstance(currency, str):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou currency inválida.",
        )

    try:
        return Checkout(
            external_id=external_id,
            gateway=Gateway.STRIPE,
            variant=variant,
            status=status,
            mode=mode,
            url=_optional_string(raw.get("url"), variant, "url"),
            amount_total=amount_total,
            currency=currency.upper(),
            customer=_customer_from_stripe(raw, variant=variant),
            reference_id=_optional_string(
                raw.get("client_reference_id"), variant, "client_reference_id"
            ),
            subscription_id=_resource_id(
                raw.get("subscription"), variant, "subscription"
            ),
            expires_at=_timestamp(raw.get("expires_at"), variant, "expires_at"),
            created_at=_timestamp(raw.get("created"), variant, "created"),
            raw=dict(raw),
        )
    except (TypeError, ValueError) as error:
        raise _protocol_error(
            variant,
            "O Stripe devolveu campos incompatíveis no checkout.",
        ) from error


def _response_mapping(raw: object, *, variant: str) -> Mapping[str, object]:
    if isinstance(raw, Mapping):
        return raw

    to_dict = getattr(raw, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
        except Exception as error:
            raise _protocol_error(
                variant, "O Stripe devolveu um checkout inválido."
            ) from error
        if isinstance(converted, Mapping):
            return dict(converted)

    raise _protocol_error(variant, "O Stripe devolveu um checkout inválido.")


def _line_item(item: CheckoutItem, request: CheckoutCreate) -> dict[str, Any]:
    if isinstance(item.price, CatalogPrice):
        return {"price": item.price.external_id, "quantity": item.quantity}

    price = item.price
    product_data: dict[str, Any] = {"name": price.name}
    if price.description is not None:
        product_data["description"] = price.description
    if price.image_url is not None:
        product_data["images"] = [price.image_url]

    price_data: dict[str, Any] = {
        "currency": price.currency.lower(),
        "unit_amount": price.unit_amount,
        "product_data": product_data,
    }
    if request.mode == CheckoutMode.SUBSCRIPTION:
        recurrence = request.recurrence
        if recurrence is None:  # protegido pela validação intrínseca do DTO
            raise ValueError("recurrence ausente para preço inline recorrente")
        interval, interval_count = CYCLES[recurrence.cycle]
        price_data["recurring"] = {
            "interval": interval,
            "interval_count": interval_count,
        }
    return {"price_data": price_data, "quantity": item.quantity}


def _customer_from_stripe(
    raw: Mapping[str, object], *, variant: str
) -> Customer | None:
    details = raw.get("customer_details")
    if details is None:
        details = {}
    if not isinstance(details, Mapping):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou customer_details inválido.",
        )

    external_id = _resource_id(raw.get("customer"), variant, "customer")
    customer = Customer(
        name=_optional_string(details.get("name"), variant, "customer.name"),
        email=_optional_string(details.get("email"), variant, "customer.email"),
        phone=_optional_string(details.get("phone"), variant, "customer.phone"),
        tax_id=_tax_id(details, variant=variant),
        external_id=external_id,
    )
    values = (
        customer.name,
        customer.email,
        customer.phone,
        customer.tax_id,
        customer.external_id,
    )
    return customer if any(values) else None


def _tax_id(details: Mapping[str, object], *, variant: str) -> str | None:
    tax_ids = details.get("tax_ids") or ()
    if not isinstance(tax_ids, (list, tuple)):
        raise _protocol_error(
            variant,
            "O checkout do Stripe informou customer.tax_ids inválido.",
        )
    for entry in tax_ids:
        if not isinstance(entry, Mapping):
            raise _protocol_error(
                variant,
                "O checkout do Stripe informou um tax_id inválido.",
            )
        if entry.get("type") in {"br_cpf", "br_cnpj"}:
            return _optional_string(entry.get("value"), variant, "customer.tax_id")
    return None


def _resource_id(value: object, variant: str, field_name: str) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("id")
    return _optional_string(value, variant, field_name)


def _optional_string(value: object, variant: str, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _protocol_error(
            variant,
            f"O checkout do Stripe informou {field_name} inválido.",
        )
    return value


def _timestamp(
    value: object, variant: str, field_name: str
) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _protocol_error(
            variant,
            f"O checkout do Stripe informou {field_name} inválido.",
        )
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise _protocol_error(
            variant,
            f"O checkout do Stripe informou {field_name} inválido.",
        ) from error


def _protocol_error(variant: str, message: str) -> GatewayProtocolError:
    return GatewayProtocolError(
        message,
        gateway=Gateway.STRIPE,
        variant=variant,
    )


__all__ = [
    "CYCLES",
    "MODE_MAP",
    "PAYMENT_METHODS",
    "STATUS_MAP",
    "build_checkout_params",
    "checkout_from_stripe",
]
