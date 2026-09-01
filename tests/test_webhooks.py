"""Verificação de entrada: provar que a requisição veio mesmo do gateway."""

from __future__ import annotations

import hashlib

import pytest

from django_checkouts.enums import Gateway
from django_checkouts.exceptions import WebhookVerificationError
from django_checkouts.webhooks import HeaderTokenWebhookAuth
from django_checkouts.webhooks import Sha256BodyWebhookAuth
from django_checkouts.webhooks import normalize_headers


class TestNormalizeHeaders:
    def test_lowercases_and_undoes_meta_mangling(self):
        """request.META, request.headers e um dict de teste precisam convergir."""
        assert normalize_headers({"HTTP_ASAAS_ACCESS_TOKEN": "x"}) == {
            "asaas-access-token": "x"
        }
        assert normalize_headers({"Asaas-Access-Token": "x"}) == {
            "asaas-access-token": "x"
        }


class TestHeaderTokenWebhookAuth:
    @pytest.fixture
    def auth(self):
        return HeaderTokenWebhookAuth(
            gateway=Gateway.ASAAS, secret="tok-secreto", header="asaas-access-token"
        )

    def test_accepts_matching_token(self, auth):
        payload = auth.verify(
            b'{"event": "CHECKOUT_PAID"}', {"asaas-access-token": "tok-secreto"}
        )
        assert payload == {"event": "CHECKOUT_PAID"}

    def test_rejects_wrong_token(self, auth):
        with pytest.raises(WebhookVerificationError, match="não confere"):
            auth.verify(b"{}", {"asaas-access-token": "errado"})

    def test_rejects_missing_header(self, auth):
        with pytest.raises(WebhookVerificationError, match="proxy"):
            auth.verify(b"{}", {})

    def test_rejects_when_secret_is_unconfigured(self):
        """Sem segredo, aceitar seria pior do que recusar."""
        insecure = HeaderTokenWebhookAuth(gateway=Gateway.ASAAS, header="x-token")
        with pytest.raises(WebhookVerificationError, match="não configurado"):
            insecure.verify(b"{}", {"x-token": "qualquer"})

    def test_rejects_non_object_json(self, auth):
        with pytest.raises(WebhookVerificationError, match="objeto JSON"):
            auth.verify(b"[1, 2]", {"asaas-access-token": "tok-secreto"})

    def test_rejects_malformed_json(self, auth):
        with pytest.raises(WebhookVerificationError, match="JSON válido"):
            auth.verify(b"{nao json", {"asaas-access-token": "tok-secreto"})

    def test_missing_secret_is_a_check_error(self):
        messages = HeaderTokenWebhookAuth(gateway=Gateway.ASAAS).validate()
        assert [m.id for m in messages] == ["django_checkouts.E002"]

    def test_secret_is_not_in_repr(self):
        auth = HeaderTokenWebhookAuth(gateway=Gateway.ASAAS, secret="tok-secreto")
        assert "tok-secreto" not in repr(auth)


class TestSha256BodyWebhookAuth:
    @pytest.fixture
    def auth(self):
        return Sha256BodyWebhookAuth(
            gateway=Gateway.PAGSEGURO, secret="tok", header="x-authenticity-token"
        )

    def digest(self, token: bytes, body: bytes) -> str:
        return hashlib.sha256(token + b"-" + body).hexdigest()

    def test_accepts_correct_digest(self, auth):
        body = b'{"id": "CHEC_123"}'
        payload = auth.verify(
            body, {"x-authenticity-token": self.digest(b"tok", body)}
        )
        assert payload == {"id": "CHEC_123"}

    def test_accepts_uppercase_digest(self, auth):
        body = b"{}"
        header = self.digest(b"tok", body).upper()
        assert auth.verify(body, {"x-authenticity-token": header}) == {}

    def test_rejects_tampered_body(self, auth):
        """O hash cobre o corpo: alterar um centavo invalida a notificação."""
        header = self.digest(b"tok", b'{"amount": 100}')
        with pytest.raises(WebhookVerificationError, match="não confere"):
            auth.verify(b'{"amount": 999}', {"x-authenticity-token": header})

    def test_error_points_at_the_usual_cause(self, auth):
        with pytest.raises(WebhookVerificationError, match="reserializado"):
            auth.verify(b"{}", {"x-authenticity-token": "deadbeef"})

    def test_rejects_when_secret_is_unconfigured(self):
        insecure = Sha256BodyWebhookAuth(gateway=Gateway.PAGSEGURO, header="x-token")
        with pytest.raises(WebhookVerificationError, match="não configurado"):
            insecure.verify(b"{}", {"x-token": "abc"})
