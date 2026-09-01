"""Matriz de erros públicos do gateway Stripe."""

from __future__ import annotations

import traceback
from unittest.mock import Mock

import pytest
import stripe

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import RetryDisposition
from django_checkouts.exceptions import CheckoutError
from django_checkouts.exceptions import ConfigurationError
from django_checkouts.exceptions import GatewayPermanentError
from django_checkouts.exceptions import GatewayTemporaryError
from django_checkouts.exceptions import ResourceNotFound
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.gateways.stripe import StripeGateway


@pytest.fixture
def gateway() -> StripeGateway:
    return StripeGateway(
        api_key="sk_test_must_not_leak",
        webhook_secret="whsec_must_not_leak",
        variant="stripe-br",
    )


@pytest.mark.parametrize(
    ("error", "mutation", "error_type", "disposition"),
    [
        pytest.param(
            stripe.RateLimitError("Authorization: Bearer secret", code="rate_limit"),
            False,
            GatewayTemporaryError,
            RetryDisposition.RETRY,
            id="rate-limit-read",
        ),
        pytest.param(
            stripe.APIConnectionError("read connection secret"),
            False,
            GatewayTemporaryError,
            RetryDisposition.RETRY,
            id="connection-read",
        ),
        pytest.param(
            stripe.APIConnectionError("mutation timed out", should_retry=True),
            True,
            GatewayTemporaryError,
            RetryDisposition.RETRY_SAME_KEY,
            id="mutation-timeout",
        ),
        pytest.param(
            stripe.IdempotencyError("same key, different request", code="conflict"),
            True,
            GatewayPermanentError,
            RetryDisposition.RECONCILE_FIRST,
            id="idempotency-conflict",
        ),
        pytest.param(
            stripe.APIError("remote result uncertain", http_status=500),
            True,
            GatewayPermanentError,
            RetryDisposition.RECONCILE_FIRST,
            id="uncertain-mutation",
        ),
        pytest.param(
            stripe.InvalidRequestError(
                "invalid Authorization header",
                param="line_items",
                code="parameter_invalid_integer",
            ),
            False,
            GatewayPermanentError,
            RetryDisposition.NEVER,
            id="invalid-request",
        ),
        pytest.param(
            stripe.AuthenticationError("sk_test_must_not_leak"),
            False,
            ConfigurationError,
            RetryDisposition.NEVER,
            id="authentication",
        ),
        pytest.param(
            stripe.InvalidRequestError(
                "No such invoice: in_missing",
                param="id",
                code="resource_missing",
                http_status=404,
            ),
            False,
            ResourceNotFound,
            RetryDisposition.NEVER,
            id="missing-resource",
        ),
    ],
)
def test_sdk_errors_have_exhaustive_public_translation(
    gateway, error, mutation, error_type, disposition
) -> None:
    external_call = Mock(side_effect=error)

    with pytest.raises(CheckoutError) as caught:
        gateway.call(external_call, mutation=mutation)

    assert type(caught.value) is error_type
    assert caught.value.retry_advice.disposition is disposition
    assert not isinstance(caught.value, stripe.StripeError)


def test_translation_keeps_only_safe_diagnostics(gateway) -> None:
    error = stripe.InvalidRequestError(
        "sk_test_must_not_leak whsec_must_not_leak Authorization raw-payload",
        param="line_items",
        code="parameter_invalid_integer",
        http_body=b"raw-payload",
        headers={"Authorization": "Bearer sk_test_must_not_leak"},
    )

    with pytest.raises(GatewayPermanentError) as caught:
        gateway.call(Mock(side_effect=error))

    rendered = " ".join(
        (
            str(caught.value),
            repr(caught.value),
            str(caught.value.gateway_message),
            "".join(traceback.format_exception(caught.value)),
        )
    )
    assert caught.value.code == "parameter_invalid_integer"
    for secret in (
        "sk_test_must_not_leak",
        "whsec_must_not_leak",
        "Authorization",
        "raw-payload",
    ):
        assert secret not in rendered


def test_invalid_webhook_never_exposes_sdk_error(gateway, monkeypatch) -> None:
    client = CheckoutClient(gateway)
    body = b"raw-payload"
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        Mock(
            side_effect=stripe.SignatureVerificationError("whsec_must_not_leak", "sig")
        ),
    )

    with pytest.raises(WebhookVerificationError) as caught:
        client.webhooks.verify(body, {"Stripe-Signature": "sig"})

    rendered = " ".join(
        (
            str(caught.value),
            repr(caught.value),
            "".join(traceback.format_exception(caught.value)),
        )
    )
    assert "whsec_must_not_leak" not in rendered
    assert "raw-payload" not in rendered
    assert not isinstance(caught.value, stripe.StripeError)
