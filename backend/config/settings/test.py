"""Settings dos testes (`pytest`, via `DJANGO_SETTINGS_MODULE` no pyproject).

O `base.py` exige `DJANGO_SECRET_KEY` e `DATABASE_URL` sem default. Para o
`pytest` correr numa máquina limpa e no CI sem `.env`, os valores de teste são
postos no ambiente **antes** de importar o base — com `setdefault`, para que o
ambiente real (CI, docker compose) continue a mandar quando os define.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "chave-de-teste-sem-valor-0123456789-abcdefghij")
os.environ.setdefault("DATABASE_URL", "postgres://stockflow@localhost:5442/stockflow_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6389")

from config.settings.base import *

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
