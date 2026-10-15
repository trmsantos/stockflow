"""A unicidade do `sku` passa a parcial: só quando existe.

A `0002_add_sku_to_product` acrescentou `sku` com `default=""` e a constraint
`catalog_product_sku_lower_uniq` sobre `(Lower("sku"), tenant)` **sem
condição**. Como a coluna é `""` e não NULL (`DJ001`), dois artigos sem SKU no
mesmo tenant eram uma violação de unicidade na base de dados — medido na
suite: 25 testes que criam `Product` sem passar pelo serviço rebentavam no
segundo artigo. Uma migração aplicada não se edita (CLAUDE.md), por isso a
correção é esta: tirar a constraint total e pôr a parcial, `WHERE sku <> ''`,
na forma da `catalog_packaging_ean_uniq`.

O comportamento da API não muda: `catalog/services.py` já preenche o `sku`
com o `short_name` quando vem vazio, e a `0003_populate_sku` já o fez às
linhas que existiam. A constraint continua a recusar dois artigos com o mesmo
SKU (sem caixa) no mesmo tenant.

## Locks

`RemoveConstraint` de uma unique é um `DROP INDEX` (`ACCESS EXCLUSIVE`), e o
`AddConstraint` constrói o índice sob `SHARE`, que bloqueia escritas durante
a construção. A tabela é pequena e a migração é atómica, por isso o índice
não se constrói `CONCURRENTLY` — mas o `SET LOCAL lock_timeout` fica, para a
migração falhar depressa em vez de fazer fila atrás de uma transação longa
(skill `django-safe-migration`). Como o `SET LOCAL` não cabe dentro de uma
operação do Django, vai num `RunSQL` à cabeça para o sentido directo e noutro
à cauda para o inverso: ao reverter, as operações correm por ordem inversa e
é o da cauda que corre primeiro.

## `reverse_sql`

Reverter repõe a constraint total da `0002`, e volta a falhar com dois
artigos sem SKU — é o estado anterior, e é isso que reverter quer dizer.
"""

from django.db import migrations, models
from django.db.models.functions import Lower

LOCK_TIMEOUT = "SET LOCAL lock_timeout = '2s';"


class Migration(migrations.Migration):
    """Troca a unicidade total do `sku` pela parcial, `WHERE sku <> ''`."""

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
        ("catalog", "0003_populate_sku"),
    ]

    operations = [
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=migrations.RunSQL.noop),
        migrations.RemoveConstraint(
            model_name="product",
            name="catalog_product_sku_lower_uniq",
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                Lower("sku"),
                models.F("tenant"),
                condition=models.Q(("sku", ""), _negated=True),
                name="catalog_product_sku_lower_uniq",
            ),
        ),
        migrations.RunSQL(sql=migrations.RunSQL.noop, reverse_sql=LOCK_TIMEOUT),
    ]
