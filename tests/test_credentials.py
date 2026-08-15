"""Credenciais de saída enviadas ao chamar a API do gateway."""

from __future__ import annotations

import requests

from django_checkouts.credentials import TokenAuth


def test_applies_bearer_scheme():
    session = requests.Session()
    TokenAuth(token="sk_test_1").apply(session)
    assert session.headers["Authorization"] == "Bearer sk_test_1"


def test_applies_raw_header_without_scheme():
    """O Asaas manda o token cru em access_token, sem esquema."""
    session = requests.Session()
    TokenAuth(token="tok", header="access_token", scheme=None).apply(session)
    assert session.headers["access_token"] == "tok"


def test_missing_token_is_a_check_error():
    messages = TokenAuth(token="").validate()
    assert [m.id for m in messages] == ["django_checkouts.E001"]


def test_wrong_prefix_is_a_check_warning():
    """Chave de produção em ambiente de teste é erro caro e silencioso."""
    messages = TokenAuth(token="sk_live_1", expected_prefix="sk_test_").validate()
    assert [m.id for m in messages] == ["django_checkouts.W001"]


def test_correct_prefix_is_silent():
    assert TokenAuth(token="sk_test_1", expected_prefix="sk_test_").validate() == []


def test_token_is_not_in_repr():
    """Objetos podem parar em logs de exceção; o segredo não pode ir junto."""
    assert "segredo" not in repr(TokenAuth(token="segredo"))
