"""Fixtures partilhadas: ambiente, os dois roles da suite e o guarda de âmbito.

Três responsabilidades, todas sobre o *arranque* da suite e nenhuma sobre
domínio: (a) tornar determinístico o ambiente que a camada de settings lê,
(b) criar a base de dados de teste com o role que migra e correr os testes com
o role que serve pedidos (ADR 0006, `django_db_setup`), e (c) montar em todos
os testes o guarda que levanta quando alguém lê uma tabela com política de RLS
fora de âmbito (ADR 0007, no fim do ficheiro).

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
import re
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import Any

import environ
import pytest
from django.conf import settings
from django.db import connections
from pytest_django.plugin import DjangoDbBlocker

from apps.shared.db import current_tenant, in_system_scope

#: O role que serve pedidos e com que os testes correm. Vai literal porque os
#: `GRANT` são DDL e um nome de role não é parametrizável; o `django_db_setup`
#: confirma que bate com o `USER` do `DATABASE_URL` antes de o usar.
APP_ROLE = "stockflow_app"

#: Tudo o que `config/settings/{base,dev,prod,test}.py` lê do ambiente. Uma
#: variável nova na camada de settings entra aqui — senão volta a haver um
#: teste que passa ou falha em função da máquina.
SETTINGS_ENV_VARS: tuple[str, ...] = (
    # As do assistente (ADR 0027). A chave vai aqui pela mesma razão das
    # outras: um `.env` com chave a sério na máquina de quem corre a suite não
    # pode ser o que decide se o `POST` responde 202 ou 503.
    "AGENTS_CHAT_API_KEY",
    "AGENTS_CHAT_BASE_URL",
    "AGENTS_CHAT_DAILY_BUDGET_EUR",
    "AGENTS_CHAT_DAILY_MESSAGES_PER_USER",
    "AGENTS_CHAT_MAX_TOKENS",
    "AGENTS_CHAT_MAX_TOOL_ITERATIONS",
    "AGENTS_CHAT_MODEL",
    "AGENTS_CHAT_RETENTION_DAYS",
    "AGENTS_CHAT_TIMEOUT_S",
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


@pytest.fixture(autouse=True)
def _media_isolado(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Um `MEDIA_ROOT` por teste, numa pasta temporária.

    O `MEDIA_ROOT` do `base.py` é `backend/media/` (ADR 0020, decisão 4: um
    volume partilhado pelo `backend` e pelo `worker`). Sem esta fixture, o
    primeiro teste que aceita um upload escreve dentro do repositório — e fica
    lá, porque nada o apaga. Autouse e não por teste: o esquecimento falha no
    lado seguro, e um teste que **queira** medir o caminho real não existe.
    """
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))


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
    # O SMTP é obrigatório no `prod.py` desde 2026-10-07: sem isto, **todos** os
    # testes de settings de produção falhariam no `required(env, "EMAIL_HOST")` e
    # a mensagem apontava para o email em vez de para o que o teste mede.
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.pt")
    monkeypatch.setenv("EMAIL_HOST_USER", "stockflow@example.pt")
    monkeypatch.setenv("EMAIL_HOST_PASSWORD", "sem-valor-nao-e-segredo")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "StockFlow <stockflow@example.pt>")


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


