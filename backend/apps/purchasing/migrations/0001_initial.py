"""As três tabelas do documento de fornecedor, e as três políticas de RLS.

Gerada por `makemigrations purchasing` e completada à mão com os blocos de RLS,
na forma do `apps/accounts/migrations/0001_initial.py`. Uma migração aplicada não
se edita (CLAUDE.md), por isso o porquê de cada linha fica aqui escrito.

## Quem tem política, e sobre que coluna

| Tabela | `ENABLE` + `FORCE` | Predicado |
|---|---|---|
| `purchasing_invoicedocument` | sim | `tenant_id = app.tenant_id` |
| `purchasing_documentfile` | sim | `tenant_id = app.tenant_id` |
| `purchasing_documentpage` | sim | `tenant_id = app.tenant_id` |

As três herdam `TenantModel`, logo as três têm `tenant_id` e as três levam
política na migração que as cria — é a regra do `CLAUDE.md` que não se discute, e
a ADR 0021 (decisão 7) repete-a para estas tabelas em particular. O `SEM_POLITICA`
do `tests/test_db_roles.py` **não mexe**: nenhuma destas tabelas é lida fora de
âmbito.

## `FORCE`, e o `NULLIF`

`ENABLE ROW LEVEL SECURITY` não se aplica ao **dono** da tabela, e o dono destas é
o `stockflow_owner`, o role que corre as migrações: sem `FORCE`, uma migração de
dados sobre elas corria sem política nenhuma (ADR 0006). A aplicação liga-se como
`stockflow_app` — `NOSUPERUSER NOBYPASSRLS`, dona de nada — e a RLS alcança-a de
facto.

O `NULLIF` não é decoração. `app.tenant_id` é um *placeholder* e o valor a que o
fim da transação o devolve é a **string vazia**, não NULL. Sem ele, `''::uuid`
levanta `invalid input syntax for type uuid: ""` a partir da segunda transação de
cada ligação persistente, e o pedido *sem* tenant (login, healthcheck, anónimo,
404 antes da view) responde 500 em vez de ver zero linhas. Fixado em
`tests/test_tenant_scope.py` e afirmado, predicado a predicado, em
`tests/test_db_roles.py`.

## Sem `WITH CHECK` separado

Sem ele o Postgres usa a expressão do `USING` também para decidir que linhas podem
ser inseridas ou actualizadas. Uma expressão só, logo não podem divergir: dentro
de `tenant_scope(A)` só se consegue escrever uma linha com `tenant_id = A`.

E sem disjuntos. O `app.scope = 'system'` do `shared_outboxevent` existe porque o
consumidor da outbox tem de reclamar linhas de qualquer tenant; nada aqui precisa
disso, e alargar o disjunto a mais uma tabela era tirar-lhe o sentido (ADR 0005).

## Nenhuma destas tabelas é append-only

O `APPEND_ONLY` do `tests/test_db_roles.py` continua vazio. `closed_at`,
`discarded_at` e os campos de normalização de uma página são `UPDATE`s legítimos
da mesma linha; a primeira tabela append-only da história deste projecto é o
`inventory_stockmovement`, na fatia 3, e o `CLAUDE.md` exige o `domain-expert`
antes dela.

## Locks

As três tabelas nascem nesta transação: nenhuma outra sessão as consegue ver
ainda, pelo que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de
espera. O `SET LOCAL lock_timeout` está lá porque a regra é incondicional (skill
`django-safe-migration`): se um dia este bloco for reordenado, ou copiado para uma
tabela que já existe, falha depressa em vez de fazer fila e esgotar o pool de
ligações.

## `reverse_sql`

Completo nos três, como no `accounts`: `migrate purchasing zero` e de volta, com o
`tests/test_db_roles.py` a afirmar as políticas nos dois sentidos depois disso.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Os nomes das tabelas vão literais e não interpolados a partir de
# `_meta.db_table`: uma migração é um registo histórico do esquema e não se move
# com o modelo, e SQL construído por f-string é a forma de que o CLAUDE.md não
# quer ver nem o hábito.
APLICAR_RLS_INVOICEDOCUMENT = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE purchasing_invoicedocument ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchasing_invoicedocument FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON purchasing_invoicedocument
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_INVOICEDOCUMENT = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON purchasing_invoicedocument;

ALTER TABLE purchasing_invoicedocument NO FORCE ROW LEVEL SECURITY;
ALTER TABLE purchasing_invoicedocument DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_DOCUMENTFILE = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE purchasing_documentfile ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchasing_documentfile FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON purchasing_documentfile
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_DOCUMENTFILE = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON purchasing_documentfile;

ALTER TABLE purchasing_documentfile NO FORCE ROW LEVEL SECURITY;
ALTER TABLE purchasing_documentfile DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_DOCUMENTPAGE = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE purchasing_documentpage ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchasing_documentpage FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON purchasing_documentpage
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_DOCUMENTPAGE = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON purchasing_documentpage;

ALTER TABLE purchasing_documentpage NO FORCE ROW LEVEL SECURITY;
ALTER TABLE purchasing_documentpage DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria as três tabelas do documento e põe as três sob RLS na mesma transação."""

    initial = True

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentFile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "position",
                    models.PositiveSmallIntegerField(editable=False, verbose_name="ordem"),
                ),
                (
                    "path",
                    models.CharField(
                        editable=False, max_length=255, verbose_name="caminho no armazenamento"
                    ),
                ),
                (
                    "original_filename",
                    models.CharField(
                        blank=True,
                        default="",
                        editable=False,
                        max_length=255,
                        verbose_name="nome que o cliente deu",
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        editable=False, max_length=100, verbose_name="tipo real dos bytes"
                    ),
                ),
                (
                    "byte_size",
                    models.PositiveIntegerField(editable=False, verbose_name="tamanho em bytes"),
                ),
                (
                    "sha256",
                    models.CharField(
                        editable=False, max_length=64, verbose_name="SHA-256 dos bytes"
                    ),
                ),
                (
                    "pages_detected",
                    models.PositiveSmallIntegerField(
                        editable=False, verbose_name="páginas detetadas"
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
                "verbose_name": "ficheiro de documento",
                "verbose_name_plural": "ficheiros de documento",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="InvoiceDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("upload", "ficheiro enviado"),
                            ("capture", "fotografado no telemóvel"),
                        ],
                        editable=False,
                        max_length=20,
                        verbose_name="origem",
                    ),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="fechado em",
                    ),
                ),
                (
                    "discarded_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="descartado em",
                    ),
                ),
                (
                    "created_by_name",
                    models.CharField(
                        blank=True,
                        default="",
                        editable=False,
                        max_length=150,
                        verbose_name="nome de quem enviou",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="enviado por",
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
                "verbose_name": "documento de fornecedor",
                "verbose_name_plural": "documentos de fornecedor",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DocumentPage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "file_page_number",
                    models.PositiveSmallIntegerField(
                        editable=False, verbose_name="página dentro do ficheiro"
                    ),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        editable=False, verbose_name="ordem no documento"
                    ),
                ),
                (
                    "image_path",
                    models.CharField(
                        blank=True,
                        default="",
                        editable=False,
                        max_length=255,
                        verbose_name="caminho da imagem normalizada",
                    ),
                ),
                (
                    "width",
                    models.PositiveIntegerField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="largura em píxeis",
                    ),
                ),
                (
                    "height",
                    models.PositiveIntegerField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="altura em píxeis",
                    ),
                ),
                (
                    "normalized_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="normalizada em",
                    ),
                ),
                (
                    "qr_payload",
                    models.TextField(
                        blank=True,
                        default="",
                        editable=False,
                        verbose_name="conteúdo do QR da fatura",
                    ),
                ),
                (
                    "file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pages",
                        to="purchasing.documentfile",
                        verbose_name="ficheiro de origem",
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
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pages",
                        to="purchasing.invoicedocument",
                        verbose_name="documento",
                    ),
                ),
            ],
            options={
                "verbose_name": "página de documento",
                "verbose_name_plural": "páginas de documento",
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="documentfile",
            name="document",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="files",
                to="purchasing.invoicedocument",
                verbose_name="documento",
            ),
        ),
        migrations.AddIndex(
            model_name="invoicedocument",
            index=models.Index(
                fields=["tenant", "-created_at"], name="purchasing__tenant__98847c_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="documentpage",
            index=models.Index(
                fields=["tenant", "-created_at"], name="purchasing__tenant__69c0e4_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentpage",
            constraint=models.UniqueConstraint(
                fields=("document", "position"), name="documentpage_document_position_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentpage",
            constraint=models.UniqueConstraint(
                fields=("file", "file_page_number"), name="documentpage_file_page_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="documentfile",
            index=models.Index(
                fields=["tenant", "-created_at"], name="purchasing__tenant__fb85c1_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentfile",
            constraint=models.UniqueConstraint(
                fields=("document", "sha256"), name="documentfile_document_sha256_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentfile",
            constraint=models.UniqueConstraint(
                fields=("document", "position"), name="documentfile_document_position_uniq"
            ),
        ),
        migrations.RunSQL(
            sql=APLICAR_RLS_INVOICEDOCUMENT, reverse_sql=REVERTER_RLS_INVOICEDOCUMENT
        ),
        migrations.RunSQL(sql=APLICAR_RLS_DOCUMENTFILE, reverse_sql=REVERTER_RLS_DOCUMENTFILE),
        migrations.RunSQL(sql=APLICAR_RLS_DOCUMENTPAGE, reverse_sql=REVERTER_RLS_DOCUMENTPAGE),
    ]
