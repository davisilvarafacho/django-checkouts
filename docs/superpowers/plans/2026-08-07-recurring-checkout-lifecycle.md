# Recurring Checkout Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pre-1.0 provider interface with a stateless, resource-oriented gateway interface supporting Stripe checkout, subscriptions, invoices, authenticated webhooks, and reconciliation end-to-end.

**Architecture:** Consumer projects use a `CheckoutClient` composed of five resources. Resources create typed commands; `BaseCheckoutGateway` validates each command before dispatching it to a gateway handler. The library owns no persistence and returns immutable normalized DTOs containing defensive copies of raw gateway payloads.

**Tech Stack:** Python 3.11+, Django 5.2, optional Django REST Framework integration, Stripe Python SDK, pytest, pytest-django, pytest-cov, mypy, Ruff, uv, Sphinx, setuptools-scm.

## Global Constraints

- Keep the library stateless: no models, migrations, views, URLs, queues, workers, or persistence.
- Implement Stripe completely; do not create empty Asaas or PagBank packages.
- Use `gateway` publicly; `variant` identifies a configured gateway account.
- Represent money as `int` in the currency minor unit; reject `float` and `bool`.
- Make public DTOs `frozen=True`, `slots=True`, and `kw_only=True`.
- Preserve `raw` with `repr=False` and `compare=False`, using a defensive copy.
- Normalize currencies to uppercase ISO 4217 and datetimes to timezone-aware UTC.
- Require a non-empty caller-supplied idempotency key on every mutation.
- Never expose Stripe SDK objects, exceptions, or annotation types publicly.
- Authenticate webhook raw bytes before parsing. Unknown events use `type=None`; unknown financial statuses raise `GatewayProtocolError`.
- Reconciliation uses `[occurred_since, occurred_before)`, opaque cursors, chronological pages, and stable gateway event IDs.
- Deterministic tests never use the network; Stripe sandbox tests remain separately marked.
- Delivery gates: pytest with at least 90% coverage, mypy, Ruff, Sphinx with warnings as errors, sdist, and wheel.

---

## File Map

| Path | Responsibility |
|---|---|
| `django_checkouts/client.py` | Public client composition root. |
| `django_checkouts/resources/*.py` | Caller-facing checkout, subscription, invoice, webhook, and event operations. |
| `django_checkouts/types/*.py` | Immutable normalized request/result DTOs. |
| `django_checkouts/enums.py` | Stable states, events, timings, and retry vocabulary. |
| `django_checkouts/capabilities.py` | Read-only technical gateway capabilities. |
| `django_checkouts/exceptions.py` | Public errors and retry advice. |
| `django_checkouts/registry.py` | Variant resolution, caching, and client construction. |
| `django_checkouts/gateways/base.py` | Validation and typed command dispatch. |
| `django_checkouts/gateways/commands.py` | Internal commands for resources and gateway authors. |
| `django_checkouts/gateways/contracts.py` | Handler and execution-context protocols. |
| `django_checkouts/gateways/options.py` | Typed gateway-option marker. |
| `django_checkouts/gateways/stripe/` | Stripe gateway, mappings, options, verification, and handlers. |
| `django_checkouts/integrations/drf.py` | Optional DRF webhook authentication. |
| `django_checkouts/testing/` | Public fake gateway and reusable contract suite. |

---

### Task 1: Define normalized vocabulary, DTOs, and errors

**Files:**
- Modify: `django_checkouts/enums.py`
- Modify: `django_checkouts/exceptions.py`
- Create: `django_checkouts/gateways/__init__.py`
- Create: `django_checkouts/gateways/options.py`
- Create: `django_checkouts/types/__init__.py`
- Create: `django_checkouts/types/common.py`
- Create: `django_checkouts/types/checkouts.py`
- Create: `django_checkouts/types/subscriptions.py`
- Create: `django_checkouts/types/invoices.py`
- Create: `django_checkouts/types/events.py`
- Create: `tests/test_types.py`
- Modify: `tests/test_base.py`

**Interfaces:**
- Consumes: Django `TextChoices`, dataclasses, `datetime`, `Mapping`.
- Produces: all public enums and DTOs, `GatewayOptions`, `CheckoutError`, and `RetryAdvice`.

- [ ] **Step 1: Write failing money, raw, and immutability tests**

```python
# tests/test_types.py
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from django_checkouts.enums import CheckoutMode, CheckoutStatus, Gateway
from django_checkouts.types import CatalogPrice, Checkout, CheckoutItem, InlinePrice


def test_money_rejects_float_and_bool():
    with pytest.raises(TypeError, match="unit_amount"):
        InlinePrice(name="Pro", unit_amount=49.90)
    with pytest.raises(TypeError, match="unit_amount"):
        InlinePrice(name="Pro", unit_amount=True)


def test_checkout_is_immutable_and_hides_raw():
    checkout = Checkout(
        external_id="cs_123", gateway=Gateway.STRIPE, variant="stripe-br",
        status=CheckoutStatus.PENDING, mode=CheckoutMode.PAYMENT,
        url=None, amount_total=4990, currency="brl", customer=None,
        reference_id="order-1", subscription_id=None, expires_at=None,
        created_at=datetime(2026, 8, 7, tzinfo=UTC), raw={"secret": "value"},
    )
    assert checkout.currency == "BRL"
    assert "secret" not in repr(checkout)
    with pytest.raises(FrozenInstanceError):
        checkout.status = CheckoutStatus.PAID


def test_quantity_is_absolute_and_positive():
    with pytest.raises(ValueError, match="quantity"):
        CheckoutItem(price=CatalogPrice(external_id="price_123"), quantity=0)
```

