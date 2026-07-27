# Integração e sandbox — Asaas

> Pesquisado em 27/07/2026 na documentação oficial. Itens marcados com ⚠️ **não
> foram confirmados** na fonte e precisam de validação manual antes de virarem
> teste automatizado.

## 1. Ambiente e credenciais

| | Valor |
|---|---|
| Criar conta sandbox | https://sandbox.asaas.com/ |
| Base URL sandbox | `https://api-sandbox.asaas.com/v3` |
| Base URL produção | `https://api.asaas.com/v3` |
| Header de autenticação | `access_token: <API_KEY>` (sem esquema, sem `Bearer`) |

Três pontos confirmados que mudam o planejamento:

1. **A conta sandbox é separada da de produção.** Mesmo tendo conta Asaas ativa,
   é preciso criar uma conta específica no sandbox.
2. **A API Key é irrecuperável.** Ela aparece **uma única vez** na criação. Se
   perder, gera outra. Isso significa: guardar no gerenciador de segredos do CI
   no momento em que for criada.
3. Chave de sandbox só funciona na URL de sandbox, e vice-versa.

Erro de chave inválida: `401` com `"A chave de API fornecida é inválida"`.

## 2. Como o checkout é criado

`POST /v3/checkouts`

```json
{
  "billingTypes": ["PIX", "CREDIT_CARD"],
  "chargeTypes": ["DETACHED"],
  "minutesToExpire": 60,
  "externalReference": "pedido-123",
  "callback": {
    "successUrl": "https://exemplo.com.br/obrigado/",
    "cancelUrl": "https://exemplo.com.br/carrinho/",
    "expiredUrl": "https://exemplo.com.br/expirou/"
  },
  "items": [
    {
      "externalReference": "SKU-1",
      "name": "Plano Pro",
      "description": "Assinatura mensal",
      "quantity": 1,
      "value": 49.90,
      "imageBase64": null
    }
  ],
  "customerData": {
    "name": "Maria Souza",
    "cpfCnpj": "12345678909",
    "email": "maria@exemplo.com.br",
    "phone": "11999999999"
  }
}
```

Resposta: `id`, `link` (URL da página de pagamento), `status`, `billingTypes`,
`chargeTypes`, `minutesToExpire`, `externalReference`.

### Impactos diretos no nosso desenho

| Nosso conceito | Asaas | Consequência |
|---|---|---|
| `amount` em **centavos** (`int`) | `value` em **reais** (`49.90`) | O provider precisa dividir por 100 na saída e multiplicar na entrada. Ponto de erro de arredondamento — usar `Decimal`, nunca `float`. |
| `PaymentMethod.BOLETO` | `billingTypes` aceita só `PIX` e `CREDIT_CARD` | **Boleto não existe no checkout do Asaas.** `SUPPORTED_PAYMENT_METHODS` fica sem `BOLETO`. |
| `expires_at` (datetime) | `minutesToExpire`, de **10 a 1440** | Converter datetime → minutos e recusar fora da janela, como já fazemos no Stripe. |
| `LineItem.image_url` | `imageBase64` | Não é URL. Ou baixamos e codificamos, ou declaramos que não suportamos e ignoramos. |
| `CheckoutMode.SUBSCRIPTION` | `chargeTypes: ["RECURRENT"]` + objeto `subscription` | Direto. |
| `provider_price_id` | não existe | Sem `Capability.PROVIDER_CATALOG`. |

Parcelamento existe (`chargeTypes: ["INSTALLMENT"]` + `installment.maxInstallmentCount`
de 1 a 21), mas está fora do MVP — fica pra v2.

### Ciclos de assinatura

O nosso `BillingCycle` foi desenhado a partir do vocabulário do Asaas, então o
mapeamento é 1:1: `WEEKLY`, `BIWEEKLY`, `MONTHLY`, `BIMONTHLY`, `QUARTERLY`,
`SEMIANNUALLY`, `YEARLY`.

⚠️ Confirmar os campos exatos do objeto `subscription` no checkout (a doc cita
`cycle`, `nextDueDate`, `endDate`).

## 3. Status

`status` do checkout: `ACTIVE`, `CANCELED`, `EXPIRED`, `PAID`.

