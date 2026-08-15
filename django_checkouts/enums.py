"""Vocabulário normalizado da interface pública de checkouts."""

from __future__ import annotations

from django.db.models import TextChoices
from django.utils.translation import pgettext_lazy


class Gateway(TextChoices):
    """Gateways financeiros conhecidos pela biblioteca."""

    STRIPE = "stripe", pgettext_lazy("checkout gateway", "Stripe")
    PAGSEGURO = "pagseguro", pgettext_lazy("checkout gateway", "PagBank")
    ASAAS = "asaas", pgettext_lazy("checkout gateway", "Asaas")


class PaymentMethod(TextChoices):
    """Meio de pagamento oferecido na tela de checkout."""

    CARD = "card", pgettext_lazy("payment method", "Cartão")
    PIX = "pix", pgettext_lazy("payment method", "Pix")
    BOLETO = "boleto", pgettext_lazy("payment method", "Boleto")


class CheckoutMode(TextChoices):
    """Cobrança única ou recorrente."""

    PAYMENT = "payment", pgettext_lazy("checkout mode", "Pagamento único")
    SUBSCRIPTION = "subscription", pgettext_lazy("checkout mode", "Assinatura")


class CheckoutStatus(TextChoices):
    """Estado normalizado de um checkout."""

    PENDING = "pending", pgettext_lazy("checkout status", "Pendente")
    PAID = "paid", pgettext_lazy("checkout status", "Pago")
    EXPIRED = "expired", pgettext_lazy("checkout status", "Expirado")
    CANCELED = "canceled", pgettext_lazy("checkout status", "Cancelado")
    FAILED = "failed", pgettext_lazy("checkout status", "Recusado")


class BillingCycle(TextChoices):
    """Periodicidade fechada de uma assinatura."""

    WEEKLY = "weekly", pgettext_lazy("billing cycle", "Semanal")
    BIWEEKLY = "biweekly", pgettext_lazy("billing cycle", "Quinzenal")
    MONTHLY = "monthly", pgettext_lazy("billing cycle", "Mensal")
    BIMONTHLY = "bimonthly", pgettext_lazy("billing cycle", "Bimestral")
    QUARTERLY = "quarterly", pgettext_lazy("billing cycle", "Trimestral")
    SEMIANNUALLY = "semiannually", pgettext_lazy("billing cycle", "Semestral")
    YEARLY = "yearly", pgettext_lazy("billing cycle", "Anual")


class SubscriptionStatus(TextChoices):
    """Estado normalizado de uma assinatura."""

    INCOMPLETE = "incomplete", pgettext_lazy("subscription status", "Incompleta")
    TRIALING = "trialing", pgettext_lazy("subscription status", "Em teste")
    ACTIVE = "active", pgettext_lazy("subscription status", "Ativa")
    PAST_DUE = "past_due", pgettext_lazy("subscription status", "Em atraso")
    PAUSED = "paused", pgettext_lazy("subscription status", "Pausada")
    UNPAID = "unpaid", pgettext_lazy("subscription status", "Não paga")
    CANCELED = "canceled", pgettext_lazy("subscription status", "Cancelada")
    EXPIRED = "expired", pgettext_lazy("subscription status", "Expirada")


class InvoiceStatus(TextChoices):
    """Estado normalizado de uma fatura."""

    DRAFT = "draft", pgettext_lazy("invoice status", "Rascunho")
    OPEN = "open", pgettext_lazy("invoice status", "Em aberto")
    PAID = "paid", pgettext_lazy("invoice status", "Paga")
    VOID = "void", pgettext_lazy("invoice status", "Anulada")
    UNCOLLECTIBLE = "uncollectible", pgettext_lazy("invoice status", "Incobrável")


class InvoiceReason(TextChoices):
    """Motivo normalizado para emissão de uma fatura."""

    INITIAL_SUBSCRIPTION = (
        "initial_subscription",
        pgettext_lazy("invoice reason", "Assinatura inicial"),
    )
    RENEWAL = "renewal", pgettext_lazy("invoice reason", "Renovação")
    SUBSCRIPTION_UPDATE = (
        "subscription_update",
        pgettext_lazy("invoice reason", "Alteração de assinatura"),
    )
    MANUAL = "manual", pgettext_lazy("invoice reason", "Manual")
    UNKNOWN = "unknown", pgettext_lazy("invoice reason", "Desconhecido")