- [ ] **Step 2: Run the test and verify missing imports**

Run: `uv run pytest tests/test_types.py -q`

Expected: collection fails because `Gateway` and `django_checkouts.types` do not exist.

- [ ] **Step 3: Implement stable enums and the public error tree**

Keep existing `PaymentMethod`, `CheckoutMode`, `CheckoutStatus`, and `BillingCycle` values. Replace `Provider` with `Gateway`. Add these exact values:

```python
class Gateway(TextChoices):
    STRIPE = "stripe", "Stripe"
    PAGSEGURO = "pagseguro", "PagBank"
    ASAAS = "asaas", "Asaas"

class SubscriptionStatus(TextChoices):
    INCOMPLETE = "incomplete"; TRIALING = "trialing"; ACTIVE = "active"
    PAST_DUE = "past_due"; PAUSED = "paused"; UNPAID = "unpaid"
    CANCELED = "canceled"; EXPIRED = "expired"

class InvoiceStatus(TextChoices):
    DRAFT = "draft"; OPEN = "open"; PAID = "paid"
    VOID = "void"; UNCOLLECTIBLE = "uncollectible"

class InvoiceReason(TextChoices):
    INITIAL_SUBSCRIPTION = "initial_subscription"; RENEWAL = "renewal"
    SUBSCRIPTION_UPDATE = "subscription_update"; MANUAL = "manual"; UNKNOWN = "unknown"

class EventType(TextChoices):
    CHECKOUT_PENDING = "checkout.pending"; CHECKOUT_PAID = "checkout.paid"
    CHECKOUT_FAILED = "checkout.failed"; CHECKOUT_EXPIRED = "checkout.expired"
    CHECKOUT_CANCELED = "checkout.canceled"
    SUBSCRIPTION_CREATED = "subscription.created"; SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELED = "subscription.canceled"
    INVOICE_OPENED = "invoice.opened"; INVOICE_PAID = "invoice.paid"
    INVOICE_PAYMENT_FAILED = "invoice.payment_failed"; INVOICE_VOIDED = "invoice.voided"
    INVOICE_UNCOLLECTIBLE = "invoice.uncollectible"

class ResourceKind(TextChoices):
    CHECKOUT = "checkout"; SUBSCRIPTION = "subscription"; INVOICE = "invoice"

class ChangeTiming(TextChoices):
    IMMEDIATELY = "immediately"; NEXT_CYCLE = "next_cycle"

class ProrationBehavior(TextChoices):
    CREATE_PRORATIONS = "create_prorations"; INVOICE_IMMEDIATELY = "invoice_immediately"; NONE = "none"

class CancellationTiming(TextChoices):
    IMMEDIATELY = "immediately"; PERIOD_END = "period_end"

class RetryDisposition(TextChoices):
    NEVER = "never"; RETRY = "retry"; RETRY_SAME_KEY = "retry_same_key"; RECONCILE_FIRST = "reconcile_first"
```

Use translated `pgettext_lazy` labels in the real implementation. Implement `RetryAdvice(disposition, retry_after)` and this exact hierarchy: `CheckoutError`; `ConfigurationError`; `ValidationError`; `CapabilityNotSupported`; `UnsupportedPaymentMethod`; `WebhookVerificationError`; `GatewayError`; `GatewayTemporaryError`; `GatewayPermanentError`; `GatewayProtocolError`; `ResourceNotFound`. `GatewayError` stores `gateway`, `variant`, optional external `code`, sanitized `gateway_message`, and `RetryAdvice`. All non-gateway errors default to `NEVER`.

- [ ] **Step 4: Implement gateway options and request primitives**

```python
# django_checkouts/gateways/options.py
@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayOptions:
    gateway: ClassVar[Gateway | str]
```

```python
# django_checkouts/types/common.py
@dataclass(frozen=True, slots=True, kw_only=True)
class InlinePrice:
    name: str
    unit_amount: int
    currency: str = "BRL"
    description: str | None = None
    image_url: str | None = None

    def __post_init__(self):
        if isinstance(self.unit_amount, bool) or not isinstance(self.unit_amount, int):
            raise TypeError("unit_amount must be an integer in the currency minor unit")
        if self.unit_amount <= 0:
            raise ValueError("unit_amount must be positive")
        object.__setattr__(self, "currency", self.currency.upper())

@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogPrice:
    external_id: str

Price = InlinePrice | CatalogPrice

@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutItem:
    price: Price
    quantity: int = 1
    reference_id: str | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    name: str | None = None
    email: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    external_id: str | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Recurrence:
    cycle: BillingCycle
    description: str | None = None
```

- [ ] **Step 5: Implement every public request/result shape**

Implement these exact shapes in their named modules:

