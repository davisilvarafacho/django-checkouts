Assinaturas
===========

.. note::

   A biblioteca não possui persistência. Sua aplicação guarda a assinatura,
   o plano contratado e o histórico de mudanças.

Crie o checkout recorrente com ``CheckoutMode.SUBSCRIPTION``. Preços inline
exigem ``Recurrence``; alterações de assinatura Stripe aceitam preços de
catálogo.

Quantidade é absoluta
----------------------

``SetQuantity(item_id="si_123", quantity=5)`` significa "a quantidade passa a
ser 5", nunca "adicione 5". Isso torna reexecuções com a mesma chave
determinísticas.

.. code-block:: python

   from django_checkouts.enums import ChangeTiming, ProrationBehavior
   from django_checkouts.types import ChangeSubscription, SetQuantity

   subscription = client.subscriptions.change(
       "sub_123",
       ChangeSubscription(
           changes=(SetQuantity(item_id="si_123", quantity=5),),
           timing=ChangeTiming.IMMEDIATELY,
           proration=ProrationBehavior.CREATE_PRORATIONS,
       ),
       idempotency_key="sub_123:seats:5:v1",
   )

Prorrata
--------

``CREATE_PRORATIONS`` cria ajustes para a próxima fatura;
``INVOICE_IMMEDIATELY`` cria ajustes e tenta faturar agora; ``NONE`` muda sem
ajuste proporcional. ``ChangeTiming.NEXT_CYCLE`` agenda a mudança para o ciclo
seguinte. Confirme a capacidade do gateway antes de expor cada opção.

Cancelamento e retomada
-----------------------

Use ``CancellationTiming.IMMEDIATELY`` para encerrar agora ou ``PERIOD_END``
para agendar o fim do ciclo. ``resume`` desfaz somente um cancelamento agendado;
uma assinatura já encerrada não pode ser retomada.

.. code-block:: python

   from django_checkouts.enums import CancellationTiming

   client.subscriptions.cancel(
       "sub_123",
       timing=CancellationTiming.PERIOD_END,
       idempotency_key="sub_123:cancel:v1",
   )
   client.subscriptions.resume(
       "sub_123",
       idempotency_key="sub_123:resume:v1",
   )
