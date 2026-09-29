"""A ligação que serve pedidos está sujeita à RLS, medido no catálogo (ADR 0006).

Este ficheiro não testa código do StockFlow: testa o **cluster** contra o qual a
suite corre. É a peça que a suite do passo 3 não conseguia ter. Lá, a política da
outbox só era avaliada porque uma fixture criava um role sem privilégios e
trocava para ele com `set_config('role', ...)`; provava a política e não provava
o produto, porque o role de `DATABASE_URL` era o bootstrap do cluster —
`SUPERUSER` com `BYPASSRLS`, que nenhuma política alcança nem com `FORCE`.

A asserção que faz a diferença é `session_user = current_user`. `current_user`
sozinho responde a "quem está a executar", e um `SET ROLE` satisfá-lo sem que
ninguém se tenha autenticado como ninguém — era isso que a fixture antiga fazia.
`session_user` é quem abriu a ligação e um `SET ROLE` não o muda: os dois iguais
é a única forma de dizer "a ligação **é** do `stockflow_app`", e depois desta ADR
não há um único `SET ROLE` no repositório.

As três varreduras do `pg_class` no fim existem para transformar regras escritas
em gates:

* o CLAUDE.md diz "toda a tabela com `tenant_id` tem política RLS na migração que
  a cria". Passa a ser um teste que falha na migração seguinte que se esqueça;
* o `roles.sql` concede DML por `ALTER DEFAULT PRIVILEGES`, que é indexado pelo
  role **que cria** a tabela: uma migração corrida pelo role errado produz
  tabelas sem GRANT nenhum, e o erro apareceria na app e não na migração. A
  varredura de privilégios apanha-o aqui;
* `APPEND_ONLY` é a lista fechada das tabelas onde `UPDATE`/`DELETE` estão
  revogados. Falha nos dois sentidos — se outra tabela os perder por acidente e
  se uma destas os recuperar.

`TRUNCATE` não entra em nenhuma asserção, e não é esquecimento: nenhuma política
o filtra, o `roles.sql` não o concede, e quem o concede é o `django_db_setup` do
`conftest.py` — no harness e só lá, porque o `flush` entre testes
`transaction=True` é um `TRUNCATE`. É por isso que o append-only que esta suite
prova é sobre `UPDATE` e `DELETE`.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.db import connection

from tests.conftest import APP_ROLE, reload_settings

#: Tabelas onde o role da app **não** tem `UPDATE` nem `DELETE`, por serem
#: append-only como regra de negócio. Hoje vazia: o `inventory_stockmovement` só
#: nasce no passo do ledger, e é a migração que o cria que faz o
#: `REVOKE UPDATE, DELETE`, ao lado do bloco de RLS. A lista existe já para que
#: a asserção exista já — e para que acrescentar a segunda entrada seja uma
#: decisão visível, com o `domain-expert` consultado (ADR 0006).
APPEND_ONLY: frozenset[str] = frozenset()

#: Uma tabela que tem de aparecer em todas as varreduras. Sem esta âncora, uma
#: query mal escrita devolvia zero linhas e todos os testes deste ficheiro
#: passavam por vacuidade.
TABELA_ANCORA = "shared_outboxevent"

_PRIVILEGIOS_DML = """
SELECT c.relname,
       has_table_privilege(%s, c.oid, 'SELECT'),
       has_table_privilege(%s, c.oid, 'INSERT'),
       has_table_privilege(%s, c.oid, 'UPDATE'),
       has_table_privilege(%s, c.oid, 'DELETE')
  FROM pg_class c
 WHERE c.relnamespace = 'public'::regnamespace
   AND c.relkind = 'r'
 ORDER BY c.relname
"""

_TABELAS_COM_TENANT_ID = """
SELECT c.relname,
       c.relrowsecurity,
       c.relforcerowsecurity,
       EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)
  FROM pg_class c
 WHERE c.relnamespace = 'public'::regnamespace
   AND c.relkind = 'r'
   AND EXISTS (
           SELECT 1
             FROM pg_attribute a
            WHERE a.attrelid = c.oid
              AND a.attname = 'tenant_id'
              AND a.attnum > 0
              AND NOT a.attisdropped
       )
 ORDER BY c.relname
