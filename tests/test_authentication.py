"""Authentication classes de DRF.

A lib não traz view: a garantia que estes testes dão é que a verificação
acontece na camada de autenticação, antes de a view rodar, e que o payload
normalizado chega em ``request.auth``.
"""

from __future__ import annotations

import pytest
import stripe
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed

from django_checkouts.authentication import AsaasWebhookAuthentication
from django_checkouts.authentication import FakeGatewayUser
from django_checkouts.authentication import StripeWebhookAuthentication
from django_checkouts.enums import EventType
from django_checkouts.enums import Provider


@pytest.fixture
def post_webhook():
    def _post(body: bytes = b"{}", **headers):
        return RequestFactory().post(
            "/webhooks/stripe/",
            data=body,
            content_type="application/json",
            **headers,
        )

    return _post


class TestStripeWebhookAuthentication:
    def test_returns_fake_user_and_payload(
        self, monkeypatch, post_webhook, load_fixture
    ):
        payload = load_fixture("providers/stripe/fixtures/webhook_completed.json")
        monkeypatch.setattr(
            stripe.Webhook, "construct_event", staticmethod(lambda **k: payload)
        )
        request = post_webhook(HTTP_STRIPE_SIGNATURE="t=1,v1=abc")

        user, auth = StripeWebhookAuthentication().authenticate(request)

        assert isinstance(user, FakeGatewayUser)
        assert user.is_authenticated
        assert str(user) == "gateway:stripe"
        assert auth.type == EventType.CHECKOUT_PAID
        assert auth.external_id == "cs_test_a1b2c3"

    def test_bad_signature_becomes_authentication_failed(
        self, monkeypatch, post_webhook
    ):
        """Vira 401 do DRF, não 500 — o Stripe não deve reenviar isso."""

        def boom(**kwargs):
            raise stripe.SignatureVerificationError("inválida", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(boom))
        request = post_webhook(HTTP_STRIPE_SIGNATURE="t=1,v1=xxx")

        with pytest.raises(AuthenticationFailed):
            StripeWebhookAuthentication().authenticate(request)

    def test_missing_signature_becomes_authentication_failed(self, post_webhook):
        with pytest.raises(AuthenticationFailed):
            StripeWebhookAuthentication().authenticate(post_webhook())

    def test_authenticate_header_names_the_realm(self):
        header = StripeWebhookAuthentication().authenticate_header(None)
        assert header == 'Webhook realm="stripe"'


def test_generated_classes_are_bound_to_their_provider():
    assert StripeWebhookAuthentication.provider_name is Provider.STRIPE
    assert AsaasWebhookAuthentication.provider_name is Provider.ASAAS
