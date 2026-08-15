Reconciliação
==============

.. note::

   A biblioteca não possui persistência. Sua aplicação mantém cursores,
   checkpoints, eventos processados e a agenda de reconciliação.

Use reconciliação para recuperar webhooks perdidos e confirmar mutações cujo
resultado ficou incerto. A janela é sempre semiaberta
``[occurred_since, occurred_before)``: inclui o início e exclui o fim.

.. code-block:: python

   page = client.events.list(
       occurred_since=window_start,
       occurred_before=window_end,
       cursor=None,
       limit=100,
   )
   while page.next_cursor is not None:
       page = client.events.list(
           occurred_since=page.occurred_since,
           occurred_before=page.occurred_before,
           cursor=page.next_cursor,
           limit=100,
       )

Datas devem ter fuso e ``occurred_since`` deve ser anterior a
``occurred_before``. Itens chegam em ordem cronológica dentro da página.

Ao agendar execuções, sobreponha uma pequena faixa com a janela anterior para
absorver atraso de entrega e diferenças de relógio. Deduplique novamente por
``(variant, event_id)``; não avance o checkpoint antes de confirmar a transação
que aplicou todos os eventos.