# ---------------------------------------------------------------------------
# (c) O guarda de âmbito (ADR 0007)
#
# A regra "nada lê uma tabela com política antes de o âmbito existir" não é
# verificável por revisão: o modo de falha é a política devolver **zero linhas
# sem erro**, que aparece como "não encontrei nada" e não como bug. Foi o padrão
# que apareceu três vezes no mesmo dia.
#
# Este guarda transforma-a num teste vermelho. Está montado por
# `connection.execute_wrapper` em **todos** os testes e levanta quando as três
# condições se verificam ao mesmo tempo:
#
#   1. `current_tenant()` é `None` — não há `tenant_scope` aberto;
#   2. o âmbito de sistema, se estiver aberto, não alcança a relação em causa.
#      Há **dois** âmbitos legítimos (ADR 0005) e o guarda tem de conhecer os
#      dois: dentro de `system_scope()` o tenant é `None` por desenho, e é assim
#      que o consumidor da outbox lê a linha antes de saber de que tenant ela é.
#      Sem o `in_system_scope()`, o guarda acusava a leitura legítima do
#      consumidor e a saída era pôr-lhe a marca de dispensa — desligar o guarda
#      inteiro num teste para calar um caso que ele devia reconhecer.
#
#      Mas o âmbito de sistema não é um passe geral, e o guarda também não o
#      trata como tal: **só a política da outbox tem o disjunto `app.scope`**
#      (ADR 0005). Dentro de `system_scope()` o `app.tenant_id` está a NULL,
#      logo uma leitura do `accounts_membership` a partir de lá devolve zero
#      linhas em silêncio — o mesmo defeito, agora com um âmbito aberto a
#      dar-lhe aparência de legitimidade. O que decide é o predicado da política,
#      lido do catálogo;
#   3. o SQL menciona uma relação que tem política de RLS.
#
# A lista das relações — e o disjunto de cada política — vem do `pg_policy`, na
# primeira query que a precisa, e não de uma constante: uma tabela nova com
# política entra no guarda **sozinha**, sem ninguém se lembrar de a acrescentar
# aqui. É a mesma escolha do `tests/test_db_roles.py`, que varre o `pg_class` em
# vez de ler modelos.
#
# ## A dispensa, e por que razão existe
#
# `@pytest.mark.sem_ambito_de_rls` desliga-o para um teste. Só a devem ter os
# testes que fazem a leitura sem âmbito **de propósito**: os que provam que a
# política devolve zero linhas em vez de levantar. Fora desses, a marca é o
# sinal de que alguém está a contornar o guarda em vez de corrigir o código.
#
# Correr sob `system_scope()` **não** é motivo para a marca, e já foi: o guarda
# não distinguia âmbito de sistema de âmbito nenhum, e três testes levavam a
# dispensa por uma limitação do guarda e não por nada que quisessem provar. A
# marca é uma dispensa total — desliga o guarda para o teste inteiro, incluindo
# as queries que não são o objeto do teste —, por isso a limitação custava
# cobertura: o `in_system_scope()` da condição 2 é o que a devolve.
#
# O guarda tem um teste próprio em `tests/test_rls_isolation.py`, que faz a
# leitura proibida e afirma que ele levanta: sem isso, um guarda quebrado ficava
# verde e calado — que é exatamente a classe de defeito que ele existe para
# apanhar.
# ---------------------------------------------------------------------------

#: Nome do marcador que dispensa o guarda. Registado em `pyproject.toml`, porque
#: a suite corre com `--strict-markers`: um marcador mal escrito é um erro de
#: recolha e não uma dispensa silenciosa.
MARCADOR_SEM_AMBITO = "sem_ambito_de_rls"

#: As quatro instruções que a RLS filtra. `TRUNCATE` fica de fora de propósito:
#: nenhuma política o filtra (é por isso que o `_GRANT_TRUNCATE` acima existe) e
#: é o que o `flush` do pytest-django corre entre testes `transaction=True`.
#: `SAVEPOINT`, `SET`, `BEGIN` e DDL também não mencionam linhas.
_PREFIXOS_DML = frozenset({"select", "insert", "update", "delete"})

#: As relações com política **e** se a política de cada uma reconhece o âmbito
#: de sistema. O segundo valor vem do texto do predicado: só o
#: `shared_outboxevent` tem o disjunto `current_setting('app.scope') = 'system'`
#: (ADR 0005), e é a diferença entre "o consumidor pode ler isto sem tenant" e
#: "isto devolve zero linhas em silêncio". Lido do catálogo e não de uma
#: constante, como a lista das relações: uma tabela nova entra no guarda sozinha,
#: e com o disjunto certo.
_POLITICAS_SQL = """
SELECT c.relname,
       bool_or(pg_get_expr(p.polqual, p.polrelid) LIKE '%%app.scope%%')
  FROM pg_policy p
  JOIN pg_class c ON c.oid = p.polrelid
 WHERE c.relnamespace = 'public'::regnamespace
 GROUP BY c.relname
"""

