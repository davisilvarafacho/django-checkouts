"""Marcadores tipados para opções exclusivas de um gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import ClassVar

if TYPE_CHECKING:
    from django_checkouts.enums import Gateway


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayOptions:
    """Base para opções não portáveis de uma implementação de gateway."""

    gateway: ClassVar[Gateway | str]
