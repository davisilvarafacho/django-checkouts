"""Marcadores tipados para opções exclusivas de um gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from django_checkouts.enums import Gateway  # noqa: TC001 - runtime hints


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayOptions:
    """Base para opções não portáveis de uma implementação de gateway."""

    gateway: ClassVar[Gateway | str]