```python
# types/checkouts.py
@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutCreate:
    items: tuple[CheckoutItem, ...]
    success_url: str
    mode: CheckoutMode = CheckoutMode.PAYMENT
    cancel_url: str | None = None
    payment_methods: tuple[PaymentMethod, ...] = (PaymentMethod.CARD,)
    customer: Customer | None = None
    recurrence: Recurrence | None = None
    reference_id: str | None = None
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    gateway_options: GatewayOptions | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Checkout:
    external_id: str; gateway: Gateway | str; variant: str
    status: CheckoutStatus; mode: CheckoutMode; url: str | None
    amount_total: int; currency: str; customer: Customer | None
    reference_id: str | None; subscription_id: str | None
    expires_at: datetime | None; created_at: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)
```

```python
# types/subscriptions.py
@dataclass(frozen=True, slots=True, kw_only=True)
class SetQuantity: item_id: str; quantity: int
@dataclass(frozen=True, slots=True, kw_only=True)
class ReplacePrice: item_id: str; price: Price; quantity: int | None = None
@dataclass(frozen=True, slots=True, kw_only=True)
class AddItem: price: Price; quantity: int = 1
@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveItem: item_id: str
SubscriptionChange = SetQuantity | ReplacePrice | AddItem | RemoveItem

@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeSubscription:
    changes: tuple[SubscriptionChange, ...]
    timing: ChangeTiming = ChangeTiming.IMMEDIATELY
    proration: ProrationBehavior = ProrationBehavior.CREATE_PRORATIONS
    metadata: Mapping[str, str] | None = None
    gateway_options: GatewayOptions | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionItem:
    external_id: str; price_id: str | None; quantity: int
    unit_amount: int | None; currency: str | None
    billing_cycle: BillingCycle | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Subscription:
    external_id: str; gateway: Gateway | str; variant: str
    status: SubscriptionStatus; customer_id: str | None
    items: tuple[SubscriptionItem, ...]
    current_period_start: datetime | None; current_period_end: datetime | None
    trial_end: datetime | None; cancel_at: datetime | None
    canceled_at: datetime | None; ended_at: datetime | None
    latest_invoice_id: str | None; reference_id: str | None
    metadata: Mapping[str, str]
    raw: Mapping[str, object] = field(repr=False, compare=False)
```

```python
# types/invoices.py
@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceLine:
    external_id: str; description: str | None; quantity: int
    unit_amount: int | None; amount: int; currency: str
    subscription_item_id: str | None
    period_start: datetime | None; period_end: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Invoice:
    external_id: str; gateway: Gateway | str; variant: str
    status: InvoiceStatus; reason: InvoiceReason
    subscription_id: str | None; customer_id: str | None
    amount_due: int; amount_paid: int; amount_remaining: int; currency: str
    lines: tuple[InvoiceLine, ...]
    due_at: datetime | None; paid_at: datetime | None
    next_payment_attempt_at: datetime | None; attempt_count: int
    hosted_url: str | None; reference_id: str | None
    raw: Mapping[str, object] = field(repr=False, compare=False)
```

```python
# types/events.py
@dataclass(frozen=True, slots=True, kw_only=True)
class WebhookEvent:
    gateway: Gateway | str; variant: str; event_id: str; event_type: str
    type: EventType | None; occurred_at: datetime
    resource_kind: ResourceKind | None; resource_id: str | None
    resource: Checkout | Subscription | Invoice | None
    livemode: bool | None
    raw: Mapping[str, object] = field(repr=False, compare=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class EventPage:
    items: tuple[WebhookEvent, ...]; next_cursor: str | None
    occurred_since: datetime; occurred_before: datetime
```

Use concrete validation helpers called by `__post_init__`: `validate_positive_integer`, `validate_checkout_create`, `validate_subscription_changes`, `normalize_currency`, and `normalize_utc`. They reject empty checkout items, mixed inline currencies, recurrence on one-time payment, missing recurrence for inline subscription prices, non-positive/bool quantities, empty subscription changes, two changes targeting the same item, naive dates, and invalid currency length. For every resource/event raw field execute:

```python
object.__setattr__(self, "raw", MappingProxyType(deepcopy(dict(self.raw))))
```

Re-export all classes plus `Price` through an explicit `django_checkouts.types.__all__`.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/test_types.py tests/test_base.py -q`

Expected: PASS; legacy imports remain temporarily available until Task 8.

```bash
git add django_checkouts/enums.py django_checkouts/exceptions.py django_checkouts/gateways django_checkouts/types tests/test_types.py tests/test_base.py
git commit -m "feat: define normalized checkout contracts"
```

---

### Task 2: Add capabilities and typed gateway dispatch

**Files:**
- Create: `django_checkouts/capabilities.py`
- Create: `django_checkouts/gateways/commands.py`
- Create: `django_checkouts/gateways/contracts.py`
- Create: `django_checkouts/gateways/base.py`
- Create: `tests/test_capabilities.py`
- Create: `tests/test_gateway_dispatch.py`

**Interfaces:**
- Consumes: Task 1 enums, DTOs, and errors.
- Produces: nested capability dataclasses, ten commands, `CommandHandler`, `ExecutionContext`, and `BaseCheckoutGateway.execute()`.

- [ ] **Step 1: Write failing validation-before-I/O tests**

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Echo(GatewayCommand[str]):
    value: str

class EchoHandler:
    command_type = Echo
    def validate(self, command, capabilities):
        if not command.value:
            raise ValidationError("value is required")
    def handle(self, command, context):
        return f"{context.variant}:{command.value}"

def test_validation_precedes_io(fake_gateway):
    with pytest.raises(ValidationError):
        fake_gateway.execute(Echo(value=""))
    assert fake_gateway.io_calls == 0

def test_missing_handler_is_capability_error(fake_gateway):
    with pytest.raises(CapabilityNotSupported):
        fake_gateway.execute(RetrieveInvoice(external_id="in_123"))
```

