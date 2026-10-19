"""`agents_conversation` e `agents_chatmessage`, e as suas políticas de RLS (ADR 0027).

Gerada por `makemigrations agents` e completada à mão com os dois blocos de RLS,
na forma da `0001_initial` deste módulo e da `accounts/0004_tenantmenuitem`. Uma
migração aplicada não se edita (CLAUDE.md), por isso o porquê fica aqui escrito.

## Duas políticas, sobre `tenant_id`

As duas tabelas herdam `TenantModel`, logo têm `tenant_id` e levam `ENABLE` +
`FORCE` + política na migração que as cria, com o predicado contra
`NULLIF(current_setting('app.tenant_id', true), '')::uuid`. O `NULLIF` não é
decoração: sem ele, `''::uuid` levanta a partir da segunda transação de cada
ligação persistente em vez de devolver zero linhas (ADR 0005). O `FORCE` sujeita o
`stockflow_owner`, que é quem corre esta migração (ADR 0006). Sem `WITH CHECK`
separado, a expressão do `USING` vale também nas escritas: dentro de
`tenant_scope(A)` a tarefa só consegue escrever turnos de A.

O que a política **não** faz: separar as conversas de duas pessoas do mesmo
estabelecimento. Isso é dos selectors (`created_by`) e da permissão da view, ao
lado da política — os dois controlos do `SECURITY.md` §1. As duas igualdades de
conjuntos do `tests/test_db_roles.py` continuam verdadeiras sem nenhuma entrada
nova nas listas fechadas: `SEM_POLITICA` não mexe.

## E não são append-only

`started_at`, `answer`, `tool_calls` e `cost_eur` são `UPDATE`s do mesmo turno
(o argumento da ADR 0021, decisão 4), e o `DELETE` da conversa é real: a purga aos
90 dias apaga-a e o `CASCADE` leva as mensagens. Nenhum `REVOKE` aqui; o
`APPEND_ONLY` do `tests/test_db_roles.py` não mexe.

## Dependências só do `accounts`

As FKs são o `tenant` e o `User` (`created_by`, `asked_by`, com `SET_NULL`).
Nenhuma FK para o `catalog`, o `inventory` ou o `purchasing`: o rasto das tools
guarda ids em JSON e nomes em texto, pela razão do `document_id` da `0001` — a
secção 7 do `ARCHITECTURE.md` promete que o `agents` sai do monólito de forma
mecânica.

## Locks e `reverse_sql`

As tabelas nascem nesta transação, logo os `ALTER TABLE` tomam o `ACCESS
EXCLUSIVE` sem fila de espera; o `SET LOCAL lock_timeout` está lá porque a regra é
incondicional (skill `django-safe-migration`). O `reverse_sql` é completo:
`migrate agents 0001` e de volta.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Os nomes das tabelas vão literais e não interpolados a partir de `_meta.db_table`:
# uma migração é um registo histórico do esquema e não se move com o modelo, e SQL
# construído por f-string é a forma de que o CLAUDE.md não quer ver nem o hábito.
APLICAR_RLS_CHAT = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE agents_conversation ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents_conversation FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON agents_conversation
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE agents_chatmessage ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents_chatmessage FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON agents_chatmessage
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_CHAT = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON agents_chatmessage;

ALTER TABLE agents_chatmessage NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agents_chatmessage DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON agents_conversation;

ALTER TABLE agents_conversation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agents_conversation DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria as duas tabelas do chat e põe-nas sob RLS na mesma transação."""

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
        ("agents", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Conversation",
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
                    "created_by_name",
                    models.CharField(
                        blank=True, default="", max_length=150, verbose_name="criada por (nome)"
                    ),
                ),
                ("title", models.CharField(max_length=120, verbose_name="título")),
                ("last_message_at", models.DateTimeField(verbose_name="última mensagem em")),
                (
                    "created_by",
                    models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criada por",
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
                "verbose_name": "conversa",
                "verbose_name_plural": "conversas",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
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
                    models.PositiveSmallIntegerField(editable=False, verbose_name="posição"),
                ),
                (
                    "asked_by_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=150,
                        verbose_name="perguntado por (nome)",
                    ),
                ),
                (
                    "role_at_time",
                    models.CharField(max_length=20, verbose_name="papel no momento"),
                ),
                ("question", models.CharField(max_length=2000, verbose_name="pergunta")),
                ("language", models.CharField(max_length=10, verbose_name="língua da pergunta")),
                ("answer", models.TextField(blank=True, default="", verbose_name="resposta")),
                (
                    "tool_calls",
                    models.JSONField(
                        default=list, editable=False, verbose_name="tools chamadas, verbatim"
                    ),
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "à espera de um worker"),
                            ("a_responder", "o modelo está a responder"),
                            ("respondida", "respondida"),
                            ("erro", "a resposta falhou"),
                        ],
                        default="pendente",
                        editable=False,
                        max_length=20,
                        verbose_name="estado",
                    ),
                ),
                (
                    "error_code",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("teto_de_iteracoes", "o modelo chamou tools demasiadas vezes"),
                            (
                                "teto_de_custo",
                                "o orçamento diário do estabelecimento esgotou-se",
                            ),
                            ("tempo_esgotado", "o modelo não respondeu a tempo"),
                            ("resposta_invalida", "a resposta do modelo não se lê"),
                            ("erro_do_modelo", "o fornecedor do modelo recusou a chamada"),
                            (
                                "pertenca_revogada",
                                "quem perguntou já não pertence ao estabelecimento",
                            ),
                        ],
                        default="",
                        editable=False,
                        max_length=40,
                        verbose_name="código do erro",
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True, default="", editable=False, verbose_name="razão do erro"
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
                    "iterations",
                    models.PositiveSmallIntegerField(
                        default=0, editable=False, verbose_name="chamadas ao modelo"
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
                    "asked_by",
                    models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="perguntado por",
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
                    "conversation",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="agents.conversation",
                        verbose_name="conversa",
                    ),
                ),
            ],
            options={
                "verbose_name": "mensagem do assistente",
                "verbose_name_plural": "mensagens do assistente",
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["tenant", "-created_at"], name="agents_conv_tenant__e981c7_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["tenant", "created_by", "-last_message_at"],
                name="conversation_autor_recente_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="chatmessage",
            index=models.Index(
                fields=["tenant", "-created_at"], name="agents_chat_tenant__340d30_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="chatmessage",
            index=models.Index(
                fields=["tenant", "asked_by", "-created_at"], name="chatmessage_autor_dia_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="chatmessage",
            constraint=models.UniqueConstraint(
                fields=("tenant", "conversation", "position"),
                name="chatmessage_conversa_posicao_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="chatmessage",
            constraint=models.UniqueConstraint(
                fields=("idempotency_key",), name="chatmessage_idempotency_key_uniq"
            ),
        ),
        migrations.RunSQL(sql=APLICAR_RLS_CHAT, reverse_sql=REVERTER_RLS_CHAT),
    ]
