# django-checkouts — ciclo recorrente stateless e interface de gateways

## Status e ordem de execução

Este design foi validado no brainstorming de 6 de agosto de 2026. Ele define um
subprojeto exclusivo do repositório `django-checkouts` e deve ser implementado,
testado, documentado e publicado antes de o template Django implementar planos,
assinaturas, seats ou entitlements.

O template consumidor não poderá importar o SDK do Stripe nem compensar lacunas
do gateway com código específico. Se o contrato normalizado ainda não cobrir uma
operação necessária, a evolução acontece primeiro nesta biblioteca.

## Objetivo

Transformar `django-checkouts` numa biblioteca open source, stateless e
desacoplada para checkout hospedado e ciclo recorrente completo. A primeira
implementação end-to-end será o Stripe; a interface deve permitir Asaas,
PagBank e gateways comunitários sem alterar os callers.

A biblioteca será responsável por:

- checkout hospedado para pagamento único e assinatura;
- consulta e cancelamento de checkouts;
- consulta, alteração, cancelamento e retomada de assinaturas;
- alteração de quantidade, inclusive seats, e de preços;
- normalização de invoices, estados recorrentes e webhooks;
- autenticação de webhooks;
- reconciliação de eventos perdidos;
- capabilities técnicas de cada gateway;
- validação anterior ao I/O;
- tradução de erros e orientação de retry;
- testes de contrato reutilizáveis por autores de gateways.

## Fora do escopo

A biblioteca não terá:

- models, migrations ou persistência;
- views ou URLs próprias;
- organizações, vínculos, seats, planos comerciais ou entitlements;
- filas, workers ou garantia exactly-once;
- política de trial, grace period, inadimplência ou bloqueio de produto;
- cálculo fiscal, ledger ou emissão de nota fiscal;
- credenciais específicas de um tenant persistidas pela biblioteca;
- implementação vazia ou anunciada de Asaas/PagBank no primeiro marco.

Persistência, idempotência recebida, decisões comerciais e efeitos sobre acesso
pertencem ao projeto consumidor.

## Vocabulário

- **Gateway**: plataforma financeira externa, como Stripe, Asaas ou PagBank.
- **Variant**: configuração concreta de um gateway, como `stripe-br` ou
  `stripe-us`. É a chave de `settings.CHECKOUT_VARIANTS`.
- **External ID**: identificador atribuído pelo gateway.
- **Reference ID**: identificador de domínio fornecido pelo caller e devolvido
  pelo gateway quando suportado.
- **Gateway options**: opções tipadas, deliberadamente não portáveis, para
  recursos exclusivos de um gateway.
- **Raw**: payload original preservado numa resposta normalizada.

Toda a nomenclatura pública anterior baseada em `provider` será substituída por
`gateway`: diretórios, classes, campos, capabilities, options e funções.

## Arquitetura

O seam externo para projetos consumidores é `CheckoutClient`, dividido em
recursos navegáveis. O seam para autores de gateways é `BaseCheckoutGateway`.
Entre eles existem comandos tipados internos, despachados para handlers do
gateway.

```text
Projeto consumidor
        |
        v
CheckoutClient
 |- checkouts
 |- subscriptions
 |- invoices
 |- webhooks
 `- events
        |
        v
comandos internos tipados
        |
        v
BaseCheckoutGateway
 |- StripeGateway
 |- futuro AsaasGateway
 `- gateways comunitários
```

Os callers não executam comandos diretamente. Os comandos formam uma interface
suportada apenas para autores de gateways e para a suíte de contrato. Isso
mantém a interface cotidiana descobrível sem voltar a uma classe base crescente
com um método abstrato por operação.

## Interface para projetos consumidores

### Registry e cliente

```python
class CheckoutClient:
    gateway: Gateway | str
    variant: str
    capabilities: GatewayCapabilities

    checkouts: CheckoutResource
    subscriptions: SubscriptionResource
    invoices: InvoiceResource
    webhooks: WebhookResource
    events: EventResource


def get_checkout_gateway(
    variant: Gateway | str,
    **credential_overrides: object,
) -> CheckoutClient: ...
```

