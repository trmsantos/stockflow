"""A unicidade do email passa a ser insensível à caixa.

Gerada por `makemigrations accounts` e reescrita à mão: o `AddConstraint` que o
Django gera constrói o índice **inline**, e o que vai para a base de dados é um
`CREATE UNIQUE INDEX CONCURRENTLY` dentro de um `SeparateDatabaseAndState`
(skill `django-safe-migration`). Uma migração aplicada não se edita
(CLAUDE.md) — por isso a unicidade nova vem aqui e a `0001_initial` fica como
está.

## A decisão, e por que razão é agora

`Ana@x.pt` e `ana@x.pt` eram duas contas: é o default do Postgres (`email = %s`
compara byte a byte) e o `normalize_email` do Django só dobra o domínio. A
decisão do produto é que são a **mesma** conta, e o momento é o ponto: com zero
contas criadas isto é um índice e nada mais. Feito mais tarde, seria este índice
mais uma política de reconciliação para as contas existentes — e essa não tem
resposta boa (qual das duas fica? o que acontece aos dados da outra?).

As outras três peças vivem fora desta migração, e sem elas o índice sozinho
seria uma armadilha: `UserManager.normalize_email` (escrita),
`UserManager.get_by_natural_key` (o lookup da autenticação) e o
`AXES_USERNAME_CALLABLE` de `config/lockout.py` (o contador de tentativas do
axes, que conta por conta pelo valor cru do formulário).

## Índice único, e não constraint de tabela

O predicado é uma expressão, e uma expressão não pode ser promovida a
constraint: o `ALTER TABLE ... ADD CONSTRAINT ... UNIQUE USING INDEX` do
Postgres recusa índices de expressão. O Django sabe disso e o `AddConstraint`
de um `UniqueConstraint(Lower(...))` emite mesmo um `CREATE UNIQUE INDEX`
(verificado com `sqlmigrate`) — o que falta é o `CONCURRENTLY`, e é só isso que
o `SeparateDatabaseAndState` daqui troca. O estado do Django continua a ser o
`UniqueConstraint` do modelo, logo o `makemigrations --check` fica limpo e o
`full_clean()` continua a validar a constraint no formulário do admin.

## Locks, e a ausência de `SET LOCAL lock_timeout`

A tabela existe e é servida por pedidos — ao contrário das três da
`0001_initial`, que nasciam na mesma transação. Um `CREATE UNIQUE INDEX` normal
toma `SHARE`: bloqueia **escritas** durante a construção do índice, e no
`accounts_user` isso é o registo e o login (que escreve `last_login`).
`CONCURRENTLY` toma `SHARE UPDATE EXCLUSIVE`, que não bloqueia leituras nem
escritas — ao preço de duas varreduras e de `atomic = False`.

Aqui **não** há `SET LOCAL lock_timeout`, e é a única migração do repositório
onde a regra incondicional da skill não se aplica: nenhuma destas instruções
toma `ACCESS EXCLUSIVE`, e as duas formas de a escrever estão medidas contra o
Postgres 16.15 do compose e não deduzidas:

1. no mesmo `RunSQL` que o `CONCURRENTLY` não funciona. O backend do Postgres
   do Django faz `prepare_sql_script` devolver `[sql]`
   (`django/db/backends/postgresql/operations.py:193`), ou seja o script inteiro
   vai num `cursor.execute()` só, e o psycopg manda-o pelo protocolo simples —
   que embrulha as instruções numa transação implícita. Medido:
   `InternalError: CREATE INDEX CONCURRENTLY cannot run inside a transaction block`;
2. num `RunSQL` à parte também não. `SET LOCAL` fora de um bloco de transação
   não tem efeito nenhum — numa migração `atomic = False` cada operação corre em
   autocommit. Medido: a seguir ao `SET LOCAL lock_timeout = '2s'`, um
   `SHOW lock_timeout` devolve `0`.

## Sem `IF NOT EXISTS`

De propósito. Um `CREATE INDEX CONCURRENTLY` que falhe a meio deixa atrás um
índice **inválido**, que não impõe unicidade nenhuma; com `IF NOT EXISTS`, a
segunda tentativa encontrava-o, não fazia nada e a migração ficava verde com a
regra desligada — exatamente a classe de defeito silencioso que este
repositório persegue. Sem ele, a repetição falha com `relation already exists` e
obriga a olhar para o índice inválido (`pg_index.indisvalid`) e a apagá-lo à
mão. O `reverse_sql` leva `IF EXISTS` pela razão simétrica: reverter tem de
funcionar depois de uma aplicação falhada.
"""

from django.db import migrations, models
from django.db.models.functions import Lower

# O nome da tabela e do índice vão literais, como na `0001_initial`: uma
# migração é um registo histórico do esquema e não se move com o modelo.
CRIAR_INDICE = """
CREATE UNIQUE INDEX CONCURRENTLY user_email_lower_uniq
    ON accounts_user (LOWER(email))
"""

APAGAR_INDICE = "DROP INDEX CONCURRENTLY IF EXISTS user_email_lower_uniq"


class Migration(migrations.Migration):
    """Um índice único funcional sobre `LOWER(email)`, construído sem bloquear."""

    # `CONCURRENTLY` não corre dentro de uma transação, nos dois sentidos.
    atomic = False

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="user",
                    constraint=models.UniqueConstraint(
                        Lower("email"),
                        name="user_email_lower_uniq",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(sql=CRIAR_INDICE, reverse_sql=APAGAR_INDICE),
            ],
        ),
    ]
