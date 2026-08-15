# Task 2 — capabilities e despacho tipado

## Escopo entregue

- Capabilities aninhadas, `frozen` e com `slots`; os conjuntos são normalizados
  para `frozenset` e o mapa de meios de pagamento é protegido por
  `MappingProxyType`.
- Os dez comandos internos tipados e os contratos `ExecutionContext` e
  `CommandHandler`.
- `BaseCheckoutGateway` com índice de handlers por tipo **exato**, validação antes
  do contexto de I/O, tradução sanitizada de exceções externas e `check()` vazio.
- Testes de capabilities, despacho exato, ausência de handler, validação pré-I/O,
  propagação da variante e sanitização do erro externo.

## Evidência TDD

1. **RED** — após criar `tests/test_capabilities.py` e
   `tests/test_gateway_dispatch.py`, executei:

   ```console
   uv run pytest tests/test_capabilities.py tests/test_gateway_dispatch.py -q
   ```

   A coleta falhou como esperado com `ModuleNotFoundError` para
   `django_checkouts.capabilities`, pois os módulos de Task 2 ainda não existiam.
2. **GREEN** — implementei somente os módulos previstos no briefing. A rodada
   focada sem cobertura passou: `7 passed in 0.08s`.
3. **REFACTOR** — a anotação da coleção de handlers passou a usar
   `CommandHandler[Any]`, permitindo handlers concretos de diferentes resultados
   sem relaxar o despacho exato em runtime. A rodada focada, Ruff e mypy foram
   repetidos após a alteração.

## Arquivos alterados

- `django_checkouts/capabilities.py`
- `django_checkouts/gateways/commands.py`
- `django_checkouts/gateways/contracts.py`
- `django_checkouts/gateways/base.py`
- `tests/test_capabilities.py`
- `tests/test_gateway_dispatch.py`

## Verificação

```console
uv run pytest tests/test_capabilities.py tests/test_gateway_dispatch.py -q --no-cov
# 7 passed

uvx ruff check django_checkouts/capabilities.py django_checkouts/gateways tests/test_capabilities.py tests/test_gateway_dispatch.py
# All checks passed!

uv run mypy django_checkouts
# Success: no issues found in 27 source files

uv run pytest
# 118 passed; cobertura total 96.31%
```

## Auto-revisão e ressalvas

- O despacho usa `type(command)`, portanto subclasses não reutilizam handlers de
  comandos-base por engano.
- `validate()` é chamado antes de criar o contexto e antes de qualquer handler
  poder chamar `context.call`; comandos inválidos e sem handler não fazem I/O.
- `call()` preserva apenas `CheckoutError`; demais `Exception` viram
  `GatewayPermanentError` sem expor a mensagem externa.
- Não foram implementados handlers ou gateways concretos, que pertencem às tarefas
  posteriores. Handlers concretos devem fazer I/O exclusivamente via
  `ExecutionContext.call` para conservar a tradução de erros públicos.