Mapeamento direto para o nosso `CheckoutStatus`:

| Asaas | Nosso |
|---|---|
| `ACTIVE` | `PENDING` |
| `PAID` | `PAID` |
| `EXPIRED` | `EXPIRED` |
| `CANCELED` | `CANCELED` |

Note que aqui **não** há o problema do par composto que o Stripe tem — o status
do checkout já é conclusivo.

## 4. Webhooks

Configuração por API: `POST /v3/webhooks` com `url`, `sendType`, `enabled`,
`email` e o array `events`.

Eventos de checkout: `CHECKOUT_CREATED`, `CHECKOUT_CANCELED`, `CHECKOUT_EXPIRED`,
`CHECKOUT_PAID`.

Autenticação: header **`asaas-access-token`**, com o token que você cadastrou.
É token estático — prova origem, não integridade do corpo. Nosso
`HeaderTokenWebhookAuth` já cobre exatamente isso.

Payload:

```json
{
  "id": "evt_...",
  "event": "CHECKOUT_PAID",
  "dateCreated": "2024-10-31 18:07:47",
  "account": {"id": "...", "ownerId": null},
  "checkout": {
    "id": "...", "link": null, "status": "ACTIVE",
    "minutesToExpire": 10, "billingTypes": [...], "chargeTypes": [...],
    "callback": {...}, "items": [...], "subscription": {...},
    "installment": null, "split": [...],
    "customer": "cus_...", "customerData": null
  }
}
```

⚠️ **Reparar na inconsistência do exemplo oficial:** o evento é `CHECKOUT_PAID`
mas `checkout.status` vem `"ACTIVE"`. Se isso for real e não erro de doc, **não
podemos derivar o status do campo `status`** — teríamos que derivá-lo do tipo do
evento. É a pergunta mais importante a responder no sandbox antes de escrever o
provider.

### Entrega e retry

- Semântica *at least once* — confirmado. Deduplicar por `id` do evento.
- Resposta fora de 2xx provoca novas tentativas.
- **Falhas repetidas interrompem a fila** da conta. Isso é grave: um bug na
  sua view não atrasa só um evento, ele para todos.
- Eventos são retidos por no máximo **14 dias**.

## 5. Dados de teste

- Cartão de teste citado na doc: **`5162306219378829`**, validade `05/2024`,
  CCV `318`. ⚠️ A validade no exemplo está no passado — confirmar se o sandbox
  aceita ou se é preciso uma data futura.
- No sandbox, **transações de cartão são aprovadas automaticamente**.
- Nenhum pagamento é de fato compensado — é só simulação.
- ⚠️ CPF/CNPJ de teste não documentado na página que li.

### Ações manuais de sandbox

O painel do sandbox tem botões para mudar o estado de uma cobrança:

- **Confirmar pagamento** — funciona para cartão de crédito.
- **Receber cobrança** — liquida um pagamento de cartão.
- Forçar o vencimento de uma cobrança.

⚠️ A doc **não expõe endpoints de API** para essas ações — só botões de painel.
Se for confirmado, o sandbox do Asaas **não é automatizável de ponta a ponta**
para o fluxo de pagamento.

## 6. O que dá para automatizar

| Operação | Automatizável em CI? |
|---|---|
| Criar checkout, consultar, cancelar | **Sim** |
| Validação de payload (400) e de credencial (401) | **Sim** |
| Conversão centavos ↔ reais | **Sim**, e é onde mais vale testar |
| Configurar webhook via `POST /v3/webhooks` | **Sim** |
| Verificar `asaas-access-token` | **Sim**, sem rede |
| Marcar checkout como pago | ⚠️ Provavelmente **não** — só pelo painel |

## 7. Lacunas a resolver

- ⚠️ O `status` no payload do `CHECKOUT_PAID` vem mesmo `"ACTIVE"`? (§4)
- ⚠️ Existe rota de API só de sandbox para liquidar cobrança? (§5)
- ⚠️ Campos exatos do objeto `subscription` dentro do checkout.
- ⚠️ Validade do cartão de teste `05/2024`.
- ⚠️ O sandbox aceita URL de webhook em `localhost`/ngrok? A doc não diz.
- Definir o que fazer com `imageBase64` (baixar e converter, ou não suportar).
