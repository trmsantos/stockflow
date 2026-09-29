"""Fixtures partilhadas: isolamento do ambiente e os dois roles da suite.

Duas responsabilidades, ambas sobre o *arranque* da suite e nenhuma sobre
domínio: (a) tornar determinístico o ambiente que a camada de settings lê, e
(b) criar a base de dados de teste com o role que migra e correr os testes com
o role que serve pedidos (ADR 0006, `django_db_setup` no fim do ficheiro).

## (a) Isolamento do ambiente

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
from django.conf import settings
from django.db import connections
from pytest_django.plugin import DjangoDbBlocker

#: O role que serve pedidos e com que os testes correm. Vai literal porque os
#: `GRANT` são DDL e um nome de role não é parametrizável; o `django_db_setup`
#: confirma que bate com o `USER` do `DATABASE_URL` antes de o usar.
APP_ROLE = "stockflow_app"

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
    # Só o `test.py` a lê (ADR 0006), e é por isso que tem de estar aqui: sem a
    # apagar, um `_reload("test")` passava a depender do `.env` de quem corre.
    "MIGRATION_DATABASE_URL",
    "REDIS_URL",
    "TRUSTED_PROXY_COUNT",
)

#: As duas que o `base.py` exige sem default em qualquer ambiente. Ficam sempre
#: definidas, senão um `_reload("base")` levanta `ImproperlyConfigured` — que é
#: o comportamento correto e está testado à parte.
#:
#: `MIGRATION_DATABASE_URL` não entra aqui de propósito: o `base.py` não a lê, e
#: o `test.py` volta a pôr-lhe o default no `setdefault` do topo quando é
#: reimportado sem ela — que é exatamente o caminho que o CI percorre.
BASE_REQUIRED_ENV: dict[str, str] = {
    "DJANGO_SECRET_KEY": "chave-de-teste-sem-valor-0123456789-abcdefghij",
    "DATABASE_URL": f"postgres://{APP_ROLE}@localhost:5442/stockflow_test",
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


# ---------------------------------------------------------------------------
# (b) Os dois roles da suite (ADR 0006)
#
# Quem migra fica dono das tabelas, e uma suite que corre como dono não prova
# nada sobre a app: `ENABLE ROW LEVEL SECURITY` não se aplica ao dono, e o
# `FORCE` que a migração liga sujeita-o à política mas não lhe tira o
# `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`. Daí a forma desta fixture:
#
#   1. a base de dados de teste é criada, migrada e apagada pelo
#      `stockflow_owner` — é o único role com `CREATEDB`, e é ele que tem de
#      ficar dono das tabelas para o esquema de teste ter a forma de produção;
#   2. os testes correm com o `stockflow_app`, que não é dono de nada, não tem
#      `CREATE` no esquema e é sujeito à RLS. A política deixa de precisar de
#      uma fixture que troque de role para valer: aplica-se em *todos* os
#      testes, e a guarda que o afirma está em `tests/test_db_roles.py`.
#
# A troca é de `USER`/`PASSWORD` na alias `default`, e não de uma segunda alias
# em `DATABASES` — a assinatura da base de dados de teste do Django não inclui o
# `USER` (`BaseDatabaseCreation.test_db_signature`), pelo que duas aliases para
# a mesma base de dados de teste colidiriam.
# ---------------------------------------------------------------------------

#: O `flush` que o pytest-django corre entre testes `transaction=True` é um
#: `TRUNCATE`, e nenhuma política de RLS o filtra: é um apagar-tudo que
#: atravessa tenants. Por isso o `docker/db/roles.sql` **não** o concede, e por
#: isso o append-only que a suite prova é sobre `UPDATE` e `DELETE`. Aqui é
#: preciso, e fica aqui — no harness, numa base de dados que só existe durante
#: a suite. O nome do role vai literal: um `GRANT` é DDL e não aceita
#: parâmetros (ver `APP_ROLE`).
_GRANT_TRUNCATE = "GRANT TRUNCATE ON ALL TABLES IN SCHEMA public TO stockflow_app"


def _usa_credenciais(user: str, password: str) -> None:
    """Põe `user`/`password` na alias `default`, nos dois sítios que a leem.

    Medido no Django 5.2.17: `connections["default"].settings_dict` **é** o
    mesmo objeto que `settings.DATABASES["default"]` (o `configure_settings` do
    `ConnectionHandler` devolve o dicionário das settings, não uma cópia), pelo
    que escrever num escreve nos dois. Escrevem-se os dois de qualquer forma,
    porque é o que o próprio `create_test_db` do Django faz com o `NAME` e é a
    única versão que sobrevive à identidade se deixar de ser verdade — um
    `override_settings(DATABASES=...)` substitui o dicionário e o
    `reset_connections` do `django.test.signals` rederiva `connections.settings`
    a partir dele.

    Quem lê qual, e quando: o `_nodb_cursor` que corre o `CREATE DATABASE` e o
    `DROP DATABASE` monta a ligação a partir de `connection.settings_dict`; o
    `get_connection_params` de cada ligação nova também. É por isso que a
    ligação tem de ser **fechada** depois da troca: mudar o dicionário não
    reautentica uma ligação já aberta.
    """
    for destino in (settings.DATABASES["default"], connections["default"].settings_dict):
        destino["USER"] = user
        destino["PASSWORD"] = password


@pytest.fixture(scope="session")
def django_db_setup(
    request: pytest.FixtureRequest,
    django_test_environment: None,
    django_db_blocker: DjangoDbBlocker,
    django_db_use_migrations: bool,
    django_db_keepdb: bool,
    django_db_createdb: bool,
    django_db_modify_db_settings: None,
) -> Iterator[None]:
    """Substitui o `django_db_setup` do pytest-django: setup do dono, testes da app.

    A assinatura repete a do original porque as dependências são as mesmas e a
    ordem entre fixtures de sessão é o que garante que o `django_test_environment`
    já correu e que os sufixos de `--parallel`/xdist já estão nas settings.
    """
    from django.test.utils import setup_databases, teardown_databases

    if not django_db_use_migrations:
        raise pytest.UsageError(
            "--no-migrations não serve nesta suite: as políticas de RLS nascem "
            "num RunSQL dentro das migrações, e sem elas os testes de "
            "isolamento passariam a medir uma base de dados sem políticas."
        )

    # Lidas antes da primeira troca, senão a segunda leitura já traz o dono.
    user_da_app = settings.DATABASES["default"]["USER"]
    password_da_app = settings.DATABASES["default"]["PASSWORD"]
    user_do_dono = settings.MIGRATION_DATABASE["USER"]
    password_do_dono = settings.MIGRATION_DATABASE["PASSWORD"]

    if user_da_app != APP_ROLE:
        raise pytest.UsageError(
            f"o DATABASE_URL da suite liga-se como {user_da_app!r} e não como "
            f"{APP_ROLE!r}: o GRANT desta fixture e as asserções de "
            f"tests/test_db_roles.py nomeiam o role literalmente."
        )
    for chave in ("HOST", "PORT"):
        if settings.MIGRATION_DATABASE[chave] != settings.DATABASES["default"][chave]:
            raise pytest.UsageError(
                f"MIGRATION_DATABASE_URL e DATABASE_URL apontam para clusters "
                f"diferentes ({chave}): só USER e PASSWORD são trocados, logo a "
                f"base de dados de teste nasceria no sítio errado."
            )

    setup_databases_args = {}
    if django_db_keepdb and not django_db_createdb:
        setup_databases_args["keepdb"] = True

    _usa_credenciais(user_do_dono, password_do_dono)
    try:
        with django_db_blocker.unblock():
            # Sem `aliases`: o `DATABASES` tem uma alias e só uma, por decisão
            # da ADR 0006, e a URL do dono nunca entra lá.
            db_cfg = setup_databases(
                verbosity=request.config.option.verbose,
                interactive=False,
                **setup_databases_args,
            )
            # Ainda como dono, que é quem acabou de ficar dono das tabelas: um
            # `GRANT` só o pode dar quem tem o objeto.
            with connections["default"].cursor() as cursor:
                cursor.execute(_GRANT_TRUNCATE)
    finally:
        # Devolver a alias à app **antes** do primeiro teste, e fechar: mudar o
        # dicionário não reautentica a ligação aberta, e é o próximo connect que
        # tem de se autenticar como `stockflow_app`.
        _usa_credenciais(user_da_app, password_da_app)
        connections["default"].close()

    yield

    if not django_db_keepdb:
        _usa_credenciais(user_do_dono, password_do_dono)
        try:
            with django_db_blocker.unblock():
                # A ligação aberta é a da app e é sobre a base de dados que se
                # vai apagar: um `DROP DATABASE` com ela aberta levaria
                # "database is being accessed by other users".
                connections["default"].close()
                try:
                    teardown_databases(db_cfg, verbosity=request.config.option.verbose)
                except Exception as exc:
                    request.node.warn(
                        pytest.PytestWarning(
                            f"Erro ao apagar a base de dados de teste: {exc!r}"
                        )
                    )
        finally:
            # A password do dono não fica no `DATABASES` depois de a suite
            # acabar: nada mais a precisa, e um `--pdb` no fim do teardown
            # deixava-a ao alcance de quem lá parasse.
            _usa_credenciais(user_da_app, password_da_app)
            connections["default"].close()