`gateway` identifica a implementação; `variant` identifica a conta/configuração.
IDs remotos e eventos devem ser persistidos pelo consumidor junto da variant.

Configuração:

```python
CHECKOUT_VARIANTS = {
    "stripe-br": (
        "django_checkouts.gateways.stripe.StripeGateway",
        {
            "api_key": env("STRIPE_API_KEY"),
            "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
            "sandbox": DEBUG,
        },
    ),
}
```

Instâncias sem overrides podem ser cacheadas por variant. Instâncias criadas
com overrides não são cacheadas, preservando o uso multi-account.

### Checkouts

```python
class CheckoutResource:
    def create(
        self,
        request: CheckoutCreate,
        *,
        idempotency_key: str,
    ) -> Checkout: ...

    def retrieve(self, external_id: str) -> Checkout: ...

    def cancel(
        self,
        external_id: str,
        *,
        idempotency_key: str,
    ) -> Checkout: ...
```

`cancel()` atua somente sobre um checkout ainda cancelável. Ele não cancela a
assinatura eventualmente criada pelo checkout.

### Assinaturas

```python
class SubscriptionResource:
    def retrieve(self, external_id: str) -> Subscription: ...

    def change(
        self,
        external_id: str,
        request: ChangeSubscription,
        *,
        idempotency_key: str,
    ) -> Subscription: ...

    def cancel(
        self,
        external_id: str,
        *,
        timing: CancellationTiming,
        idempotency_key: str,
    ) -> Subscription: ...

    def resume(
        self,
        external_id: str,
        *,
        idempotency_key: str,
    ) -> Subscription: ...
```

`resume()` remove um cancelamento agendado para o fim do período. Não revive
uma assinatura encerrada e não retoma automaticamente uma assinatura pausada
por outro motivo.

### Invoices

```python
class InvoiceResource:
    def retrieve(self, external_id: str) -> Invoice: ...
```

### Webhooks e eventos

```python
class WebhookResource:
    def verify(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> WebhookEvent: ...


class EventResource:
    def list(
        self,
        *,
        occurred_since: datetime,
        occurred_before: datetime,
        cursor: str | None = None,
        limit: int = 100,
    ) -> EventPage: ...
```

`EventResource.list()` é reconciliação, não analytics. É uma capability
opcional: gateways sem log remoto consultável falham localmente com
`CapabilityNotSupported`.

## DTOs públicos

Todos os DTOs são dataclasses `frozen=True`, `slots=True` e `kw_only=True`.
Nenhum tipo do SDK do gateway aparece nas anotações públicas.

### Preços, itens e cliente

```python
class InlinePrice:
    name: str
    unit_amount: int
    currency: str = "BRL"
    description: str | None = None
    image_url: str | None = None


class CatalogPrice:
    external_id: str


Price = InlinePrice | CatalogPrice


class CheckoutItem:
    price: Price
    quantity: int = 1
    reference_id: str | None = None


class Customer:
    name: str | None = None
    email: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    external_id: str | None = None


class Recurrence:
    cycle: BillingCycle
    description: str | None = None
```

Dinheiro é sempre `int` na menor unidade monetária. Para BRL, R$ 49,90 é
`4990`. `float` e `bool` são recusados. Todos os itens inline de um checkout
devem usar a mesma moeda.

Em assinatura, `recurrence` é obrigatória quando existe preço inline e proibida
em pagamento único. Um preço de catálogo pode carregar sua recorrência no
gateway; nesse caso `recurrence` é opcional. Se os dados conhecidos forem
incompatíveis, a biblioteca falha antes do I/O; incompatibilidades existentes
apenas no catálogo remoto são traduzidas para `GatewayPermanentError` durante
a execução.

### Criação de checkout

```python
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
```

### Alterações de assinatura

