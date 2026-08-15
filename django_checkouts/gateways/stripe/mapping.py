"""Mapeamento estrito entre respostas do Stripe e tipos normalizados."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from typing import Any

from django_checkouts.enums import BillingCycle
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import Gateway
from django_checkouts.enums import InvoiceReason
from django_checkouts.enums import InvoiceStatus
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import ProrationBehavior
from django_checkouts.enums import SubscriptionStatus
from django_checkouts.exceptions import GatewayProtocolError
from django_checkouts.gateways.stripe.options import StripeCheckoutOptions
from django_checkouts.types import AddItem
from django_checkouts.types import CatalogPrice
from django_checkouts.types import Checkout
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import CheckoutItem
from django_checkouts.types import Customer
from django_checkouts.types import InlinePrice
from django_checkouts.types import Invoice
from django_checkouts.types import InvoiceLine
from django_checkouts.types import RemoveItem
from django_checkouts.types import ReplacePrice
from django_checkouts.types import SetQuantity
from django_checkouts.types import Subscription
from django_checkouts.types import SubscriptionChange
from django_checkouts.types import SubscriptionItem

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

SUBSCRIPTION_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "incomplete": SubscriptionStatus.INCOMPLETE,
    "incomplete_expired": SubscriptionStatus.EXPIRED,
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "paused": SubscriptionStatus.PAUSED,
    "unpaid": SubscriptionStatus.UNPAID,
    "canceled": SubscriptionStatus.CANCELED,
}

INVOICE_STATUS_MAP: dict[str, InvoiceStatus] = {
    "draft": InvoiceStatus.DRAFT,
    "open": InvoiceStatus.OPEN,
    "paid": InvoiceStatus.PAID,
    "void": InvoiceStatus.VOID,
    "uncollectible": InvoiceStatus.UNCOLLECTIBLE,
}

INVOICE_REASON_MAP: dict[str, InvoiceReason] = {
    "subscription_create": InvoiceReason.INITIAL_SUBSCRIPTION,
    "subscription_cycle": InvoiceReason.RENEWAL,
    "subscription_update": InvoiceReason.SUBSCRIPTION_UPDATE,
    "manual": InvoiceReason.MANUAL,
}

PRORATION_MAP: dict[ProrationBehavior, str] = {
    ProrationBehavior.CREATE_PRORATIONS: "create_prorations",
    ProrationBehavior.INVOICE_IMMEDIATELY: "always_invoice",
    ProrationBehavior.NONE: "none",
}

STRIPE_CYCLES: dict[tuple[str, int], BillingCycle] = {
    stripe_cycle: cycle for cycle, stripe_cycle in CYCLES.items()
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


def build_subscription_change_items(
    changes: tuple[SubscriptionChange, ...],
) -> list[dict[str, Any]]:
    """Traduz mudanças absolutas para os itens aceitos pelo Stripe."""
    items: list[dict[str, Any]] = []
    for change in changes:
        if isinstance(change, SetQuantity):
            items.append({"id": change.item_id, "quantity": change.quantity})
        elif isinstance(change, ReplacePrice):
            item = {"id": change.item_id, **_subscription_price(change.price)}
            if change.quantity is not None:
                item["quantity"] = change.quantity
            items.append(item)
        elif isinstance(change, AddItem):
            items.append(
                {**_subscription_price(change.price), "quantity": change.quantity}
            )
        elif isinstance(change, RemoveItem):
            items.append({"id": change.item_id, "deleted": True})
    return items


def subscription_from_stripe(raw: object, *, variant: str) -> Subscription:
    """Normaliza uma assinatura, recusando status e quantidades desconhecidos."""
    response = _response_mapping(raw, variant=variant)
    external_id = _required_string(response.get("id"), variant, "subscription.id")
    try:
        status = SUBSCRIPTION_STATUS_MAP[response.get("status")]  # type: ignore[index]
    except (KeyError, TypeError):
        raise _protocol_error(
            variant,
            "A assinatura do Stripe informou um estado financeiro desconhecido.",
        ) from None

    items = tuple(
        _subscription_item_from_stripe(item, variant=variant)
        for item in _list_data(response.get("items"), variant, "subscription.items")
    )
    metadata = _metadata(response.get("metadata"), variant, "subscription.metadata")
    try:
        return Subscription(
            external_id=external_id,
            gateway=Gateway.STRIPE,
            variant=variant,
            status=status,
            customer_id=_resource_id(
                response.get("customer"), variant, "subscription.customer"
            ),
            items=items,
            current_period_start=_timestamp(
                response.get("current_period_start"),
                variant,
                "subscription.current_period_start",
            ),
            current_period_end=_timestamp(
                response.get("current_period_end"),
                variant,
                "subscription.current_period_end",
            ),
            trial_end=_timestamp(
                response.get("trial_end"), variant, "subscription.trial_end"
            ),
            cancel_at=_timestamp(
                response.get("cancel_at"), variant, "subscription.cancel_at"
            ),
            canceled_at=_timestamp(
                response.get("canceled_at"), variant, "subscription.canceled_at"
            ),
            ended_at=_timestamp(
                response.get("ended_at"), variant, "subscription.ended_at"
            ),
            latest_invoice_id=_resource_id(
                response.get("latest_invoice"),
                variant,
                "subscription.latest_invoice",
            ),
            reference_id=metadata.get("reference_id"),
            metadata=metadata,
            raw=dict(response),
        )
    except (TypeError, ValueError) as error:
        raise _protocol_error(
            variant,
            "O Stripe devolveu campos incompatíveis na assinatura.",
        ) from error


def invoice_from_stripe(raw: object, *, variant: str) -> Invoice:
    """Normaliza uma fatura, recusando status e quantidades desconhecidos."""
    response = _response_mapping(raw, variant=variant)
    external_id = _required_string(response.get("id"), variant, "invoice.id")
    try:
        status = INVOICE_STATUS_MAP[response.get("status")]  # type: ignore[index]
    except (KeyError, TypeError):
        raise _protocol_error(
            variant,
            "A fatura do Stripe informou um estado financeiro desconhecido.",
        ) from None

    metadata = _metadata(response.get("metadata"), variant, "invoice.metadata")
    billing_reason = response.get("billing_reason")
    reason = (
        INVOICE_REASON_MAP.get(billing_reason, InvoiceReason.UNKNOWN)
        if isinstance(billing_reason, str)
        else InvoiceReason.UNKNOWN
    )
    transitions = _optional_mapping(
        response.get("status_transitions"),
        variant,
        "invoice.status_transitions",
    )
    try:
        return Invoice(
            external_id=external_id,
            gateway=Gateway.STRIPE,
            variant=variant,
            status=status,
            reason=reason,
            subscription_id=_invoice_subscription_id(response, variant=variant),
            customer_id=_resource_id(
                response.get("customer"), variant, "invoice.customer"
            ),
            amount_due=_required_integer(
                response.get("amount_due"), variant, "invoice.amount_due"
            ),
            amount_paid=_required_integer(
                response.get("amount_paid"), variant, "invoice.amount_paid"
            ),
            amount_remaining=_required_integer(
                response.get("amount_remaining"),
                variant,
                "invoice.amount_remaining",
            ),
            currency=_required_string(
                response.get("currency"), variant, "invoice.currency"
            ),
            lines=tuple(
                _invoice_line_from_stripe(line, variant=variant)
                for line in _list_data(
                    response.get("lines"), variant, "invoice.lines"
                )
            ),
            due_at=_timestamp(
                response.get("due_date"), variant, "invoice.due_date"
            ),
            paid_at=_timestamp(
                transitions.get("paid_at"), variant, "invoice.paid_at"
            ),
            next_payment_attempt_at=_timestamp(
                response.get("next_payment_attempt"),
                variant,
                "invoice.next_payment_attempt",
            ),
            attempt_count=_required_integer(
                response.get("attempt_count"), variant, "invoice.attempt_count"
            ),
            hosted_url=_optional_string(
                response.get("hosted_invoice_url"),
                variant,
                "invoice.hosted_invoice_url",
            ),
            reference_id=metadata.get("reference_id"),
            raw=dict(response),
        )
    except (TypeError, ValueError) as error:
        raise _protocol_error(
            variant,
            "O Stripe devolveu campos incompatíveis na fatura.",
        ) from error


def scheduled_subscription_phases(
    subscription: Subscription,
    schedule: object,
    changes: tuple[SubscriptionChange, ...],
    *,
    proration: ProrationBehavior,
    metadata: Mapping[str, str] | None,
    variant: str,
) -> list[dict[str, Any]]:
    """Preserva a fase atual e aplica mudanças ao conjunto do próximo ciclo."""
    schedule_response = _response_mapping(schedule, variant=variant)
    phases_value = schedule_response.get("phases")
    if not isinstance(phases_value, Sequence) or isinstance(
        phases_value, (str, bytes, bytearray)
    ):
        raise _protocol_error(
            variant, "O Stripe devolveu fases inválidas para a assinatura."
        )
    phases = [
        _phase_for_update(phase, variant=variant) for phase in phases_value
    ]
    if not phases:
        raise _protocol_error(
            variant, "O Stripe não devolveu a fase atual da assinatura."
        )
    if subscription.current_period_end is None:
        raise _protocol_error(
            variant, "O Stripe não informou o fim do período da assinatura."
        )
    billing_cycle = next(
        (
            item.billing_cycle
            for item in subscription.items
            if item.billing_cycle is not None
        ),
        None,
    )
    if billing_cycle is None:
        raise _protocol_error(
            variant, "O Stripe não informou o ciclo atual da assinatura."
        )
    interval, interval_count = CYCLES[billing_cycle]

    next_items = [
        {
            "item_id": item.external_id,
            "price": item.price_id,
            "quantity": item.quantity,
        }
        for item in subscription.items
    ]
    _apply_scheduled_changes(next_items, changes, variant=variant)
    next_phase: dict[str, Any] = {
        "start_date": int(subscription.current_period_end.timestamp()),
        "duration": {
            "interval": interval,
            "interval_count": interval_count,
        },
        "items": [
            {key: value for key, value in item.items() if key != "item_id"}
            for item in next_items
        ],
        "proration_behavior": PRORATION_MAP[proration],
    }
    if metadata is not None:
        next_phase["metadata"] = dict(metadata)
    return [*phases, next_phase]


def _subscription_price(price: CatalogPrice | InlinePrice) -> dict[str, Any]:
    if isinstance(price, CatalogPrice):
        return {"price": price.external_id}

    product_data: dict[str, Any] = {"name": price.name}
    if price.description is not None:
        product_data["description"] = price.description
    if price.image_url is not None:
        product_data["images"] = [price.image_url]
    return {
        "price_data": {
            "currency": price.currency.lower(),
            "unit_amount": price.unit_amount,
            "product_data": product_data,
        }
    }


def _subscription_item_from_stripe(
    raw: object, *, variant: str
) -> SubscriptionItem:
    if not isinstance(raw, Mapping):
        raise _protocol_error(variant, "O Stripe devolveu um item inválido.")
    price = _optional_mapping(
        raw.get("price"), variant, "subscription.item.price"
    )
    recurring = _optional_mapping(
        price.get("recurring"), variant, "subscription.item.price.recurring"
    )
    cycle = None
    if recurring:
        interval = recurring.get("interval")
        interval_count = recurring.get("interval_count", 1)
        if isinstance(interval_count, bool) or not isinstance(interval_count, int):
            raise _protocol_error(
                variant, "O Stripe informou interval_count inválido."
            )
        if isinstance(interval, str):
            cycle = STRIPE_CYCLES.get((interval, interval_count))

    unit_amount = price.get("unit_amount")
    if unit_amount is not None:
        unit_amount = _required_integer(
            unit_amount, variant, "subscription.item.price.unit_amount"
        )
    currency = price.get("currency")
    try:
        return SubscriptionItem(
            external_id=_required_string(
                raw.get("id"), variant, "subscription.item.id"
            ),
            price_id=_resource_id(
                raw.get("price"), variant, "subscription.item.price"
            ),
            quantity=_required_quantity(
                raw.get("quantity"), variant, "subscription.item.quantity"
            ),
            unit_amount=unit_amount,
            currency=(
                _required_string(
                    currency, variant, "subscription.item.price.currency"
                )
                if currency is not None
                else None
            ),
            billing_cycle=cycle,
            raw=dict(raw),
        )
    except (TypeError, ValueError) as error:
        raise _protocol_error(
            variant, "O Stripe devolveu um item de assinatura incompatível."
        ) from error


def _invoice_line_from_stripe(raw: object, *, variant: str) -> InvoiceLine:
    if not isinstance(raw, Mapping):
        raise _protocol_error(variant, "O Stripe devolveu uma linha inválida.")
    price_value = raw.get("price")
    if price_value is None:
        pricing = _optional_mapping(
            raw.get("pricing"), variant, "invoice.line.pricing"
        )
        price_details = _optional_mapping(
            pricing.get("price_details"),
            variant,
            "invoice.line.pricing.price_details",
        )
        price_value = price_details.get("price")
    price = (
        price_value
        if isinstance(price_value, Mapping)
        else {}
    )
    period = _optional_mapping(
        raw.get("period"), variant, "invoice.line.period"
    )
    unit_amount = price.get("unit_amount")
    if unit_amount is not None:
        unit_amount = _required_integer(
            unit_amount, variant, "invoice.line.price.unit_amount"
        )
    try:
        return InvoiceLine(
            external_id=_required_string(raw.get("id"), variant, "invoice.line.id"),
            description=_optional_string(
                raw.get("description"), variant, "invoice.line.description"
            ),
            quantity=_required_quantity(
                raw.get("quantity"), variant, "invoice.line.quantity"
            ),
            unit_amount=unit_amount,
            amount=_required_integer(
                raw.get("amount"), variant, "invoice.line.amount"
            ),
            currency=_required_string(
                raw.get("currency"), variant, "invoice.line.currency"
            ),
            subscription_item_id=_invoice_line_subscription_item_id(
                raw, variant=variant
            ),
            period_start=_timestamp(
                period.get("start"), variant, "invoice.line.period.start"
            ),
            period_end=_timestamp(
                period.get("end"), variant, "invoice.line.period.end"
            ),
            raw=dict(raw),
        )
    except (TypeError, ValueError) as error:
        raise _protocol_error(
            variant, "O Stripe devolveu uma linha de fatura incompatível."
        ) from error


def _invoice_subscription_id(
    raw: Mapping[str, object], *, variant: str
) -> str | None:
    direct = _resource_id(raw.get("subscription"), variant, "invoice.subscription")
    if direct is not None:
        return direct
    parent = _optional_mapping(raw.get("parent"), variant, "invoice.parent")
    details = _optional_mapping(
        parent.get("subscription_details"),
        variant,
        "invoice.parent.subscription_details",
    )
    return _resource_id(
        details.get("subscription"), variant, "invoice.subscription"
    )


def _invoice_line_subscription_item_id(
    raw: Mapping[str, object], *, variant: str
) -> str | None:
    direct = _resource_id(
        raw.get("subscription_item"), variant, "invoice.line.subscription_item"
    )
    if direct is not None:
        return direct
    parent = _optional_mapping(raw.get("parent"), variant, "invoice.line.parent")
    details = _optional_mapping(
        parent.get("subscription_item_details"),
        variant,
        "invoice.line.parent.subscription_item_details",
    )
    return _resource_id(
        details.get("subscription_item"),
        variant,
        "invoice.line.subscription_item",
    )


def _phase_for_update(raw: object, *, variant: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _protocol_error(variant, "O Stripe devolveu uma fase inválida.")
    phase: dict[str, Any] = {}
    for field_name in ("start_date", "end_date", "metadata"):
        value = raw.get(field_name)
        if value is not None:
            phase[field_name] = value
    items = raw.get("items")
    if not isinstance(items, Sequence) or isinstance(
        items, (str, bytes, bytearray)
    ):
        raise _protocol_error(
            variant, "O Stripe devolveu itens inválidos na fase atual."
        )
    phase["items"] = [
        _phase_item_for_update(item, variant=variant) for item in items
    ]
    return phase


def _phase_item_for_update(raw: object, *, variant: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _protocol_error(
            variant, "O Stripe devolveu um item inválido na fase atual."
        )
    return {
        "price": _required_string(
            _resource_id(raw.get("price"), variant, "schedule.phase.item.price"),
            variant,
            "schedule.phase.item.price",
        ),
        "quantity": _required_quantity(
            raw.get("quantity"), variant, "schedule.phase.item.quantity"
        ),
    }


def _apply_scheduled_changes(
    items: list[dict[str, Any]],
    changes: tuple[SubscriptionChange, ...],
    *,
    variant: str,
) -> None:
    by_id = {item["item_id"]: item for item in items}
    for change in changes:
        if isinstance(change, AddItem):
            items.append(
                {
                    "item_id": None,
                    **_subscription_price(change.price),
                    "quantity": change.quantity,
                }
            )
            continue

        item = by_id.get(change.item_id)
        if item is None:
            raise _protocol_error(
                variant,
                "A alteração referencia um item ausente na assinatura do Stripe.",
            )
        if isinstance(change, SetQuantity):
            item["quantity"] = change.quantity
        elif isinstance(change, ReplacePrice):
            item.pop("price", None)
            item.update(_subscription_price(change.price))
            if change.quantity is not None:
                item["quantity"] = change.quantity
        elif isinstance(change, RemoveItem):
            items.remove(item)


def _list_data(
    value: object, variant: str, field_name: str
) -> Sequence[object]:
    mapping = _optional_mapping(value, variant, field_name)
    data = mapping.get("data")
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        raise _protocol_error(variant, f"O Stripe informou {field_name} inválido.")
    return data


def _metadata(value: object, variant: str, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in value.items()
    ):
        raise _protocol_error(variant, f"O Stripe informou {field_name} inválido.")
    return dict(value)


def _optional_mapping(
    value: object, variant: str, field_name: str
) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _protocol_error(variant, f"O Stripe informou {field_name} inválido.")
    return value


def _required_string(value: object, variant: str, field_name: str) -> str:
    result = _optional_string(value, variant, field_name)
    if not result:
        raise _protocol_error(variant, f"O Stripe não informou {field_name}.")
    return result


def _required_integer(value: object, variant: str, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _protocol_error(variant, f"O Stripe informou {field_name} inválido.")
    return value


def _required_quantity(value: object, variant: str, field_name: str) -> int:
    quantity = _required_integer(value, variant, field_name)
    if quantity <= 0:
        raise _protocol_error(variant, f"O Stripe informou {field_name} inválido.")
    return quantity


def _response_mapping(raw: object, *, variant: str) -> Mapping[str, object]:
    converted = _plain_response_value(raw, variant=variant)
    if isinstance(converted, dict):
        return converted

    raise _protocol_error(variant, "O Stripe devolveu um checkout inválido.")


def _plain_response_value(value: object, *, variant: str) -> object:
    """Remove containers e objetos do SDK da resposta do Stripe."""
    if isinstance(value, Mapping):
        return {
            key: _plain_response_value(item, variant=variant)
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_plain_response_value(item, variant=variant) for item in value]

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _plain_response_value(to_dict(), variant=variant)
        except Exception as error:
            raise _protocol_error(
                variant, "O Stripe devolveu um checkout inválido."
            ) from error

    return value


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
    "INVOICE_REASON_MAP",
    "INVOICE_STATUS_MAP",
    "MODE_MAP",
    "PAYMENT_METHODS",
    "PRORATION_MAP",
    "STATUS_MAP",
    "SUBSCRIPTION_STATUS_MAP",
    "build_checkout_params",
    "build_subscription_change_items",
    "checkout_from_stripe",
    "invoice_from_stripe",
    "scheduled_subscription_phases",
    "subscription_from_stripe",
]
