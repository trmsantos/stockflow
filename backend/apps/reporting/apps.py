"""Configuração do app reporting."""

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """App de relatórios e painel."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    verbose_name = "Relatórios"
