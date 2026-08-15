================
django-checkouts
================

``django-checkouts`` oferece uma fronteira tipada para checkout hospedado,
assinaturas, faturas, webhooks e reconciliação. Stripe está completo; Asaas e
PagBank ainda não estão implementados.

.. important::

   A biblioteca não possui persistência: não cria models nem grava dados. Sua
   aplicação é dona do banco, das transações, filas e regras de negócio.

.. toctree::
   :maxdepth: 2
   :caption: Guia público

   quickstart
   subscriptions
   webhooks
   reconciliation
   errors-and-retries
   gateway-options
   writing-a-gateway
   migration-pre-1.0
