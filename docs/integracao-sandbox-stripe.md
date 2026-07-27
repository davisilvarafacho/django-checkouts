# Integração e sandbox — Stripe

> Pesquisado em 27/07/2026 na documentação oficial. Itens marcados com ⚠️ **não
> foram confirmados** na fonte e precisam de validação manual antes de virarem
> teste automatizado.

## 1. Ambiente e credenciais

| | Valor |
|---|---|
| Painel de chaves de teste | https://dashboard.stripe.com/test/apikeys |
| Chave secreta de teste | `sk_test_...` |
| Base URL | Não se aplica — usamos o SDK oficial `stripe` |
| Sandboxes (isolados) | https://dashboard.stripe.com/sandboxes |

O Stripe tem **dois** conceitos de teste, e a diferença importa para CI:

- **Test mode** — o modo de teste embutido na sua conta. Compartilhado por todo
  mundo da conta.
- **Sandboxes** — ambientes isolados dentro da conta, criados sob demanda:
  *"an isolated test environment that allows you to test Stripe functionality in
  your account without affecting your live integration"*.

Para CI, **Sandbox é o certo**: dados de um job não poluem os de outro nem o test
mode que a equipe usa manualmente.

## 2. Como o checkout é criado

Não há chamada HTTP crua — usamos o SDK. Já implementado em
`django_checkouts/providers/stripe/checkout.py`.

```python
stripe.checkout.Session.create(
    mode="payment",                      # ou "subscription"
    line_items=[{
        "price_data": {
            "currency": "brl",
            "unit_amount": 4990,          # centavos
            "product_data": {"name": "Plano Pro"},
            # "recurring": {"interval": "month", "interval_count": 3},
        },
        "quantity": 1,
    }],
    success_url="https://exemplo.com.br/obrigado/",
    cancel_url="https://exemplo.com.br/carrinho/",
    payment_method_types=["card", "pix", "boleto"],
    client_reference_id="pedido-123",
    expires_at=1785000000,               # 30 min a 24 h a partir de agora
    api_key="sk_test_...",
)
```

Resposta relevante: `id`, `url`, `status` (`open`/`complete`/`expired`),
`payment_status` (`paid`/`unpaid`/`no_payment_required`), `amount_total`,
`currency`, `customer`, `customer_details`, `client_reference_id`, `expires_at`.

Cancelar = `stripe.checkout.Session.expire(id)`.

## 3. Dados de teste

### Cartões (confirmados na doc)

| Cenário | Número |
|---|---|
| Aprovado | `4242424242424242` |
| Exige 3DS | `4000002500003155` |
| Recusado | `4000000000009995` |
| **Aprovado, emissor no Brasil** | `4000000760000002` |

Atalhos sem passar pelo formulário: `pm_card_br` (PaymentMethod) e `tok_br`
(Token), ambos Visa do Brasil.

Qualquer CVC de 3 dígitos e qualquer validade futura funcionam.

### Pix

Ao pedir o CPF na tela do Pix, informe **`1234567890`**. O Stripe gera um QR code
de teste; ao lê-lo com a câmera comum do celular (não precisa de app de banco),
você cai numa página de teste do Stripe onde **escolhe** se a transação sucede ou
falha.

Consequência prática: **o Pix não é automatizável de ponta a ponta** sem
interação humana ou automação de browser. Ver §6.

### Boleto

Confirmado: o boleto é assíncrono, exige campo de CPF/CNPJ, e no Checkout você
seleciona Boleto e clica em pagar.

⚠️ **Não confirmei** qual CPF de teste usar, nem como forçar um boleto de teste a
ser liquidado ou expirar, nem em quanto tempo. É a maior lacuna deste documento.

## 4. Webhooks em sandbox

O Stripe CLI resolve o problema de expor a máquina local:

```bash
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe/
# imprime o whsec_... a usar como webhook_secret
```

Para capturar o segredo direto numa variável:

```bash
STRIPE_WEBHOOK_SECRET=$(stripe listen --print-secret)
```

Disparar eventos sem criar pagamento de verdade:

```bash
stripe trigger checkout.session.completed
```

Eventos que o nosso `EVENT_MAP` já traduz:

| Evento Stripe | Nosso `EventType` |
|---|---|
| `checkout.session.completed` | `CHECKOUT_PAID` |
| `checkout.session.async_payment_succeeded` | `CHECKOUT_PAID` |
| `checkout.session.async_payment_failed` | `CHECKOUT_FAILED` |
| `checkout.session.expired` | `CHECKOUT_EXPIRED` |

⚠️ Atenção a uma armadilha do nosso mapeamento: em pix/boleto,
`checkout.session.completed` chega com `payment_status="unpaid"` — a sessão
terminou, mas o dinheiro **não** entrou. Nosso `STATUS_MAP` já trata
(`complete/unpaid` → `PENDING`), mas o `EVENT_MAP` traduz o evento para
`CHECKOUT_PAID`. **Isso é uma inconsistência real do nosso código** e precisa de
teste em sandbox para decidir o comportamento certo.

## 5. Fluxo de teste manual (roteiro para validar o provider)

1. Criar Sandbox no painel, gerar `sk_test_...`.
2. `stripe listen --forward-to ...` numa aba.
3. `create_checkout` com cartão → abrir a `url` → pagar com `4000000760000002`.
4. Conferir que chega `checkout.session.completed` com `payment_status="paid"`.
5. `retrieve_checkout` → deve dar `CheckoutStatus.PAID`.
6. Repetir com `payment_methods=["pix"]` e observar o par
   `completed` (unpaid) → `async_payment_succeeded`.
7. `create_checkout` com `expires_at` de 30 min e chamar `cancel_checkout` →
   conferir `checkout.session.expired`.

## 6. O que dá para automatizar

| Operação | Automatizável em CI? | Como |
|---|---|---|
| `create_checkout` (todos os modos) | **Sim** | Chamada de API pura |
| `retrieve_checkout` | **Sim** | Idem |
| `cancel_checkout` | **Sim** | `Session.expire` é API pura |
| Validação de erro (400, credencial) | **Sim** | Payload inválido de propósito |
| Verificação de assinatura de webhook | **Sim** | Assinar o corpo com o `whsec` de teste e chamar `verify_webhook` — não precisa de rede |
| Pagamento com cartão | **Não** direto | Exige preencher o formulário hospedado; só com automação de browser |
| Pagamento Pix/Boleto | **Não** | Exige interação na página de simulação |

Conclusão: o valor da suíte de sandbox no Stripe está em provar que **os nossos
payloads são aceitos** e que **as respostas reais batem com o nosso
mapeamento** — não em simular o pagador.

## 7. Lacunas a resolver

- ⚠️ CPF de teste e simulação de liquidação/expiração de boleto.
- ⚠️ Confirmar se `expires_at` aceita assinatura (`mode=subscription`) ou só
  pagamento único.
- ⚠️ Confirmar o comportamento de `payment_method_types` com pix + assinatura —
  hoje recusamos localmente, mas convém confirmar que o Stripe também recusaria.
- Decidir o que fazer com `completed` + `unpaid` (ver §4).
