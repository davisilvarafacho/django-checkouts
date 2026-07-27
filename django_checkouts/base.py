"""``BaseCheckoutProvider`` — o contrato que todo provider de checkout implementa.

Providers nunca tocam o banco: recebem argumentos simples e devolvem
dataclasses normalizados. A persistência é sua.

Aqui há uma segunda divisão, entre público e protegido:

* Os métodos **públicos** (``create_checkout``, ``retrieve_checkout``, ...) são
  concretos e vivem nesta classe. Validam tudo o que dá para validar sem rede e
  levantam :class:`ValidationError` na hora. Um ``amount`` negativo ou um ciclo
  que o provedor não suporta falha em microssegundos, não num 400 obscuro depois
  do round-trip.
* Os métodos **protegidos** (``_create_checkout``, ...) são o que um provider
  novo precisa escrever. Recebem um :class:`CheckoutRequest` já validado e podem
  confiar nele.

Escrever um provider é subclassear, declarar os mapas e capacidades, e
implementar quatro métodos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import urlparse

from django.utils import timezone

from django_checkouts.dto import CheckoutRequest
from django_checkouts.dto import ProviderState
from django_checkouts.enums import BillingCycle
from django_checkouts.enums import Capability
from django_checkouts.enums import CheckoutMode
from django_checkouts.enums import CheckoutStatus
from django_checkouts.enums import EventType
from django_checkouts.enums import PaymentMethod
from django_checkouts.enums import Provider
from django_checkouts.exceptions import CapabilityNotSupported
from django_checkouts.exceptions import ProviderPermanentError
from django_checkouts.exceptions import UnsupportedPaymentMethod
from django_checkouts.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence
    from datetime import datetime

    from django_checkouts.credentials import BaseAuth
    from django_checkouts.dto import CheckoutData
    from django_checkouts.dto import Customer
    from django_checkouts.dto import LineItem
    from django_checkouts.dto import Recurrence
    from django_checkouts.dto import WebhookPayload
    from django_checkouts.webhooks import BaseWebhookAuth


class BaseCheckoutProvider:
    """Interface única de checkout hospedado.

    Instancie via :func:`django_checkouts.registry.get_checkout_provider` para
    usar a configuração de ``settings``, ou diretamente com kwargs para
    sobrescrevê-la no caso multi-tenant.
    """

    name: Provider | str = ""
    """Identidade do provedor. Use um membro de
    :class:`~django_checkouts.enums.Provider` — string crua só num provider que
    você escreveu e que a lib não conhece."""

    STATUS_MAP: dict[str, CheckoutStatus] = {}
    """Status do provedor → :class:`CheckoutStatus`. Ver :meth:`map_status`."""

    EVENT_MAP: dict[str, EventType] = {}
    """Evento do provedor → :class:`EventType`. Ver :meth:`map_event`."""

    CAPABILITIES: set[Capability] = set()
    """Operações opcionais que este provider implementa."""

    SUPPORTED_PAYMENT_METHODS: set[PaymentMethod] = set()

    SUPPORTED_CYCLES: set[BillingCycle] = set()
    """Ciclos de assinatura aceitos. Vazio quando não há assinatura."""

    state_class: type[ProviderState] = ProviderState

    default_currency: str = "BRL"

    auth: BaseAuth
    """Credenciais de API. Definida no ``__init__`` de cada provider e lida
    pelos system checks."""

    webhook_auth: BaseWebhookAuth
    """Como provar que um webhook veio deste provedor. Idem."""

    # --- API pública -------------------------------------------------------

    def create_checkout(
        self,
        *,
        items: Sequence[LineItem],
        success_url: str,
        cancel_url: str | None = None,
        mode: CheckoutMode | str = CheckoutMode.PAYMENT,
        payment_methods: Sequence[PaymentMethod | str] = (PaymentMethod.CARD,),
        customer: Customer | None = None,
        recurrence: Recurrence | None = None,
        reference_id: str | None = None,
        expires_at: datetime | None = None,
        currency: str | None = None,
        metadata: Mapping[str, str] | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> CheckoutData:
        """Cria um checkout e devolve os dados, com a ``url`` para redirecionar.

        Args:
            items: Produtos a cobrar. Pelo menos um.
            success_url: Para onde mandar o pagador depois de pagar. Precisa ser
                absoluta (``http://`` ou ``https://``).
            cancel_url: Para onde mandar se ele desistir.
            mode: Cobrança única ou assinatura.
            payment_methods: Meios oferecidos na tela.
            customer: Dados do pagador, para pré-preencher.
            recurrence: Obrigatório se ``mode=SUBSCRIPTION``, proibido se não.
            reference_id: Seu id interno. Volta no webhook — é o caminho mais
                curto para achar o pedido sem consultar a API.
            expires_at: Validade do link. Precisa ser aware e no futuro.
            currency: ISO 4217. Default: ``default_currency`` do provider.
            metadata: Pares string→string carregados junto do checkout.
            provider_options: Válvula de escape repassada crua ao provedor.

        Raises:
            ValidationError: Argumento inválido. Antes de qualquer I/O.
            UnsupportedPaymentMethod: Meio de pagamento fora das capacidades.
            CapabilityNotSupported: Operação que este provider não implementa.
            ProviderTemporaryError: Falha transitória; pode repetir.
            ProviderPermanentError: O provedor recusou em definitivo.
        """
        request = self.build_request(
            items=items,
            success_url=success_url,
            cancel_url=cancel_url,
            mode=mode,
            payment_methods=payment_methods,
            customer=customer,
            recurrence=recurrence,
            reference_id=reference_id,
            expires_at=expires_at,
            currency=currency,
            metadata=metadata,
            provider_options=provider_options,
        )
        return self._create_checkout(request)

    def retrieve_checkout(self, external_id: str) -> CheckoutData:
        """Busca o estado atual de um checkout.

        Use para conciliar quando o webhook não chegou, ou na volta do
        ``success_url`` — nunca confie só no redirect para liberar o produto.
        """
        return self._retrieve_checkout(self._clean_id(external_id))

    def cancel_checkout(self, external_id: str) -> CheckoutData:
        """Cancela um checkout ainda não pago e invalida o link."""
        self.require_capability(Capability.CANCEL)
        return self._cancel_checkout(self._clean_id(external_id))

    def verify_webhook(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookPayload:
        """Verifica a autenticidade da requisição e normaliza o payload.

        Args:
            raw_body: Corpo **cru**, em bytes. Reserializar o JSON antes de
                passar aqui invalida a verificação por hash do PagBank e do
                Stripe.
            headers: Cabeçalhos da requisição. Case-insensitive.

        Raises:
            WebhookVerificationError: A requisição não veio do provedor.
        """
        payload = self.webhook_auth.verify(raw_body, headers)
        return self._parse_webhook(payload)

    # --- tradução ----------------------------------------------------------

    def map_status(self, gateway_status: str) -> CheckoutStatus:
        """Traduz um status do provedor, **levantando** no que não conhece.

        Falhar alto é proposital: um status não mapeado que virasse ``UNKNOWN``
        circularia pelo seu código como se fosse um estado legítimo, e a
        primeira vez que você notaria seria conciliando dinheiro.
        """
        try:
            return self.STATUS_MAP[gateway_status]
        except KeyError as exc:
            raise ProviderPermanentError(
                f"O provedor '{self.name}' devolveu um status não mapeado: "
                f"'{gateway_status}'. Acrescente-o ao STATUS_MAP."
            ) from exc

    def map_event(self, gateway_event: str) -> EventType | None:
        """Traduz um tipo de evento, devolvendo ``None`` no que não conhece.

        Ao contrário de :meth:`map_status`, aqui não se levanta: os provedores
        emitem dezenas de eventos que não têm nada a ver com checkout, e derrubar
        o webhook por causa deles interromperia a fila de notificações da conta.
        Evento desconhecido chega com ``type=None`` e o ``raw`` intacto.
        """
        return self.EVENT_MAP.get(gateway_event)

    def parse_state(self, raw: Mapping) -> ProviderState:
        """Visão tipada e tolerante do payload cru deste provedor."""
        return self.state_class.from_raw(raw)

    def require_capability(self, capability: Capability) -> None:
        if capability not in self.CAPABILITIES:
            raise CapabilityNotSupported(self.name, capability.value)

    # --- validação ---------------------------------------------------------

    def build_request(
        self,
        *,
        items: Sequence[LineItem],
        success_url: str,
        cancel_url: str | None = None,
        mode: CheckoutMode | str = CheckoutMode.PAYMENT,
        payment_methods: Sequence[PaymentMethod | str] = (PaymentMethod.CARD,),
        customer: Customer | None = None,
        recurrence: Recurrence | None = None,
        reference_id: str | None = None,
        expires_at: datetime | None = None,
        currency: str | None = None,
        metadata: Mapping[str, str] | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> CheckoutRequest:
        """Valida tudo e congela num :class:`CheckoutRequest`.

        Público para que você possa validar um pedido sem enviá-lo — útil em
        teste e em formulário.
        """
        from django_checkouts.dto import LineItem as _LineItem

        items = tuple(items)
        if not items:
            raise ValidationError("Informe pelo menos um item em `items`.")
        for index, item in enumerate(items):
            if not isinstance(item, _LineItem):
                raise ValidationError(
                    f"items[{index}] deve ser um LineItem, e não "
                    f"{type(item).__name__}."
                )
            if item.provider_price_id is not None:
                self.require_capability(Capability.PROVIDER_CATALOG)

        mode = CheckoutMode(mode)
        if mode == CheckoutMode.SUBSCRIPTION:
            self.require_capability(Capability.SUBSCRIPTION)

        methods = tuple(dict.fromkeys(PaymentMethod(item) for item in payment_methods))
        if not methods:
            raise ValidationError("Informe pelo menos um meio em `payment_methods`.")
        for method in methods:
            if method not in self.SUPPORTED_PAYMENT_METHODS:
                raise UnsupportedPaymentMethod(
                    self.name, str(method), self.SUPPORTED_PAYMENT_METHODS
                )

        self._validate_url("success_url", success_url, required=True)
        self._validate_url("cancel_url", cancel_url, required=False)

        if mode == CheckoutMode.SUBSCRIPTION:
            if recurrence is None:
                raise ValidationError(
                    "mode=SUBSCRIPTION exige `recurrence=Recurrence(cycle=...)`."
                )
            cycle = BillingCycle(recurrence.cycle)
            if cycle not in self.SUPPORTED_CYCLES:
                raise ValidationError(
                    f"O provedor '{self.name}' não suporta o ciclo '{cycle}'. "
                    f"Suportados: "
                    f"{sorted(str(item) for item in self.SUPPORTED_CYCLES)}."
                )
        elif recurrence is not None:
            raise ValidationError(
                "`recurrence` só faz sentido com mode=SUBSCRIPTION. Remova o "
                "argumento ou mude o modo."
            )

        if expires_at is not None:
            self.require_capability(Capability.EXPIRATION)
            if timezone.is_naive(expires_at):
                raise ValidationError(
                    "`expires_at` precisa ser timezone-aware. Use "
                    "django.utils.timezone.now()."
                )
            if expires_at <= timezone.now():
                raise ValidationError(
                    f"`expires_at` precisa estar no futuro; recebi {expires_at}."
                )

        if customer is not None:
            self.require_capability(Capability.CUSTOMER_PREFILL)

        clean_metadata: dict[str, str] = {}
        for key, value in (metadata or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValidationError(
                    f"`metadata` aceita apenas pares string→string (recebi "
                    f"{key!r}: {type(value).__name__}). Serialize você mesmo se "
                    f"precisar de outro tipo."
                )
            clean_metadata[key] = value

        return CheckoutRequest(
            items=items,
            success_url=success_url,
            cancel_url=cancel_url,
            mode=mode,
            payment_methods=methods,
            customer=customer,
            recurrence=recurrence,
            reference_id=reference_id,
            expires_at=expires_at,
            currency=(currency or self.default_currency).upper(),
            metadata=clean_metadata,
            provider_options=dict(provider_options or {}),
        )

    @staticmethod
    def _clean_id(external_id: str) -> str:
        if not external_id or not external_id.strip():
            raise ValidationError("`external_id` não pode ser vazio.")
        return external_id.strip()

    @staticmethod
    def _validate_url(field_name: str, value: str | None, *, required: bool) -> None:
        if value is None or not value.strip():
            if required:
                raise ValidationError(f"`{field_name}` é obrigatório.")
            return
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError(
                f"`{field_name}` precisa ser uma URL absoluta http(s); recebi "
                f"{value!r}. Use request.build_absolute_uri(reverse('...')) "
                f"para montá-la."
            )

    # --- a implementar pelos providers -------------------------------------

    def _create_checkout(self, request: CheckoutRequest) -> CheckoutData:
        """Cria o checkout. ``request`` já vem validado."""
        raise NotImplementedError

    def _retrieve_checkout(self, external_id: str) -> CheckoutData:
        """Busca o checkout. ``external_id`` já vem não-vazio."""
        raise NotImplementedError

    def _cancel_checkout(self, external_id: str) -> CheckoutData:
        """Cancela o checkout. ``external_id`` já vem não-vazio."""
        raise NotImplementedError

    def _parse_webhook(self, payload: dict[str, Any]) -> WebhookPayload:
        """Normaliza um payload **já verificado**."""
        raise NotImplementedError
