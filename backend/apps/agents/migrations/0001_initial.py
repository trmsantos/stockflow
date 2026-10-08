"""`agents_extraction`, e a sua política de RLS.

Gerada por `makemigrations agents` e completada à mão com o bloco de RLS, na forma
do `apps/accounts/migrations/0001_initial.py`. Uma migração aplicada não se edita
(CLAUDE.md), por isso o porquê fica aqui escrito.

## Política, sobre `tenant_id`

A tabela herda `TenantModel`, logo tem `tenant_id` e leva `ENABLE` + `FORCE` +
política na migração que a cria, com o predicado contra
`NULLIF(current_setting('app.tenant_id', true), '')::uuid`. O `NULLIF` não é
decoração: sem ele, `''::uuid` levanta a partir da segunda transação de cada
ligação persistente em vez de devolver zero linhas (ADR 0005). O `SEM_POLITICA` do
`tests/test_db_roles.py` **não mexe**.

## O `document_id` não tem FK, logo esta migração não depende do `purchasing`

É a decisão 5 da ADR 0021: a secção 7 do `ARCHITECTURE.md` nomeia o `agents` como
o candidato óbvio a sair para serviço próprio, e uma FK para a tabela do
`purchasing` quebrava essa promessa ao nível do esquema. A consequência visível
aqui é que a lista de `dependencies` tem o `accounts` (pelo `tenant`) e **não** o
`purchasing` — o que é também o que permite aplicar as duas migrações em qualquer
ordem.

## E não é append-only

`started_at`, `finished_at`, `cost_eur` e `status` são `UPDATE`s da mesma chamada
(ADR 0021, decisão 4). Nenhum `REVOKE` aqui: o `APPEND_ONLY` do
`tests/test_db_roles.py` continua vazio e a sua primeira entrada é o
`inventory_stockmovement`, na fatia 3.

## Locks e `reverse_sql`

A tabela nasce nesta transação, logo o `ALTER TABLE` toma o `ACCESS EXCLUSIVE` sem
fila de espera; o `SET LOCAL lock_timeout` está lá porque a regra é incondicional
(skill `django-safe-migration`). O `reverse_sql` é completo: `migrate agents zero`
e de volta.
"""

import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

# O nome da tabela vai literal e não interpolado a partir de `_meta.db_table`: uma
# migração é um registo histórico do esquema e não se move com o modelo, e SQL
# construído por f-string é a forma de que o CLAUDE.md não quer ver nem o hábito.
APLICAR_RLS_EXTRACTION = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE agents_extraction ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents_extraction FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON agents_extraction
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_EXTRACTION = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON agents_extraction;

ALTER TABLE agents_extraction NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agents_extraction DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria `agents_extraction` e põe-na sob RLS na mesma transação."""

    initial = True

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
    ]

    operations = [
        migrations.CreateModel(
            name="Extraction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("document_id", models.UUIDField(editable=False, verbose_name="documento")),
                (
                    "attempt",
                    models.PositiveSmallIntegerField(editable=False, verbose_name="tentativa"),
                ),
                (
                    "model",
                    models.CharField(
                        blank=True,
                        default="",
                        editable=False,
                        max_length=100,
                        verbose_name="modelo chamado",
                    ),
                ),
                (
                    "prompt_version",
                    models.CharField(
                        blank=True,
                        default="",
                        editable=False,
                        max_length=50,
                        verbose_name="versão do prompt",
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        editable=False, max_length=200, verbose_name="chave de idempotência"
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="começou em",
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        verbose_name="acabou em",
                    ),
                ),
                (
                    "input_tokens",
                    models.PositiveIntegerField(
                        default=0, editable=False, verbose_name="tokens de entrada"
                    ),
                ),
                (
                    "output_tokens",
                    models.PositiveIntegerField(
                        default=0, editable=False, verbose_name="tokens de saída"
                    ),
                ),
                (
                    "cost_eur",
                    models.DecimalField(
                        decimal_places=6,
                        default=0,
                        editable=False,
                        max_digits=12,
                        verbose_name="custo em euros",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "a chamada começou e não acabou"),
                            ("lido", "o modelo respondeu e a resposta valida"),
                            ("ilegivel", "o modelo respondeu e a resposta não valida"),
                            ("erro", "a chamada falhou"),
                        ],
                        default="pendente",
                        editable=False,
                        max_length=20,
                        verbose_name="estado",
                    ),
                ),
                (
                    "confidence",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        default=None,
                        editable=False,
                        max_digits=4,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(1),
                        ],
                        verbose_name="confiança",
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        default=dict, editable=False, verbose_name="resposta do modelo, verbatim"
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True,
                        default="",
                        editable=False,
                        verbose_name="razão legível de um erro",
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
                "verbose_name": "extração",
                "verbose_name_plural": "extrações",
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"], name="agents_extr_tenant__075015_idx"
                    ),
                    models.Index(
                        fields=["tenant", "document_id", "-attempt"],
                        name="extraction_doc_attempt_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "document_id", "attempt"),
                        name="extraction_documento_tentativa_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("idempotency_key",), name="extraction_idempotency_key_uniq"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("confidence__isnull", True),
                            models.Q(("confidence__gte", 0), ("confidence__lte", 1)),
                            _connector="OR",
                        ),
                        name="extraction_confidence_entre_0_e_1",
                    ),
                ],
            },
        ),
        migrations.RunSQL(sql=APLICAR_RLS_EXTRACTION, reverse_sql=REVERTER_RLS_EXTRACTION),
    ]
