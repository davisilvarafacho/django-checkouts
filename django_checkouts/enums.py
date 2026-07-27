"""Vocabulário comum a todos os provedores.

Os estados usam ``TextChoices`` em vez de ``StrEnum``: o valor serializa
como string e cai direto num campo de model, mas o rótulo passa pelo
``pgettext_lazy`` e é traduzível. O idioma-fonte é pt-BR; ``locale/en`` traduz
para inglês.
"""

from __future__ import annotations

from django.db.models import TextChoices
from django.utils.translation import pgettext_lazy


class Provider(TextChoices):
    """Provedores com implementação nesta lib."""

    STRIPE = "stripe", pgettext_lazy("checkout provider", "Stripe")
    PAGSEGURO = "pagseguro", pgettext_lazy("checkout provider", "PagBank")
    ASAAS = "asaas", pgettext_lazy("checkout provider", "Asaas")


class PaymentMethod(TextChoices):
    """Meio de pagamento oferecido na tela de checkout."""

    CARD = "card", pgettext_lazy("payment method", "Cartão")
    PIX = "pix", pgettext_lazy("payment method", "Pix")
    BOLETO = "boleto", pgettext_lazy("payment method", "Boleto")


class CheckoutMode(TextChoices):
    """Cobrança única ou recorrente.

    Parcelamento no cartão ("3x sem juros") é um terceiro caso, distinto de
    assinatura, e está fora do MVP — entra como ``INSTALLMENT`` na v2.
    Acrescentar um membro aqui é aditivo e não quebra código existente.
    """

    PAYMENT = "payment", pgettext_lazy("checkout mode", "Pagamento único")
    SUBSCRIPTION = "subscription", pgettext_lazy("checkout mode", "Assinatura")


class CheckoutStatus(TextChoices):
    """Estado normalizado de um checkout.

    Traduzir o zoo de status de cada provedor para estes cinco é o principal
    trabalho da lib. Não existe membro ``UNKNOWN``: um status que a lib não
    conhece levanta ``ProviderPermanentError`` em
    :meth:`~django_checkouts.base.BaseCheckoutProvider.map_status`,
    para você mapeá-lo — melhor quebrar alto do que deixar um estado errado
    circular pelo seu código.
    """

    PENDING = "pending", pgettext_lazy("checkout status", "Pendente")
    """Criado, aguardando o pagador. Inclui pix e boleto emitidos e não pagos."""

    PAID = "paid", pgettext_lazy("checkout status", "Pago")
    """Dinheiro confirmado. Só libere o produto neste estado."""

    EXPIRED = "expired", pgettext_lazy("checkout status", "Expirado")
    """Passou da validade sem pagamento."""

    CANCELED = "canceled", pgettext_lazy("checkout status", "Cancelado")
    """Cancelado por você ou pelo pagador."""

    FAILED = "failed", pgettext_lazy("checkout status", "Recusado")
    """Tentativa de pagamento recusada em definitivo."""


class BillingCycle(TextChoices):
    """Periodicidade de uma assinatura.

    Opções fechadas de propósito. A alternativa — expor o par ``interval`` +
    ``interval_count`` do Stripe — não sobrevive à tradução: Asaas e PagBank só
    aceitam ciclos nomeados, e um ``interval_count=5`` não teria para onde ir.
    Cada provider converte: ``QUARTERLY`` vira ``interval="month",
    interval_count=3`` no Stripe e ``cycle="QUARTERLY"`` no Asaas.

    Os nomes seguem os do Asaas, que é o provedor com o vocabulário mais
    restrito dos três — o denominador comum.
    """

    WEEKLY = "weekly", pgettext_lazy("billing cycle", "Semanal")
    BIWEEKLY = "biweekly", pgettext_lazy("billing cycle", "Quinzenal")
    MONTHLY = "monthly", pgettext_lazy("billing cycle", "Mensal")
    BIMONTHLY = "bimonthly", pgettext_lazy("billing cycle", "Bimestral")
    QUARTERLY = "quarterly", pgettext_lazy("billing cycle", "Trimestral")
    SEMIANNUALLY = "semiannually", pgettext_lazy("billing cycle", "Semestral")
    YEARLY = "yearly", pgettext_lazy("billing cycle", "Anual")


class EventType(TextChoices):
    """Tipo normalizado de evento de webhook."""

    CHECKOUT_PAID = "checkout.paid", pgettext_lazy("event type", "Checkout pago")
    CHECKOUT_EXPIRED = (
        "checkout.expired",
        pgettext_lazy("event type", "Checkout expirado"),
    )
    CHECKOUT_CANCELED = (
        "checkout.canceled",
        pgettext_lazy("event type", "Checkout cancelado"),
    )
    CHECKOUT_FAILED = (
        "checkout.failed",
        pgettext_lazy("event type", "Checkout recusado"),
    )
    CHECKOUT_PENDING = (
        "checkout.pending",
        pgettext_lazy("event type", "Checkout pendente"),
    )


class Capability(TextChoices):
    """Operações opcionais que um provider pode declarar que suporta.

    Em vez de cada provider levantar ``NotImplementedError`` de um jeito
    diferente, ele declara o que faz em ``CAPABILITIES`` e a base recusa o resto
    de forma uniforme, antes de qualquer chamada de rede.
    """

    SUBSCRIPTION = "subscription"
    """Aceita ``mode=SUBSCRIPTION`` em ``create_checkout``."""

    CANCEL = "cancel"
    """Cancela um checkout ainda não pago pela API."""

    EXPIRATION = "expiration"
    """Aceita uma data de validade definida por você."""

    CUSTOMER_PREFILL = "customer_prefill"
    """Pré-preenche a tela com os dados do pagador."""

    PROVIDER_CATALOG = "provider_catalog"
    """Aceita preço pré-cadastrado via ``LineItem.provider_price_id``."""
