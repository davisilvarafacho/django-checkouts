"""Handlers registrados pelo gateway Stripe."""

from __future__ import annotations

from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeCancelCheckoutHandler,
)
from django_checkouts.gateways.stripe.handlers.checkouts import StripeCancelSetupHandler
from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeCreateCheckoutHandler,
)
from django_checkouts.gateways.stripe.handlers.checkouts import StripeCreateSetupHandler
from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeRetrieveCheckoutHandler,
)
from django_checkouts.gateways.stripe.handlers.checkouts import (
    StripeRetrieveSetupHandler,
)
from django_checkouts.gateways.stripe.handlers.events import StripeListEventsHandler
from django_checkouts.gateways.stripe.handlers.invoices import (
    StripeRetrieveInvoiceHandler,
)
from django_checkouts.gateways.stripe.handlers.subscriptions import (
    StripeCancelSubscriptionHandler,
)
from django_checkouts.gateways.stripe.handlers.subscriptions import (
    StripeChangeSubscriptionHandler,
)
from django_checkouts.gateways.stripe.handlers.subscriptions import (
    StripeResumeSubscriptionHandler,
)
from django_checkouts.gateways.stripe.handlers.subscriptions import (
    StripeRetrieveSubscriptionHandler,
)

__all__ = [
    "StripeCancelCheckoutHandler",
    "StripeCancelSetupHandler",
    "StripeCancelSubscriptionHandler",
    "StripeChangeSubscriptionHandler",
    "StripeCreateCheckoutHandler",
    "StripeCreateSetupHandler",
    "StripeListEventsHandler",
    "StripeResumeSubscriptionHandler",
    "StripeRetrieveCheckoutHandler",
    "StripeRetrieveInvoiceHandler",
    "StripeRetrieveSetupHandler",
    "StripeRetrieveSubscriptionHandler",
]
