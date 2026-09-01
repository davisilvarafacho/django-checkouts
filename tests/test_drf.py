"""Integração DRF opcional para autenticação de webhooks."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from django_checkouts.integrations.drf import CheckoutWebhookAuthentication
from django_checkouts.integrations.drf import checkout_webhook_authentication
from django_checkouts.types import WebhookEvent


def webhook_event() -> WebhookEvent:
    return WebhookEvent(
        gateway="fake",
        variant="fake-br",
        event_id="evt_verified_1",
        event_type="checkout.paid",
        type=None,
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        resource_kind=None,
        resource_id=None,
        resource=None,
        livemode=False,
        raw={"id": "evt_verified_1"},
    )


def test_authentication_verifies_original_body_and_sets_event_as_auth(
    monkeypatch,
) -> None:
    event = webhook_event()
    verify = Mock(return_value=event)
    client = SimpleNamespace(webhooks=SimpleNamespace(verify=verify))
    get_gateway = Mock(return_value=client)
    monkeypatch.setattr(
        "django_checkouts.integrations.drf.get_checkout_gateway", get_gateway
    )
    authentication_class = checkout_webhook_authentication("fake-br")
    django_request = APIRequestFactory().post(
        "/webhook/",
        b'{"signed":true}',
        content_type="application/json",
        HTTP_X_SIGNATURE="signature",
    )
    request = Request(django_request)

    user, auth = authentication_class().authenticate(request)

    get_gateway.assert_called_once_with("fake-br")
    verify.assert_called_once_with(bytes(request.body), request.headers)
    assert isinstance(user, AnonymousUser)
    assert auth is event


def test_factory_returns_concrete_no_argument_authentication_class() -> None:
    authentication_class = checkout_webhook_authentication("stripe-br")

    assert issubclass(authentication_class, CheckoutWebhookAuthentication)
    assert authentication_class.variant == "stripe-br"
    assert isinstance(authentication_class(), CheckoutWebhookAuthentication)


def test_drf_assigns_verified_event_to_request_auth(monkeypatch) -> None:
    event = webhook_event()
    client = SimpleNamespace(webhooks=SimpleNamespace(verify=Mock(return_value=event)))
    monkeypatch.setattr(
        "django_checkouts.integrations.drf.get_checkout_gateway",
        Mock(return_value=client),
    )

    django_request = APIRequestFactory().post(
        "/webhook/", b"{}", content_type="application/json"
    )
    request = Request(
        django_request,
        authenticators=[checkout_webhook_authentication("fake-br")()],
    )

    assert request.auth is event
