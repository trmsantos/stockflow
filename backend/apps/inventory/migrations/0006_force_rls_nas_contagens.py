"""`FORCE ROW LEVEL SECURITY` nas duas tabelas de contagem (ADR 0006).

A `0005_add_stockcount_models` criou `inventory_stockcount` e
`inventory_stockcountline` com `ENABLE ROW LEVEL SECURITY` e as políticas
`stockcount_tenant_isolation` / `stockcountline_tenant_isolation` — com o
`NULLIF` certo — mas **sem `FORCE`**. Uma migração aplicada não se edita
(CLAUDE.md), por isso o `FORCE` chega aqui, numa migração própria.

## Porque é que o `FORCE` não é opcional

`ENABLE` não se aplica ao **dono** da tabela, e o dono é o `stockflow_owner`,
o role que corre as migrações (ADR 0006). Sem `FORCE`, uma migração de dados
sobre as contagens corria sem política nenhuma: lia e escrevia linhas de todos
os tenants com o `app.tenant_id` a NULL. Foi o gate
`test_toda_a_tabela_com_politica_tem_enable_e_force` do
`tests/test_db_roles.py` que o apanhou — a política existia, estava `ENABLE`,
passava nas duas igualdades de conjuntos, e não alcançava o dono.

A ligação que serve pedidos (`stockflow_app`) já estava sujeita à política:
não é dona de nada e não tem `BYPASSRLS`. O buraco era só do lado do dono, e
é por isso que esta migração não toca nas políticas nem no `ENABLE`.

## Locks

Ao contrário da `0004_tenantmenuitem` do `accounts`, as tabelas **já existem**
e podem ter leitores: o `ALTER TABLE ... FORCE ROW LEVEL SECURITY` toma
`ACCESS EXCLUSIVE` e faz fila atrás de qualquer transação aberta sobre elas.
O `SET LOCAL lock_timeout` é o que o faz falhar depressa em vez de esgotar o
pool de ligações (skill `django-safe-migration`). A migração é atómica, logo o
`SET LOCAL` vale para os dois `ALTER TABLE` que se seguem na mesma transação.

## `reverse_sql`

`NO FORCE` nas duas, com o mesmo `lock_timeout`. Reverter devolve o esquema ao
estado da `0005` — e o `tests/test_db_roles.py` volta a ficar vermelho, que é
o comportamento certo.
"""

from django.db import migrations

# Os nomes das tabelas vão literais e não interpolados a partir de
# `_meta.db_table`: uma migração é um registo histórico do esquema e não se
# move com o modelo, e SQL construído por f-string é a forma de que o
# CLAUDE.md não quer nem o hábito.
FORCAR_RLS_NAS_CONTAGENS = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE inventory_stockcount FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline FORCE ROW LEVEL SECURITY;
"""

REVERTER_FORCE_NAS_CONTAGENS = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE inventory_stockcount NO FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline NO FORCE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Sujeita o dono das tabelas de contagem às políticas que a `0005` criou."""

    dependencies = [
        ("inventory", "0005_add_stockcount_models"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORCAR_RLS_NAS_CONTAGENS,
            reverse_sql=REVERTER_FORCE_NAS_CONTAGENS,
        ),
    ]