- [ ] **Step 2: Run tests and verify missing command modules**

Run: `uv run pytest tests/test_capabilities.py tests/test_gateway_dispatch.py -q`

Expected: collection fails because capability/command modules do not exist.

- [ ] **Step 3: Implement nested immutable capabilities**

Create `CheckoutCapabilities(modes, payment_methods_by_mode, billing_cycles, supports_catalog_prices, supports_inline_prices, supports_expiration, supports_customer_prefill)`, `SubscriptionCapabilities(retrieve, change_quantity, replace_price, add_remove_items, timings, proration_behaviors, cancellation_timings, resume_scheduled_cancellation, atomic_multi_change)`, `InvoiceCapabilities(retrieve)`, `WebhookCapabilities(signed)`, `ReconciliationCapabilities(events, maximum_page_size)`, and `GatewayCapabilities(checkouts, subscriptions, invoices, webhooks, reconciliation)` as frozen slotted dataclasses. `CheckoutCapabilities.payment_methods_for(mode)` returns an empty frozenset when unsupported.

- [ ] **Step 4: Implement all commands and contracts**

```python
ResultT = TypeVar("ResultT")
class GatewayCommand(Generic[ResultT]):
    pass

@dataclass(frozen=True, slots=True, kw_only=True)
class CreateCheckout(GatewayCommand[Checkout]):
    request: CheckoutCreate
    idempotency_key: str

@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveCheckout(GatewayCommand[Checkout]): external_id: str
@dataclass(frozen=True, slots=True, kw_only=True)
class CancelCheckout(GatewayCommand[Checkout]): external_id: str; idempotency_key: str
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveSubscription(GatewayCommand[Subscription]): external_id: str
@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeRemoteSubscription(GatewayCommand[Subscription]): external_id: str; request: ChangeSubscription; idempotency_key: str
@dataclass(frozen=True, slots=True, kw_only=True)
class CancelRemoteSubscription(GatewayCommand[Subscription]): external_id: str; timing: CancellationTiming; idempotency_key: str
@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeSubscription(GatewayCommand[Subscription]): external_id: str; idempotency_key: str
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrieveInvoice(GatewayCommand[Invoice]): external_id: str
@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyWebhook(GatewayCommand[WebhookEvent]): raw_body: bytes; headers: Mapping[str, str]
@dataclass(frozen=True, slots=True, kw_only=True)
class ListEvents(GatewayCommand[EventPage]):
    occurred_since: datetime; occurred_before: datetime; cursor: str | None = None; limit: int = 100
```

`ExecutionContext` has `gateway`, `variant`, and `call`. `CommandHandler` declares exact `command_type`, `validate(command, capabilities) -> None`, and `handle(command, context) -> ResultT` methods.

- [ ] **Step 5: Implement concrete exact-type dispatch**

```python
class BaseCheckoutGateway:
    name: Gateway | str
    capabilities: GatewayCapabilities
    handlers: tuple[CommandHandler, ...] = ()

    def __init__(self, *, variant: str, **configuration: object):
        self.variant = variant
        self._handlers = {handler.command_type: handler for handler in self.handlers}

    def execute(self, command: GatewayCommand[ResultT]) -> ResultT:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise CapabilityNotSupported(f"{self.name} does not support {type(command).__name__}")
        handler.validate(command, self.capabilities)
        context = ExecutionContext(gateway=self.name, variant=self.variant, call=self.call)
        return cast(ResultT, handler.handle(command, context))
```

`call()` catches external exceptions and delegates to `translate_error(error, mutation=bool)`. The default translator returns a sanitized `GatewayPermanentError`; `check()` returns an empty `Sequence[CheckMessage]`.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/test_capabilities.py tests/test_gateway_dispatch.py -q`

Expected: PASS with zero I/O for invalid/unsupported commands.

```bash
git add django_checkouts/capabilities.py django_checkouts/gateways tests/test_capabilities.py tests/test_gateway_dispatch.py
git commit -m "feat: add typed gateway dispatch"
```

---

### Task 3: Build resources, client, registry, and fake gateway

**Files:**
- Create: `django_checkouts/resources/{__init__,checkouts,subscriptions,invoices,webhooks,events}.py`
- Create: `django_checkouts/client.py`
- Modify: `django_checkouts/registry.py`
- Create: `django_checkouts/testing/{__init__,fakes}.py`
- Create: `tests/test_client.py`
- Modify: `tests/test_registry.py`

**Interfaces:**
- Consumes: `BaseCheckoutGateway.execute()` and Task 2 commands.
- Produces: `CheckoutClient`, five resources, `get_checkout_gateway()`, and `FakeCheckoutGateway`.

- [ ] **Step 1: Write failing client tests**

```python
def test_client_exposes_five_resources(fake_gateway):
    client = CheckoutClient(fake_gateway)
    assert (client.checkouts.gateway, client.subscriptions.gateway,
            client.invoices.gateway, client.webhooks.gateway,
            client.events.gateway) == (fake_gateway,) * 5

