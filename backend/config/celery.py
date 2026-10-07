"""Aplicação Celery.

Os efeitos secundários do StockFlow (extração de faturas, emails de alerta,
previsões, consumo da outbox) correm todos aqui — nunca no ciclo do pedido
(CLAUDE.md, ARCHITECTURE.md §4).

Configuração: em `config/settings/base.py` com o prefixo `CELERY_`, lida por
`config_from_object`. Com uma exceção que morde: o Celery lê `CELERY_BROKER_URL`
e `CELERY_RESULT_BACKEND` do **ambiente** com precedência sobre as settings, pelo
que `settings.CELERY_BROKER_URL` pode divergir do `app.conf.broker_url` efetivo.
Quem quiser fixá-las tem de as pôr no ambiente — é o que o `config/settings/test.py`
faz para a suite não falar com um broker real.
"""

import os
from logging.config import dictConfig

from celery import Celery
from celery.signals import setup_logging
from django.conf import settings

# O default é `prod`, igual ao `config/wsgi.py` e ao `config/asgi.py`. Tem de
# ser: o `config/__init__.py` importa esta app, logo *qualquer* import de
# `config` sem a variável definida fixava-a aqui para o resto do processo. Um
# worker de produção a arrancar sem DJANGO_SETTINGS_MODULE ficava com
# DEBUG=True, a BD sem `sslmode=verify-full` e o email na consola — em
# silêncio. Quem quer `dev` diz-lo, no `.env` ou no compose. O `manage.py`
# continua em `dev` por ser CLI de desenvolvimento.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

# `task_cls` em vez de `base=` em cada `@app.task`: o Celery não tem middleware,
# e o âmbito da RLS não pode depender de alguém se lembrar de o pedir. Com a
# base no app, toda a tarefa — incluindo as de `@shared_task`, que usa o app
# atual — herda `tenant_id` obrigatório e o corpo dentro de `tenant_scope`
# (ADR 0005, ARCHITECTURE.md §4.8). Em string e não importada: resolve-se na
# criação da primeira tarefa, e não puxa `apps.shared` durante o import de
# `config`, que acontece antes de o registo de apps do Django estar populado.
app = Celery("stockflow", task_cls="apps.shared.tasks:TenantTask")

# `namespace="CELERY"` = só as settings com esse prefixo; evita colisões com as
# settings do Django.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Descobre `tasks.py` em cada app instalada.
app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**kwargs: object) -> None:
    """Impede o Celery de substituir o logging do Django.

    Sem isto o worker instala os seus próprios handlers e as linhas deixam de
    ser JSON — perdem-se `request_id`/`tenant_id` e a allowlist de campos
    (ARCHITECTURE.md §8, `config/log.py`).
    """
    dictConfig(settings.LOGGING)
