from __future__ import annotations

SECRET_KEY = "django-checkouts-tests"

DEBUG = True

USE_TZ = True

TIME_ZONE = "America/Sao_Paulo"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_checkouts",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# A chave fica como string de propósito: é assim que o settings de um projeto
# real se parece — módulo de settings não importa a lib. No código, use
# `Gateway.STRIPE`; como é TextChoices, casa com esta chave.
CHECKOUT_VARIANTS = {
    "stripe": (
        "django_checkouts.gateways.stripe.StripeGateway",
        {
            "api_key": "sk_test_dummy",
            "webhook_secret": "whsec_dummy",
            "sandbox": True,
        },
    ),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
