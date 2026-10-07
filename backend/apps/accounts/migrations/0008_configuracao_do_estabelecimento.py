"""As três colunas que a ADR 0017 põe no `EstabelecimentoOut`.

`vat_regime`, `business_day_starts_at` e `is_demo` no `accounts_tenant`. A ADR
0013 decidiu as duas primeiras e nunca as criou; a terceira é da ADR 0018 e entra
aqui porque o contrato da 0017 a expõe (só de leitura) — um contrato com um campo
sem coluna promete o que não existe.

## Metadata-only, e é o `db_default` que o garante

Os três `AddField` são `NOT NULL` **com** `db_default`, pelo que o Postgres 11+
não reescreve a tabela: guarda o default no catálogo e as linhas existentes
passam a lê-lo de lá. Verificado com `sqlmigrate`, que é a única fonte que conta:

    ALTER TABLE "accounts_tenant"
      ADD COLUMN "vat_regime" varchar(20) DEFAULT 'normal' NOT NULL;
    ALTER TABLE "accounts_tenant"
      ADD COLUMN "business_day_starts_at" time DEFAULT '04:00:00'::time NOT NULL;
    ALTER TABLE "accounts_tenant"
      ADD COLUMN "is_demo" boolean DEFAULT false NOT NULL;

Sem o `db_default` seriam três varrimentos da tabela sob `ACCESS EXCLUSIVE`. Com
ele, o que resta é a actualização do catálogo — e o `lock_timeout` abaixo é por
causa do **lock**, não do varrimento: o `accounts_tenant` é lido em cada login
(ADR 0007), logo uma espera indefinida por `ACCESS EXCLUSIVE` aqui prendia a
entrada de todos os clientes atrás de uma transação longa.

`SET LOCAL` e não `SET`: o timeout morre com a transação desta migração e não
fica colado à ligação.

## A constraint **não** está aqui, e é de propósito

O `CHECK` da janela do dia de negócio vive na 0009, com `NOT VALID` seguido de
`VALIDATE`. Juntá-los dava uma migração cujo docstring diz "metadata-only" e cujo
`sqlmigrate` mostra um varrimento — que é exactamente a classe de mentira que o
docstring da 0005 existe para não repetir.

## O que **não** está aqui

Nenhuma linha muda de valor. Todos os estabelecimentos de hoje ficam em regime
normal, com o dia de negócio às 04:00 e `is_demo = false` — e os dois primeiros
são **hipóteses** e não respostas de um utilizador real (`domain-expert`,
2026-10-07): a hora exacta é a Q6 da sessão 0, e o regime é uma das perguntas que
a ADR 0013 já mandou para lá.
"""

from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_configuracao_no_registo_de_rotas"),
    ]

    operations = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '2s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="tenant",
            name="vat_regime",
            field=models.CharField(
                choices=[
                    ("normal", "Regime normal"),
                    ("isento_art_53", "Isento (art. 53.º)"),
                ],
                db_default="normal",
                default="normal",
                help_text=(
                    "Decide se o IVA de uma compra é custo. "
                    "Não é validado contra o volume de negócios."
                ),
                max_length=20,
                verbose_name="regime de IVA",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="business_day_starts_at",
            field=models.TimeField(
                db_default=time(4, 0),
                default=time(4, 0),
                help_text=(
                    "A hora que separa um dia do seguinte nos totais e nos alertas. "
                    "Não afeta validades."
                ),
                verbose_name="início do dia de negócio",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="is_demo",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text="Semeado para experimentar. Os dados não são de um negócio real.",
                verbose_name="é de demonstração",
            ),
        ),
    ]
