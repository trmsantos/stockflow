"""A tabela da localização, e a sua política de RLS.

Gerada por `makemigrations inventory` e completada à mão com o bloco de RLS, na
forma do `apps/purchasing/migrations/0001_initial.py`. Uma migração aplicada não
se edita (CLAUDE.md), por isso o porquê de cada linha fica aqui escrito.

## Quem tem política, e sobre que coluna

| Tabela | `ENABLE` + `FORCE` | Predicado |
|---|---|---|
| `inventory_location` | sim | `tenant_id = app.tenant_id` |

Herda `TenantModel`, logo tem `tenant_id` e leva política na migração que a cria
— é a regra do `CLAUDE.md` que não se discute. O `SEM_POLITICA` do
`tests/test_db_roles.py` **não mexe**: a localização nunca é lida fora de âmbito.

É a **primeira** tabela do `inventory`, e deliberadamente a única desta fatia: o
ledger (`inventory_lot`, `inventory_stockmovement`, `inventory_stocklevel`,
`inventory_productcost`) é a fatia 3 da ADR 0021, e é a migração dele que traz o
primeiro `REVOKE UPDATE, DELETE` deste projecto — o `APPEND_ONLY` do
`tests/test_db_roles.py` continua vazio até lá.

## `FORCE`, e o `NULLIF`

`ENABLE ROW LEVEL SECURITY` não se aplica ao **dono** da tabela, e o dono desta é
o `stockflow_owner`, o role que corre as migrações: sem `FORCE`, uma migração de
dados sobre ela corria sem política nenhuma (ADR 0006). A aplicação liga-se como
`stockflow_app` — `NOSUPERUSER NOBYPASSRLS`, dona de nada — e a RLS alcança-a de
facto.

O `NULLIF` não é decoração. `app.tenant_id` é um *placeholder* e o valor a que o
fim da transação o devolve é a **string vazia**, não NULL. Sem ele, `''::uuid`
levanta `invalid input syntax for type uuid: ""` a partir da segunda transação de
cada ligação persistente, e o pedido *sem* tenant (login, healthcheck, anónimo,
404 antes da view) responde 500 em vez de ver zero linhas. Fixado em
`tests/test_tenant_scope.py` e afirmado, predicado a predicado, em
`tests/test_db_roles.py`.

## Sem `WITH CHECK` separado, e sem disjuntos

Uma expressão só para ler e escrever: dentro de `tenant_scope(A)` só se consegue
escrever uma linha com `tenant_id = A`. E sem o disjunto `app.scope` da outbox —
nada aqui precisa do âmbito de sistema (ADR 0005).

## Locks

A tabela nasce nesta transação: nenhuma outra sessão a consegue ver ainda, pelo
que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de espera. O
`SET LOCAL lock_timeout` está lá porque a regra é incondicional (skill
`django-safe-migration`): se um dia este bloco for copiado para uma tabela que já
existe, falha depressa em vez de fazer fila e esgotar o pool de ligações.

## `reverse_sql`

Completo, como no `purchasing`: `migrate inventory zero` e de volta, com o
`tests/test_db_roles.py` a afirmar a política nos dois sentidos depois disso.
"""

import uuid

import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models

# O nome da tabela vai literal e não interpolado a partir de `_meta.db_table`:
# uma migração é um registo histórico do esquema e não se move com o modelo, e
# SQL construído por f-string é a forma de que o CLAUDE.md não quer ver nem o
# hábito.
APLICAR_RLS_LOCATION = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE inventory_location ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_location FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON inventory_location
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_LOCATION = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON inventory_location;

ALTER TABLE inventory_location NO FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_location DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria a tabela da localização e põe-na sob RLS na mesma transação."""

    initial = True

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("name", models.CharField(max_length=60, verbose_name="nome")),
                ("position", models.PositiveSmallIntegerField(verbose_name="ordem")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativa")),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.tenant",
                        verbose_name="tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "localização",
                "verbose_name_plural": "localizações",
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"], name="inventory_l_tenant__f9ca9e_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        django.db.models.functions.text.Lower("name"),
                        models.F("tenant"),
                        name="inventory_location_name_lower_uniq",
                    )
                ],
            },
        ),
        migrations.RunSQL(sql=APLICAR_RLS_LOCATION, reverse_sql=REVERTER_RLS_LOCATION),
    ]