_politicas_por_relacao: dict[str, bool] | None = None
_a_consultar_o_catalogo = False


class LeituraSemAmbito(AssertionError):
    """Query a uma tabela com política de RLS fora de um âmbito que a alcance.

    `AssertionError` e não `Exception`: isto é uma falha de teste, não uma
    condição de runtime. Em produção a mesma query não levanta — devolve zero
    linhas, que é o que a torna difícil de encontrar sem este guarda.
    """


def _politicas(conexao: Any) -> dict[str, bool]:
    """`{relação: a política reconhece o âmbito de sistema}`, lido uma vez."""
    global _politicas_por_relacao, _a_consultar_o_catalogo
    if _politicas_por_relacao is None:
        # A própria query ao catálogo passa pelo wrapper: sem esta bandeira,
        # recursão infinita na primeira leitura.
        _a_consultar_o_catalogo = True
        try:
            with conexao.cursor() as cursor:
                cursor.execute(_POLITICAS_SQL)
                _politicas_por_relacao = dict(cursor.fetchall())
        finally:
            _a_consultar_o_catalogo = False
    return _politicas_por_relacao


def _guarda_de_ambito(
    execute: Callable[..., object],
    sql: str,
    params: object,
    many: bool,
    context: dict[str, object],
) -> object:
    if _a_consultar_o_catalogo or current_tenant() is not None:
        return execute(sql, params, many, context)

    if sql.lstrip()[:6].lower() not in _PREFIXOS_DML:
        return execute(sql, params, many, context)

    sistema = in_system_scope()
    mencionadas = sorted(
        nome
        for nome, reconhece_sistema in _politicas(context["connection"]).items()
        if not (sistema and reconhece_sistema) and re.search(rf"\b{re.escape(nome)}\b", sql)
    )
    if mencionadas:
        raise LeituraSemAmbito(_porque_e_que_isto_devolve_zero_linhas(mencionadas, sql, sistema))
    return execute(sql, params, many, context)


def _porque_e_que_isto_devolve_zero_linhas(
    mencionadas: list[str], sql: str, sistema: bool
) -> str:
    """A mensagem do guarda, que é diferente nos dois casos que ele apanha."""
    if sistema:
        # Âmbito de sistema não é um passe geral: só a política do
        # `shared_outboxevent` tem o disjunto `app.scope` (ADR 0005). Nas outras,
        # `app.tenant_id` está a NULL dentro de `system_scope()` e a leitura
        # devolve zero linhas sem erro — o mesmo defeito silencioso, com um
        # âmbito aberto a dar-lhe uma aparência de legitimidade.
        return (
            f"query a {mencionadas} dentro de system_scope(), e a política "
            f"destas relações não tem o disjunto app.scope: com app.tenant_id a "
            f"NULL devolve zero linhas sem erro. O âmbito de sistema serve para "
            f"reclamar linhas da outbox e mais nada — lê a linha, fecha o bloco "
            f"e reentra em tenant_scope(row.tenant_id) antes de tocar em "
            f"dados do tenant (ADR 0005)."
            f"\nSQL: {sql[:200]}"
        )
    return (
        f"query a {mencionadas} sem âmbito nenhum — nem tenant_scope nem "
        f"system_scope. Em produção isto não levanta: a política devolve zero "
        f"linhas e o bug aparece como 'não encontrei nada'. Abre o âmbito "
        f"(ADR 0005) ou, se a leitura sem âmbito é o que o teste quer provar, "
        f"marca-o com @pytest.mark.{MARCADOR_SEM_AMBITO}."
        f"\nSQL: {sql[:200]}"
    )


@pytest.fixture(autouse=True)
def guarda_de_rls(request: pytest.FixtureRequest) -> Iterator[None]:
    """Monta o guarda em todos os testes que não o dispensem."""
    if request.node.get_closest_marker(MARCADOR_SEM_AMBITO):
        yield
        return
    with connections["default"].execute_wrapper(_guarda_de_ambito):
        yield
