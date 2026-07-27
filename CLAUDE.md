# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

`django-checkouts` — biblioteca (não projeto Django) que dá uma interface única e tipada
para checkout hospedado de Stripe, PagBank e Asaas, com foco no mercado brasileiro.
**MVP em construção:** só o Stripe está implementado; PagBank e Asaas ainda não existem
como código (só como docs de pesquisa em `docs/`).

A lib **não tem models, views, urls nem migrations** — ela nunca toca o banco. Recebe
argumentos simples, devolve dataclasses normalizados; a persistência é do projeto que a usa.

## Comandos

```console
uv sync --all-extras          # ambiente (uv >= 0.11.28, Python 3.12 via .python-version)
uv run pytest                 # suíte completa; gate de 90% de cobertura
uv run pytest tests/providers/stripe/test_checkout.py::TestCreateCheckout::test_builds_inline_price_data
uv run pytest -q --no-cov     # rodada rápida sem o relatório de cobertura
uv run mypy django_checkouts
uvx ruff check .
```

`pytest` usa `test_settings.py` como `DJANGO_SETTINGS_MODULE` (sqlite em memória, uma
variante `stripe` já configurada com credenciais falsas).

## Arquitetura

### O contrato dos providers (`base.py`)

`BaseCheckoutProvider` divide público de protegido, e a divisão é o coração da lib:

- **Público e concreto** (`create_checkout`, `retrieve_checkout`, `cancel_checkout`,
  `verify_webhook`) — vive na base, valida tudo o que dá para validar sem rede e levanta
  `ValidationError`/`CapabilityNotSupported` **antes de qualquer I/O**.
- **Protegido e abstrato** (`_create_checkout`, `_retrieve_checkout`, `_cancel_checkout`,
  `_parse_webhook`) — é o que um provider novo escreve. Recebe um `CheckoutRequest` já
  validado e pode confiar nele.

`build_request()` é o funil de validação; `CheckoutRequest` existe justamente para que
acrescentar um campo em `create_checkout` não mude a assinatura de todos os providers.

### Registry e configuração (`registry.py`)

Providers são "variantes nomeadas" em `settings.CHECKOUT_VARIANTS`:
`{"stripe": ("caminho.pontilhado.Classe", {**kwargs_do_construtor})}`.
`get_checkout_provider("stripe")` cacheia a instância em `PROVIDER_CACHE`;
`get_checkout_provider("asaas", api_key=...)` (com overrides) **não** cacheia — é o caso
multi-tenant. `conftest.py` limpa o cache entre testes por autouse fixture.

### As duas direções de autenticação

Fácil de confundir; são módulos separados de propósito:

- `credentials.py` — **saída** (app → gateway). `BaseAuth`/`TokenAuth` aplicam o header de
  API numa sessão de requests. Token com `repr=False` para não vazar em traceback.
- `webhooks.py` — **entrada** (gateway → app). `BaseWebhookAuth` prova a origem e devolve
  o payload já decodificado. Comparação de segredo sempre com `hmac.compare_digest`.
  `HeaderTokenWebhookAuth` (modelo Asaas) e `Sha256BodyWebhookAuth` (modelo PagBank) já
  existem, sem provider que as use ainda.

Ambos expõem `validate() -> list[CheckMessage]`, e `checks.py` transforma isso em saída do
`manage.py check` — credencial ausente vira erro de deploy, não 401 no primeiro cliente.

`authentication.py` é a camada DRF opcional: `webhook_auth_for(Provider.STRIPE)` fabrica a
authentication class, e o `WebhookPayload` verificado chega em `request.auth`. O
`request.user` vira um `FakeGatewayUser` — usuário falso, sem banco, que só existe porque o
DRF exige o par `(user, auth)`.

### Invariantes que atravessam tudo

- **Dinheiro é sempre `int` em centavos.** R$ 49,90 é `4990`. `amount_decimal` /
  `amount_total_decimal` existem só para exibição.
- **Todo objeto de resposta carrega `raw`** — o payload cru intacto. Para visão tipada do
  cru, cada provider declara uma subclasse de `ProviderState` (`from_raw` descarta chaves
  desconhecidas, então campo novo do provedor não quebra nada).
