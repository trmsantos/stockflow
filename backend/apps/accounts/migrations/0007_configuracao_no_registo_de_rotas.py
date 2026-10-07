"""O `configuracao` entra na lista fechada de rotas que o menu pode nomear.

## Não toca na base de dados, como a 0005 não tocou

É a segunda vez que esta migração existe — a 0005 fez o mesmo pelo `painel` — e a
razão de ser um no-op é a mesma: só mudou o `choices`, que é validação em Python.
O `max_length` continua 32 e a coluna continua `varchar(32) NOT NULL`. Verificado
com `sqlmigrate` **antes** de esta ser escrita, que é a única fonte que conta:

    BEGIN;
    -- Alter field route_id on tenantmenuitem
    -- (no-op)
    COMMIT;

Zero `ACCESS EXCLUSIVE`, zero varrimento, zero necessidade de `lock_timeout`.

## Porque existe uma migração para um no-op

Porque o Django guarda o estado dos modelos nas migrações, e sem esta o
`makemigrations --check` do CI fica vermelho para sempre. O valor dela é de
registo: o dia em que alguém pergunte quando é que o `configuracao` entrou na
união fechada, a resposta está aqui com data — 2026-10-07, ADR 0017.

## O que **não** está aqui, e é a parte que vale ler

Nenhuma linha é criada nem alterada. Um estabelecimento que já tenha o menu
configurado **não** ganha uma linha para o `configuracao`: o registo vive em
código e a linha nasce na primeira escrita (ADR 0011), logo um tenant sem linha
vê o default — visível, no grupo "Equipa", ordem 70, e **só para o `owner`**.

E não há aqui coluna nenhuma do estabelecimento. O `vat_regime` e o
`business_day_starts_at` que a ADR 0017 põe no `EstabelecimentoOut` são colunas
do `accounts_tenant` e vêm na sua própria migração: esta é sobre a lista de ids
que o menu pode nomear, e juntar as duas coisas num ficheiro dava uma migração
que o `sqlmigrate` mostra a mexer na base de dados com um docstring a dizer que
não mexe.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_tema_do_utilizador"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantmenuitem",
            name="route_id",
            # Uma escolha por linha, e não a linha de 276 caracteres que o
            # `makemigrations` gera: o `line-length = 100` do ruff recusa-a, e
            # acrescentar uma excepção ao `per-file-ignores` por causa de
            # formatação seria gastar o mecanismo que o CLAUDE.md reserva para
            # decisões com ADR. A lista é a mesma, na mesma ordem.
            field=models.CharField(
                choices=[
                    ("inicio", "Início"),
                    ("painel", "Painel de gestão"),
                    ("alertas", "Alertas"),
                    ("stock", "Stock"),
                    ("contar", "Contar"),
                    ("receber", "Receber"),
                    ("convites", "Convites"),
                    ("configuracao", "Configuração"),
                ],
                max_length=32,
                verbose_name="rota",
            ),
        ),
    ]
