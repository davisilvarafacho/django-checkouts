Escrevendo um gateway
=====================

.. note::

   A biblioteca não possui persistência. Uma implementação de gateway também
   não deve criar models nem assumir regras de domínio da aplicação.

Implemente uma subclasse de ``BaseCheckoutGateway`` com ``name``,
``capabilities`` e uma tupla de handlers. Cada handler declara um
``command_type`` exato, valida o comando antes de I/O e devolve o DTO normalizado
declarado pelo comando.

Use ``ExecutionContext.call`` para chamadas externas. Essa fronteira injeta a
variante, preserva chaves de idempotência e converte exceções externas em
``CheckoutError``. Resultados devem usar UTC, moedas maiúsculas, tipos exatos e
``raw`` imutável e oculto do ``repr``. Webhooks devem autenticar os bytes
originais antes de mapear o payload e preservar eventos desconhecidos.

Publique capabilities apenas quando houver um handler correspondente. O método
``check()`` deve validar configuração localmente e nunca acessar a rede.

Suíte de contrato
-----------------

Execute ``GatewayContractSuite`` nos testes da integração. Ela cobre handlers
únicos e exatos, acordo com capabilities, validação antes de I/O, idempotência,
tipos normalizados, UTC, moeda, ``raw``, erros públicos sanitizados e invariantes
de eventos.

.. code-block:: python

   from django_checkouts.testing import GatewayContractSuite

   suite = GatewayContractSuite(my_gateway)
   suite.assert_unique_exact_handlers()
   suite.assert_capability_handler_agreement()

Além da suíte reutilizável, teste payloads reais do serviço externo, paginação,
taxonomia de estados, matriz de erros e nenhuma chamada de rede nos checks.