def test_create_builds_command(fake_gateway, checkout_create):
    CheckoutClient(fake_gateway).checkouts.create(checkout_create, idempotency_key="order-1:v1")
    assert fake_gateway.commands == [CreateCheckout(request=checkout_create, idempotency_key="order-1:v1")]

def test_empty_idempotency_key_fails(fake_gateway, checkout_create):
    with pytest.raises(ValidationError, match="idempotency_key"):
        CheckoutClient(fake_gateway).checkouts.create(checkout_create, idempotency_key="")
```

- [ ] **Step 2: Run tests and verify missing client**

Run: `uv run pytest tests/test_client.py tests/test_registry.py -q`

Expected: collection fails because `CheckoutClient` does not exist.

- [ ] **Step 3: Implement exact resource methods**

`CheckoutResource`: `create(request, *, idempotency_key)`, `retrieve(external_id)`, `cancel(external_id, *, idempotency_key)`. `SubscriptionResource`: `retrieve(external_id)`, `change(external_id, request, *, idempotency_key)`, `cancel(external_id, *, timing, idempotency_key)`, `resume(external_id, *, idempotency_key)`. `InvoiceResource.retrieve(external_id)`. `WebhookResource.verify(raw_body, headers)`. `EventResource.list(*, occurred_since, occurred_before, cursor=None, limit=100)`. Each method constructs its matching command; each mutation calls:

```python
def require_idempotency_key(value: str) -> None:
    if not value or not value.strip():
        raise ValidationError("idempotency_key must not be empty")
```

- [ ] **Step 4: Implement client and registry**

```python
class CheckoutClient:
    def __init__(self, gateway: BaseCheckoutGateway):
        self._gateway = gateway
        self.gateway, self.variant = gateway.name, gateway.variant
        self.capabilities = gateway.capabilities
        self.checkouts = CheckoutResource(gateway)
        self.subscriptions = SubscriptionResource(gateway)
        self.invoices = InvoiceResource(gateway)
        self.webhooks = WebhookResource(gateway)
        self.events = EventResource(gateway)
```

`get_checkout_gateway(variant, **credential_overrides)` imports the configured dotted path. Cache clients by variant only when no overrides exist; never cache an override instance.

- [ ] **Step 5: Implement deterministic fake**

```python
class FakeCheckoutGateway(BaseCheckoutGateway):
    name = "fake"
    def __init__(self, *, results, capabilities, variant="fake"):
        super().__init__(variant=variant)
        self.results, self.capabilities, self.commands = dict(results), capabilities, []
    def execute(self, command):
        self.commands.append(command)
        result = self.results[type(command)]
        return result(command) if callable(result) else result
```

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/test_client.py tests/test_registry.py -q`

Expected: PASS; cached variants reuse clients and override variants do not.

```bash
git add django_checkouts/client.py django_checkouts/resources django_checkouts/registry.py django_checkouts/testing tests/test_client.py tests/test_registry.py
git commit -m "feat: add resource-oriented checkout client"
```

---

### Task 4: Port Stripe checkout operations

**Files:**
- Create: `django_checkouts/gateways/stripe/{__init__,gateway,capabilities,options,mapping}.py`
- Create: `django_checkouts/gateways/stripe/handlers/{__init__,checkouts}.py`
- Create: `tests/gateways/stripe/test_checkouts.py`
- Move: `tests/providers/stripe/fixtures/session_{open,paid}.json` to `tests/gateways/stripe/fixtures/`

**Interfaces:**
- Consumes: checkout commands, normalized DTOs, validation seam.
- Produces: `StripeGateway`, checkout handlers/mappers, capabilities, and `StripeCheckoutOptions`.

- [ ] **Step 1: Write failing checkout tests**

```python
def test_subscription_checkout_sends_quantity_and_key(stripe_client, stripe_mock):
    stripe_mock.checkout.Session.create.return_value = load_fixture("session_open.json")
    stripe_client.checkouts.create(subscription_checkout(quantity=10), idempotency_key="org-42:v1")
    kwargs = stripe_mock.checkout.Session.create.call_args.kwargs
    assert kwargs["line_items"] == [{"price": "price_pro", "quantity": 10}]
    assert kwargs["idempotency_key"] == "org-42:v1"

def test_subscription_pix_fails_before_sdk(stripe_client, stripe_mock):
    with pytest.raises(UnsupportedPaymentMethod):
        stripe_client.checkouts.create(subscription_checkout(method=PaymentMethod.PIX), idempotency_key="x:v1")
    stripe_mock.checkout.Session.create.assert_not_called()
```

