"""A preferência de tema de cada pessoa (ADR 0016).

## O que isto corre, e porque é seguro

    ALTER TABLE "accounts_user" ADD COLUMN "tema" varchar(16)
      DEFAULT 'escuro' NOT NULL;

Verificado com `sqlmigrate` antes de ser escrita. Duas propriedades fazem disto
uma operação de metadados e não uma reescrita:

* **o default é não-volátil** (uma string literal), e o Postgres 11+ guarda-o no
  catálogo em vez de o escrever em cada linha. Sem isso, um `ADD COLUMN ... NOT
  NULL DEFAULT` reescrevia a tabela inteira sob `ACCESS EXCLUSIVE`;
* **o `db_default` do modelo é o que o põe lá.** O `default` do Django é só do
  ORM: num deploy em rolling o código **antigo** continua a inserir linhas sem
  esta coluna, e sem um default na base de dados esses inserts falhavam com
  `NOT NULL violation`. É o primeiro erro da checklist da skill de migrações, e
  o Django 5 tem `db_default` precisamente para o fechar.

## O `lock_timeout`, e porque 2s

Metadata-only não quer dizer sem lock: o `ALTER TABLE` toma `ACCESS EXCLUSIVE`
por milissegundos. O perigo não é o lock, é a **fila**: ele espera por qualquer
transacção longa que esteja aberta, e tudo o que chega depois espera por ele —
numa tabela quente isso cascateia até esgotar o pool de ligações.

`SET LOCAL lock_timeout = '2s'` troca essa cascata por uma falha rápida e
legível. Dois segundos é o default da skill e é generoso para o que isto é: a
`accounts_user` é lida em todos os pedidos mas escrita raramente, e não há
transacção longa nenhuma a tocá-la. `SET LOCAL` e não `SET`: fica no âmbito desta
transacção e não afecta sessão nenhuma depois de terminar.

## O que isto **não** faz

Não escreve em linha nenhuma. As contas que já existem ficam com `escuro`, que
é a identidade aprovada e o que elas já viam — a coluna nasce a concordar com o
ecrã, logo ninguém vê o tema mudar por causa desta migração.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_painel_no_registo_de_rotas'),
    ]

    operations = [
        # Antes do `ACCESS EXCLUSIVE`, e no mesmo `atomic` — ver o topo.
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '2s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name='user',
            name='tema',
            # Uma linha por argumento, como na 0005 e pela mesma razão: o
            # `makemigrations` gera 250 caracteres numa linha e o `line-length`
            # do ruff recusa-a. Não se abre excepção de lint por formatação.
            field=models.CharField(
                choices=[
                    ("escuro", "Escuro"),
                    ("meio_termo", "Meio termo"),
                    ("claro", "Claro"),
                ],
                db_default="escuro",
                default="escuro",
                help_text=(
                    "A paleta que esta pessoa prefere. Preferência da pessoa, "
                    "não da empresa."
                ),
                max_length=16,
                verbose_name="tema",
            ),
        ),
    ]
