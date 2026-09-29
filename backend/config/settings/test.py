"""Settings dos testes (`pytest`, via `DJANGO_SETTINGS_MODULE` no pyproject).

O `base.py` exige `DJANGO_SECRET_KEY` e `DATABASE_URL` sem default. Para o
`pytest` correr numa máquina limpa e no CI sem `.env`, os valores de teste são
postos no ambiente **antes** de importar o base — com `setdefault`, para que o
ambiente real (CI, docker compose) continue a mandar quando os define.

O `.env` é lido antes destes `setdefault`, no `config/settings/__init__.py`, e é
o que faz `uv run pytest` falar com o Postgres do compose: o `DATABASE_URL` aqui
em baixo não tem password, e sem aquela leitura prévia era ele que ganhava. Quem
corre a suite numa máquina sem `.env` — o CI — cai nestes valores, que é para
isso que existem.

A suite é o único ambiente que lê **duas** credenciais (ADR 0006): a base de
dados de teste é criada, migrada e apagada pelo `stockflow_owner`, e os testes
correm como `stockflow_app`. Quem faz a troca é o `django_db_setup` do
`tests/conftest.py`; aqui só se lê a credencial do dono, para uma setting
própria.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "chave-de-teste-sem-valor-0123456789-abcdefghij")
os.environ.setdefault("DATABASE_URL", "postgres://stockflow_app@localhost:5442/stockflow_test")
os.environ.setdefault(
    "MIGRATION_DATABASE_URL", "postgres://stockflow_owner@localhost:5442/stockflow_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6389")

# Estas duas são `os.environ[...] =`, não `setdefault`, e é deliberado: o Celery
# lê `CELERY_BROKER_URL` e `CELERY_RESULT_BACKEND` do **ambiente** por cima do
# que o `config_from_object` traz das settings do Django. Com um `.env` no disco
# (o `read_env` do base injeta-o em `os.environ`), uma atribuição de settings
# passava a valer em `settings.CELERY_BROKER_URL` e a não valer no
# `app.conf.broker_url` efetivo — e a suite publicava tarefas num Redis real.
# Forçar aqui faz a precedência do Celery trabalhar a favor. Coberto por
# `tests/test_celery_config.py`.
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

from config.env import required_db
from config.settings.base import *
from config.settings.base import env

#: Credencial do `stockflow_owner`: o role que cria, migra e apaga a base de
#: dados de teste (ADR 0006). O `dev.py` e o `prod.py` **não** a leem — lá o
#: role é propriedade do processo, e o `migrate` corre num processo cujo
#: `DATABASE_URL` é o `MIGRATION_DATABASE_URL`.
#:
#: Uma setting, e deliberadamente **não** uma segunda alias em `DATABASES`: uma
#: alias é uma base de dados aos olhos do Django, logo o `setup_databases`
#: tentaria criar (e apagar) uma base de dados de teste também para ela. Só
#: `USER` e `PASSWORD` daqui são usados; `HOST`, `PORT` e `NAME` continuam a vir
#: do `DATABASE_URL`, porque é o mesmo cluster e a mesma base de dados.
MIGRATION_DATABASE = required_db(env, "MIGRATION_DATABASE_URL")

# Nunca `True` em testes: com DEBUG ligado o Django devolve páginas de erro em
# vez de 500 e os testes de permissão passam por acidente.
DEBUG = False

# O lockout de login é testado explicitamente nos testes que o cobrem, com
# override de settings. Ligado por omissão, trancava o resto da suite.
AXES_ENABLED = False

# Sem worker nem Redis nos testes: a tarefa corre em processo e as exceções
# propagam para o teste em vez de ficarem no resultado.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

# MD5 **só aqui**: o Argon2id gasta ~100 ms por hash de propósito, e cada
# fixture de utilizador paga isso. Em qualquer outro ambiente é Argon2id.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Cache local ao processo: os testes não dependem de um Redis a correr.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

API_DOCS_ENABLED = False
