"""Reconciliação paginada de eventos do Stripe."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe

from django_checkouts.client import CheckoutClient
from django_checkouts.enums import EventType
from django_checkouts.exceptions import ValidationError
from django_checkouts.gateways.stripe import StripeGateway


@pytest.fixture
def stripe_mock(monkeypatch):
    monkeypatch.setattr(stripe.Event, "list", Mock())
    return stripe


@pytest.fixture
def stripe_client() -> CheckoutClient:
    return CheckoutClient(
        StripeGateway(
            api_key="sk_test_per_account",
            webhook_secret="whsec_test",
            variant="stripe-br",
        )
    )


@pytest.fixture
def window():
    return SimpleNamespace(
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 8, 2, tzinfo=UTC),
    )


def event_at(payload, *, event_id: str, created: int):
    event = deepcopy(payload)
    event["id"] = event_id
    event["created"] = created
    return event


def test_uses_exact_half_open_reconciliation_window(
    stripe_client, stripe_mock, load_fixture, window
):
    stripe_mock.Event.list.return_value = {
        "data": [load_fixture("event_invoice_paid.json")],
        "has_more": False,
    }

    page = stripe_client.events.list(
        occurred_since=window.start,
        occurred_before=window.end,
        cursor="evt_previous",
        limit=50,
    )

    assert stripe_mock.Event.list.call_args.kwargs == {
        "created": {
            "gte": int(window.start.timestamp()),
            "lt": int(window.end.timestamp()),
        },
        "starting_after": "evt_previous",
        "limit": 50,
        "api_key": "sk_test_per_account",
    }
    assert page.occurred_since == window.start
    assert page.occurred_before == window.end


def test_reverses_stripe_page_and_uses_last_remote_id_as_cursor(
    stripe_client, stripe_mock, load_fixture, window
):
    payload = load_fixture("event_invoice_paid.json")
    newest = event_at(payload, event_id="evt_3", created=1785715203)
    middle = event_at(payload, event_id="evt_2", created=1785715202)
    oldest = event_at(payload, event_id="evt_1", created=1785715201)
    stripe_mock.Event.list.return_value = {
        "data": [newest, middle, oldest],
        "has_more": True,
    }

    page = stripe_client.events.list(
        occurred_since=window.start,
        occurred_before=window.end,
    )

    assert [item.event_id for item in page.items] == ["evt_1", "evt_2", "evt_3"]
    assert all(item.type == EventType.INVOICE_PAID for item in page.items)
    assert page.next_cursor == "evt_1"


def test_omits_cursor_when_stripe_has_no_more_events(
    stripe_client, stripe_mock, load_fixture, window
):
    stripe_mock.Event.list.return_value = {
        "data": [load_fixture("event_invoice_paid.json")],
        "has_more": False,
    }

    page = stripe_client.events.list(
        occurred_since=window.start,
        occurred_before=window.end,
    )

    assert page.next_cursor is None


@pytest.mark.parametrize(
    ("since", "before", "limit", "message"),
    [
        (
            datetime(2026, 8, 1),  # noqa: DTZ001 - exercita data ingênua
            datetime(2026, 8, 2, tzinfo=UTC),
            50,
            "timezone-aware",
        ),
        (
            datetime(2026, 8, 2, tzinfo=UTC),
            datetime(2026, 8, 2, tzinfo=UTC),
            50,
            "anterior",
        ),
        (
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 2, tzinfo=UTC),
            0,
            "1 e 100",
        ),
        (
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 2, tzinfo=UTC),
            101,
            "1 e 100",
        ),
    ],
)
def test_rejects_invalid_windows_before_io(
    stripe_client, stripe_mock, since, before, limit, message
):
    with pytest.raises(ValidationError, match=message):
        stripe_client.events.list(
            occurred_since=since,
            occurred_before=before,
            limit=limit,
        )

    stripe_mock.Event.list.assert_not_called()