- **Corpo cru de webhook, sempre.** Reserializar o JSON invalida a assinatura do Stripe e o
  hash do PagBank.
- **`map_status` levanta no desconhecido; `map_event` devolve `None`.** Não há
  `CheckoutStatus.UNKNOWN`: um status não mapeado circularia como estado legítimo e só
  apareceria na conciliação de dinheiro. Evento desconhecido é o oposto — os provedores
  emitem dezenas de eventos sem relação com checkout, e derrubar o webhook por causa deles
  travaria a fila de notificações da conta.
- **Nada que não seja `CheckoutError` sai de um provider.** Se `requests.Timeout` ou
  `KeyError` vazar, é bug. A divisão `ProviderTemporaryError` vs `ProviderPermanentError`
  carrega a semântica de retry no próprio tipo.
- **Capacidades opcionais são declaradas, não improvisadas.** `CAPABILITIES`,
  `SUPPORTED_PAYMENT_METHODS` e `SUPPORTED_CYCLES` fazem a base recusar de forma uniforme,
  antes da rede, em vez de cada provider levantar `NotImplementedError` do seu jeito.
- **`BillingCycle` tem opções fechadas** (nomes seguem os do Asaas, o vocabulário mais
  restrito dos três). Expor o par `interval`+`interval_count` do Stripe não sobreviveria à
  tradução. Cada provider converte: `QUARTERLY` → `("month", 3)` no Stripe.

### Escrever um provider novo

Subclassear `BaseCheckoutProvider`; definir `name`, `STATUS_MAP`, `EVENT_MAP`,
`CAPABILITIES`, `SUPPORTED_PAYMENT_METHODS`, `SUPPORTED_CYCLES`, `state_class`; no
`__init__` montar `self.auth` e `self.webhook_auth`; implementar os quatro métodos
protegidos. O Stripe (`providers/stripe/checkout.py`) é o modelo de referência — inclusive
do `_call()`, que traduz os erros do SDK para a taxonomia da lib. Note que o `STATUS_MAP`
dele é chaveado por `f"{status}/{payment_status}"`, porque no Stripe "a sessão terminou" e
"o dinheiro entrou" são campos diferentes.

## Convenções

- **Português (pt-BR) em docstrings, mensagens de erro e comentários.** As mensagens são
  longas de propósito: dizem o que fazer, não só o que falhou. Mantenha esse tom.
- Enums são `models.TextChoices` com `pgettext_lazy` — serializam como string direto num
  campo de model e o rótulo é traduzível.
- **Identidade de provedor é `Provider`, nunca string solta.** `name = Provider.STRIPE`,
  `get_checkout_provider(Provider.STRIPE)`, `webhook_auth_for(Provider.PAGSEGURO)`. Como é
  `TextChoices`, o membro casa com a chave string do `CHECKOUT_VARIANTS` em `settings` —
  e o settings do usuário continua com string crua, porque um módulo de settings não deve
  importar a lib. String crua no código só para variante com nome próprio (`"stripe-br"`,
  multi-tenant); por isso as anotações são `Provider | str`.
- Ruff: um import por linha (`force-single-line`) e `from __future__ import annotations`
  obrigatório no topo de todo módulo, inclusive testes.
- Nenhum teste toca a rede: SDK e respostas HTTP são substituídos, com fixtures de payload
  real em `tests/providers/<provider>/fixtures/`. A fixture `load_fixture` do `conftest.py`
  resolve o caminho ao lado do módulo de teste.
- Versão vem do `setuptools_scm` (tag git) e é escrita em `django_checkouts/version.py`,
  que é gitignored.

## `docs/`

Notas de pesquisa, não documentação de usuário: `integracao-sandbox-{stripe,pagseguro,asaas}.md`
levantam as particularidades de cada API (credenciais, sandbox, formato de webhook) e
marcam com ⚠️ o que **não** foi confirmado na fonte oficial. `plano-testes-sandbox.md`
descreve uma suíte contra sandbox real, ainda não implementada. Ao implementar PagBank ou
Asaas, esses arquivos são o ponto de partida — e os itens ⚠️ precisam de validação antes de
virarem código.
