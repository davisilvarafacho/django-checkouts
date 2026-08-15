"""Gateway Stripe para a interface orientada a recursos."""

from __future__ import annotations

from django_checkouts.gateways.stripe.gateway import StripeGateway
from django_checkouts.gateways.stripe.options import StripeCheckoutOptions

__all__ = ["StripeCheckoutOptions", "StripeGateway"]

