"""O `assistente` entra na lista fechada de rotas que o menu pode nomear (ADR 0027).

## Não toca na base de dados, como a 0005, a 0007 e a 0010 não tocaram

Só mudou o `choices`, que é validação em Python. O `max_length` continua 32 e a
coluna continua `varchar(32) NOT NULL`. Verificado com `sqlmigrate` antes de esta
ser escrita:

    BEGIN;
    -- Alter field route_id on tenantmenuitem
    -- (no-op)
    COMMIT;

Zero `ACCESS EXCLUSIVE`, zero varrimento, zero necessidade de `lock_timeout`.

## Porque existe uma migração para um no-op

Porque o Django guarda o estado dos modelos nas migrações, e sem esta o
`makemigrations --check` do CI fica vermelho para sempre. O valor dela é de
registo: o dia em que alguém pergunte quando é que o `assistente` entrou na união
fechada, a resposta está aqui com data — 2026-10-15, ADR 0027, decisão 10.

## Nenhuma linha nasce aqui

Um estabelecimento que já tenha o menu configurado **não** ganha uma linha para o
`assistente`: o registo vive em código e a linha nasce na primeira escrita (ADR
0011), logo um tenant sem linha vê o default — visível, ordem 25, para os três
papéis. E uma migração de dados sobre esta tabela apagaria ou escreveria zero
linhas em silêncio, pelo `FORCE` (medido na 0010).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantmenuitem",
            name="route_id",
            # Uma escolha por linha, pela razão da 0005: o `line-length = 100` do
            # ruff recusa a linha que o `makemigrations` gera.
            field=models.CharField(
                choices=[
                    ("inicio", "Início"),
                    ("painel", "Painel de gestão"),
                    ("alertas", "Alertas"),
                    ("assistente", "Assistente"),
                    ("stock", "Stock"),
                    ("contar", "Contar"),
                    ("receber", "Receber"),
                ],
                max_length=32,
                verbose_name="rota",
            ),
        ),
    ]