```python
class SetQuantity:
    item_id: str
    quantity: int


class ReplacePrice:
    item_id: str
    price: Price
    quantity: int | None = None


class AddItem:
    price: Price
    quantity: int = 1


class RemoveItem:
    item_id: str


SubscriptionChange = SetQuantity | ReplacePrice | AddItem | RemoveItem


class ChangeSubscription:
    changes: tuple[SubscriptionChange, ...]
    timing: ChangeTiming = ChangeTiming.IMMEDIATELY
    proration: ProrationBehavior = ProrationBehavior.CREATE_PRORATIONS
    metadata: Mapping[str, str] | None = None
    gateway_options: GatewayOptions | None = None
```

Quantidades são absolutas, inteiras e positivas. Zero não significa remoção;
o caller usa `RemoveItem`. Duas alterações conflitantes sobre o mesmo item são
recusadas. Uma mudança com múltiplas operações só é aceita quando o gateway
declara execução atômica; a biblioteca não simula atomicidade com várias
chamadas remotas.

### Resultados normalizados

```python
class Checkout:
    external_id: str
    gateway: Gateway | str
    variant: str
    status: CheckoutStatus
    mode: CheckoutMode
    url: str | None
    amount_total: int
    currency: str
    customer: Customer | None
    reference_id: str | None
    subscription_id: str | None
    expires_at: datetime | None
    created_at: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)


class SubscriptionItem:
    external_id: str
    price_id: str | None
    quantity: int
    unit_amount: int | None
    currency: str | None
    billing_cycle: BillingCycle | None
    raw: Mapping[str, object] = field(repr=False, compare=False)


class Subscription:
    external_id: str
    gateway: Gateway | str
    variant: str
    status: SubscriptionStatus
    customer_id: str | None
    items: tuple[SubscriptionItem, ...]
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_end: datetime | None
    cancel_at: datetime | None
    canceled_at: datetime | None
    ended_at: datetime | None
    latest_invoice_id: str | None
    reference_id: str | None
    metadata: Mapping[str, str]
    raw: Mapping[str, object] = field(repr=False, compare=False)


class InvoiceLine:
    external_id: str
    description: str | None
    quantity: int
    unit_amount: int | None
    amount: int
    currency: str
    subscription_item_id: str | None
    period_start: datetime | None
    period_end: datetime | None
    raw: Mapping[str, object] = field(repr=False, compare=False)


class Invoice:
    external_id: str
    gateway: Gateway | str
    variant: str
    status: InvoiceStatus
    reason: InvoiceReason
    subscription_id: str | None
    customer_id: str | None
    amount_due: int
    amount_paid: int
    amount_remaining: int
    currency: str
    lines: tuple[InvoiceLine, ...]
    due_at: datetime | None
    paid_at: datetime | None
    next_payment_attempt_at: datetime | None
    attempt_count: int
    hosted_url: str | None
    reference_id: str | None
    raw: Mapping[str, object] = field(repr=False, compare=False)
```

`raw` é uma cópia defensiva do payload original recebido do gateway. Ele existe
em todos os recursos normalizados e eventos, fica fora de `repr`/comparação e
pode conter PII. A documentação proíbe logá-lo indiscriminadamente. Campos
desconhecidos do gateway não quebram a construção do DTO normalizado.

Todas as datas devolvidas são timezone-aware e normalizadas para UTC. Moedas
usam ISO 4217 em maiúsculas.

## Gateway options

`GatewayOptions` é um marcador tipado para recursos exclusivos de um gateway.
O caminho portável não depende dele.

```python
class GatewayOptions:
    gateway: ClassVar[Gateway | str]


class StripeCheckoutOptions(GatewayOptions):
    gateway = Gateway.STRIPE

    allow_promotion_codes: bool = False
    automatic_tax: bool = False
    billing_address_required: bool = False
```

Uso explícito:

```python
CheckoutCreate(
    ...,
    gateway_options=StripeCheckoutOptions(
        allow_promotion_codes=True,
        automatic_tax=True,
    ),
)
```

A option deve corresponder ao gateway do cliente. Ela não pode conter objetos
do SDK nem sobrescrever silenciosamente itens, preços, moeda, URLs,
idempotency key ou outros campos portáveis. Cada tipo de operação pode ter uma
classe de options própria dentro do módulo do gateway.

