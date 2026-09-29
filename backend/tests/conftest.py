"""Fixtures partilhadas — isolamento do ambiente para os testes de settings.

Os testes que reimportam `config.settings.*` leem `os.environ` no momento do
`importlib.reload`. Sem isolamento, o resultado depende da máquina de quem
corre a suite, e isso já aconteceu: `DJANGO_DEBUG=false uv run pytest` dava um
teste vermelho, porque a variável do shell chegava ao `dev.py`.

Duas coisas resolvem isso, e são as duas necessárias:

1. `clean_env` — apaga todas as variáveis que a camada de settings lê e repõe
   só as duas obrigatórias, com valores de teste. O ambiente passa a ser o
   mesmo na máquina de qualquer pessoa e no CI.

2. `_restaura_os_environ` (autouse) — snapshot e restore de `os.environ` a cada
   teste. O `monkeypatch` não chega: a camada de settings chama
   `environ.Env.read_env(.env)` e o django-environ **escreve as chaves do
   ficheiro em `os.environ`** de forma permanente (`environ/environ.py
   read_env`). Numa máquina com `.env`, um teste que apague ou substitua uma
   dessas variáveis contaminava todos os seguintes, incluindo os que nada têm a
   ver com settings.

O `clean_env` também neutraliza o `read_env`: com as variáveis apagadas, um
`.env` no disco deixa de ser ignorado (o django-environ não sobrepõe o que já
existe, mas preenche o que falta) e voltaria a decidir o resultado do teste. O
que se testa aqui são os **defaults do código**, não o `.env` de quem corre a
suite.

Onde é que o `.env` é lido, já que isso decide o que o `clean_env` tem de
neutralizar: em `config/settings/__init__.py`, uma vez, quando o Python importa
o pacote. O `base.py` não o lê — ver o docstring desse `__init__.py`.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from types import ModuleType

import environ
import pytest

#: Tudo o que `config/settings/{base,dev,prod,test}.py` lê do ambiente. Uma
#: variável nova na camada de settings entra aqui — senão volta a haver um
#: teste que passa ou falha em função da máquina.
SETTINGS_ENV_VARS: tuple[str, ...] = (
    "ALLOWED_HOSTS",
    "API_DOCS_ENABLED",
    "CACHE_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CSRF_TRUSTED_ORIGINS",
    "DATABASE_CONN_MAX_AGE",
    "DATABASE_SSLROOTCERT",
    "DATABASE_URL",
    "DJANGO_ADMIN_URL",
    "DJANGO_DEBUG",
    "DJANGO_LOG_LEVEL",
    "DJANGO_SECRET_KEY",
    "REDIS_URL",
    "TRUSTED_PROXY_COUNT",
)

#: As duas que o `base.py` exige sem default em qualquer ambiente. Ficam sempre
#: definidas, senão um `_reload("base")` levanta `ImproperlyConfigured` — que é
#: o comportamento correto e está testado à parte.
BASE_REQUIRED_ENV: dict[str, str] = {
    "DJANGO_SECRET_KEY": "chave-de-teste-sem-valor-0123456789-abcdefghij",
    "DATABASE_URL": "postgres://stockflow@localhost:5442/stockflow_test",
}


@pytest.fixture(autouse=True)
def _restaura_os_environ() -> Iterator[None]:
    """Devolve `os.environ` ao estado em que estava antes do teste."""
    snapshot = os.environ.copy()
    yield
    if os.environ != snapshot:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiente determinístico para reimportar módulos de settings."""
    # Sem isto o `.env` do repositório (quando existe) preenche as variáveis que
    # acabámos de apagar, e o teste volta a depender da máquina.
    monkeypatch.setattr(
        environ.Env,
        "read_env",
        staticmethod(lambda *args, **kwargs: None),
    )
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in BASE_REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def prod_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiente mínimo para `config.settings.prod` importar.

    Sem `DATABASE_URL`: o `prod.py` não lê essa variável — herda o `DATABASES`
    do `base` pelo `import *`, e um `importlib.reload("prod")` não reexecuta o
    `base` (já está em `sys.modules`). Quem a precisa é o `_reload("base")`, e
    vem do `clean_env`.
    """
    monkeypatch.setenv("ALLOWED_HOSTS", "stockflow.example.pt")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://stockflow.example.pt")
    monkeypatch.setenv("DJANGO_ADMIN_URL", "gestao-interna/")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")


def reload_settings(name: str) -> ModuleType:
    """Importa (ou reimporta) um módulo de settings, para reler o ambiente.

    Usar sempre com o `clean_env` (ou com o `prod_env`, que o inclui): sem ele
    o resultado depende das variáveis do shell e do `.env` da máquina.
    """
    return importlib.reload(importlib.import_module(f"config.settings.{name}"))
