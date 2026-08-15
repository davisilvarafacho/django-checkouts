# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

## 1.0.0

- Publica `CheckoutClient`, `Gateway` e `get_checkout_gateway` como entradas
  oficiais do pacote.
- Adiciona recursos tipados para checkouts, assinaturas, faturas, webhooks e
  reconciliação de eventos.
- Completa o ciclo Stripe de checkout e cobrança recorrente, com opções
  específicas tipadas e tradução pública de erros.
- Publica integração opcional com DRF, fake determinístico e suíte de contrato
  para gateways externos.
- Remove a superfície experimental anterior a 1.0; consulte o guia de migração.
- Mantém o projeto sob a licença BSD-3-Clause.
