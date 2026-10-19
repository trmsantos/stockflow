"""As três alterações que ligar as contagens exige (ADR 0030).

**Zero tabelas novas, logo zero políticas novas.** O `inventory_stockcount` e o
`inventory_stockcountline` já existem, já têm `tenant_id` e já têm `ENABLE` +
`FORCE ROW LEVEL SECURITY` com o predicado do `NULLIF` (a `0005` criou as
políticas, a `0006` acrescentou o `FORCE`). As colunas novas não mudam o
predicado e os índices novos não lhe tocam: não há bloco de RLS nesta migração
porque não há tabela nova a proteger.

O que entra:

1. `inventory_stockcount.closing_reason` — a justificação do fecho, que passa a
   ser **sempre obrigatória** (ADR 0030, segunda ronda de respostas do dono: o
   limiar de 50 € era uma hipótese por calibrar). `NOT NULL DEFAULT ''`, pela
   convenção da `0007`: um valor só para "nada".
2. `inventory_stockcountline.counted_at` e `.counted_by_name` — quem contou e
   quando. O `counted_by_name` é uma **cópia** do nome da pertença, como o
   `created_by_name` do ledger: sobrevive à conta ser apagada e nunca é o email.
   Duas pessoas a contar o mesmo artigo deixam uma linha só, e o contrato exige
   dizer quem foi a última — "última a escrever ganha, mas nunca em silêncio".
3. Os dois índices únicos: um por estabelecimento para a contagem aberta
   (parcial, `WHERE status = 'open'`), e um por `(contagem, artigo, lote)` para
   o `POST /lines` ser upsert e não acumulação.

## Porque é que a reconciliação de dados tem de desarmar o `FORCE`

Os dois índices únicos podem encontrar linhas que os violam, e nenhuma delas é
hipotética: até hoje o `abrir_contagem` **nunca procurava** uma contagem já
aberta e o `adicionar_linha_contagem` criava uma linha nova a cada chamada
(ADR 0030, decisões 2 e 4). Uma base com duas contagens abertas no mesmo tenant,
ou com o mesmo artigo contado duas vezes na mesma contagem, é o estado que o
código de hoje produz — e o `CREATE UNIQUE INDEX` falharia sobre ela.

A reconciliação é um `UPDATE` e um `DELETE`, e corre sob `stockflow_owner`, que
é quem corre as migrações. Fora de um pedido não há `app.tenant_id`: o GUC é a
**string vazia**, o `NULLIF` da política transforma-o em `NULL`, o predicado dá
`NULL` para toda a linha e as duas instruções afectariam **zero linhas, em
silêncio** — e o `CREATE UNIQUE INDEX` a seguir rebentava com as linhas ainda lá.
É exactamente o modo de falha medido na `0007` (0 linhas com o `FORCE` armado,
341 com `NO FORCE`, sobre as mesmas linhas e na mesma ligação), e usa-se o mesmo
padrão: `NO FORCE` → converter → `FORCE`, tudo dentro da transação da migração.

O que torna a janela segura é o que o `NO FORCE` faz e o que não faz, e é o
argumento da `0007` sem uma vírgula a mudar: **não desliga a política** (só isenta
o dono; o `ENABLE` continua e o `stockflow_app`, que não é dono de nada e não tem
`BYPASSRLS`, fica sujeito do princípio ao fim), o `ACCESS EXCLUSIVE` dos `ALTER
TABLE` impede qualquer outra sessão de ler ou escrever estas tabelas durante a
transação, e um erro a seguir reverte tudo — incluindo o `NO FORCE`. O invariante
que o `tests/test_db_roles.py` afirma é **em repouso**, e em repouso continua a
valer.

## Que linha é que sobrevive, e porquê

* **Contagens abertas a mais**: fica aberta a que começou **mais tarde** — é a
  que alguém está a usar — e as outras passam a `closed` com
  `closed_at = started_at` e uma `closing_reason` que diz porquê. Fechar não
  inventa nada no ledger: uma contagem aberta nunca mexeu em stock (é o fecho que
  grava os `adjustment`), logo fechá-la aqui não gera movimento nenhum e não
  reescreve história. Apagá-las era a alternativa, e perdia o que lá estava
  contado.
* **Linhas duplicadas**: fica a **última** a ser criada, pelo `created_at` e com
  o `id` a desempatar. É precisamente a regra que o upsert passa a impor ("a
  última a escrever ganha, e nunca se somam os dois números"), aplicada
  retroactivamente ao que ficou de um tempo em que não havia regra nenhuma.

## `reverse_sql`

Completo e simétrico, operação a operação: os índices caem, as colunas caem, o
`FORCE` volta ao sítio. **Não é um inverso exacto da reconciliação, e não pode
ser**: as linhas apagadas não voltam e as contagens fechadas não reabrem — é
informação que esta migração descarta de propósito. Os `RunSQL` de dados têm por
reverso um `RunSQL.noop` explícito, para o `migrate --backwards` correr em vez de
recusar.

## Locks

`SET LOCAL lock_timeout = '2s'` (skill `django-safe-migration`, regra
incondicional), **um em cada ponta** da lista: a migração é atómica e um
`SET LOCAL` vale para toda a transação, mas na reversão a ordem inverte-se e o
timeout tem de estar posto antes do primeiro `ALTER TABLE` nos dois sentidos.

Sem `CONCURRENTLY` nos índices e sem `atomic = False`, pela mesma razão da
`0007`: entre operações a tabela ficaria, visível e commitada, com o `FORCE`
desarmado. As duas tabelas são pequenas — uma contagem por semana e algumas
centenas de linhas cada — e o varrimento do `CREATE UNIQUE INDEX` não domina
nada; numa tabela do tamanho do ledger a troca mereceria outra discussão.
"""

