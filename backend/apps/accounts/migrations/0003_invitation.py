"""A tabela dos convites, **com** política de RLS — a decisão central da ADR 0010.

Gerada por `makemigrations accounts` e completada à mão com o bloco de RLS, como
a `0001_initial`. Uma migração aplicada não se edita (CLAUDE.md), por isso o
porquê de cada linha fica aqui escrito.

## Porque é que esta tabela tem política, contra o instinto

Um convite é lido **antes** de existir sessão, como o login. O reflexo é
concluir que a tabela tem de ficar sem política, na lista fechada que o
`tests/test_db_roles.py` verifica — e foi essa a forma que o pedido original
assumia. **Não é preciso, e a ADR 0010 recusa-a.** O token nomeia o tenant: o
link é `/ativar#<uuid-do-tenant>.<token>`, a view de activação — dispensada de
âmbito, como o login — abre `tenant_scope(uuid que vem do link)` e lê o convite
**lá dentro**. É a inversão da ADR 0007 na letra, com o link no lugar da sessão:
**o link escolhe o âmbito, a política concede-o.**

O uuid é argumento e não credencial. Forjá-lo escolhe um âmbito onde nenhum
`token_hash` existe, a leitura devolve zero linhas e a recusa é a genérica —
exatamente como um `tenant_id` forjado na sessão escolhe um âmbito onde a query
do `TenantMiddleware` não devolve nada.

A alternativa (convites sem política) punha email, papel e `tenant_id` de
**todos** os convites pendentes de **todos** os clientes legíveis por qualquer
ligação da app: a ameaça "acesso a dados de outro tenant" do `SECURITY.md` §1 na
forma literal, ao preço evitável de não pôr um uuid no link.

Consequência para os gates: `accounts_invitation` aparece na varredura do
`pg_class` do lado das tabelas **com** política, e **não** entra em
`SEM_POLITICA`. As duas igualdades de conjuntos do `tests/test_db_roles.py`
continuam verdadeiras sem nenhuma entrada nova na lista fechada.

## `FORCE`, o `NULLIF` e a ausência de `WITH CHECK`

As três razões são as da `0001_initial` e valem igual aqui:

* `ENABLE` não se aplica ao **dono** da tabela, e o dono é o `stockflow_owner`,
  o role que corre as migrações: sem `FORCE`, uma migração de dados sobre esta
  tabela corria sem política nenhuma (ADR 0006);
* o `NULLIF` não é decoração. `app.tenant_id` é um *placeholder* e o valor a que
  o fim da transação o devolve é a **string vazia**, não NULL — medido no
  PostgreSQL 16.15, na mesma ligação. Sem ele, `''::uuid` levanta
  `invalid input syntax for type uuid: ""` a partir da segunda transação de cada
  ligação persistente, e o pedido *sem* tenant responde 500 em vez de ver zero
  linhas. Fixado em `tests/test_tenant_scope.py`;
* sem `WITH CHECK` separado, o Postgres usa a expressão do `USING` também para
  decidir que linhas podem ser escritas. Uma expressão só, logo não podem
  divergir: dentro de `tenant_scope(A)` só se consegue criar um convite com
  `tenant_id = A`.

E sem disjuntos. O `app.scope = 'system'` do `shared_outboxevent` existe porque o
consumidor da outbox tem de reclamar linhas de qualquer tenant; nada aqui
precisa disso — a activação **sabe** de que tenant é o convite, porque o link
di-lo — e alargar o disjunto a mais uma tabela era tirar-lhe o sentido
(ADR 0005).

## O que não está aqui: `REVOKE UPDATE, DELETE`

Um convite **não** é append-only. `accepted_at` e `revoked_at` são `UPDATE`s, e
são eles que fazem o uso único e a revogação. O `APPEND_ONLY` do
`tests/test_db_roles.py` não muda, e acrescentar uma tabela a essa lista é uma
decisão de domínio que passa pelo `domain-expert` (ADR 0006).

## Índices, e o que cada um serve

| Índice | Serve |
|---|---|
| `accounts_in_tenant__a0e001_idx` | a listagem: `(tenant_id, -created_at)` |
| `invitation_token_hash_uniq` | a activação, por igualdade sobre o hash |
| `invitation_pendente_uniq` | a unicidade do convite pendente por (tenant, email) |

O `invitation_pendente_uniq` é parcial — `WHERE accepted_at IS NULL AND
revoked_at IS NULL` — e dobra a caixa do email (`LOWER(email)`), pela mesma
regra do `accounts_user`: `Ana@x.pt` e `ana@x.pt` são a mesma conta, logo são o
mesmo convite. `expires_at` não entra na condição porque `now()` não é imutável
e o Postgres recusa-o num índice; a consequência está escrita no
`services.criar_convite`.

## Locks

A tabela nasce nesta transação: nenhuma outra sessão a consegue ver ainda, pelo
que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de espera. O
`SET LOCAL lock_timeout` está lá porque a regra é incondicional (skill
`django-safe-migration`): se este bloco for um dia reordenado, ou copiado para
uma tabela que já existe, falha depressa em vez de fazer fila e esgotar o pool
de ligações.

## `reverse_sql`

Completo, e provado: `migrate accounts 0002` e de volta, com o
`tests/test_db_roles.py` a afirmar as políticas nos dois sentidos depois disso.
"""

import uuid

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models

# O nome da tabela vai literal e não interpolado a partir de `_meta.db_table`:
# uma migração é um registo histórico do esquema e não se move com o modelo, e
# SQL construído por f-string é a forma de que o CLAUDE.md não quer nem o hábito.
APLICAR_RLS_INVITATION = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE accounts_invitation ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_invitation FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON accounts_invitation
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_INVITATION = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON accounts_invitation;

ALTER TABLE accounts_invitation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE accounts_invitation DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria `accounts_invitation` e põe-na sob RLS na mesma transação."""

    dependencies = [
        ("accounts", "0002_user_email_lower_uniq"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invitation",
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
                    "email",
                    models.EmailField(max_length=254, verbose_name="email convidado"),
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
                (
                    "display_name",
                    models.CharField(max_length=150, verbose_name="nome exibido"),
                ),
                (
                    "token_hash",
                    models.CharField(
                        editable=False,
                        max_length=64,
                        verbose_name="SHA-256 do token",
                    ),
                ),
                ("expires_at", models.DateTimeField(verbose_name="expira em")),
                (
                    "accepted_at",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        null=True,
                        verbose_name="aceite em",
                    ),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        null=True,
                        verbose_name="revogado em",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="convidado por",
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
                "verbose_name": "convite",
                "verbose_name_plural": "convites",
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"],
                        name="accounts_in_tenant__a0e001_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        models.F("tenant"),
                        django.db.models.functions.text.Lower("email"),
                        condition=models.Q(
                            ("accepted_at__isnull", True),
                            ("revoked_at__isnull", True),
                        ),
                        name="invitation_pendente_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("token_hash",),
                        name="invitation_token_hash_uniq",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql=APLICAR_RLS_INVITATION,
            reverse_sql=REVERTER_RLS_INVITATION,
        ),
    ]
