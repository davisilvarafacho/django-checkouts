Quickstart
==========

.. note::

   A biblioteca não possui persistência. Salve IDs, estados e referências nos
   models da sua aplicação.

Instale o extra Stripe:

.. code-block:: console

   pip install 'django-checkouts[stripe]'

Configure ``django_checkouts`` em ``INSTALLED_APPS`` e uma variante em
``CHECKOUT_VARIANTS``:

.. code-block:: python

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

``python manage.py check`` valida credenciais e o caminho configurado sem fazer
I/O. Crie um checkout com dinheiro em centavos e chave de idempotência:

.. code-block:: python

   from django_checkouts import Gateway, get_checkout_gateway
   from django_checkouts.types import CheckoutCreate, CheckoutItem, InlinePrice

   client = get_checkout_gateway(Gateway.STRIPE)
   checkout = client.checkouts.create(
       CheckoutCreate(
           items=(
               CheckoutItem(
                   price=InlinePrice(name="Plano Pro", unit_amount=4990),
                   quantity=1,
               ),
           ),
           success_url="https://example.com/sucesso/",
           cancel_url="https://example.com/cancelado/",
           reference_id="order-42",
       ),
       idempotency_key="order-42:checkout:v1",
   )

Guarde ``checkout.external_id`` e redirecione para ``checkout.url``. Para
credenciais por conta, passe o override a ``get_checkout_gateway``; clientes
com override não entram no cache compartilhado.

Coleta de forma de pagamento
-----------------------------

Use ``client.setups.create(SetupCreate(...), idempotency_key=...)`` para abrir
uma sessão hospedada que apenas coleta uma forma de pagamento. O pedido não
aceita itens nem valor e o Stripe recebe ``mode=setup``; não substitua esse
fluxo por um item de preço zero.