- [ ] **Step 2: Run tests and verify missing StripeGateway**

Run: `uv run pytest tests/gateways/stripe/test_checkouts.py -q`

Expected: collection fails because `StripeGateway` does not exist.

- [ ] **Step 3: Declare capabilities and typed options**

Stripe supports payment `{card,pix,boleto}`, subscription `{card}`, all existing billing cycles, inline/catalog prices, expiration/prefill, all subscription changes/timings/proration/cancellation, resume, atomic multi-change, invoice retrieve, signed webhooks, and reconciliation page size 100.

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class StripeCheckoutOptions(GatewayOptions):
    gateway = Gateway.STRIPE
    allow_promotion_codes: bool = False
    automatic_tax: bool = False
    billing_address_required: bool = False
```

- [ ] **Step 4: Implement create/retrieve/cancel mapping**

Build catalog items as `{"price": id, "quantity": quantity}` and inline items as Stripe `price_data`, adding recurring interval only for subscription. Map portable URLs, customer, reference, expiration, metadata, and payment methods explicitly. Reject a non-Stripe `gateway_options`; typed options may only set promotion codes, automatic tax, and billing-address collection.

```python
class StripeCreateCheckoutHandler:
    command_type = CreateCheckout
    def validate(self, command, capabilities):
        validate_checkout_create(command.request, capabilities.checkouts, Gateway.STRIPE)
    def handle(self, command, context):
        raw = context.call(stripe.checkout.Session.create,
            **build_checkout_params(command.request),
            idempotency_key=command.idempotency_key, mutation=True)
        return checkout_from_stripe(raw, variant=context.variant)
```

Retrieve calls `Session.retrieve(external_id)`. Cancel calls `Session.expire(external_id, idempotency_key=key)` and never cancels a subscription. Strictly map status/mode, UTC timestamps, customer, subscription ID, uppercase currency, and raw.

- [ ] **Step 5: Assemble StripeGateway and translate checkout errors**

`StripeGateway` owns `api_key`, optional `webhook_secret`, and `sandbox`. Its call wrapper supplies the key per SDK call; it never mutates Stripe global configuration. It registers the three checkout handlers.

- [ ] **Step 6: Run parity tests and commit**

Run: `uv run pytest tests/gateways/stripe/test_checkouts.py tests/providers/stripe/test_checkout.py -q`

Expected: PASS; legacy tests remain until Task 8.

```bash
git add django_checkouts/gateways/stripe tests/gateways/stripe tests/providers/stripe
git commit -m "feat: port Stripe checkout gateway"
```

---

### Task 5: Implement Stripe subscriptions and invoices

**Files:**
- Create: `django_checkouts/gateways/stripe/handlers/{subscriptions,invoices}.py`
- Modify: `django_checkouts/gateways/stripe/{gateway,mapping}.py`
- Create: `tests/gateways/stripe/test_{subscriptions,invoices}.py`
- Create: `tests/gateways/stripe/fixtures/{subscription_active,subscription_canceling,invoice_paid,invoice_failed}.json`

**Interfaces:**
- Consumes: recurring commands/DTOs and Stripe call wrapper.
- Produces: retrieve/change/cancel/resume subscriptions and retrieve invoices.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_change_sets_absolute_quantity(stripe_client, stripe_mock):
    stripe_client.subscriptions.change("sub_1",
        ChangeSubscription(changes=(SetQuantity(item_id="si_1", quantity=25),),
                           proration=ProrationBehavior.INVOICE_IMMEDIATELY),
        idempotency_key="org-42:seats:25:v1")
    kwargs = stripe_mock.Subscription.modify.call_args.kwargs
    assert kwargs["items"] == [{"id": "si_1", "quantity": 25}]
    assert kwargs["proration_behavior"] == "always_invoice"

def test_cancel_period_end_and_resume(stripe_client, stripe_mock):
    stripe_client.subscriptions.cancel("sub_1", timing=CancellationTiming.PERIOD_END,
                                          idempotency_key="sub_1:cancel:v1")
    assert stripe_mock.Subscription.modify.call_args.kwargs["cancel_at_period_end"] is True
    stripe_client.subscriptions.resume("sub_1", idempotency_key="sub_1:resume:v1")
    assert stripe_mock.Subscription.modify.call_args.kwargs["cancel_at_period_end"] is False
```

- [ ] **Step 2: Run tests and verify absent handlers**

Run: `uv run pytest tests/gateways/stripe/test_subscriptions.py tests/gateways/stripe/test_invoices.py -q`

Expected: FAIL with `CapabilityNotSupported`.

- [ ] **Step 3: Implement subscription translation**

Map `SetQuantity` to `{id, quantity}`, `ReplacePrice` to `{id, price/price_data, quantity?}`, `AddItem` to `{price/price_data, quantity}`, and `RemoveItem` to `{id, deleted: True}`. Map proration to `create_prorations`, `always_invoice`, or `none`. Immediate changes call `Subscription.modify`; `NEXT_CYCLE` uses a Subscription Schedule and then retrieves the current subscription. Pass the caller key unchanged.

- [ ] **Step 4: Implement retrieve/cancel/resume/invoice**

