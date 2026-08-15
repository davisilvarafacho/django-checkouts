Migração da API anterior a 1.0
================================

.. warning::

   A biblioteca não possui persistência. A migração muda somente a fronteira
   de integração; models e dados continuam sob responsabilidade da aplicação.

A superfície experimental foi removida, sem aliases. Atualize todos os imports e
chamadas antes de instalar 1.0.

.. list-table:: Mapeamento antigo para novo
   :header-rows: 1
   :widths: 45 55

   * - Antes de 1.0
     - 1.0
   * - ``get_checkout_provider(variant)``
     - ``get_checkout_gateway(variant)``
   * - ``Provider``
     - ``Gateway``
   * - ``BaseCheckoutProvider``
     - ``BaseCheckoutGateway``
   * - ``django_checkouts.providers.stripe.StripeCheckoutProvider``
     - ``django_checkouts.gateways.stripe.StripeGateway``
   * - ``provider.create_checkout(...)``
     - ``client.checkouts.create(CheckoutCreate(...), idempotency_key=...)``
   * - ``provider.retrieve_checkout(id)``
     - ``client.checkouts.retrieve(id)``
   * - ``provider.cancel_checkout(id)``
     - ``client.checkouts.cancel(id, idempotency_key=...)``
   * - ``provider.verify_webhook(body, headers)``
     - ``client.webhooks.verify(body, headers)``
   * - ``dto.LineItem``
     - ``types.CheckoutItem`` com ``InlinePrice`` ou ``CatalogPrice``
   * - ``dto.CheckoutRequest``
     - ``types.CheckoutCreate``
   * - ``dto.CheckoutData``
     - ``types.Checkout``
   * - ``dto.WebhookPayload``
     - ``types.WebhookEvent``
   * - ``ProviderTemporaryError``
     - ``GatewayTemporaryError`` e ``retry_advice``
   * - ``ProviderPermanentError``
     - ``GatewayPermanentError`` e ``retry_advice``
   * - ``CheckoutNotFound``
     - ``ResourceNotFound``
   * - ``provider_options={...}``
     - ``gateway_options=StripeCheckoutOptions(...)``
   * - ``StripeWebhookAuthentication``
     - ``checkout_webhook_authentication(Gateway.STRIPE)``

Principais mudanças comportamentais
-----------------------------------

As mutações agora exigem chave de idempotência. Quantidades de assinatura são
absolutas. Resultados são dataclasses imutáveis e ``raw`` não deve alimentar
regras de negócio. Webhooks deduplicam por ``(variant, event_id)``. A
reconciliação usa janelas ``[since, before)``. Opções Stripe são tipadas e
explicitamente não portáveis.
