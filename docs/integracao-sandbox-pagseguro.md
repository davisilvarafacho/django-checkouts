# Integração e sandbox — PagBank (PagSeguro)

> Pesquisado em 27/07/2026 na documentação oficial. Itens marcados com ⚠️ **não
> foram confirmados** na fonte e precisam de validação manual antes de virarem
> teste automatizado.

## 1. Ambiente e credenciais

| | Valor |
|---|---|
| Base URL sandbox | `https://sandbox.api.pagseguro.com` |
| Base URL produção | `https://api.pagseguro.com` |
| Sandbox de transferência/Pix Bacen | `https://secure.sandbox.api.pagseguro.com` |
| Painel sandbox | https://sandbox.pagseguro.uol.com.br/ |
| Header de autenticação | `Authorization: Bearer <TOKEN>` |

Como obter o token de sandbox: painel → **Vendas Online** → **Integrações** →
*Gerar Token*. Se já tiver sido gerado, é reenviado ao e-mail de cadastro.

Duas particularidades confirmadas que não existem nos outros dois:

1. **O e-mail do comprador no sandbox precisa usar o domínio
   `@sandbox.pagseguro.com.br`.** Um e-mail normal não funciona no ambiente de
   teste.
2. **Há homologação obrigatória.** Depois dos testes em sandbox é preciso passar
   por certificação com o PagBank antes de ir a produção. Existe uma página
   "Solicitar homologação" no portal. ⚠️ Não confirmei o que a homologação exige
   — pode ser o item de maior prazo de todo o projeto e vale descobrir cedo.

## 2. Como o checkout é criado

`POST /checkouts`

Campos (todos confirmados na referência):

| Campo | Tipo | Obrigatório | Nota |
|---|---|---|---|
| `items` | array | **sim** | único campo obrigatório |
| `reference_id` | string | não | máx. 64 caracteres |
| `customer` | object | condicional | obrigatório se `customer_modifiable=false`, e aí todos os campos dele passam a ser obrigatórios |
| `customer_modifiable` | bool | não | default `true` |
| `expiration_date` | date-time | não | ISO-8601; default: criação + 2 h |
| `additional_amount` | int | não | centavos, máx. 999999900 |
| `discount_amount` | int | não | centavos |
| `shipping` | object | condicional | se houver entrega |
| `payment_methods` | array | não | meios aceitos |
| `payment_methods_configs` | array | não | só CREDIT_CARD e DEBIT_CARD |
| `soft_descriptor` | string | não | máx. 17 caracteres na fatura |
| `redirect_url` | string | não | máx. 255 |
| `redirect_waiting_time` | int | não | segundos, máx. 120 |
| `notification_urls` | array[string] | não | mudanças do **checkout**, máx. 100 chars |
| `payment_notification_urls` | array[string] | não | mudanças do **pagamento**, 5–100 chars |
| `recurrence_plan` | object | não | recorrência |
| `return_url` | string | não | máx. 255 |

Resposta: a URL de pagamento vem dentro de `links`:

```json
{
  "links": [
    {"rel": "PAY", "href": "https://pagamento.pagseguro.uol.com.br/pagamento?code=XXXX", "method": "GET"}
  ]
}
```

### Impactos diretos no nosso desenho

| Nosso conceito | PagBank | Consequência |
|---|---|---|
| `CheckoutData.url` | procurar `rel == "PAY"` em `links` | Não é um campo direto; o provider precisa varrer o array e falhar claro se não achar. |
| `success_url` | **dois** campos: `redirect_url` e `return_url` | ⚠️ Precisa descobrir a diferença. Provavelmente `redirect_url` = pós-pagamento, `return_url` = pós-transação. |
| Webhook único | **dois** campos: `notification_urls` e `payment_notification_urls` | O PagBank separa evento de checkout de evento de pagamento. Nosso `verify_webhook` vai receber os dois numa URL só, e o `_parse_webhook` precisa distinguir pelo formato do corpo. |
| `expires_at` | `expiration_date` ISO-8601 | Direto, sem janela mínima aparente (default 2 h). |
| `amount` em centavos | centavos também | ✅ Sem conversão, ao contrário do Asaas. |
| `provider_price_id` | não existe | Sem `Capability.PROVIDER_CATALOG`. |
| Assinatura | `recurrence_plan` | ⚠️ Estrutura e ciclos aceitos não confirmados. Bloqueia o mapeamento de `BillingCycle`. |

