"""Texto vazio é `''` e nunca `NULL` nos quatro campos que ainda o permitiam (2026-10-19).

`StockMovement.reason`, `StockMovement.reason_detail`, `StockMovement.reference` e
`StockCountLine.zone` nasceram `null=True, blank=True`. É a convenção que o Django
desaconselha e que o `ruff` nomeia (`DJ001`): com `null=True` num campo de texto passam a
existir **dois** valores a significar "nada", e todo o leitor tem de tratar os dois — daí os
`or ""` e `or None` espalhados pelo `reporting`, pelo `inventory.api` e pelo `agents.tools`.
O resto do repositório já segue a convenção (ver `purchasing/models.py`). Esta migração
alinha o `inventory`: `default=""`, `blank=True`, `NOT NULL`.

## Porque é que o `UPDATE` tem de desarmar o `FORCE` primeiro

As duas tabelas têm `ENABLE` **e** `FORCE ROW LEVEL SECURITY` (ADR 0006, e a
`0006_force_rls_nas_contagens` para as contagens). O `FORCE` existe precisamente para
sujeitar o **dono** da tabela à política, e o dono — `stockflow_owner` — é quem corre as
migrações. Fora de um pedido não há `app.tenant_id`: o GUC é a **string vazia**, o `NULLIF`
da política transforma-o em `NULL`, o predicado dá `NULL` para toda a linha e o
`UPDATE ... WHERE reason IS NULL` afetaria **zero linhas**, em silêncio. O
`ALTER COLUMN ... SET NOT NULL` que vem a seguir rebentaria com os `NULL` ainda lá.

Por isso a migração faz, numa transação só: `NO FORCE` → `UPDATE` → `ALTER COLUMN` → `FORCE`.
O `FORCE` só volta no fim, e não logo a seguir ao `UPDATE`, porque o próprio Django emite um
`UPDATE ... SET <campo> = '' WHERE <campo> IS NULL` antes de cada `SET NOT NULL` (está no
`sqlmigrate`): com o `FORCE` já reposto esse `UPDATE` do Django seria cego, e o que ficava de
pé era só o `UPDATE` explícito aqui em baixo. Deixar os dois a funcionar tira do caminho uma
dependência subtil de ordem.

E o que torna a janela segura não é a brevidade, é o que o `NO FORCE` faz e o que não faz:

* **não desliga a política.** `NO FORCE` só isenta o *dono* da tabela; o `ENABLE` continua, e
  `stockflow_app` — que não é dono de nada e não tem `BYPASSRLS` — fica sujeito à política do
  princípio ao fim. Nenhuma ligação que sirva pedidos ganha alcance nenhum aqui;
* **nenhuma outra sessão lê ou escreve estas tabelas durante a transação.** O próprio
  `ALTER TABLE` toma `ACCESS EXCLUSIVE`, e só o larga no `COMMIT`, já com o `FORCE` reposto;
* se qualquer operação a seguir falhar, a transação inteira é revertida — incluindo o
  `NO FORCE`. Não há estado intermédio que sobreviva a um erro.

O invariante que o `tests/test_db_roles.py` afirma é **em repouso** ("toda a tabela com
política tem `ENABLE` + `FORCE`"), e em repouso ele continua a valer.

Medido na base de desenvolvimento a 2026-10-19, como `stockflow_owner` e fora de âmbito:
`UPDATE inventory_stockmovement SET reason = '' WHERE reason IS NULL` afetou **0** linhas com
o `FORCE` armado e **341** com `NO FORCE`, sobre as mesmas linhas e na mesma ligação. O modo
de falha desta migração não era um erro — era não fazer nada e dizer que sim.

## O caminho que não se tomou

Iterar os tenants e correr o `UPDATE` dentro de `tenant_scope(tenant_id)` era a alternativa.
Foi rejeitada por três razões: uma migração não deve importar código da aplicação
(`apps.shared.db` move-se, o esquema histórico não); a lista de tenants só se descobre pelo
`accounts_user.tenant_ids` (ARCHITECTURE.md §4.9), logo um tenant sem utilizador ativo ficava
com os `NULL` lá e o `SET NOT NULL` rebentava na mesma; e N transações de âmbito fazem N
varrimentos da tabela onde este faz um.

## Porque é que são três `RunSQL` e não um

Porque a reversão corre as operações pela ordem **inversa**, e o inverso correto é
`NO FORCE` → `DROP NOT NULL` → `UPDATE` para `NULL` → `FORCE`. Com um `RunSQL` único a
embrulhar tudo, o `UPDATE` que repõe `NULL` corria **antes** do `DROP NOT NULL` dos
`AlterField` e o `migrate --backwards` morria com violação de `NOT NULL` — medido no
`sqlmigrate --backwards` da primeira versão desta migração. Separar o desarmar, o preencher
e o repor em três operações faz com que cada uma tenha por inverso a sua simétrica e que a
ordem saia certa nos dois sentidos.

## Locks

`SET LOCAL lock_timeout = '2s'` (skill `django-safe-migration`, regra incondicional): os
`ALTER TABLE` tomam `ACCESS EXCLUSIVE` e, sem o timeout, fazem fila atrás de qualquer
transação aberta e arrastam todas as queries seguintes atrás deles. A migração é atómica,
logo um `SET LOCAL` vale para toda a transação — mas há **um em cada ponta** da lista de
operações, porque na reversão a ordem inverte-se e o timeout tem de estar posto antes do
primeiro `ALTER TABLE` nos **dois** sentidos.

Não se usou `CONCURRENTLY` para o índice nem `ADD CONSTRAINT ... NOT VALID` + `VALIDATE` para
o `SET NOT NULL`: os dois exigem `atomic = False`, que é exatamente o que o `NO FORCE` →
`UPDATE` → `FORCE` não pode ter — entre operações a tabela ficaria, visível e commitada, com
o `FORCE` desarmado. Numa tabela grande essa troca mereceria discussão; nesta, o varrimento
do `SET NOT NULL` domina de qualquer forma e já serializa a tabela.

## O índice parcial

`inv_stockmv_tenant_ref_idx` era `WHERE reference IS NOT NULL`. Com a coluna `NOT NULL`, esse
predicado passa a ser verdadeiro para **todas** as linhas e o índice parcial vira um índice
total sem ninguém dar por isso. O predicado passa a `WHERE NOT (reference = '')`, que é o que
o índice sempre quis dizer: indexa os movimentos que referenciam um documento.

## `reverse_sql`

Completo e simétrico, operação a operação. **Não é um inverso exato, e não pode ser**: as
linhas que já tinham `''` antes desta migração — o `zone`, que o `count_services` escreve com
`zone or ""` desde sempre — passam a `NULL` na reversão. A informação que distinguia os dois
valores é a que esta migração apaga de propósito.
"""