class EventType(TextChoices):
    """Tipo normalizado de evento de webhook."""

    CHECKOUT_PENDING = (
        "checkout.pending",
        pgettext_lazy("event type", "Checkout pendente"),
    )
    CHECKOUT_PAID = "checkout.paid", pgettext_lazy("event type", "Checkout pago")
    CHECKOUT_FAILED = (
        "checkout.failed",
        pgettext_lazy("event type", "Checkout recusado"),
    )
    CHECKOUT_EXPIRED = (
        "checkout.expired",
        pgettext_lazy("event type", "Checkout expirado"),
    )
    CHECKOUT_CANCELED = (
        "checkout.canceled",
        pgettext_lazy("event type", "Checkout cancelado"),
    )
    SUBSCRIPTION_CREATED = (
        "subscription.created",
        pgettext_lazy("event type", "Assinatura criada"),
    )
    SUBSCRIPTION_UPDATED = (
        "subscription.updated",
        pgettext_lazy("event type", "Assinatura atualizada"),
    )
    SUBSCRIPTION_CANCELED = (
        "subscription.canceled",
        pgettext_lazy("event type", "Assinatura cancelada"),
    )
    INVOICE_OPENED = "invoice.opened", pgettext_lazy("event type", "Fatura aberta")
    INVOICE_PAID = "invoice.paid", pgettext_lazy("event type", "Fatura paga")
    INVOICE_PAYMENT_FAILED = (
        "invoice.payment_failed",
        pgettext_lazy("event type", "Falha no pagamento da fatura"),
    )
    INVOICE_VOIDED = "invoice.voided", pgettext_lazy("event type", "Fatura anulada")
    INVOICE_UNCOLLECTIBLE = (
        "invoice.uncollectible",
        pgettext_lazy("event type", "Fatura incobrável"),
    )


class ResourceKind(TextChoices):
    """Tipo de recurso associado a um evento."""

    CHECKOUT = "checkout", pgettext_lazy("resource kind", "Checkout")
    SUBSCRIPTION = "subscription", pgettext_lazy("resource kind", "Assinatura")
    INVOICE = "invoice", pgettext_lazy("resource kind", "Fatura")


class ChangeTiming(TextChoices):
    """Quando uma alteração de assinatura deve vigorar."""

    IMMEDIATELY = "immediately", pgettext_lazy("change timing", "Imediatamente")
    NEXT_CYCLE = "next_cycle", pgettext_lazy("change timing", "No próximo ciclo")


class ProrationBehavior(TextChoices):
    """Como tratar o saldo proporcional de uma alteração."""

    CREATE_PRORATIONS = (
        "create_prorations",
        pgettext_lazy("proration behavior", "Criar ajustes proporcionais"),
    )
    INVOICE_IMMEDIATELY = (
        "invoice_immediately",
        pgettext_lazy("proration behavior", "Faturar imediatamente"),
    )
    NONE = "none", pgettext_lazy("proration behavior", "Não ajustar")


class CancellationTiming(TextChoices):
    """Quando uma assinatura deve ser cancelada."""

    IMMEDIATELY = "immediately", pgettext_lazy("cancellation timing", "Imediatamente")
    PERIOD_END = "period_end", pgettext_lazy("cancellation timing", "No fim do ciclo")


class RetryDisposition(TextChoices):
    """Ação segura depois de uma falha na fronteira do gateway."""

    NEVER = "never", pgettext_lazy("retry disposition", "Não repetir")
    RETRY = "retry", pgettext_lazy("retry disposition", "Repetir")
    RETRY_SAME_KEY = (
        "retry_same_key",
        pgettext_lazy("retry disposition", "Repetir com a mesma chave"),
    )
    RECONCILE_FIRST = (
        "reconcile_first",
        pgettext_lazy("retry disposition", "Conciliar antes de repetir"),
    )