## 3. Status

⚠️ **Não consegui a lista completa de status de checkout.** A doc menciona
`ACTIVE`, e para pedidos/cobranças menciona `PAID`, `AUTHORIZED`, `DECLINED`,
`CANCELED`, `IN_ANALYSIS`, `WAITING`.

Isso é um problema real para o nosso desenho, porque `map_status` **levanta** em
status desconhecido. Dois deles não têm equivalente óbvio:

- `AUTHORIZED` — autorizado mas não capturado. Não é `PAID` (dinheiro não entrou)
  nem `PENDING` (o pagador já fez a parte dele).
- `IN_ANALYSIS` — em análise antifraude.

Ambos provavelmente mapeiam para `PENDING`, mas é decisão a tomar com dado real
na mão, não por dedução.

## 4. Webhooks

Verificação: header **`x-authenticity-token`**, contendo o
**SHA-256 hexadecimal de `<token>-<corpo cru>`**.

Fórmula confirmada na doc (exemplo oficial em Java):

```java
String sha256hex = DigestUtils.sha256Hex(token + "-" + requestBody);
```

O token vem do iBanking da conta. O payload precisa ser o **cru, sem formatação**
— reserializar quebra a validação. Nosso `Sha256BodyWebhookAuth` já implementa
exatamente isso e a mensagem de erro já aponta essa causa.

⚠️ **Alerta da comunidade:** há relatos de que o header `x-authenticity-token`
**não é enviado no sandbox**. Se confirmado, a verificação de webhook do PagBank
só é testável em produção — e a suíte de sandbox precisa de um caminho que
permita testar o parsing sem a assinatura.

⚠️ Payload de webhook de checkout não documentado na página que li (existe uma
seção `/reference/webhooks-checkout` separada). Para pedido/cobrança, o corpo
traz o objeto de pedido completo com array `charges` aninhado.

## 5. Dados de teste

Cartões de teste (confirmados, todos com validade `12/2026`):

| Bandeira | Aprovado | Recusado | CVV |
|---|---|---|---|
| Visa | `4539620659922097` | `4929291898380766` | 123 |
| Mastercard | `5240082975622454` | `5530062640663264` | 123 |
| Amex | `345817690311361` | `372938001199778` | 1234 |
| Elo | `4514161122113757` | `4389350446134811` | 123 |
| Hiper | `6062828598919021` | `6062822916014409` | 123 |

O cartão aprovado retorna `AUTHORIZED` ou `PAID`; o recusado, `DECLINED`.

⚠️ CPF de teste não documentado.

⚠️ **Aviso importante encontrado:** *"Em modo Sandbox, o PagSeguro não envia
retornos de transação automaticamente, porque não sabe se você quer testar uma
aprovação ou rejeição."* Se isso valer para o checkout, os webhooks em sandbox
podem precisar de disparo manual — o que inviabiliza teste de webhook automatizado
contra o sandbox real.

## 6. O que dá para automatizar

| Operação | Automatizável em CI? |
|---|---|
| Criar checkout, consultar | **Sim** |
| Extrair a URL de `links[rel=PAY]` | **Sim** |
| Validação de payload e credencial | **Sim** |
| Verificação do `x-authenticity-token` | **Sim**, sem rede — é só SHA-256 local |
| Receber webhook real em sandbox | ⚠️ Provavelmente **não** (§5) |
| Pagamento | **Não** — formulário hospedado |

## 7. Lacunas a resolver — este é o provider com mais incógnitas

Em ordem de risco:

1. ⚠️ **Homologação obrigatória**: o que exige, quanto demora. Pode ser o
   caminho crítico do projeto inteiro.
2. ⚠️ Lista completa de status de checkout, e o que fazer com `AUTHORIZED` e
   `IN_ANALYSIS`.
3. ⚠️ O `x-authenticity-token` chega no sandbox?
4. ⚠️ Estrutura do `recurrence_plan` e ciclos aceitos.
5. ⚠️ Diferença entre `redirect_url` e `return_url`.
6. ⚠️ Payload de webhook de checkout (`/reference/webhooks-checkout`).
7. ⚠️ Existe endpoint de cancelamento de checkout? Não encontrei — se não
   existir, o PagBank não declara `Capability.CANCEL`.
