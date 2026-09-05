# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

## 1.0.0 (2026-09-05)


### Features

* add resource-oriented checkout client ([f047bdd](https://github.com/davisilvarafacho/django-checkouts/commit/f047bdded3f73f595ca02b62a3250b7309b22cbc))
* add Stripe recurring lifecycle ([c1b5449](https://github.com/davisilvarafacho/django-checkouts/commit/c1b54498c20cb4edf20a852cb2db4b0bfaf39a0c))
* add Stripe webhooks and reconciliation ([2fd4706](https://github.com/davisilvarafacho/django-checkouts/commit/2fd4706d777e926dbfca575d901f852fed66df92))
* add typed gateway dispatch ([c4c981e](https://github.com/davisilvarafacho/django-checkouts/commit/c4c981e0f8f2cc304e2f741fee9d1c607fc4ee91))
* adicionar setup de forma de pagamento ([83c1fb5](https://github.com/davisilvarafacho/django-checkouts/commit/83c1fb546b9269ed40af0dbb16d2492386d8208c))
* define normalized checkout contracts ([cb5a15e](https://github.com/davisilvarafacho/django-checkouts/commit/cb5a15ec6ba68b4e7e95cc815def27c05629195c))
* expor fatos financeiros de faturas Stripe ([4695875](https://github.com/davisilvarafacho/django-checkouts/commit/4695875a903e1ce4b628b41837efb86eefed7e8a))
* port Stripe checkout gateway ([ea47443](https://github.com/davisilvarafacho/django-checkouts/commit/ea47443512288400175d063cec9c351780f7395b))
* publish gateway integration contracts ([dddca1c](https://github.com/davisilvarafacho/django-checkouts/commit/dddca1c9aee029318375c1e8c26040a75102e819))
* publish recurring gateway interface ([733964a](https://github.com/davisilvarafacho/django-checkouts/commit/733964ae0cd9b253ac8c3a75dd83e205fd3bcbc2))


### Bug Fixes

* completar ciclo de setup de pagamento ([3c0b988](https://github.com/davisilvarafacho/django-checkouts/commit/3c0b988c9d8a78b3fd2723c939c131787f3d0d73))
* deeply normalize Stripe checkout responses ([d76b0b5](https://github.com/davisilvarafacho/django-checkouts/commit/d76b0b5c5be2cc758df54970de2cf1d7654e8d4a))
* harden normalized gateway contracts ([9a4fdd9](https://github.com/davisilvarafacho/django-checkouts/commit/9a4fdd90072ad7686277960eff78c03223af7eb8))
* normalizar eventos de setup ([ce17107](https://github.com/davisilvarafacho/django-checkouts/commit/ce17107186e2153b72efb4e9e5a432e67d7f48a1))
* normalize Stripe SDK checkout responses ([30d0af7](https://github.com/davisilvarafacho/django-checkouts/commit/30d0af77eada641a7d75eeda7a05303beb345f33))
* reject Stripe inline subscription prices ([3236c2c](https://github.com/davisilvarafacho/django-checkouts/commit/3236c2c4687538219dc8e461dd6788b688ff7da9))

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
