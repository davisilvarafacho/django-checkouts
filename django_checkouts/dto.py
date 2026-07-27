"""Dataclasses normalizados que atravessam a fronteira entre você e os provedores.

Duas regras valem para tudo aqui:

**Dinheiro é sempre ``int`` em centavos.** Nunca ``float``, nunca ``Decimal`` de
reais. Os três provedores falam centavos na API; converter na borda e trabalhar
com inteiro no meio elimina uma classe inteira de erro de arredondamento. Use
``amount_decimal`` só para exibir.

**Todo objeto de resposta carrega ``raw``.** A lib normaliza o que dá; o resto
continua acessível sem largar a abstração. Para uma visão *tipada* do payload
cru, cada provider declara uma subclasse de :class:`ProviderState`.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from typing import TYPE_CHECKING
from typing import Any

from django_checkouts.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from decimal import Decimal
    from typing import Self

    from django_checkouts.enums import BillingCycle
    from django_checkouts.enums import CheckoutMode
    from django_checkouts.enums import CheckoutStatus
    from django_checkouts.enums import EventType
    from django_checkouts.enums import PaymentMethod
    from django_checkouts.enums import Provider


@dataclass(frozen=True)
class ProviderState:
    """Base de dataclasses tolerantes sobre o payload cru de um provedor.

    ``from_raw`` descarta as chaves que a dataclass não declara, então um campo
    novo introduzido pelo provedor não quebra nada — mas os campos que você
    declarou ficam tipados e conferidos.
    """

    @classmethod
    def from_raw(cls, raw: Mapping) -> Self:
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in raw.items() if key in known})


@dataclass(frozen=True)
class LineItem:
    """Um produto na tela de checkout."""

    name: str
    """Nome exibido ao pagador."""

    amount: int
    """Preço **unitário em centavos**. R$ 49,90 é ``4990``."""

    quantity: int = 1

    description: str | None = None

    image_url: str | None = None
    """Ignorado por provedores que não exibem imagem no checkout."""

    reference_id: str | None = None
    """Seu SKU ou id interno, devolvido no webhook quando o provedor suporta."""

    provider_price_id: str | None = None
    """Preço pré-cadastrado no provedor (ex.: ``price_123`` do Stripe).

    Quando presente, o provider usa esse id e ignora ``name``/``amount`` — evita
    criar um Product novo a cada checkout e sujar seu catálogo. Exige a
    capacidade ``PROVIDER_CATALOG``; provedores sem catálogo (PagBank, Asaas)
    recusam o campo em vez de ignorá-lo em silêncio.
    """

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationError("LineItem.name não pode ser vazio.")
        if self.provider_price_id is None and self.amount <= 0:
            raise ValidationError(
                f"LineItem.amount deve ser inteiro positivo em centavos; "
                f"recebi {self.amount!r}. Lembre: R$ 49,90 é 4990, não 49.90."
            )
        if self.quantity <= 0:
            raise ValidationError(
                f"LineItem.quantity deve ser >= 1; recebi {self.quantity!r}."
            )

    @property
    def total(self) -> int:
        """Preço unitário vezes quantidade, em centavos."""
        return self.amount * self.quantity

    @property
    def amount_decimal(self) -> Decimal:
        """Preço unitário na unidade maior. **Só para exibição.**"""
        from decimal import Decimal as _Decimal

        return _Decimal(self.amount) / 100


@dataclass(frozen=True)
class Customer:
    """Dados do pagador.

    Todos os campos são opcionais na lib, mas cada provider valida o que a sua
    API exige e levanta :class:`ValidationError` antes de ir para a rede.
    """

    name: str | None = None
    email: str | None = None

    tax_id: str | None = None
    """CPF ou CNPJ, só dígitos.

    Sem análogo no Stripe internacional, mas é o identificador de fato do
    pagador no Brasil — PagBank e Asaas usam para pré-preencher e antifraude.
    """

    phone: str | None = None
    """E.164 (``+5511999999999``) ou só dígitos com DDD."""

    provider_customer_id: str | None = None
    """Cliente já existente no provedor (``cus_123``). Tem precedência sobre os
    outros campos quando presente."""


@dataclass(frozen=True)
class Recurrence:
    """Configuração de assinatura. Obrigatória quando ``mode=SUBSCRIPTION``."""

    cycle: BillingCycle
    """Com que frequência renova. Veja :class:`BillingCycle` sobre por que não
    existe multiplicador aqui."""

    description: str | None = None
    """Rótulo do plano, quando o provedor exibe um."""


@dataclass(frozen=True)
class CheckoutRequest:
    """Pedido de checkout já validado, do jeito que os providers recebem.

    Você não constrói isto: ``create_checkout`` monta a partir dos kwargs,
    valida, e entrega ao ``_create_checkout`` do provider. Existe para que
    acrescentar um campo ao ``create_checkout`` não mude a assinatura de todos
    os providers ao mesmo tempo — inclusive os que você escreveu.
    """

    items: tuple[LineItem, ...]
    success_url: str
    mode: CheckoutMode
    payment_methods: tuple[PaymentMethod, ...]
    currency: str
    cancel_url: str | None = None
    customer: Customer | None = None
    recurrence: Recurrence | None = None
    reference_id: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    provider_options: dict[str, Any] = field(default_factory=dict)
    """Repassado cru ao SDK/API do provedor, mesclado por último.

    A válvula de escape para o que a abstração não cobre. O que você põe aqui
    é, por definição, específico de um provedor e não portável.
    """

    @property
    def amount_total(self) -> int:
        """Soma dos itens em centavos.

        Só um palpite local: o total que vale é o ``amount_total`` que o
        provedor devolve em :class:`CheckoutData`, já com desconto e frete.
        """
        return sum(item.total for item in self.items)


@dataclass(frozen=True)
class CheckoutData:
    """Estado normalizado de um checkout, devolvido pelo provider.

    ``url`` é o único campo necessário no fluxo feliz: redirecione o pagador
    para lá. ``external_id`` é o que você guarda para conciliar com o webhook.
    """

    external_id: str
    """Identificador no provedor. Guarde junto do seu pedido."""

    status: CheckoutStatus
    provider: Provider | str
    """O ``name`` do provider que devolveu este checkout."""

    mode: CheckoutMode

    url: str | None = None
    """Página de pagamento hospedada. ``None`` em checkout finalizado ou
    cancelado, quando o provedor invalida o link."""

    amount_total: int = 0
    """Total em centavos, como o provedor calculou — não como você somou.
    Divergência aqui é sinal de desconto ou frete aplicado do outro lado."""

    currency: str = "BRL"
    """ISO 4217 em maiúsculas."""

    customer: Customer | None = None
    reference_id: str | None = None
    """O ``reference_id`` que você mandou no ``create_checkout``."""

    expires_at: datetime | None = None

    raw: dict = field(default_factory=dict)
    """Resposta crua do provedor, sem tocar. Sempre presente."""

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"

    @property
    def amount_total_decimal(self) -> Decimal:
        """Total na unidade maior. **Só para exibição.**"""
        from decimal import Decimal as _Decimal

        return _Decimal(self.amount_total) / 100


@dataclass(frozen=True)
class WebhookPayload:
    """Um webhook já verificado e normalizado.

    """

    provider: Provider | str
    """O ``name`` do provider que verificou este webhook."""

    event_id: str
    """Id do evento no provedor. É a chave de idempotência: webhooks são
    entregues *at least once*, então guarde-o e ignore repetição."""

    event_type: str
    """Tipo cru, como o provedor mandou. O tipo normalizado está em
    :attr:`type`."""

    type: EventType | None = None
    """Tipo normalizado, quando a lib reconhece o evento. ``None`` para eventos
    que ela não traduz — nesse caso use ``event_type`` e ``raw``."""

    external_id: str | None = None
    """Id do checkout a que o evento se refere."""

    reference_id: str | None = None
    """Seu id interno, quando o provedor devolve no payload. Costuma ser o
    caminho mais curto para achar o pedido sem consultar a API."""

    status: CheckoutStatus | None = None
    """Estado do checkout **depois** deste evento."""

    data: CheckoutData | None = None
    """Checkout completo, quando o payload traz dados suficientes para montá-lo
    sem uma chamada extra à API."""

    raw: dict = field(default_factory=dict)
    """Payload cru do webhook, sem tocar. Sempre presente."""
