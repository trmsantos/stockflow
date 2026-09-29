"""Pacote de configuração do projeto.

A app Celery é importada aqui para ficar registada assim que o Django carrega
`config` — é o que faz o `autodiscover_tasks` e o `@shared_task` funcionarem.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
