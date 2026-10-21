"""A exclusividade da contagem aberta passa a ser por localização (ADR 0033, d1).

**Zero tabelas novas, zero colunas, zero políticas RLS novas.** O
`inventory_stockcount` já existe, já tem `tenant_id` e já tem `ENABLE` + `FORCE
ROW LEVEL SECURITY` com o predicado do `NULLIF` (a `0005` criou a política, a
`0006` acrescentou o `FORCE`). Trocar um índice não toca no predicado, logo não
há bloco de RLS nesta migração — não há tabela nova a proteger.

Duas operações: largar `inventory_stockcount_uma_aberta_por_tenant` e criar
`inventory_stockcount_uma_aberta_por_local` sobre `(tenant_id, location_id)
WHERE status = 'open'`, composto a começar no `tenant` como os outros.

## Porque é que **não** há reconciliação de dados, ao contrário da `0008`

A `0008` teve de fechar contagens a mais antes de criar o seu índice, porque
estreitava o que a base permitia e as linhas que o violavam eram o estado normal
do código de então. Aqui é ao contrário: o índice novo é **mais permissivo** que
o velho. Uma contagem aberta por estabelecimento implica, no máximo, uma por
localização — logo nenhuma linha existente viola o índice novo, e não há nada a
converter. É por isso que esta migração não desarma o `FORCE`: sem `UPDATE` nem
`DELETE` de dados, não há nada que a política pudesse silenciar.

## A ordem das operações

Cria-se o índice novo **antes** de largar o velho. Dentro da transação da
migração a ordem é indiferente para quem está de fora, mas lida de cima para
baixo diz a verdade do que se está a fazer: a exclusividade estreita entra, e só
depois a larga sai. Nunca há um instante — nem no papel — em que a tabela fique
sem nenhuma.

## A reversão, e o que ela não consegue prometer

`migrate inventory 0008` volta a criar o índice por estabelecimento. Isso é
**estreitar**, e estreitar falha se entretanto houver duas contagens abertas em
localizações diferentes — que é exactamente o estado que esta migração passa a
permitir. Não se automatiza o contrário (fechar contagens para a reversão
passar): fechar uma contagem é uma decisão com justificação e, se tiver linhas
contadas, escreve `adjustment` irreversíveis no ledger. Quem reverter com
contagens abertas a mais fecha-as primeiro, uma a uma, pela aplicação.

## Locks

`SET LOCAL lock_timeout = '2s'` (skill `django-safe-migration`, regra
incondicional), **um em cada ponta** da lista: a migração é atómica e um
`SET LOCAL` vale para toda a transação, mas na reversão a ordem inverte-se e o
timeout tem de estar posto antes do `DROP INDEX`, que é o que pede `ACCESS
EXCLUSIVE`. Com ele, a migração falha depressa e com erro legível em vez de
ficar na fila atrás de uma transação longa, arrastando a fila toda atrás de si.

Sem `CONCURRENTLY` e sem `atomic = False`, pela razão da `0008`: o
`inventory_stockcount` é uma tabela de contagens (uma por localização e por
semana, ordens de grandeza abaixo do ledger), o varrimento do `CREATE UNIQUE
INDEX` não domina nada, e um `atomic = False` trocaria um lock de milissegundos
por uma migração que pode ficar a meio — com o índice novo criado e o velho
ainda de pé, ou pior, ao contrário. Numa tabela do tamanho do
`inventory_stockmovement` a troca mereceria outra discussão.

O `AddConstraint`/`RemoveConstraint` do Django emite `CREATE UNIQUE INDEX` e
`DROP INDEX` e não `ALTER TABLE ... ADD CONSTRAINT`: um `UniqueConstraint` com
`condition` é um índice parcial, e um índice parcial não pode ser uma constraint
de tabela em PostgreSQL. É a mesma forma que a `0008` gerou.
"""

from django.db import migrations, models

#: Igual ao da `0008`: uma migração é um registo histórico e não se move com o
#: modelo, logo o SQL vai literal e nunca interpolado a partir do `_meta`.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '2s';"


class Migration(migrations.Migration):
    """Uma contagem aberta por localização, e não uma por estabelecimento."""

    dependencies = [
        ("inventory", "0008_ligar_as_contagens"),
    ]

    operations = [
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
        migrations.AddConstraint(
            model_name="stockcount",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "open")),
                fields=("tenant", "location"),
                name="inventory_stockcount_uma_aberta_por_local",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="stockcount",
            name="inventory_stockcount_uma_aberta_por_tenant",
        ),
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
    ]
