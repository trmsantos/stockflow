"""Tabela da outbox e a primeira política de Row-Level Security do projeto.

Gerada por `makemigrations shared` e depois completada à mão com o bloco de RLS.
O que segue é o porquê de cada linha desse bloco, porque uma migração aplicada
não se edita (CLAUDE.md) e uma política mal escrita descobre-se tarde.

## Porque é que `ENABLE` não basta: `FORCE`

`ENABLE ROW LEVEL SECURITY` não se aplica ao **dono** da tabela, e o dono desta é
o `stockflow_owner` — o role que corre as migrações. Sem `FORCE`, uma migração de
dados corria sem política nenhuma. `FORCE ROW LEVEL SECURITY` sujeita-o, e entra
em todas as migrações de tabelas com `tenant_id` desde a primeira (ADR 0005).

Nota histórica, porque explica a forma deste ficheiro: quando esta migração foi
escrita o role da aplicação era o `stockflow` do compose, que é o bootstrap do
cluster (`initdb -U stockflow`) e portanto `SUPERUSER` com `BYPASSRLS` — e um
superuser **não** é sujeito a políticas nem com `FORCE`. A política existia e não
era imposta em runtime. A ADR 0006 separou os roles: a aplicação liga-se agora
como `stockflow_app`, `NOSUPERUSER NOBYPASSRLS` e dona de nada, e a RLS
alcança-a. O teste de isolamento deixou de precisar de trocar o role da ligação;
a guarda que o confirma mudou de casa para `tests/test_db_roles.py`.

## Porque é que o predicado leva `NULLIF`

O que `SECURITY.md` §3 e a ADR 0005 escrevem é
`current_setting('app.tenant_id', true)::uuid`, e a promessa é "sem tenant
definido, a comparação é NULL, zero linhas, sem erro". Medido contra o Postgres
16.15 do compose, a promessa só se cumpre na **primeira** transação de cada
ligação:

    -- ligação nova, nunca definiu o GUC
    current_setting('app.tenant_id', true)  ->  NULL
    -- depois de um set_config(..., true) e do fim da transação
    current_setting('app.tenant_id', true)  ->  ''      (string vazia)
    ''::uuid                                ->  ERRO: invalid input syntax

`app.tenant_id` é um *placeholder*, e o valor de arranque de um placeholder é a
string vazia, não NULL — é a esse valor que o fim da transação o devolve. Com
`CONN_MAX_AGE = 60` as ligações são persistentes, logo o segundo pedido sem
tenant servido pela mesma ligação levantava `invalid input syntax for type
uuid: ""` em vez de devolver zero linhas: falha aberta em forma de 500, num
caminho — login, healthcheck, anónimo — que é precisamente o que a ADR diz que
"não falha com erro".

`NULLIF(..., '')::uuid` devolve o predicado a NULL e a promessa cumpre-se em
qualquer transação da ligação. Está fixado em `tests/test_tenant_scope.py`.

## O disjunto de sistema, e porque é só aqui

O consumidor da outbox não é um pedido: não tem tenant e tem de poder reclamar
linhas de qualquer um. `app.scope = 'system'` é a única forma de ver uma linha
sem casar o `tenant_id`, e **só esta tabela** o tem na sua política (ADR 0005).
Não leva `NULLIF`: é comparação de texto, `'' = 'system'` é falso e NULL
propaga-se pelo `OR` sem erro.

## O que a política impõe nas escritas

Não há `WITH CHECK`, de propósito: sem ele o Postgres usa a expressão do `USING`
também para decidir que linhas podem ser inseridas ou atualizadas. Uma única
expressão, logo não podem divergir. O efeito é o que se quer — dentro de
`tenant_scope(A)` só se consegue escrever uma linha com `tenant_id = A`.

## Locks

`CreateModel` cria a tabela nesta transação: nenhuma outra sessão a consegue ver
ainda, pelo que os `CREATE INDEX` e os `ALTER TABLE` a seguir tomam o
`ACCESS EXCLUSIVE` sem fila de espera. O `SET LOCAL lock_timeout` está lá de
qualquer forma porque a regra é incondicional (skill `django-safe-migration`):
se um dia esta migração for reordenada, ou o bloco copiado para uma tabela que
já existe, falha depressa em vez de fazer fila e esgotar o pool.
"""

import uuid

from django.db import migrations, models

# O nome da tabela vai literal e não interpolado a partir de `_meta.db_table`:
# uma migração é um registo histórico do esquema e não se move com o modelo, e
# SQL construído por f-string é a forma de que o CLAUDE.md não quer ver nem o
# hábito.
APLICAR_RLS = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE shared_outboxevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_outboxevent FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON shared_outboxevent
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.scope', true) = 'system'
    );
"""

REVERTER_RLS = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON shared_outboxevent;

ALTER TABLE shared_outboxevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE shared_outboxevent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria `shared_outboxevent` e põe-na sob RLS na mesma transação."""

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("tenant_id", models.UUIDField(verbose_name="tenant")),
                (
                    "event_type",
                    models.CharField(max_length=200, verbose_name="tipo de evento"),
                ),
                ("payload", models.JSONField(default=dict, verbose_name="conteúdo")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="escrito em"),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        null=True,
                        verbose_name="processado em",
                    ),
                ),
                (
                    "attempts",
                    models.PositiveIntegerField(default=0, verbose_name="tentativas"),
                ),
                (
                    "last_error",
                    models.TextField(blank=True, default="", verbose_name="último erro"),
                ),
            ],
            options={
                "verbose_name": "evento na outbox",
                "verbose_name_plural": "eventos na outbox",
                "indexes": [
                    models.Index(
                        condition=models.Q(("processed_at__isnull", True)),
                        fields=["created_at"],
                        name="outbox_pendentes_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "created_at"],
                        name="outbox_tenant_idx",
                    ),
                ],
            },
        ),
        migrations.RunSQL(sql=APLICAR_RLS, reverse_sql=REVERTER_RLS),
    ]
