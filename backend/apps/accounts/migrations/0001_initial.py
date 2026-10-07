"""As três tabelas de identidade, e duas políticas de RLS — não três.

Gerada por `makemigrations accounts` e completada à mão com os blocos de RLS.
Uma migração aplicada não se edita (CLAUDE.md), por isso o porquê de cada linha
fica aqui escrito.

## Quem tem política, e sobre que coluna

| Tabela                | `ENABLE` + `FORCE` | Predicado                              |
|-----------------------|--------------------|----------------------------------------|
| `accounts_tenant`     | sim                | `id = app.tenant_id`                   |
| `accounts_membership` | sim                | `tenant_id = app.tenant_id`            |
| `accounts_user`       | **não**            | — (lista fechada do gate)              |

A regra do CLAUDE.md passou de "coluna" para "papel" (ADR 0007): *toda a tabela
de dados de um tenant tem política na migração que a cria, e o predicado compara
a coluna que identifica o tenant contra
`NULLIF(current_setting('app.tenant_id', true), '')::uuid`; essa coluna é
`tenant_id` em toda a parte exceto no `accounts_tenant`, onde é `id`, porque a
tabela **é** o tenant.*

Sem a política do `accounts_tenant`, qualquer ligação autenticada leria a lista
completa de clientes com os seus nomes — a ameaça "acesso a dados de outro
tenant" do SECURITY.md §1 na sua forma mais literal. O predicado ser sobre `id`
tem uma consequência que não é óbvia e é a que torna o registo possível: como
não há `WITH CHECK` separado, o Postgres usa o `USING` também nas escritas, logo
criar um tenant é gerar o UUID em Python, abrir `tenant_scope(esse uuid)` e
inserir — `id = app.tenant_id` é verdade. É o que o
`apps/accounts/services.py::criar_tenant` faz, e está provado em
`tests/test_rls_isolation.py`.

## Porque é que o `accounts_user` não tem política

Não é por não ter `tenant_id`. É que qualquer política que lhe puséssemos
precisava de uma porta para a única query que corre antes de haver identidade
nenhuma — o `WHERE email = %s` do login — e uma política com uma porta para o
login não é uma política. Um utilizador pertence a vários tenants (a
contabilista, o consultor, o dono que também é gerente noutra sociedade), pelo
que a tabela é global por desenho. A resposta é **encolher a tabela**, não
fingir que está protegida: o que fica legível sem âmbito é um email e um hash,
não um perfil. Entra na lista fechada de `tests/test_db_roles.py`, comentada
entrada por entrada, e o risco residual está nomeado no SECURITY.md §3.

As duas tabelas de junção do `PermissionsMixin` (`accounts_user_groups` e
`accounts_user_user_permissions`) seguem o `accounts_user`: são permissões do
admin do Django, não têm `tenant_id`, e estão na mesma lista fechada.

## `FORCE`, e o `NULLIF`

`ENABLE ROW LEVEL SECURITY` não se aplica ao **dono** da tabela, e o dono desta
é o `stockflow_owner`, o role que corre as migrações: sem `FORCE`, uma migração
de dados sobre estas tabelas corria sem política nenhuma (ADR 0006). A
aplicação liga-se como `stockflow_app` — `NOSUPERUSER NOBYPASSRLS`, dona de
nada — e a RLS alcança-a de facto.

O `NULLIF` não é decoração. `app.tenant_id` é um *placeholder* e o valor a que o
fim da transação o devolve é a **string vazia**, não NULL — medido no PostgreSQL
16.15, na mesma ligação. Sem ele, `''::uuid` levanta
`invalid input syntax for type uuid: ""` a partir da segunda transação de cada
ligação persistente, e o pedido *sem* tenant (login, healthcheck, anónimo, 404
antes da view) responde 500 em vez de ver zero linhas. Fixado em
`tests/test_tenant_scope.py`.

## Sem `WITH CHECK` separado

Pela mesma razão do `shared_outboxevent`: sem ele o Postgres usa a expressão do
`USING` também para decidir que linhas podem ser inseridas ou atualizadas. Uma
expressão só, logo não podem divergir. O efeito é o que se quer — dentro de
`tenant_scope(A)` só se consegue escrever uma linha com `tenant_id = A` (ou, no
`accounts_tenant`, com `id = A`).

E sem disjuntos. O `app.scope = 'system'` do `shared_outboxevent` existe porque o
consumidor da outbox tem de reclamar linhas de qualquer tenant; nada no
`accounts_membership` precisa disso, e alargar o disjunto a mais uma tabela era
tirar-lhe o sentido (ADR 0005).

## Locks

As três tabelas nascem nesta transação: nenhuma outra sessão as consegue ver
ainda, pelo que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de
espera. O `SET LOCAL lock_timeout` está lá porque a regra é incondicional
(skill `django-safe-migration`): se um dia este bloco for reordenado, ou
copiado para uma tabela que já existe, falha depressa em vez de fazer fila e
esgotar o pool de ligações.

## `reverse_sql`

Completo, e provado: `migrate accounts zero` e de volta, com o
`tests/test_db_roles.py` a afirmar as políticas nos dois sentidos depois disso.
"""

