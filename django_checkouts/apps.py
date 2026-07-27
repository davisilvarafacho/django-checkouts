from __future__ import annotations

from django.apps import AppConfig


class DjangoCheckoutsConfig(AppConfig):
    name = "django_checkouts"
    verbose_name = "Django Checkouts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django_checkouts import checks  # noqa: F401
