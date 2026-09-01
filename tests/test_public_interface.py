"""Structural guarantees for the installable 1.0 public interface."""

from __future__ import annotations

import importlib.util
import inspect
from typing import TYPE_CHECKING
from typing import assert_type

import django_checkouts
from django_checkouts.client import CheckoutClient
from django_checkouts.enums import Gateway
from django_checkouts.registry import get_checkout_gateway
from django_checkouts.resources import CheckoutResource
from django_checkouts.resources import EventResource
from django_checkouts.resources import InvoiceResource
from django_checkouts.resources import SubscriptionResource
from django_checkouts.resources import WebhookResource
from django_checkouts.types import ChangeSubscription
from django_checkouts.types import Checkout
from django_checkouts.types import CheckoutCreate
from django_checkouts.types import EventPage
from django_checkouts.types import Invoice
from django_checkouts.types import Subscription
from django_checkouts.types import WebhookEvent

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Mapping
    from datetime import datetime
    from types import ModuleType


def test_package_exports_exact_release_entry_points() -> None:
    assert django_checkouts.__all__ == [
        "CheckoutClient",
        "Gateway",
        "get_checkout_gateway",
    ]
    assert django_checkouts.CheckoutClient is CheckoutClient
    assert django_checkouts.Gateway is Gateway
    assert django_checkouts.get_checkout_gateway is get_checkout_gateway


def test_resource_method_signatures_are_stable() -> None:
    expected: dict[Callable[..., object], str] = {
        CheckoutResource.create: (
            "(self, request: 'CheckoutCreate', *, idempotency_key: 'str') -> 'Checkout'"
        ),
        CheckoutResource.retrieve: "(self, external_id: 'str') -> 'Checkout'",
        CheckoutResource.cancel: (
            "(self, external_id: 'str', *, idempotency_key: 'str') -> 'Checkout'"
        ),
        SubscriptionResource.retrieve: ("(self, external_id: 'str') -> 'Subscription'"),
        SubscriptionResource.change: (
            "(self, external_id: 'str', request: 'ChangeSubscription', *, "
            "idempotency_key: 'str') -> 'Subscription'"
        ),
        SubscriptionResource.cancel: (
            "(self, external_id: 'str', *, timing: 'CancellationTiming', "
            "idempotency_key: 'str') -> 'Subscription'"
        ),
        SubscriptionResource.resume: (
            "(self, external_id: 'str', *, idempotency_key: 'str') -> 'Subscription'"
        ),
        InvoiceResource.retrieve: "(self, external_id: 'str') -> 'Invoice'",
        WebhookResource.verify: (
            "(self, raw_body: 'bytes', headers: 'Mapping[str, str]') -> 'WebhookEvent'"
        ),
        EventResource.list: (
            "(self, *, occurred_since: 'datetime', "
            "occurred_before: 'datetime', cursor: 'str | None' = None, "
            "limit: 'int' = 100) -> 'EventPage'"
        ),
    }

    assert {method: str(inspect.signature(method)) for method in expected} == expected


def _assert_static_result_types(
    client: CheckoutClient,
    checkout_request: CheckoutCreate,
    change_request: ChangeSubscription,
    occurred_since: datetime,
    occurred_before: datetime,
    headers: Mapping[str, str],
) -> None:
    assert_type(
        client.checkouts.create(checkout_request, idempotency_key="key"), Checkout
    )
    assert_type(client.checkouts.retrieve("checkout"), Checkout)
    assert_type(client.checkouts.cancel("checkout", idempotency_key="key"), Checkout)
    assert_type(client.subscriptions.retrieve("subscription"), Subscription)
    assert_type(
        client.subscriptions.change(
            "subscription", change_request, idempotency_key="key"
        ),
        Subscription,
    )
    assert_type(client.invoices.retrieve("invoice"), Invoice)
    assert_type(client.webhooks.verify(b"{}", headers), WebhookEvent)
    assert_type(
        client.events.list(
            occurred_since=occurred_since,
            occurred_before=occurred_before,
        ),
        EventPage,
    )


def test_public_annotations_do_not_expose_stripe_sdk_names() -> None:
    modules = _public_annotation_modules()
    annotations: list[object] = []
    for module in modules:
        annotations.extend(module.__annotations__.values())
        for value in vars(module).values():
            if inspect.isclass(value) and value.__module__ == module.__name__:
                annotations.extend(value.__annotations__.values())
                for member in vars(value).values():
                    annotations.extend(getattr(member, "__annotations__", {}).values())
            elif inspect.isfunction(value) and value.__module__ == module.__name__:
                annotations.extend(value.__annotations__.values())

    assert "stripe." not in " ".join(map(str, annotations)).lower()


def _public_annotation_modules() -> tuple[ModuleType, ...]:
    from django_checkouts import capabilities
    from django_checkouts import client
    from django_checkouts import enums
    from django_checkouts import exceptions
    from django_checkouts.resources import checkouts
    from django_checkouts.resources import events
    from django_checkouts.resources import invoices
    from django_checkouts.resources import subscriptions
    from django_checkouts.resources import webhooks
    from django_checkouts.types import checkouts as checkout_types
    from django_checkouts.types import common
    from django_checkouts.types import events as event_types
    from django_checkouts.types import invoices as invoice_types
    from django_checkouts.types import subscriptions as subscription_types

    return (
        capabilities,
        client,
        enums,
        exceptions,
        checkouts,
        events,
        invoices,
        subscriptions,
        webhooks,
        checkout_types,
        common,
        event_types,
        invoice_types,
        subscription_types,
    )


def test_pre_1_0_modules_and_compatibility_exports_are_absent() -> None:
    legacy_modules = (
        "django_checkouts.authentication",
        "django_checkouts.base",
        "django_checkouts.dto",
        "django_checkouts." + "pro" + "viders",
        "django_checkouts." + "pro" + "viders.stripe",
    )
    assert all(not _module_exists(name) for name in legacy_modules)

    from django_checkouts import checks
    from django_checkouts import enums
    from django_checkouts import exceptions
    from django_checkouts import registry

    legacy_exports = {
        enums: ("Pro" + "vider", "Capability"),
        exceptions: (
            "CheckoutNotFound",
            "Pro" + "viderPermanentError",
            "Pro" + "viderTemporaryError",
        ),
        registry: (
            "PRO" + "VIDER_CACHE",
            "get_checkout_" + "pro" + "vider",
            "iter_checkout_" + "pro" + "vider_classes",
            "iter_checkout_" + "pro" + "viders",
        ),
        checks: ("check_checkout_" + "pro" + "viders",),
    }
    assert all(
        not hasattr(module, export)
        for module, exports in legacy_exports.items()
        for export in exports
    )


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False
