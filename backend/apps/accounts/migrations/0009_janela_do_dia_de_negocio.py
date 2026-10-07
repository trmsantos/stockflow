"""O `CHECK` que impede um dia de negócio fora da janela 00:00–06:00.

## Porque é que isto é uma constraint e não só validação

O serializer já recusa uma hora fora da janela com um 400 por campo. Isto é a
**rede**, pela mesma razão com que a unicidade do menu vive na base de dados e
com que o isolamento entre clientes vive na RLS: um dia de negócio a começar às
16:00 parte todos os dias em dois **em silêncio**, e silêncio é o modo de falha
que esta casa não aceita. Uma linha assim não deve conseguir existir, venha de
onde vier — de um shell, de um comando de gestão, de um fixture.

A janela vem da consulta ao `domain-expert` (2026-10-07): a meia-noite é o limite
inferior legítimo (uma casa que fecha ao jantar) e as 06:00 o superior (um bar com
licença até às 04:00, mais a limpeza).

## `NOT VALID` e depois `VALIDATE`, e `atomic = False`

Um `ADD CONSTRAINT ... CHECK` normal toma `ACCESS EXCLUSIVE` **e varre a tabela
inteira** antes de largar o lock. O `accounts_tenant` é lido em cada login (ADR
0007), pelo que o varrimento acontece com a entrada de todos os clientes à espera.
Partido em dois, o lock que bloqueia dura milissegundos:

* `ADD CONSTRAINT … NOT VALID` cria a constraint e passa a impô-la **nas escritas
  novas** sem varrer o que já lá está;
* `VALIDATE CONSTRAINT` varre, sob `SHARE UPDATE EXCLUSIVE`, que não bloqueia
  leituras nem escritas.

`atomic = False` é obrigatório para o segundo passo: com a transação da migração
por fora, o `VALIDATE` segurava os locks de tudo o que veio antes durante o
varrimento inteiro — e o `SHARE UPDATE EXCLUSIVE` conflitua consigo próprio.

**O `SET LOCAL` vai na *mesma* `RunSQL` do `ALTER`, e isto não é arrumação.** Com
`atomic = False` cada operação corre fora de uma transação envolvente, logo um
`RunSQL("SET LOCAL …")` sozinho reverteria antes da operação seguinte começar — a
linha existiria e o efeito não. Juntas numa `RunSQL`, as duas instruções seguem na
mesma transação implícita e o timeout aplica-se ao `ALTER`.

## A janela de integridade que o `NOT VALID` abre, e porque não importa aqui

Entre os dois passos, as linhas antigas estão por validar. Neste caso a janela é
vazia por construção: a coluna nasceu na 0008 com `db_default = '04:00'`, pelo que
**todas** as linhas existentes satisfazem o predicado antes de o `VALIDATE` correr.
Fica escrito porque numa tabela com dados a sério esta frase seria diferente.

## `SeparateDatabaseAndState`, e o nome da constraint é o contrato entre as duas metades

O Django não sabe emitir `NOT VALID`, logo o SQL é nosso e o **estado** é dele. O
`name=` do `CheckConstraint` no modelo e o nome no `ALTER TABLE` têm de ser o
mesmo literal: se divergirem, o `makemigrations --check` fica verde (o estado está
certo) e a base de dados tem uma constraint que nenhuma migração conhece — o
`reverse_sql` deixava de a apanhar e o `sqlmigrate` não mostraria nada de errado.
"""

from datetime import time

from django.db import migrations, models

#: O nome, escrito **uma vez** e usado nos três sítios (estado, criação, reversão).
#: É a forma de o contrato descrito acima não poder divergir por um erro de dedo.
NOME = "tenant_dia_de_negocio_entre_0_e_6"


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("accounts", "0008_configuracao_do_estabelecimento"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="tenant",
                    constraint=models.CheckConstraint(
                        # Os mesmos `time` do modelo e não as strings
                        # equivalentes: o `makemigrations --check` compara o
                        # estado por valor, e `"00:00:00"` != `time(0, 0)` para
                        # ele — o que gera uma décima migração a remover e
                        # recriar a mesma constraint. Medido.
                        condition=models.Q(
                            business_day_starts_at__range=(time(0, 0), time(6, 0))
                        ),
                        name=NOME,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "SET LOCAL lock_timeout = '2s';"
                        f'ALTER TABLE "accounts_tenant" ADD CONSTRAINT "{NOME}" '
                        "CHECK (\"business_day_starts_at\" BETWEEN '00:00:00' AND '06:00:00') "
                        "NOT VALID;"
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "accounts_tenant" DROP CONSTRAINT "{NOME}";'
                    ),
                ),
                migrations.RunSQL(
                    sql=f'ALTER TABLE "accounts_tenant" VALIDATE CONSTRAINT "{NOME}";',
                    # Validar não se desfaz: o que se desfaz é a constraint, e é
                    # o `reverse_sql` da operação acima que a larga.
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