from django.conf import settings
from django.db import migrations, models

#: Os nomes das tabelas vão literais e não interpolados a partir de `_meta.db_table`:
#: uma migração é um registo histórico do esquema e não se move com o modelo, e SQL
#: construído por f-string é a forma de que o CLAUDE.md não quer nem o hábito.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '2s';"

DESARMAR_FORCE = """
ALTER TABLE inventory_stockcount NO FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline NO FORCE ROW LEVEL SECURITY;
"""

REPOR_FORCE = """
ALTER TABLE inventory_stockcount FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_stockcountline FORCE ROW LEVEL SECURITY;
"""

#: Fecha as contagens abertas a mais, uma por estabelecimento. Fica a que começou
#: mais tarde; o `id` desempata um empate exacto de `started_at`, para o resultado
#: não depender da ordem física das linhas.
FECHAR_CONTAGENS_ABERTAS_A_MAIS = """
UPDATE inventory_stockcount AS c
   SET status = 'closed',
       closed_at = COALESCE(c.closed_at, c.started_at),
       closing_reason = 'Fechada pela migração 0008: só pode haver uma contagem '
                        'aberta por estabelecimento.',
       updated_at = NOW()
 WHERE c.status = 'open'
   AND EXISTS (
         SELECT 1
           FROM inventory_stockcount AS mais_recente
          WHERE mais_recente.tenant_id = c.tenant_id
            AND mais_recente.status = 'open'
            AND (mais_recente.started_at, mais_recente.id) > (c.started_at, c.id)
       );
"""

#: Apaga as linhas duplicadas de `(contagem, artigo, lote)`, ficando a última a ser
#: criada — a regra que o upsert passa a impor.
APAGAR_LINHAS_DUPLICADAS = """
DELETE FROM inventory_stockcountline AS l
 WHERE EXISTS (
         SELECT 1
           FROM inventory_stockcountline AS mais_recente
          WHERE mais_recente.tenant_id = l.tenant_id
            AND mais_recente.stock_count_id = l.stock_count_id
            AND mais_recente.product_id = l.product_id
            AND mais_recente.lot_id IS NOT DISTINCT FROM l.lot_id
            AND (mais_recente.created_at, mais_recente.id) > (l.created_at, l.id)
       );
"""


class Migration(migrations.Migration):
    """Justificação do fecho, autor da linha e os dois índices únicos (ADR 0030)."""

    dependencies = [
        ("accounts", "0011_assistente_no_registo_de_rotas"),
        ("catalog", "0004_sku_unico_so_quando_existe"),
        ("inventory", "0007_texto_sem_null_no_ledger_e_nas_contagens"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
        migrations.AddField(
            model_name="stockcount",
            name="closing_reason",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="justificação do fecho",
            ),
        ),
        migrations.AddField(
            model_name="stockcountline",
            name="counted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="contada em"),
        ),
        migrations.AddField(
            model_name="stockcountline",
            name="counted_by_name",
            field=models.CharField(
                blank=True, default="", max_length=150, verbose_name="contada por"
            ),
        ),
        migrations.RunSQL(sql=DESARMAR_FORCE, reverse_sql=REPOR_FORCE),
        migrations.RunSQL(
            sql=FECHAR_CONTAGENS_ABERTAS_A_MAIS,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=APAGAR_LINHAS_DUPLICADAS,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(sql=REPOR_FORCE, reverse_sql=DESARMAR_FORCE),
        migrations.AddConstraint(
            model_name="stockcount",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "open")),
                fields=("tenant",),
                name="inventory_stockcount_uma_aberta_por_tenant",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockcountline",
            constraint=models.UniqueConstraint(
                fields=("tenant", "stock_count", "product", "lot"),
                name="inventory_stockcountline_uma_por_artigo",
                nulls_distinct=False,
            ),
        ),
        migrations.RunSQL(sql=LOCK_TIMEOUT, reverse_sql=LOCK_TIMEOUT),
    ]
