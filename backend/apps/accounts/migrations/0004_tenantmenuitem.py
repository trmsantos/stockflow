"""A tabela do menu por tenant, **com** política de RLS (ADR 0009 e ADR 0011).

Gerada por `makemigrations accounts` e completada à mão com o bloco de RLS, como
a `0001_initial` e a `0003_invitation`. Uma migração aplicada não se edita
(CLAUDE.md), por isso o porquê de cada linha fica aqui escrito.

## A política não é uma pergunta, mas a decisão fica registada

`accounts_tenantmenuitem` tem `tenant_id`, logo leva política na migração que a
cria — é a regra do CLAUDE.md e não tem excepção. Vale a pena dizer o que ela
protege, porque "esconder um item de menu é apresentação" (ADR 0009) convida ao
raciocínio errado: o que a política protege não é o esconder, é a **linha de
configuração de um cliente**. Sem ela, qualquer ligação da app lia como é que
cada restaurante organizou o seu menu, que nomes deu aos grupos e que ecrãs
esconde — e a `ordem` de um menu diz que parte do produto cada cliente usa.

Consequência para os gates: a tabela aparece na varredura do `pg_class` do lado
das tabelas **com** política e **não** entra em `SEM_POLITICA`. As duas
igualdades de conjuntos do `tests/test_db_roles.py` continuam verdadeiras sem
nenhuma entrada nova na lista fechada — e há uma âncora explícita lá, do lado
certo, para a decisão não passar em silêncio.

## `FORCE`, o `NULLIF` e a ausência de `WITH CHECK`

As três razões são as da `0001_initial` e valem igual aqui:

* `ENABLE` não se aplica ao **dono** da tabela, e o dono é o `stockflow_owner`,
  o role que corre as migrações: sem `FORCE`, uma migração de dados sobre esta
  tabela corria sem política nenhuma (ADR 0006);
* o `NULLIF` não é decoração. `app.tenant_id` é um *placeholder* e o valor a que
  o fim da transação o devolve é a **string vazia**, não NULL — medido no
  PostgreSQL 16.15. Sem ele, `''::uuid` levanta
  `invalid input syntax for type uuid: ""` a partir da segunda transação de cada
  ligação persistente, e o pedido *sem* tenant — login, healthcheck, anónimo,
  404 antes da view — responde 500 em vez de ver zero linhas;
* sem `WITH CHECK` separado, o Postgres usa a expressão do `USING` também para
  decidir que linhas podem ser escritas. Uma expressão só, logo não podem
  divergir: dentro de `tenant_scope(A)` o `PUT` do menu só consegue escrever
  linhas com `tenant_id = A`, e é isso que torna a substituição total segura
  sem o service ter de repetir o filtro em todas as escritas (repete-o de
  qualquer forma — são os dois controlos que o `SECURITY.md` §1 exige).

E sem disjuntos. O `app.scope = 'system'` do `shared_outboxevent` existe porque o
consumidor da outbox tem de reclamar linhas de qualquer tenant; nada aqui precisa
disso — o menu resolve-se com o tenant que a sessão já resolveu — e alargar o
disjunto a mais uma tabela era tirar-lhe o sentido (ADR 0005).

## O que não está aqui: `REVOKE UPDATE, DELETE`

A configuração do menu é para mudar. O `PUT` de substituição total apaga as
linhas do tenant e reescreve-as numa transação, logo esta tabela precisa de
`DELETE` — e não é um ledger. O `APPEND_ONLY` do `tests/test_db_roles.py` não
muda, e acrescentar uma tabela a essa lista é uma decisão de domínio que passa
pelo `domain-expert` (ADR 0006).

## Nenhuma linha nasce aqui

Os defaults vivem em código (`apps/accounts/menu.py`) e a linha nasce na primeira
escrita (ADR 0011). Logo esta migração **não** tem `RunPython` nenhum: semear
uma linha por rota e por tenant existente era guardar um default — que é precisamente o
que o deixa de poder mudar — e obrigava a iterar tenants com âmbito aberto numa
migração de dados, pelo `FORCE`.

## Índices, e o que cada um serve

| Índice | Serve |
|---|---|
| `accounts_te_tenant__7e3f04_idx` | a forma da casa: `(tenant_id, -created_at)` |
| `tenantmenuitem_tenant_route_uniq` | a unicidade `(tenant, route_id)` **e** a leitura |

O índice composto do `TenantModel` não é o que a projecção usa — ela lê as linhas
todas de um tenant e ordena por `ordem` — e fica porque é a forma herdada e
porque a tabela tem, por tenant, no máximo tantas linhas quantas o registo de
rotas tem ids. O índice que serve de facto é o da constraint única.

## Locks

A tabela nasce nesta transação: nenhuma outra sessão a consegue ver ainda, pelo
que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de espera. O
`SET LOCAL lock_timeout` está lá porque a regra é incondicional (skill
`django-safe-migration`): se este bloco for um dia reordenado, ou copiado para
uma tabela que já existe, falha depressa em vez de fazer fila e esgotar o pool
de ligações.

## `reverse_sql`

Completo, e provado: `migrate accounts 0003` e de volta, com o
`tests/test_db_roles.py` a afirmar as políticas nos dois sentidos depois disso.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

# O nome da tabela vai literal e não interpolado a partir de `_meta.db_table`:
# uma migração é um registo histórico do esquema e não se move com o modelo, e
# SQL construído por f-string é a forma de que o CLAUDE.md não quer nem o hábito.
APLICAR_RLS_TENANTMENUITEM = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE accounts_tenantmenuitem ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_tenantmenuitem FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON accounts_tenantmenuitem
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_TENANTMENUITEM = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON accounts_tenantmenuitem;

ALTER TABLE accounts_tenantmenuitem NO FORCE ROW LEVEL SECURITY;
ALTER TABLE accounts_tenantmenuitem DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria `accounts_tenantmenuitem` e põe-na sob RLS na mesma transação."""

    dependencies = [
        ("accounts", "0003_invitation"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantMenuItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "route_id",
                    models.CharField(
                        choices=[
                            ("inicio", "Início"),
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
                ("grupo", models.CharField(max_length=50, verbose_name="grupo")),
                ("ordem", models.PositiveSmallIntegerField(verbose_name="ordem")),
                ("visivel", models.BooleanField(default=True, verbose_name="visível")),
                (
                    "rotulo",
                    models.CharField(blank=True, max_length=50, verbose_name="rótulo"),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.tenant",
                        verbose_name="tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "item de menu",
                "verbose_name_plural": "itens de menu",
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"],
                        name="accounts_te_tenant__7e3f04_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "route_id"),
                        name="tenantmenuitem_tenant_route_uniq",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql=APLICAR_RLS_TENANTMENUITEM,
            reverse_sql=REVERTER_RLS_TENANTMENUITEM,
        ),
    ]
