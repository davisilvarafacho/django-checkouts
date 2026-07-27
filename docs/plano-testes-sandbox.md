# Plano — testes contra sandbox real

Complementa, e não substitui, a suíte atual. Os 93 testes de hoje não tocam a
rede e continuam sendo o portão de todo commit. Esta suíte responde a outra
pergunta: **as nossas suposições sobre a API real estão certas?**

## 1. O que uma suíte de sandbox pode e não pode provar

Nos três provedores, o pagamento acontece numa página hospedada. Nenhum deles
tem endpoint de "pague este checkout". Consequência: **o pagador não é
automatizável** sem dirigir um browser, e o valor da suíte não está aí.

O que ela prova de verdade:

1. **Nossos payloads são aceitos.** Um campo com nome errado, um valor em reais
   onde o provedor quer centavos, um enum inválido — tudo isso vira 400 real, e
   é exatamente o que mock nenhum pega.
2. **Nossas fixtures não envelheceram.** As fixtures JSON dos testes unitários
   foram escritas por mim a partir da documentação. Se o provedor mudar um campo,
   só a chamada real percebe.
3. **Nosso `STATUS_MAP` cobre a realidade.** Como `map_status` levanta em status
   desconhecido, um status novo aparece como falha explícita.

O que ela **não** prova: que um pagamento real é processado corretamente. Isso
continua sendo roteiro manual.

## 2. Isolamento

Testes de sandbox **nunca** rodam junto com a suíte normal:

```toml
[tool.pytest.ini_options]
markers = ["sandbox: toca a API real do provedor; exige credenciais"]
addopts = [..., "-m", "not sandbox"]
```

Rodar de propósito:

```bash
uv run pytest -m sandbox
```

Regras:

- Credenciais só por variável de ambiente, nunca em arquivo versionado.
- Sem credencial → `pytest.skip`, não falha. Quem clona o repo sem conta de
  sandbox continua com a suíte verde.
- **Fora do gate de cobertura.** Cobertura mede a suíte determinística; misturar
  as duas tornaria o número dependente de rede.
- Todo recurso criado leva `reference_id` com prefixo `ci-` e timestamp, para dar
  para identificar e limpar.

Variáveis:

```bash
DJC_STRIPE_API_KEY=sk_test_...
DJC_STRIPE_WEBHOOK_SECRET=whsec_...
DJC_ASAAS_API_KEY=...
DJC_ASAAS_WEBHOOK_TOKEN=...
DJC_PAGSEGURO_TOKEN=...
DJC_PAGSEGURO_WEBHOOK_TOKEN=...
```

## 3. Estrutura

```
tests/sandbox/
  conftest.py                # skip_if_missing_credentials, prefixo ci-
  test_stripe_sandbox.py
  test_asaas_sandbox.py
  test_pagseguro_sandbox.py
```

## 4. A suíte de contrato

Os mesmos casos, parametrizados por provider, é o que dá valor real — a
divergência entre eles aparece sozinha:

| # | Caso | O que prova |
|---|---|---|
| 1 | `create_checkout` mínimo (1 item, cartão) | Payload básico aceito; devolve `external_id` e `url` |
| 2 | `retrieve_checkout` do que acabou de criar | Ida e volta; status inicial é `PENDING` |
| 3 | `create_checkout` com todos os campos opcionais | `customer`, `metadata`, `reference_id`, `expires_at` |
| 4 | `create_checkout` com pix | Meio aceito onde declaramos suportar |
| 5 | `create_checkout` com assinatura em cada `BillingCycle` suportado | **O teste mais valioso** — prova a conversão de ciclo contra a API real |
| 6 | `cancel_checkout` (onde há `Capability.CANCEL`) | Cancelamento e status resultante |
| 7 | Valor inválido de propósito | Vira `ProviderPermanentError`, não exceção crua |
| 8 | Credencial inválida | Vira `ProviderPermanentError`, não `KeyError` |
| 9 | `reference_id` volta em `retrieve` | Conciliação funciona |

Os casos 7 e 8 são os que mais protegem o usuário: são a prova de que nenhuma
exceção de `requests` ou do SDK vaza pela nossa fronteira.

### Regravar fixtures

A chamada real serve para regravar as fixtures dos testes unitários:

```bash
uv run pytest -m sandbox --record-fixtures
```

Grava a resposta crua em `tests/providers/<provider>/fixtures/`. O diff no git
vira a revisão: mudou campo, aparece no PR.

## 5. Webhooks

Cada provedor exige um tratamento diferente, e essa é a maior descoberta da
pesquisa:

| Provedor | Dá para testar webhook em sandbox? |
|---|---|
| **Stripe** | **Sim, e bem.** `stripe listen --forward-to` + `stripe trigger checkout.session.completed`. É o único com ferramenta oficial para isso. |
| **Asaas** | Parcial. Dá para cadastrar via `POST /v3/webhooks`, mas o disparo depende de mudar o estado da cobrança, e isso parece ser só por botão de painel. |
| **PagBank** | ⚠️ Provavelmente não. A doc diz que em sandbox o PagSeguro não envia retornos automaticamente, e há relato de que o `x-authenticity-token` nem chega. |

Por isso a **verificação de assinatura fica nos testes unitários, não aqui**: ela
é computação local (SHA-256, `compare_digest`, `construct_event`) e não precisa de
rede. Basta assinar um corpo com o segredo de teste e conferir que
`verify_webhook` aceita — o que já fazemos.

O único teste de webhook que vale no sandbox é o do Stripe, via CLI, e mesmo
esse depende de ter o binário instalado — então entra com `skip` próprio.

## 6. CI

**Não roda em PR.** Motivos: precisa de segredo (PR de fork não teria),
depende de serviço externo (falha de rede vira PR vermelho sem culpa do autor) e
é lento.

Proposta: job separado, `workflow_dispatch` + agendado semanalmente. Falha ali
abre issue, não bloqueia merge.

## 7. Ordem de execução sugerida

1. **Stripe primeiro.** O provider já existe; a suíte de sandbox valida o que
   está escrito e estabelece o formato que os outros dois vão copiar.
2. **Asaas em seguida.** É o mais simples dos dois que faltam: status conclusivo,
   sem homologação, sem os dois campos de webhook do PagBank. A conversão
   centavos ↔ reais é o principal risco, e é justamente o que a chamada real
   pega.
3. **PagBank por último**, e começando pela pergunta da homologação — ela pode
   ser o caminho crítico e é melhor descobrir isso antes de escrever código.

## 8. Perguntas que a primeira rodada precisa responder

Estão detalhadas em cada documento de provedor. As três que mais afetam o
desenho do núcleo:

1. **Asaas**: o `CHECKOUT_PAID` chega mesmo com `checkout.status == "ACTIVE"`?
   Se sim, o status precisa vir do tipo do evento, não do campo — e aí
   `map_status(str)` é abstração fraca demais.
2. **PagBank**: `AUTHORIZED` e `IN_ANALYSIS` aparecem em checkout? São dois
   estados sem equivalente limpo no nosso enum.
3. **Stripe**: qual o comportamento correto para `checkout.session.completed`
   com `payment_status="unpaid"` (pix/boleto emitido e não pago). Hoje
   traduzimos o evento para `CHECKOUT_PAID` enquanto o status resolve para
   `PENDING` — incoerência nossa, não do provedor.
