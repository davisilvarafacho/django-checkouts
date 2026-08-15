"""Validações compartilhadas pelos recursos públicos."""

from __future__ import annotations

from django_checkouts.exceptions import ValidationError


def require_idempotency_key(value: str) -> None:
    """Recusa mutações sem uma chave de idempotência significativa."""
    if not value or not value.strip():
        raise ValidationError("idempotency_key must not be empty")