"""


def _linhas(sql: str, params: list[object] | None = None) -> list[tuple[object, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _uma_linha(sql: str, params: list[object] | None = None) -> tuple[object, ...]:
    linhas = _linhas(sql, params)
    assert len(linhas) == 1, f"esperava uma linha, veio {len(linhas)}"
    return linhas[0]


# ---------------------------------------------------------------------------
# Quem é a ligação
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_a_ligacao_do_django_autenticou_se_como_o_role_da_app() -> None:
    utilizador_de_sessao, utilizador_atual, superuser, bypassrls = _uma_linha(
        """
        SELECT session_user, current_user, rolsuper, rolbypassrls
          FROM pg_roles
         WHERE rolname = current_user
        """
    )

    assert utilizador_atual == APP_ROLE
    assert utilizador_de_sessao == utilizador_atual, (
        "session_user != current_user: alguém fez SET ROLE. A ligação não é do "
        "role da app, só está a fingir que é — e um SET ROLE volta atrás."
    )
    assert superuser is False, "role com SUPERUSER: nenhuma política o alcança"
    assert bypassrls is False, "role com BYPASSRLS: nenhuma política o alcança"


@pytest.mark.django_db
def test_a_app_nao_pode_criar_no_esquema_public() -> None:
    """É o que faz um `migrate` com a URL errada morrer no primeiro
    `CREATE TABLE`, em vez de aplicar metade das operações."""
    pode_usar, pode_criar = _uma_linha(
        """
        SELECT has_schema_privilege(%s, 'public', 'USAGE'),
               has_schema_privilege(%s, 'public', 'CREATE')
        """,
        [APP_ROLE, APP_ROLE],
    )

    # O USAGE não é decoração: sem ele o `False` do CREATE não distinguia "sem
    # privilégio" de "o role não vê o esquema".
    assert pode_usar is True
    assert pode_criar is False


@pytest.mark.django_db
def test_a_app_nao_e_dona_de_nada_no_esquema_public() -> None:
    """O dono pode `DISABLE ROW LEVEL SECURITY` e `DROP POLICY`.

    Vale para qualquer `relkind` — tabelas, sequências, índices, vistas — porque
    a posse de uma sequência já dá `ALTER SEQUENCE` a quem não devia tê-lo.
    """
    da_app = [
        nome
        for (nome,) in _linhas(
            """
            SELECT c.relname
              FROM pg_class c
              JOIN pg_roles r ON r.oid = c.relowner
             WHERE c.relnamespace = 'public'::regnamespace
               AND r.rolname = %s
             ORDER BY c.relname
            """,
            [APP_ROLE],
        )
    ]
    assert da_app == []

    # E o outro lado da mesma moeda, que também é o que prova que a varredura
    # não está a olhar para um esquema vazio: as tabelas são todas do dono.
    donos = {
        dono
        for (dono,) in _linhas(
            """
            SELECT DISTINCT r.rolname
              FROM pg_class c
              JOIN pg_roles r ON r.oid = c.relowner
             WHERE c.relnamespace = 'public'::regnamespace
               AND c.relkind = 'r'
            """
        )
    }
    assert donos == {settings.MIGRATION_DATABASE["USER"]}


# ---------------------------------------------------------------------------
# Varredura do `pg_class`: privilégios e políticas
# ---------------------------------------------------------------------------
@pytest.fixture
def privilegios(db: None) -> dict[str, tuple[bool, bool, bool, bool]]:
    """`{tabela: (SELECT, INSERT, UPDATE, DELETE)}` para o role da app.

    Pede o `db` do pytest-django, que é o que dá acesso à base de dados aos dois
    testes que a usam — por isso é que eles não levam o marcador.
    """
    linhas = _linhas(_PRIVILEGIOS_DML, [APP_ROLE] * 4)
    mapa = {nome: (sel, ins, upd, dele) for nome, sel, ins, upd, dele in linhas}
    assert TABELA_ANCORA in mapa, "a varredura do pg_class não encontrou nada"
    return mapa


def test_a_app_le_e_escreve_em_todas_as_tabelas(
    privilegios: dict[str, tuple[bool, bool, bool, bool]],
) -> None:
    """Uma tabela criada por outro role não herda os `ALTER DEFAULT PRIVILEGES`
    do `stockflow_owner` e chega aqui sem GRANT nenhum."""
    sem_select = sorted(nome for nome, (sel, *_) in privilegios.items() if not sel)
    sem_insert = sorted(nome for nome, (_sel, ins, *_) in privilegios.items() if not ins)

    assert sem_select == []
    assert sem_insert == []


def test_so_as_tabelas_append_only_perdem_update_e_delete(
    privilegios: dict[str, tuple[bool, bool, bool, bool]],
) -> None:
    assert APPEND_ONLY <= privilegios.keys(), (
        "APPEND_ONLY nomeia tabelas que não existem no esquema: a lista ficou "
        "atrás de um rename ou de uma migração revertida."
    )

    sem_escrita_destrutiva = {
        nome for nome, (_sel, _ins, upd, dele) in privilegios.items() if not (upd and dele)
    }

    assert sem_escrita_destrutiva == set(APPEND_ONLY), (
        "a lista fechada de tabelas append-only mudou. Se foi de propósito, é "
        "uma decisão de domínio e passa pelo domain-expert (ADR 0006)."
    )


@pytest.mark.django_db
def test_toda_a_tabela_com_tenant_id_tem_rls_forcada_e_politica() -> None:
    """A regra do CLAUDE.md como gate, e não como item de revisão.

    O `FORCE` é o que sujeita o `stockflow_owner` à política: uma migração de
    dados sobre uma tabela de tenant corre como dono e tem de ver zero linhas
    até definir o `app.tenant_id` — a saída é iterar tenants, não `NO FORCE`.
    """
    linhas = _linhas(_TABELAS_COM_TENANT_ID)

    nomes = {nome for nome, *_ in linhas}
    assert TABELA_ANCORA in nomes, (
        f"{TABELA_ANCORA} tem coluna tenant_id e não apareceu: a varredura está "
        f"a olhar para o sítio errado e todo este teste passaria por vacuidade."
    )

    em_falta = sorted(
        nome
        for nome, enable, force, politica in linhas
        if not (enable and force and politica)
    )
    assert em_falta == [], (
        "tabelas com tenant_id sem ENABLE + FORCE ROW LEVEL SECURITY e sem "
        "política: a RLS entra no RunSQL da migração que cria a tabela."
    )


# ---------------------------------------------------------------------------
# A credencial do dono é uma setting, não uma alias
# ---------------------------------------------------------------------------
def test_o_databases_continua_a_ter_uma_alias_e_e_a_da_app() -> None:
    """Como alias, o `setup_databases` tentaria criar uma base de dados de teste
    também para o dono. E é esta asserção que prova que o `django_db_setup`
    devolveu a credencial à app antes do primeiro teste."""
    assert list(settings.DATABASES) == ["default"]
    assert settings.DATABASES["default"]["USER"] == APP_ROLE


def test_so_as_settings_de_teste_leem_a_credencial_do_dono(prod_env: None) -> None:
    """Em dev e em prod o role é propriedade do *processo*: o `migrate` corre num
    processo cujo `DATABASE_URL` é o `MIGRATION_DATABASE_URL`. Se o `prod.py` a
    lesse, a password do dono passava a existir em cada gunicorn e worker."""
    assert not hasattr(reload_settings("dev"), "MIGRATION_DATABASE")
    assert not hasattr(reload_settings("prod"), "MIGRATION_DATABASE")
    # A âncora: sem ela, um rename do nome da setting fazia os dois `not
    # hasattr` acima passar por vacuidade.
    assert hasattr(reload_settings("test"), "MIGRATION_DATABASE")