## Estados e eventos

Enums continuam baseados em `models.TextChoices`, com valores estáveis e labels
traduzíveis.

Estados mínimos:

- checkout: `pending`, `paid`, `expired`, `canceled`, `failed`;
- assinatura: `incomplete`, `trialing`, `active`, `past_due`, `paused`,
  `unpaid`, `canceled`, `expired`;
- invoice: `draft`, `open`, `paid`, `void`, `uncollectible`.

Eventos normalizados:

```text
checkout.pending
checkout.paid
checkout.failed
checkout.expired
checkout.canceled

subscription.created
subscription.updated
subscription.canceled

invoice.opened
invoice.paid
invoice.payment_failed
invoice.voided
invoice.uncollectible
```

Não existe `subscription.renewed`: renovação é `invoice.paid` com
`invoice.reason == RENEWAL`. Inadimplência é `invoice.payment_failed`,
acompanhada do snapshot atualizado quando o gateway o fornece. Isso evita dois
eventos canônicos para o mesmo fato financeiro.

```python
class WebhookEvent:
    gateway: Gateway | str
    variant: str
    event_id: str
    event_type: str
    type: EventType | None
    occurred_at: datetime
    resource_kind: ResourceKind | None
    resource_id: str | None
    resource: Checkout | Subscription | Invoice | None
    livemode: bool | None
    raw: Mapping[str, object] = field(repr=False, compare=False)


class EventPage:
    items: tuple[WebhookEvent, ...]
    next_cursor: str | None
    occurred_since: datetime
    occurred_before: datetime
```

O corpo cru do webhook é autenticado antes do parse. Evento desconhecido
produz `type=None`, preservando `event_type` e `raw`; status financeiro
desconhecido gera erro permanente de protocolo, não um estado `unknown`.

Webhooks são at-least-once e podem chegar fora de ordem. O consumidor persiste
unicidade em `(variant, event_id)` e não deve regredir estado com base apenas na
ordem de chegada.

Reconciliação usa janela semifechada `[occurred_since, occurred_before)`, cursor
opaco e ordem cronológica. Todas as páginas mantêm a mesma janela. Eventos
conciliados preservam os mesmos IDs dos webhooks. O consumidor usa pequena
sobreposição entre janelas e deduplica pelos IDs.

## Capabilities

Capabilities descrevem funcionalidades técnicas do gateway; não são
entitlements comerciais de um plano.

```python
class GatewayCapabilities:
    checkouts: CheckoutCapabilities
    subscriptions: SubscriptionCapabilities
    invoices: InvoiceCapabilities
    webhooks: WebhookCapabilities
    reconciliation: ReconciliationCapabilities
```

Elas informam, de forma somente leitura:

- modos e meios de pagamento compatíveis;
- ciclos de cobrança;
- preços inline e de catálogo;
- expiração customizada e prefill de cliente;
- alteração de quantidade e preço;
- adição e remoção de itens;
- timings e comportamentos de proration;
- cancelamento imediato ou ao fim do período;
- remoção de cancelamento agendado;
- atomicidade de alterações múltiplas;
- invoices, webhooks assinados e reconciliação de eventos.

O caller comum não precisa consultar capabilities: todo resource valida a
operação automaticamente antes do I/O e levanta uma mensagem acionável. A
consulta pública existe para interfaces dinâmicas e integrações avançadas.
Restrições dinâmicas da conta do merchant ainda podem ser recusadas durante a
execução.

## Idempotência, erros e retry

Toda mutação exige `idempotency_key` explícita. A biblioteca não inventa a
chave. Um retry usa exatamente a mesma chave e o mesmo conteúdo; reutilizar a
chave com semântica diferente é erro.

```text
CheckoutError
|- ConfigurationError
|- ValidationError
|- CapabilityNotSupported
|- UnsupportedPaymentMethod
|- WebhookVerificationError
`- GatewayError
   |- GatewayTemporaryError
   `- GatewayPermanentError
      |- GatewayProtocolError
      `- ResourceNotFound
