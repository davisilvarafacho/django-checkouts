===============
django-checkouts
===============

Checkout hospedado e cobrança recorrente para Django por uma interface única,
tipada e orientada a recursos. O gateway Stripe está completo; integrações com
Asaas e PagBank ainda não estão implementadas.

A biblioteca não cria models e não persiste checkouts, assinaturas, faturas ou
eventos. A aplicação decide seu modelo de dados, transações, filas e regras de
negócio.

Instalação
==========

.. code-block:: console

   pip install 'django-checkouts[stripe]'

Adicione ``django_checkouts`` ao ``INSTALLED_APPS`` e configure uma variante:

.. code-block:: python

   INSTALLED_APPS = [
       ...,
       "django_checkouts",
   ]

   CHECKOUT_VARIANTS = {
       "stripe": (
           "django_checkouts.gateways.stripe.StripeGateway",
           {
               "api_key": env("STRIPE_API_KEY"),
               "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
               "sandbox": DEBUG,
           },
       ),
   }

Use ``python manage.py check`` para validar a configuração sem fazer chamadas
externas.

Primeiro checkout
=================

Valores monetários são inteiros na menor unidade da moeda: R$ 49,90 é ``4990``.
Toda mutação exige uma chave de idempotência estável.

.. code-block:: python

   from django.shortcuts import redirect

   from django_checkouts import Gateway, get_checkout_gateway
   from django_checkouts.enums import PaymentMethod
   from django_checkouts.types import CheckoutCreate, CheckoutItem, InlinePrice

   client = get_checkout_gateway(Gateway.STRIPE)
   result = client.checkouts.create(
       CheckoutCreate(
           items=(
               CheckoutItem(
                   price=InlinePrice(name="Plano Pro", unit_amount=4990),
                   quantity=1,
               ),
           ),
           success_url="https://example.com/obrigado/",
           cancel_url="https://example.com/carrinho/",
           payment_methods=(PaymentMethod.CARD,),
           reference_id="pedido-123",
       ),
       idempotency_key="pedido-123:checkout:v1",
   )
   return redirect(result.url)

O cliente publica cinco recursos: ``checkouts``, ``subscriptions``,
``invoices``, ``webhooks`` e ``events``. Resultados são dataclasses imutáveis e
normalizados; o campo ``raw`` é somente leitura, oculto do ``repr`` e deve ser
usado apenas para diagnóstico.

Webhooks e reconciliação
========================

Sempre verifique os bytes originais do corpo:

.. code-block:: python

   event = client.webhooks.verify(request.body, request.headers)

Persista a deduplicação na sua aplicação com unicidade em
``(variant, event_id)``. Para recuperar eventos perdidos, percorra janelas
semiabertas ``[occurred_since, occurred_before)`` e deduplique a sobreposição.

Documentação
=============

A documentação completa cobre assinaturas, webhooks, reconciliação, erros,
opções Stripe, autoria de gateways e migração da API anterior a 1.0 em
``docs/``.

Desenvolvimento
===============

.. code-block:: console

   uv sync --all-extras --all-groups
   uv run pytest
   uv run mypy django_checkouts
   uvx ruff check .
   uv run sphinx-build -W -b html docs docs/_build/html
   uv build

Licença
========

BSD-3-Clause. Consulte ``LICENSE``.
