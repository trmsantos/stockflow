"""O `painel` entra na lista fechada de rotas que o menu pode nomear.

## Isto não toca na base de dados, e vale dizê-lo

`AlterField` numa tabela de dados de um tenant costuma ser a operação a olhar com
desconfiança — e esta não emite SQL nenhum. Verificado com `sqlmigrate` antes de
ser escrita, que é a única fonte que conta:

    BEGIN;
    -- Alter field route_id on tenantmenuitem
    -- (no-op)
    COMMIT;

A razão é que só mudou o `choices`, que é validação em Python: o `max_length`
continua 32 e a coluna continua `varchar(32) NOT NULL`. Zero `ACCESS EXCLUSIVE`,
zero varrimento, zero necessidade de `lock_timeout` — e nada a correr num deploy
em rolling que possa prender a tabela.

## Porque existe uma migração para um no-op

Porque o Django guarda o estado dos modelos nas migrações, e sem esta o
`makemigrations --check` do CI fica vermelho para sempre — foi assim que ela
apareceu. O valor dela é de registo: o dia em que alguém pergunte quando é que o
`painel` entrou na união fechada, a resposta está aqui com data.

## O que **não** está aqui

Nenhuma linha é criada nem alterada. Os estabelecimentos que já tenham o menu
configurado não ganham uma linha para o `painel`: o registo vive em código e a
linha nasce na primeira escrita (ADR 0011), logo um tenant sem linha vê o default
— que é o item visível, no grupo "Painel", só para o `owner`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_tenantmenuitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantmenuitem',
            name='route_id',
            # Uma escolha por linha, e não a linha de 251 caracteres que o
            # `makemigrations` gera: o `line-length = 100` do ruff recusa-a, e
            # acrescentar uma terceira excepção ao `per-file-ignores` por causa de
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
                ],
                max_length=32,
                verbose_name="rota",
            ),
        ),
    ]