```

Nenhuma exceção de SDK, HTTP client ou parser atravessa a interface.

```python
class RetryDisposition(models.TextChoices):
    NEVER = "never"
    RETRY = "retry"
    RETRY_SAME_KEY = "retry_same_key"
    RECONCILE_FIRST = "reconcile_first"


class RetryAdvice:
    disposition: RetryDisposition
    retry_after: timedelta | None = None
```

Política:

- validação, configuração, capability e webhook inválido: `NEVER`;
- rate limit e indisponibilidade confirmada: `RETRY`;
- timeout durante mutação: `RETRY_SAME_KEY`;
- resultado remoto incerto ou conflito: `RECONCILE_FIRST`.

Erros de gateway carregam `gateway`, `variant`, código externo, mensagem
externa sanitizada e `RetryAdvice`. Segredos nunca aparecem em `repr`, logs ou
mensagens públicas.

## Interface para gateways

A documentação usará “interface para gateways”, não a sigla SPI.

```python
class BaseCheckoutGateway:
    name: Gateway | str
    capabilities: GatewayCapabilities
    handlers: tuple[CommandHandler, ...]

    def execute(
        self,
        command: GatewayCommand[ResultT],
    ) -> ResultT: ...

    def check(self) -> Sequence[CheckMessage]: ...
```

`execute()` é concreto na base: valida o comando, verifica capabilities,
despacha pelo tipo exato e garante a tradução de erros. Handler ausente produz
`CapabilityNotSupported`, nunca `NotImplementedError`.

```python
class CommandHandler(Protocol[CommandT, ResultT]):
    command_type: type[CommandT]

    def handle(
        self,
        command: CommandT,
        context: ExecutionContext,
    ) -> ResultT: ...
```

Commands e handlers são estáveis para autores de gateways, mas não são o
caminho normal de projetos consumidores.

## Stripe no primeiro marco

`StripeGateway` implementará end-to-end:

- criar, consultar e cancelar Checkout Session;
- checkout de assinatura somente com cartão;
- preço inline e preço de catálogo;
- consultar Subscription;
- alterar quantidade/preço e adicionar/remover itens conforme capability;
- proration suportada pelo Stripe;
- cancelar imediatamente ou ao fim do período;
- remover cancelamento agendado via `resume()`;
- consultar Invoice;
- verificar e normalizar webhooks de checkout, subscription e invoice;
- listar eventos para reconciliação;
- traduzir todas as exceções do SDK;
- preservar payloads crus;
- aplicar idempotency key nas mutações.

Asaas e PagBank permanecem pesquisa/documentação até um marco próprio. Não
existirão packages vazios que deem impressão de suporte.

## Estrutura de arquivos

```text
django_checkouts/
|- __init__.py
|- apps.py
|- checks.py
|- client.py
|- registry.py
|- capabilities.py
|- enums.py
|- exceptions.py
|- resources/
|  |- checkouts.py
|  |- subscriptions.py
|  |- invoices.py
|  |- webhooks.py
|  `- events.py
|- types/
|  |- common.py
|  |- checkouts.py
|  |- subscriptions.py
|  |- invoices.py
|  `- events.py
|- gateways/
|  |- base.py
|  |- commands.py
|  |- contracts.py
|  |- options.py
|  `- stripe/
|     |- gateway.py
|     |- capabilities.py
|     |- options.py
|     |- mapping.py
|     |- webhooks.py
|     `- handlers/
|        |- checkouts.py
|        |- subscriptions.py
|        |- invoices.py
|        `- events.py
|- integrations/
|  `- drf.py
`- testing/
   |- contracts.py
   `- fakes.py
