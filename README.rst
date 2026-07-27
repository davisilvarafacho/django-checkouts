===============
django-checkouts
===============

Checkout hospedado para Django com uma interface única e tipada, com foco no
mercado brasileiro. Você escreve o mesmo código para Stripe, PagBank e Asaas; a
lib traduz para a API de cada um e devolve dataclasses normalizados.

Estado
======

**MVP em construção.** O provider do Stripe está implementado; PagBank e Asaas
vêm em seguida. Parcelamento no cartão ("3x sem juros") está fora do MVP e entra
na v2 como ``CheckoutMode.INSTALLMENT``.

Instalação
==========

.. code-block:: console

   pip install 'django-checkouts[stripe]'

Adicione ao ``INSTALLED_APPS`` para habilitar os system checks:

.. code-block:: python

   INSTALLED_APPS = [
       ...,
       "django_checkouts",
   ]

Configuração
============

As credenciais de cada provedor ficam numa variante nomeada:

.. code-block:: python

   CHECKOUT_VARIANTS = {
       "stripe": (
           "django_checkouts.providers.stripe.StripeCheckoutProvider",
           {
               "api_key": env("STRIPE_API_KEY"),
               "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
               "sandbox": DEBUG,
           },
       ),
   }

Rode ``python manage.py check`` depois de configurar. Credencial ausente, chave
de produção em sandbox e sandbox com ``DEBUG=False`` viram mensagens ali, em vez
de 401 no primeiro cliente real.

Criando um checkout
===================

.. code-block:: python

   from django.shortcuts import redirect

   from django_checkouts import get_checkout_provider
   from django_checkouts.dto import Customer
   from django_checkouts.dto import LineItem
   from django_checkouts.enums import PaymentMethod

   def comprar(request, pedido_id):
       pedido = get_object_or_404(Pedido, pk=pedido_id)
       provider = get_checkout_provider("stripe")

       data = provider.create_checkout(
           items=[LineItem(name="Plano Pro", amount=4990)],  # centavos!
           success_url=request.build_absolute_uri(reverse("obrigado")),
           cancel_url=request.build_absolute_uri(reverse("carrinho")),
           payment_methods=[PaymentMethod.PIX, PaymentMethod.CARD],
           customer=Customer(email=request.user.email, tax_id=pedido.cpf),
           reference_id=str(pedido.pk),
       )

       pedido.checkout_id = data.external_id
       pedido.save(update_fields=["checkout_id"])
       return redirect(data.url)

Dinheiro é sempre ``int`` em centavos. R$ 49,90 é ``4990``, nunca ``49.90``.

Assinaturas
-----------

.. code-block:: python

   from django_checkouts.enums import BillingCycle, CheckoutMode
   from django_checkouts.dto import Recurrence

   data = provider.create_checkout(
       items=[LineItem(name="Plano Pro", amount=4990)],
       success_url=...,
       mode=CheckoutMode.SUBSCRIPTION,
       recurrence=Recurrence(cycle=BillingCycle.QUARTERLY),
   )

``BillingCycle`` tem opções fechadas em vez do par ``interval`` +
``interval_count`` do Stripe, porque Asaas e PagBank só aceitam ciclos nomeados
e um ``interval_count=5`` não teria para onde ir. Cada provider converte:
``QUARTERLY`` vira ``interval="month", interval_count=3`` no Stripe.

Multi-tenant
------------

Passe as credenciais direto e elas se mesclam por cima das de ``settings``:

.. code-block:: python

   provider = get_checkout_provider("asaas", api_key=tenant.asaas_key)

Instâncias com override não são cacheadas.

Webhooks
========

**A lib não traz view nem rota de webhook.** Roteamento, transação, fila e o que
fazer com um pagamento confirmado são decisões do seu projeto, e qualquer default
seria engessado. O que ela traz é a parte idêntica em todo projeto e fácil de
errar em silêncio: provar que a requisição veio mesmo do provedor, e normalizar
o payload.

Com DRF, use a authentication class — a verificação acontece antes de a view
rodar e o payload chega em ``request.auth``:

.. code-block:: python

   from rest_framework.response import Response
   from rest_framework.views import APIView

   from django_checkouts.authentication import StripeWebhookAuthentication
   from django_checkouts.enums import EventType

   class StripeWebhookView(APIView):
       authentication_classes = [StripeWebhookAuthentication]
       permission_classes = []

       def post(self, request):
           evento = request.auth          # WebhookPayload já verificado
           if evento.type == EventType.CHECKOUT_PAID:
               liberar_pedido(evento.reference_id)
           return Response(status=200)

