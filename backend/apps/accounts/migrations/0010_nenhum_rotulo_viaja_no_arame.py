"""O `grupo` aceita vazio, e as duas rotas de definições saem da lista fechada.

Duas alterações de `choices`/`blank`, as duas **no-op na base de dados** —
verificado com `sqlmigrate` antes de ser escrita:

    BEGIN;
    -- Alter field grupo on tenantmenuitem
    -- (no-op)
    -- Alter field route_id on tenantmenuitem
    -- (no-op)
    COMMIT;

O `blank` é validação em Python e o `choices` também; a coluna continua
`varchar(50) NOT NULL` e `varchar(32) NOT NULL`. Zero `ACCESS EXCLUSIVE`, zero
varrimento, zero `lock_timeout`.

## O que mudou no significado, que é a parte que importa

**`grupo` em branco passa a querer dizer "usa o default"**, a mesma assimetria
que o `rotulo` já tinha. Antes disto o `grupo` viajava **resolvido** no contrato
e era obrigatório no `PUT` — e como o `PUT /menu` é substituição total, a
primeira gravação congelava "Inventário" e "Equipa" na linha do tenant. Medido na
base de dados a correr: depois de gravar o menu com os defaults, a linha ficava
com `grupo='Inventário'` e `rotulo=''`. Nenhuma tradução alcançava o primeiro.

O nome por omissão de um grupo é **copy do produto**, e copy traduz-se no
catálogo do cliente (ADR 0019, decisão 5). O que esta coluna guarda é o nome que
**esta empresa** escolheu, que é texto dela e numa língua só.

**E o `convites` e o `configuracao` saem do `choices`** (ADR 0019, decisão 7):
definições não são uma pergunta de operação, e o menu é a projecção de que ecrãs
de operação uma empresa mostra às suas pessoas. Os dois ecrãs passaram a secções
do `/definicoes`, alcançado pelo pé da sidebar.

## Nenhuma migração de dados, e por três razões que se somam

1. **Uma linha órfã já é tratada por desenho.** O `rota_do_registo` devolve
   `None` para um `route_id` que o registo não conhece e a `projeccao_de_menu`
   ignora a linha — é o caminho do rolling deploy, onde um backend novo serve um
   bundle antigo. A linha cura-se sozinha no `PUT` seguinte, que é substituição
   total construída a partir de um `GET /menu/rotas` que já não lista o id.
2. **Nenhum tenant configurou estes dois ids.** O `configuracao` entrou ontem
   (migração 0007) e o `convites` só existe numa linha se alguém tiver gravado o
   menu.
3. **Uma migração de dados sobre esta tabela apagaria zero linhas em silêncio**,
   e isto foi medido e não presumido: o `accounts_tenantmenuitem` tem
   `FORCE ROW LEVEL SECURITY`, que sujeita o `stockflow_owner` (`SECURITY.md`
   §3), e uma migração corre sem `app.tenant_id`. Medido: o mesmo `SELECT` como
   owner dá 2 linhas dentro do âmbito e **0 linhas** sem âmbito. Fica escrito
   para ninguém escrever uma e achar que apagou.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_janela_do_dia_de_negocio"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantmenuitem",
            name="grupo",
            field=models.CharField(blank=True, max_length=50, verbose_name="grupo"),
        ),
        migrations.AlterField(
            model_name="tenantmenuitem",
            name="route_id",
            # Uma escolha por linha, pela razão da 0005: o `line-length = 100` do
            # ruff recusa a linha que o `makemigrations` gera, e uma excepção de
            # formatação gastava o mecanismo que o CLAUDE.md reserva para
            # decisões com ADR.
            field=models.CharField(
                choices=[
                    ("inicio", "Início"),
                    ("painel", "Painel de gestão"),
                    ("alertas", "Alertas"),
                    ("stock", "Stock"),
                    ("contar", "Contar"),
                    ("receber", "Receber"),
                ],
                max_length=32,
                verbose_name="rota",
            ),
        ),
    ]
