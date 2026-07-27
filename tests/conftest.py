from __future__ import annotations

import json
from pathlib import Path

import pytest

from django_checkouts.registry import PROVIDER_CACHE


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """Impede que uma variante instanciada num teste vaze para o seguinte."""
    PROVIDER_CACHE.clear()
    yield
    PROVIDER_CACHE.clear()


TESTS_ROOT = Path(__file__).parent


@pytest.fixture
def load_fixture(request):
    """Carrega um JSON de ``fixtures/`` ao lado do módulo de teste.

    Aceita também um caminho relativo à raiz de ``tests/``, para quem precisa
    reaproveitar a fixture de outro provider.
    """

    def _load(name: str) -> dict:
        local = Path(request.path).parent / "fixtures" / name
        path = local if local.exists() else TESTS_ROOT / name
        return json.loads(path.read_text(encoding="utf-8"))

    return _load