import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Os nomes das tabelas vão literais e não interpolados a partir de
# `_meta.db_table`: uma migração é um registo histórico do esquema e não se move
# com o modelo, e SQL construído por f-string é a forma de que o CLAUDE.md não
# quer ver nem o hábito.
APLICAR_RLS_TENANT = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE accounts_tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_tenant FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON accounts_tenant
    USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_TENANT = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON accounts_tenant;

ALTER TABLE accounts_tenant NO FORCE ROW LEVEL SECURITY;
ALTER TABLE accounts_tenant DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_MEMBERSHIP = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE accounts_membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_membership FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON accounts_membership
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_MEMBERSHIP = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON accounts_membership;

ALTER TABLE accounts_membership NO FORCE ROW LEVEL SECURITY;
ALTER TABLE accounts_membership DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria `accounts_tenant`, `accounts_user` e `accounts_membership`, e põe
    duas delas sob RLS na mesma transação."""

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tenant",
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
                ("name", models.CharField(max_length=200, verbose_name="nome")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
            ],
            options={
                "verbose_name": "tenant",
                "verbose_name_plural": "tenants",
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(blank=True, null=True, verbose_name="last login"),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates that this user has all permissions without "
                            "explicitly assigning them."
                        ),
                        verbose_name="superuser status",
                    ),
                ),
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
                    "email",
                    models.EmailField(max_length=254, unique=True, verbose_name="email"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Acesso ao admin. Nunca para clientes — ver o papel no "
                            "Membership."
                        ),
                        verbose_name="operador do StockFlow",
                    ),
                ),
                (
                    "tenant_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.UUIDField(),
                        blank=True,
                        default=list,
                        editable=False,
                        size=None,
                        verbose_name="âmbitos que pode tentar",
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
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "The groups this user belongs to. A user will get all "
                            "permissions granted to each of their groups."
                        ),
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "utilizador",
                "verbose_name_plural": "utilizadores",
            },
        ),
        migrations.CreateModel(
            name="Membership",
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
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "dono"),
                            ("manager", "gerente"),
                            ("staff", "colaborador"),
                        ],
                        max_length=20,
                        verbose_name="papel",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativa")),
                (
                    "display_name",
                    models.CharField(max_length=150, verbose_name="nome exibido"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="utilizador",
                    ),
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
                "verbose_name": "pertença",
                "verbose_name_plural": "pertenças",
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"],
                        name="accounts_me_tenant__6201db_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "tenant"),
                        name="membership_user_tenant_uniq",
                    ),
                ],
            },
        ),
        migrations.RunSQL(sql=APLICAR_RLS_TENANT, reverse_sql=REVERTER_RLS_TENANT),
        migrations.RunSQL(sql=APLICAR_RLS_MEMBERSHIP, reverse_sql=REVERTER_RLS_MEMBERSHIP),
    ]