from django.db import migrations, models

#: Os nomes das tabelas vão literais e não interpolados a partir de `_meta.db_table`: uma
#: migração é um registo histórico do esquema e não se move com o modelo, e SQL construído
#: por f-string é a forma de que o CLAUDE.md não quer nem o hábito.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '2s';"

DESARMAR_FORCE = """
ALTER TABLE inventory_stockmovement NO FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline NO FORCE ROW LEVEL SECURITY;
"""

REPOR_FORCE = """
ALTER TABLE inventory_stockmovement FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline FORCE ROW LEVEL SECURITY;
"""

PREENCHER_COM_VAZIO = """
UPDATE inventory_stockmovement
   SET reason = COALESCE(reason, ''),
       reason_detail = COALESCE(reason_detail, ''),
       reference = COALESCE(reference, '')
 WHERE reason IS NULL OR reason_detail IS NULL OR reference IS NULL;

UPDATE inventory_stockcountline
   SET zone = ''
 WHERE zone IS NULL;
"""

REPOR_NULL = """
UPDATE inventory_stockmovement
   SET reason = NULLIF(reason, ''),
       reason_detail = NULLIF(reason_detail, ''),
       reference = NULLIF(reference, '')
 WHERE reason = '' OR reason_detail = '' OR reference = '';

UPDATE inventory_stockcountline
   SET zone = NULL
 WHERE zone = '';
"""


class Migration(migrations.Migration):
    """`''` em vez de `NULL` nos quatro campos de texto opcionais do `inventory`."""

    dependencies = [
        ("inventory", "0006_force_rls_nas_contagens"),
    ]

    operations = [
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
        migrations.RunSQL(sql=DESARMAR_FORCE, reverse_sql=REPOR_FORCE),
        migrations.RunSQL(sql=PREENCHER_COM_VAZIO, reverse_sql=REPOR_NULL),
        migrations.RemoveIndex(
            model_name="stockmovement",
            name="inv_stockmv_tenant_ref_idx",
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("expired", "Expirado"),
                    ("spoiled", "Estragado"),
                    ("prep_loss", "Perda de preparação"),
                    ("breakage", "Quebra"),
                    ("other", "Outro"),
                ],
                default="",
                max_length=20,
                verbose_name="motivo",
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="reason_detail",
            field=models.TextField(blank=True, default="", verbose_name="detalhes do motivo"),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="reference",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="referência de documento",
            ),
        ),
        migrations.AlterField(
            model_name="stockcountline",
            name="zone",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="zona"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(
                condition=models.Q(("reference", ""), _negated=True),
                fields=["tenant", "reference"],
                name="inv_stockmv_tenant_ref_idx",
            ),
        ),
        migrations.RunSQL(sql=REPOR_FORCE, reverse_sql=DESARMAR_FORCE),
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
    ]
