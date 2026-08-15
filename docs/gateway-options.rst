Opções específicas de gateway
==============================

.. note::

   A biblioteca não possui persistência. Opções de gateway não alteram essa
   fronteira nem salvam configuração por conta.

Use ``StripeCheckoutOptions`` para recursos do Stripe que não têm equivalente
portável:

.. code-block:: python

   from django_checkouts.gateways.stripe import StripeCheckoutOptions
   from django_checkouts.types import CheckoutCreate

   request = CheckoutCreate(
       items=items,
       success_url=success_url,
       gateway_options=StripeCheckoutOptions(
           allow_promotion_codes=True,
           automatic_tax=True,
           billing_address_required=True,
       ),
   )

Essas opções são tipadas e validadas contra o gateway ativo; não são um dict
livre para sobrescrever campos portáveis.

.. warning::

   Código que usa ``StripeCheckoutOptions`` deixa de ser portável. Isole-o na
   composição da requisição e ofereça um caminho sem extensões quando a mesma
   regra precisar funcionar em outro gateway.
