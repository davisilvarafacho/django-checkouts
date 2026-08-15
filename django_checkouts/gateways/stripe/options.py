"""Opções exclusivas de Checkout Session do Stripe."""

from __future__ import annotations

from dataclasses import dataclass

from django_checkouts.enums import Gateway
from django_checkouts.gateways.options import GatewayOptions


@dataclass(frozen=True, slots=True, kw_only=True)
class StripeCheckoutOptions(GatewayOptions):
    """Opções Stripe que não sobrescrevem campos portáveis."""

    gateway = Gateway.STRIPE
    allow_promotion_codes: bool = False
    automatic_tax: bool = False
    billing_address_required: bool = False


__all__ = ["StripeCheckoutOptions"]