Sem DRF, chame o provider direto:

.. code-block:: python

   from django_checkouts.exceptions import WebhookVerificationError

   @csrf_exempt
   @require_POST
   def stripe_webhook(request):
       provider = get_checkout_provider("stripe")
       try:
           evento = provider.verify_webhook(request.body, request.headers)
       except WebhookVerificationError:
           return HttpResponse(status=400)
       ...
       return HttpResponse(status=200)

Passe ``request.body`` **cru**. Reserializar o JSON antes da verificação invalida
a assinatura do Stripe e o hash do PagBank — é a causa nº 1 de webhook que
"não confere".

Idempotência: webhooks são *at least once*
------------------------------------------

Todo provedor reenvia o webhook se a sua view demorar, cair ou responder 5xx.
Sem deduplicar, "pagamento confirmado" vira crédito em dobro. Use
``payload.event_id`` como chave.

O jeito mais durável é uma tabela sua com ``UniqueConstraint`` em ``event_id``,
dentro da mesma transação que credita o pedido. Se preferir o cache do Django,
``cache.add()`` é a primitiva atômica certa:

.. code-block:: python

   from django.core.cache import cache

   if not cache.add(f"checkout:evt:{evento.event_id}", True, timeout=60 * 60 * 24):
       return HttpResponse(status=200)  # já processado

**Atenção ao backend de cache.** O recomendado é ter um processo dedicado de
cache — Redis ou Memcached. Mas se você não tem nenhum dos dois,
``DatabaseCache`` resolve sem precisar subir instância nova:

.. list-table::
   :header-rows: 1

   * - Backend
     - Compartilhado entre workers?
     - ``add()`` atômico?
     - Serve para dedup?
   * - ``LocMemCache`` (**padrão se você não configurar nada**)
     - Não, um por processo
     - Só dentro do processo
     - **Não**
   * - ``DatabaseCache``
     - Sim
     - Sim (INSERT com unique)
     - **Sim**
   * - ``FileBasedCache``
     - Sim, na mesma máquina
     - Não, tem race
     - Fraco
   * - Redis / Memcached
     - Sim
     - Sim
     - Sim

O caso ruim é justamente o padrão: com ``LocMemCache`` e quatro workers de
gunicorn, o reenvio cai em outro processo, o dedup não enxerga nada e o
pagamento é processado duas vezes — e some tudo a cada deploy.
``DatabaseCache`` só precisa de:

.. code-block:: console

   python manage.py createcachetable

Capacidades por provedor
========================

Cada provider declara o que faz em ``CAPABILITIES``; pedir o que ele não suporta
levanta ``CapabilityNotSupported`` **antes** de qualquer chamada de rede, em vez
de virar um 400 obscuro.

.. list-table::
   :header-rows: 1

   * - Capacidade
     - Stripe
     - PagBank
     - Asaas
   * - Cartão / Pix / Boleto
     - sim
     - a fazer
     - a fazer
   * - Assinatura
     - sim (só cartão)
     - a fazer
     - a fazer
   * - Cancelar pela API
     - sim (expira a sessão)
     - a fazer
     - a fazer
   * - Validade definida por você
     - sim (30 min a 24 h)
     - a fazer
     - a fazer
   * - Preço de catálogo (``provider_price_id``)
     - sim
     - não tem catálogo
     - não tem catálogo

Tratamento de erro
==================

Os erros carregam a semântica de retry no próprio tipo:

.. code-block:: python

   from django_checkouts.exceptions import ProviderPermanentError
   from django_checkouts.exceptions import ProviderTemporaryError

   try:
       data = provider.create_checkout(...)
   except ProviderTemporaryError:
       ...  # timeout, 5xx, rate limit — repetir é seguro
   except ProviderPermanentError:
       ...  # 400, credencial inválida — repetir dá no mesmo

Um status que a lib não conhece levanta ``ProviderPermanentError`` pedindo que
você o acrescente ao ``STATUS_MAP``, em vez de virar um ``UNKNOWN`` silencioso
que circularia pelo seu código como se fosse estado legítimo.

Desenvolvimento
===============

Instale o `uv <https://docs.astral.sh/uv/getting-started/installation/>`_ e
prepare o ambiente:

.. code-block:: console

   uv sync --all-extras

Execute as verificações:

.. code-block:: console

   uv run pytest
   uv run mypy django_checkouts
   uvx ruff check .

A suíte exige 90% de cobertura para passar. Nenhum teste toca a rede: os SDKs e
as respostas HTTP são substituídos, com fixtures de payload real em
``tests/providers/<provider>/fixtures/``.