Immediate cancellation calls `Subscription.cancel`; period-end calls `Subscription.modify(cancel_at_period_end=True)`; resume retrieves first, rejects ended/canceled subscriptions, then modifies `cancel_at_period_end=False`. Invoice retrieval expands line price data. Strict mappings raise `GatewayProtocolError` for unknown financial status; `billing_reason=subscription_cycle` maps to `InvoiceReason.RENEWAL`.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/gateways/stripe/test_subscriptions.py tests/gateways/stripe/test_invoices.py -q`

Expected: PASS, including fixtures and unknown-status cases.

```bash
git add django_checkouts/gateways/stripe tests/gateways/stripe
git commit -m "feat: add Stripe recurring lifecycle"
```

---

### Task 6: Authenticate webhooks and reconcile events

**Files:**
- Create: `django_checkouts/gateways/stripe/webhooks.py`
- Create: `django_checkouts/gateways/stripe/handlers/events.py`
- Modify: `django_checkouts/gateways/stripe/{gateway,mapping}.py`
- Create: `tests/gateways/stripe/test_{webhooks,events}.py`
- Create: `tests/gateways/stripe/fixtures/{event_invoice_paid,event_unknown}.json`

**Interfaces:**
- Consumes: `VerifyWebhook`, `ListEvents`, normalized mappers.
- Produces: verified `WebhookEvent` and chronological `EventPage`.

- [ ] **Step 1: Write failing security/reconciliation tests**

```python
def test_verifies_original_bytes(stripe_client, stripe_mock, signed_payload):
    body, headers = signed_payload
    stripe_client.webhooks.verify(body, headers)
    stripe_mock.Webhook.construct_event.assert_called_once_with(
        payload=body, sig_header=headers["Stripe-Signature"], secret="whsec_test")

def test_unknown_event_is_preserved(stripe_client, stripe_mock):
    stripe_mock.Webhook.construct_event.return_value = load_fixture("event_unknown.json")
    event = stripe_client.webhooks.verify(b"{}", {"Stripe-Signature": "ok"})
    assert event.type is None
    assert event.event_type == "customer.tax_id.updated"

def test_half_open_reconciliation_window(stripe_client, stripe_mock, window):
    stripe_client.events.list(occurred_since=window.start, occurred_before=window.end, limit=50)
    assert stripe_mock.Event.list.call_args.kwargs["created"] == {
        "gte": int(window.start.timestamp()), "lt": int(window.end.timestamp())}
```

- [ ] **Step 2: Run tests and verify missing handlers**

Run: `uv run pytest tests/gateways/stripe/test_webhooks.py tests/gateways/stripe/test_events.py -q`

Expected: FAIL with `CapabilityNotSupported`.

- [ ] **Step 3: Verify before mapping and normalize taxonomy**

Call `stripe.Webhook.construct_event(payload=raw_body, sig_header=header, secret=secret)` before reading JSON. Translate invalid body/signature to `WebhookVerificationError`. Map checkout pending/paid/failed/expired/canceled, subscription created/updated/canceled, and invoice opened/paid/payment_failed/voided/uncollectible. Unknown remote event types use `type=None`. Never emit `subscription.renewed`; renewal is invoice paid with reason renewal.

- [ ] **Step 4: Implement reconciliation pagination**

Validate aware dates, `since < before`, and limit 1–100 before I/O. Call Stripe Events with `created={gte, lt}`, `starting_after=cursor`, and limit. Reverse Stripe's descending page into chronological order. Return the last remote ID as `next_cursor` only when `has_more`; preserve the requested window in every page.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/gateways/stripe/test_webhooks.py tests/gateways/stripe/test_events.py -q`

Expected: PASS for altered body, invalid signature, unknown/incomplete events, cursor, ordering, and windows.

```bash
git add django_checkouts/gateways/stripe tests/gateways/stripe
git commit -m "feat: add Stripe webhooks and reconciliation"
```

---

### Task 7: Complete errors, DRF integration, checks, and contract testing

**Files:**
- Modify: `django_checkouts/gateways/stripe/gateway.py`
- Modify: `django_checkouts/checks.py`
- Create: `django_checkouts/integrations/{__init__,drf}.py`
- Create: `django_checkouts/testing/contracts.py`
- Modify: `django_checkouts/testing/__init__.py`
- Create: `tests/gateways/stripe/test_errors.py`
- Create: `tests/test_{drf,checks,contract_suite}.py`

**Interfaces:**
- Consumes: complete client/gateway surface.
- Produces: public-only errors, DRF auth, system checks, and `GatewayContractSuite`.

- [ ] **Step 1: Write failing SDK error matrix**

Test rate limit/read connection failure as `GatewayTemporaryError+RETRY`; mutation timeout as `GatewayTemporaryError+RETRY_SAME_KEY`; idempotency conflict/uncertain mutation as `GatewayPermanentError+RECONCILE_FIRST`; invalid request as `GatewayPermanentError+NEVER`; authentication as `ConfigurationError`; missing resource as `ResourceNotFound`; invalid webhook as `WebhookVerificationError`. Assert no test catches `stripe.StripeError`.

- [ ] **Step 2: Implement exhaustive sanitized translation**

