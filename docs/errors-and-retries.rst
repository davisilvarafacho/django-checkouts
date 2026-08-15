Erros e repetições
==================

.. note::

   A biblioteca não possui persistência. Sua aplicação registra tentativas,
   agenda repetições e conserva chaves de idempotência.

Capture ``CheckoutError`` na fronteira. ``ValidationError`` e
``CapabilityNotSupported`` acontecem antes de I/O; ``ConfigurationError`` pede
correção de deploy; ``WebhookVerificationError`` recusa entrada não autenticada;
``ResourceNotFound`` informa ausência remota; erros de gateway carregam
``retry_advice`` sem expor mensagens ou segredos do SDK.

Cada ``RetryDisposition`` tem uma ação exata:

``NEVER``
   Não repita sem corrigir entrada, configuração ou estado. É a disposição
   padrão de erros permanentes.

``RETRY``
   Repita uma consulta ou operação segura. Respeite ``retry_after`` quando
   informado e use backoff com jitter.

``RETRY_SAME_KEY``
   Repita a mutação com a mesma chave de idempotência, nunca com uma nova.

``RECONCILE_FIRST``
   O resultado pode ter sido aplicado remotamente. Consulte o recurso ou liste
   eventos antes de decidir se deve repetir.

.. code-block:: python

   from django_checkouts.enums import RetryDisposition
   from django_checkouts.exceptions import CheckoutError

   try:
       result = operation()
   except CheckoutError as error:
       match error.retry_advice.disposition:
           case RetryDisposition.RETRY:
               schedule_retry()
           case RetryDisposition.RETRY_SAME_KEY:
               schedule_retry(same_idempotency_key=True)
           case RetryDisposition.RECONCILE_FIRST:
               schedule_reconciliation()
           case RetryDisposition.NEVER:
               report_permanent_failure()
