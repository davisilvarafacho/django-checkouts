Webhooks
========

.. warning::

   A biblioteca não possui persistência. A aplicação deve gravar a
   deduplicação e aplicar o evento em sua própria transação.

Verifique sempre o corpo bruto, antes de acessar JSON ou ``request.data``:

.. code-block:: python

   event = client.webhooks.verify(request.body, request.headers)

Reserializar JSON muda os bytes assinados e invalida a verificação. Com DRF,
use ``checkout_webhook_authentication(variant)``; o evento normalizado chega em
``request.auth``. Essa integração não cria view, URL ou autorização de domínio.

Entrega é *at least once*. Crie uma restrição única composta por
``(variant, event_id)``. O ID isolado não é suficiente quando variantes ou
contas diferentes podem usar espaços de IDs independentes.

Dentro de uma transação:

1. tente inserir ``(variant, event_id)``;
2. se já existir, responda sucesso sem repetir o efeito;
3. aplique a mudança de domínio;
4. confirme ambos juntos.

Tipos externos desconhecidos são preservados em ``event.event_type`` com
``event.type is None``. Registre-os e atualize a integração sem inventar um
estado financeiro.