Translate every Stripe SDK branch above. Copy only request/error code and sanitized external message. Never include API key, webhook secret, headers, or raw payload in exception text/repr.

- [ ] **Step 3: Implement optional DRF authentication**

```python
class CheckoutWebhookAuthentication(BaseAuthentication):
    variant: Gateway | str
    def authenticate(self, request):
        event = get_checkout_gateway(self.variant).webhooks.verify(bytes(request.body), request.headers)
        return AnonymousUser(), event
```

Add `checkout_webhook_authentication(variant)` returning a concrete no-argument subclass. It sets `request.auth` to `WebhookEvent`; it adds no view, URL, persistence, or domain authorization.

- [ ] **Step 4: Implement non-network system checks**

For each configured variant import and instantiate the gateway, then append `gateway.check()` messages. Emit `django_checkouts.E001` for bad dotted path/config. Stripe requires non-empty API key and webhook secret for signed webhooks. Reject legacy provider paths. Never call Stripe.

- [ ] **Step 5: Publish fake and contract suite**

`GatewayContractSuite` must assert unique exact handlers, capability/handler agreement, validation before I/O, unchanged idempotency key, normalized result types, UTC dates, uppercase currency, immutable hidden raw, public-error-only behavior, verified event IDs, and unknown-event handling. Export both `FakeCheckoutGateway` and `GatewayContractSuite`.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/gateways/stripe/test_errors.py tests/test_drf.py tests/test_checks.py tests/test_contract_suite.py -q`

Expected: PASS and no external exception escapes.

```bash
git add django_checkouts/gateways/stripe/gateway.py django_checkouts/checks.py django_checkouts/integrations django_checkouts/testing tests
git commit -m "feat: publish gateway integration contracts"
```

---

### Task 8: Replace pre-1.0 surface, document, and verify release

**Files:**
- Modify: `django_checkouts/__init__.py`, `README.rst`, `CHANGELOG.md`, `docs/index.rst`, `test_settings.py`
- Delete: `django_checkouts/base.py`, `django_checkouts/authentication.py`, `django_checkouts/dto.py`, `django_checkouts/providers/`, `tests/providers/`
- Create: `docs/{quickstart,subscriptions,webhooks,reconciliation,errors-and-retries,gateway-options,writing-a-gateway,migration-pre-1.0}.rst`
- Create: `tests/test_public_interface.py`

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: final installable package for the Django template.

- [ ] **Step 1: Write failing structural interface tests**

Assert exact package exports `CheckoutClient`, `Gateway`, `get_checkout_gateway`; exact `inspect.signature` output for every resource method; static result types with `assert_type`; absence of Stripe SDK names in public annotations; and absence of legacy modules/exports.

- [ ] **Step 2: Run structural tests and verify legacy failure**

Run: `uv run pytest tests/test_public_interface.py -q`

Expected: FAIL because old exports/modules remain.

- [ ] **Step 3: Replace exports and remove legacy paths**

```python
from django_checkouts.client import CheckoutClient
from django_checkouts.enums import Gateway
from django_checkouts.registry import get_checkout_gateway

__all__ = ["CheckoutClient", "Gateway", "get_checkout_gateway"]
```

Change test settings to `django_checkouts.gateways.stripe.StripeGateway`. Delete legacy code only after Tasks 1–7 pass.

- [ ] **Step 4: Write complete public documentation**

Document configuration/quickstarts; absolute seat quantity, proration, cancellation/resume; raw-body verification and `(variant,event_id)` uniqueness; `[since,before)` reconciliation with overlap/dedup; every retry disposition; typed Stripe options and portability warning; gateway author interface/contract suite; every pre-1.0 old/new mapping. Every page says the library owns no persistence. README marks Stripe complete and Asaas/PagBank unimplemented and retains BSD-3-Clause.

- [ ] **Step 5: Run complete delivery gates**

```bash
uv sync --all-extras --all-groups
uv run pytest
uv run mypy django_checkouts
uvx ruff check .
uv run sphinx-build -W -b html docs docs/_build/html
uv build
rg -n "providers|Provider|get_checkout_provider|BaseCheckoutProvider|provider_options" django_checkouts tests README.rst docs -g '*.py' -g '*.rst'
rg -n "stripe\." django_checkouts/client.py django_checkouts/resources django_checkouts/types django_checkouts/capabilities.py django_checkouts/enums.py django_checkouts/exceptions.py
```

Expected: tests pass with at least 90% coverage; mypy/Ruff/Sphinx/build exit 0; wheel and sdist exist; the first scan finds old terms only in `docs/migration-pre-1.0.rst`; the second scan prints nothing.

- [ ] **Step 6: Commit release surface**

```bash
git add django_checkouts tests README.rst CHANGELOG.md docs test_settings.py pyproject.toml uv.lock
git commit -m "feat: publish recurring gateway interface"
```

---

## Template Handoff Gate

Do not implement billing in the Django template until this plan is complete and an installable library revision exists. Verify the five resources and structural tests, all Stripe lifecycle/contract tests, clean-environment wheel installation, immutable version/tag or VCS revision, and template usage without importing Stripe or reading `raw` on the primary path.