```

Quando Asaas for implementado, repetirá a forma interna do Stripe em
`gateways/asaas/`, com `gateway.py`, capabilities, options, mappings, webhooks
e handlers próprios.

## Integração opcional com DRF

A biblioteca continuará oferecendo autenticação opcional de webhook para DRF,
agora em `django_checkouts.integrations.drf`. A classe/factory autentica o corpo
cru e entrega `WebhookEvent` em `request.auth`. Ela não fornece view, rota,
persistência nem autorização de domínio.

## Validação estrutural e testes

A interface é a superfície principal de testes. O gate de entrega exige:

- testes de `inspect.signature` para classes e métodos públicos;
- testes estáticos que confirmem o tipo retornado por cada resource;
- snapshot explícito dos exports do pacote;
- verificação de que nenhum tipo do SDK Stripe aparece em anotações públicas;
- testes unitários dos DTOs e de todas as invariantes;
- matriz operação x capability, garantindo falha antes de I/O;
- suíte pública de contrato executada pelo Stripe e pelo fake gateway;
- fixtures reais de checkout, subscription, invoice e webhook;
- status desconhecidos, eventos desconhecidos e payloads incompletos;
- corpo adulterado, assinatura inválida e corpo reserializado;
- webhooks duplicados, atrasados e fora de ordem;
- todos os erros do SDK traduzidos com retry correto;
- timeout de mutação repetido com a mesma idempotency key;
- paginação e sobreposição de janelas de reconciliação;
- preservação de `raw` sem incluí-lo em `repr`;
- teste garantindo que nenhuma exceção externa escape;
- testes sandbox Stripe separados da suíte determinística.

A biblioteca exportará:

```python
from django_checkouts.testing import FakeCheckoutGateway
from django_checkouts.testing import GatewayContractSuite
```

Um gateway comunitário poderá executar a mesma suíte de contrato sem copiar os
testes do Stripe.

Os gates atuais permanecem: pytest com pelo menos 90% de cobertura, mypy e
Ruff. A documentação deve incluir quickstart, assinaturas, webhooks,
reconciliação, erros/retry, gateway options, interface para gateways e migração
pré-1.0.

## Migração da interface pré-1.0

Como ainda não existem tags estáveis nem consumidores registrados, a interface
pode ser substituída antes da versão 1.0. O guia de migração mapeará:

- `get_checkout_provider()` para `get_checkout_gateway()`;
- `BaseCheckoutProvider` para `BaseCheckoutGateway`;
- `Provider` para `Gateway`;
- `create_checkout()` para `client.checkouts.create()`;
- `retrieve_checkout()` para `client.checkouts.retrieve()`;
- `cancel_checkout()` para `client.checkouts.cancel()`;
- `verify_webhook()` para `client.webhooks.verify()`;
- `provider_options` para `gateway_options` tipadas;
- `CheckoutData` para `Checkout`;
- `WebhookPayload` para `WebhookEvent`.

Após a primeira versão estável, a biblioteca seguirá SemVer e depreciação
explícita. Mudanças incompatíveis exigirão major version.

## Open source e documentação

O pacote continua sob licença BSD-3-Clause. A interface para gateways, a suíte
de contrato, o fake gateway e exemplos completos serão documentação pública.
O README deve deixar explícito o que a biblioteca não persiste e mostrar como o
consumer implementa idempotência de webhooks.

O changelog separará mudanças para consumidores das mudanças para autores de
gateways. A primeira release deste design só anunciará Stripe como suportado.

## Critérios de aceitação

O subprojeto estará concluído quando:

1. a interface pública orientada a resources existir com a nomenclatura
   `gateway`;
2. todos os DTOs e invariantes descritos estiverem implementados;
3. Stripe cobrir checkout, subscription, invoice, webhook e reconciliação;
4. toda mutação exigir idempotency key;
5. nenhuma exceção ou tipo do SDK escapar;
6. capabilities forem públicas e validadas antes do I/O;
7. raw for preservado com proteção contra logging acidental;
8. fake gateway e suíte pública de contrato estiverem disponíveis;
9. testes determinísticos, mypy, Ruff e documentação passarem;
10. a migração pré-1.0 estiver publicada;
11. uma release instalável da biblioteca estiver disponível para o template;
12. o template conseguir integrar checkout e ciclo recorrente sem importar
    Stripe nem acessar `raw` no caminho principal.

Somente depois desses critérios a spec do template poderá transformar eventos
financeiros normalizados em assinatura de organização, seats e entitlements.
