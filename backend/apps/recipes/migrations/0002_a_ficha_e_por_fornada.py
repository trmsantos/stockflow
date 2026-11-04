"""A ficha técnica passa a ser por **fornada** (ADR 0035, decisão 8).

## O que isto corre

Verificado com `uv run manage.py sqlmigrate recipes 0002`, que é a única fonte
que conta:

    SET LOCAL lock_timeout = '2s';
    ALTER TABLE "recipes_recipe"
      ADD COLUMN "batch_size" numeric(12, 3) DEFAULT 1.000 NOT NULL;
    ALTER TABLE "recipes_recipe" ALTER COLUMN "batch_size" DROP DEFAULT;
    ALTER TABLE "recipes_recipe"
      ADD CONSTRAINT "recipes_recipe_batch_size_positivo" CHECK ("batch_size" > 0);

O `DEFAULT 1.000` seguido de `DROP DEFAULT` é o que o Django emite para um
`AddField` com `preserve_default=False`, e é **de propósito** que ele não
sobrevive à migração — ver abaixo. O default é não-volátil (um literal), logo o
Postgres 11+ guarda-o no catálogo em vez de o escrever em cada linha: zero
reescrita, mesmo que houvesse linhas.

Os dois `AlterField` abaixo (`yield_factor` e `quantity_per_base_unit`) não
emitem SQL nenhum — o primeiro só ganha um `default` do ORM, que o Django **não**
escreve na base de dados, e o segundo só muda o `help_text`.

## Porque é que a coluna fica **sem `db_default`** depois disto

É o primeiro erro da checklist da skill `django-safe-migration`, e a razão dela é
uma só: num deploy em rolling o código **antigo** continua a inserir linhas sem a
coluna, e sem default na base de dados esses inserts falham com `NOT NULL
violation`. Duas coisas fecham-no, e as duas foram medidas e não presumidas:

1. **Não existe caminho de escrita nenhum para `recipes_recipe`.** Não há
   endpoint (`apps.recipes.urls` não existia até este PR), não há admin
   registado, e `grep -rn "Recipe.objects.create" apps/` não devolve uma linha —
   só testes. O código antigo nunca insere, logo não há insert para falhar.
2. **A tabela está vazia em todos os ambientes.** Confirmado em dev com
   `SELECT count(*) FROM recipes_recipe` → `0` (e `recipes_recipelineitem` → 0).
   Um `ADD COLUMN NOT NULL` sem default só falha se houver linhas; com zero é uma
   operação de catálogo e não uma reescrita.

**E um `db_default` aqui era pior do que a ausência dele.** A fornada é o divisor
do custo por unidade: um default permanente de `1` fazia uma ficha gravada sem
`batch_size` sair com o custo da fornada inteira colado a uma unidade — errado
por um factor de 400 num pastel de nata, e em silêncio. A coluna existe
precisamente para obrigar quem escreve a dizer o número.

Este é **o último instante** em que isto custa zero, e é esse o argumento da
decisão 8: a partir da primeira ficha gravada, mudar o significado da coluna
passava a ser uma migração de dados.

## O `lock_timeout`, e porque 2s

Metadata-only não quer dizer sem lock: o `ALTER TABLE` toma `ACCESS EXCLUSIVE`
por milissegundos, e o `ADD CONSTRAINT … CHECK` toma-o também — sobre uma tabela
de **zero linhas**, logo a varredura de validação não tem nada que varrer e a
janela é a actualização do catálogo. O perigo nunca foi o lock, é a **fila**: ele
espera por qualquer transacção longa aberta sobre a tabela, e tudo o que chega
depois espera por ele.

`SET LOCAL lock_timeout = '2s'` troca essa cascata por uma falha rápida e
legível. Dois segundos é o default da skill. `SET LOCAL` e não `SET`: fica no
âmbito desta transacção.

**Sem `NOT VALID` + `VALIDATE` no `CHECK`**, e é uma excepção consciente ao que a
skill pede: esse par existe para tirar a varredura de dentro do `ACCESS
EXCLUSIVE`, e aqui a varredura é de zero linhas. O preço do par — um
`SeparateDatabaseAndState` com `RunSQL` e `atomic = False`, que por sua vez
**anula** o `SET LOCAL lock_timeout` (medido na `accounts/0002`) — era pagar
máquina de segurança com segurança a menos.

## O que isto **não** faz

Não escreve em linha nenhuma, porque não há linha nenhuma. E não renomeia
`quantity_per_base_unit`, apesar de o nome ter passado a dizer menos do que a
coluna guarda: um `RenameField` é um `ACCESS EXCLUSIVE` que parte o código antigo
a meio do deploy (o `produzir()` e as tools de receitas seleccionam a coluna pelo
nome), e a ADR 0035 pede para mudar o significado e não o nome. Fica nomeado no
`models.py`.
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0001_initial"),
    ]

    operations = [
        # Antes dos dois `ACCESS EXCLUSIVE`, e no mesmo `atomic` — ver o topo.
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '2s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="recipe",
            name="batch_size",
            # Uma linha por argumento, como nas migrações do `accounts` e pela
            # mesma razão: o `makemigrations` gera uma linha que o
            # `line-length = 100` do ruff recusa, e não se abre excepção de
            # lint por formatação.
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("1.000"),
                help_text=(
                    "Quanto acabado sai de **uma fornada**, na unidade base do "
                    "artigo acabado (ex: 2400 para 2,4 kg de massa). Um prato "
                    "sem fornada escreve-se com 1. Deve ser > 0."
                ),
                max_digits=12,
            ),
            # O `default` acima é o que o Django exige para poder materializar a
            # coluna; **não** chega à base de dados (não é `db_default`) e sai do
            # `models.py` de propósito — ver o topo. Com a tabela vazia não
            # preenche linha nenhuma.
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="recipe",
            name="yield_factor",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("1.000"),
                help_text=(
                    "Fator de rendimento do processo. Nasce a 1,000 porque a "
                    "perda já está na fornada (ADR 0035, decisão 8). Deve ser "
                    "> 0, sem tecto."
                ),
                max_digits=5,
            ),
        ),
        migrations.AlterField(
            model_name="recipelineitem",
            name="quantity_per_base_unit",
            field=models.DecimalField(
                decimal_places=3,
                help_text=(
                    "Quantidade **por fornada**, na unidade base do ingrediente "
                    "(ex: 500 para 500 g de farinha numa fornada). Desde a ADR "
                    "0035 não é por unidade do acabado — o nome da coluna é "
                    "anterior."
                ),
                max_digits=12,
            ),
        ),
        migrations.AddConstraint(
            model_name="recipe",
            constraint=models.CheckConstraint(
                condition=models.Q(batch_size__gt=Decimal("0")),
                name="recipes_recipe_batch_size_positivo",
            ),
        ),
    ]
