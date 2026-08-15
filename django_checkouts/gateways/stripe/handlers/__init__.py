"""Handlers registrados pelo gateway Stripe."""

from __future__ import annotations

from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeCancelCheckoutHandler,
)
from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeCreateCheckoutHandler,
)
from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeRetrieveCheckoutHandler,
)

__all__ = [
    "StripeCancelCheckoutHandler",
    "StripeCreateCheckoutHandler",
    "StripeRetrieveCheckoutHandler",
]
