# Task 1 — vocabulário normalizado, DTOs e erros

## Implementação

- Substituído o vocabulário público de `Provider` por `Gateway`, preservando
  `Provider = Gateway` durante a migração dos módulos legados.
- Adicionados os enums normalizados de assinatura, fatura, evento, recurso,
  alterações e retry, todos com rótulos traduzíveis via `pgettext_lazy`.
- Criada a taxonomia pública de erros com `RetryAdvice`, a árvore de erros de
  gateway e aliases compatíveis para `ProviderTemporaryError`,
  `ProviderPermanentError` e `CheckoutNotFound`.
- Criado `GatewayOptions`, os DTOs públicos de checkout, assinatura, fatura e
  evento, e a reexportação explícita em `django_checkouts.types`.
- As dataclasses são congeladas, slotted e keyword-only (exceto
  `RetryAdvice`, cuja forma posicional é a indicada pela especificação).
- Centralizados os validadores de quantidades, moeda, UTC, criação de checkout
  e alterações de assinatura. Resultados e eventos fazem uma cópia defensiva
  de `raw` com `MappingProxyType(deepcopy(dict(...)))` e omitem esse campo do
  `repr` e da comparação.

## TDD

1. RED: criado `tests/test_types.py` com os três testes prescritos (dinheiro,
   imutabilidade/`raw`, quantidade) e executado
   `uv run pytest tests/test_types.py -q`. A coleta falhou como esperado com
   `ImportError: cannot import name 'Gateway'`.
2. RED ampliado: antes da implementação, os testes passaram a abranger itens
   vazios/moedas mistas/recorrência incompatível, quantidades booleanas,
   conflitos de alteração, UTC, cópia defensiva de `raw` e `RetryAdvice`.
   A execução continuou falhando pela mesma API inexistente.
3. GREEN: após a implementação, `uv run pytest tests/test_types.py
   tests/test_base.py -q --no-cov` passou com **32 testes**.

## Comandos e resultados

| Comando | Resultado |
| --- | --- |
| `uv run pytest tests/test_types.py -q` (RED) | coleta falhou: `Gateway` ausente |
| `uv run pytest tests/test_types.py tests/test_base.py -q --no-cov` | 32 passed |
| `uv run pytest -q` | 102 passed; cobertura total 94,39% |
| `uv run mypy django_checkouts` | sucesso, sem problemas |
| `uvx ruff check django_checkouts/enums.py django_checkouts/exceptions.py django_checkouts/gateways django_checkouts/types tests/test_types.py` | sucesso |
| `git diff --check` | sucesso |

O comando literal do brief, sem `--no-cov`, executa os 32 testes com sucesso,
mas termina com código 1 porque o gate global de 90% de cobertura é aplicado a
um subconjunto da suíte (64,03%); a suíte completa passa o gate com 94,39%.

## Arquivos alterados

- `django_checkouts/enums.py`
- `django_checkouts/exceptions.py`
- `django_checkouts/gateways/__init__.py`
- `django_checkouts/gateways/options.py`
- `django_checkouts/types/__init__.py`
- `django_checkouts/types/common.py`
- `django_checkouts/types/checkouts.py`
- `django_checkouts/types/subscriptions.py`
- `django_checkouts/types/invoices.py`
- `django_checkouts/types/events.py`
- `tests/test_types.py`

## Auto-revisão

- Conferidos os valores de todos os novos enums e os campos de `Checkout`,
  `Subscription`, `Invoice`, `WebhookEvent` e `EventPage` por introspecção de
  dataclasses.
- Confirmados `Price` e todos os DTOs no `__all__` explícito.
- Confirmadas as normalizações de moeda e UTC, a imutabilidade de dataclasses,
  a ocultação de `raw` no `repr` e a proteção contra mutação da raiz de `raw`.
- Mantida compatibilidade de imports legados necessária à suíte atual; não
  foram implementadas tarefas posteriores de gateways/resources.

## Pontos de atenção

- `uvx ruff check .` ainda acusa duas violações preexistentes em
  `django_checkouts/registry.py` (`S112` e `BLE001`); elas não pertencem a
  este escopo. O lint de todos os arquivos alterados está limpo.
- A especificação pede `MappingProxyType` na raiz de `raw`; portanto, valores
  aninhados continuam objetos mutáveis da cópia defensiva, exatamente conforme
  a construção prescrita.

## Correção da revisão — 2026-08-15

### RED/GREEN

1. RED: ampliados `tests/test_types.py` e `tests/test_base.py`; a execução de
   `uv run pytest tests/test_types.py tests/test_base.py -q --no-cov` falhou
   com 5 falhas esperadas: resultados aceitavam `bool`/`float`, `RetryAdvice`
   aceitava argumentos posicionais, `GatewayError` retinha token externo e o
   status financeiro desconhecido ainda levantava `ProviderPermanentError`.
2. GREEN: adicionada validação estrita de inteiro a todos os montantes públicos
   de resultado; valores negativos continuam permitidos para créditos e
   reembolsos. `RetryAdvice` passou a ser `frozen`, `slots` e `kw_only`.
   Mensagens externas de gateway são substituídas por diagnóstico seguro antes
   de serem armazenadas. `BaseCheckoutProvider.map_status` agora levanta
   `GatewayProtocolError`; a herança preserva a compatibilidade com o alias
   `ProviderPermanentError`.

### Evidência de testes

| Comando | Resultado |
| --- | --- |
| `uv run pytest tests/test_types.py tests/test_base.py -q --no-cov` (RED) | 5 failed, 31 passed — falhas esperadas descritas acima |
| `uv run pytest tests/test_types.py tests/test_base.py -q --no-cov` (GREEN) | 36 passed |
| `uv run pytest tests/providers/stripe/test_checkout.py -q --no-cov` | 32 passed |
| `uv run pytest -q` | 106 passed; cobertura total 94,67% |
| `uv run mypy django_checkouts` | sucesso, sem problemas |
| `uvx ruff check django_checkouts/exceptions.py django_checkouts/base.py django_checkouts/types tests/test_types.py tests/test_base.py` | sucesso |
| `git diff --check` | sucesso |

### Auto-revisão da correção

- Conferidos os sete campos monetários solicitados: todos recusam `bool` e
  `float`; nenhum impõe positividade nos resultados de gateway.
- Confirmado que segredos e tokens fornecidos via `gateway_message` não são
  armazenados nem aparecem em `repr`/`str`.
- Confirmado que o mapeamento desconhecido é `GatewayProtocolError`, mantendo
  captura legada como `ProviderPermanentError` para provedores existentes.
- Não há preocupações pendentes no escopo desta correção.
