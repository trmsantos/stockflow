"""As quatro tabelas do catálogo, e as quatro políticas de RLS.

Gerada por `makemigrations catalog` e completada à mão com os blocos de RLS, na
forma do `apps/purchasing/migrations/0001_initial.py`. Uma migração aplicada não
se edita (CLAUDE.md), por isso o porquê de cada linha fica aqui escrito.

## Quem tem política, e sobre que coluna

| Tabela | `ENABLE` + `FORCE` | Predicado |
|---|---|---|
| `catalog_product` | sim | `tenant_id = app.tenant_id` |
| `catalog_productpackaging` | sim | `tenant_id = app.tenant_id` |
| `catalog_supplier` | sim | `tenant_id = app.tenant_id` |
| `catalog_supplierproductcode` | sim | `tenant_id = app.tenant_id` |

As quatro herdam `TenantModel`, logo as quatro têm `tenant_id` e as quatro levam
política na migração que as cria — é a regra do `CLAUDE.md` que não se discute,
e a ADR 0021 (decisão 7) repete-a para estas tabelas em particular. O
`SEM_POLITICA` do `tests/test_db_roles.py` **não mexe**: nenhuma destas tabelas é
lida fora de âmbito. Um catálogo **partilhado** entre tenants (EAN → descrição,
ADR 0005) seria outra tabela, sem `tenant_id`, e não existe nesta fatia.

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

## As unicidades são índices de expressão, e vêem o que a ligação não lê

`(tenant, Lower(short_name))`, `(tenant, product, Lower(label))`,
`(tenant, Lower(name))`: a unicidade é **sem caixa**, e é imposta pelo Postgres e
não por um `iexact` em Python — o serializer dá a frase, o índice é a rede. As
duas parciais (`ean <> ''`, `nif <> ''`) são o que permite N linhas em branco e
nenhuma repetida. Nenhuma destas unicidades atravessa tenants (todas levam o
`tenant_id`), ao contrário da chave primária, que é global por ser a chave
primária: é por isso que o `apps/demo` não pode reutilizar um uuid que um demo
revogado ainda tenha.

## Nenhuma destas tabelas é append-only

O `APPEND_ONLY` do `tests/test_db_roles.py` continua vazio. Um artigo edita-se
(`PATCH`), uma memória de código actualiza-se a cada confirmação, e o primeiro
append-only da história deste projecto é o `inventory_stockmovement`, na fatia 3.

## Locks

As quatro tabelas nascem nesta transação: nenhuma outra sessão as consegue ver
ainda, pelo que os `ALTER TABLE` a seguir tomam o `ACCESS EXCLUSIVE` sem fila de
espera. O `SET LOCAL lock_timeout` está lá porque a regra é incondicional (skill
`django-safe-migration`): se um dia este bloco for reordenado, ou copiado para uma
tabela que já existe, falha depressa em vez de fazer fila e esgotar o pool de
ligações.

## `reverse_sql`

Completo nos quatro, como no `purchasing`: `migrate catalog zero` e de volta, com
o `tests/test_db_roles.py` a afirmar as políticas nos dois sentidos depois disso.
"""

import uuid
from decimal import Decimal

import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models

# Os nomes das tabelas vão literais e não interpolados a partir de
# `_meta.db_table`: uma migração é um registo histórico do esquema e não se move
# com o modelo, e SQL construído por f-string é a forma de que o CLAUDE.md não
# quer ver nem o hábito.
APLICAR_RLS_PRODUCT = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE catalog_product ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_product FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON catalog_product
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_PRODUCT = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON catalog_product;

ALTER TABLE catalog_product NO FORCE ROW LEVEL SECURITY;
ALTER TABLE catalog_product DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_PRODUCTPACKAGING = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE catalog_productpackaging ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_productpackaging FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON catalog_productpackaging
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_PRODUCTPACKAGING = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON catalog_productpackaging;

ALTER TABLE catalog_productpackaging NO FORCE ROW LEVEL SECURITY;
ALTER TABLE catalog_productpackaging DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_SUPPLIER = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE catalog_supplier ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_supplier FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON catalog_supplier
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_SUPPLIER = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON catalog_supplier;

ALTER TABLE catalog_supplier NO FORCE ROW LEVEL SECURITY;
ALTER TABLE catalog_supplier DISABLE ROW LEVEL SECURITY;
"""

APLICAR_RLS_SUPPLIERPRODUCTCODE = """
SET LOCAL lock_timeout = '2s';

ALTER TABLE catalog_supplierproductcode ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_supplierproductcode FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON catalog_supplierproductcode
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

REVERTER_RLS_SUPPLIERPRODUCTCODE = """
SET LOCAL lock_timeout = '2s';

DROP POLICY IF EXISTS tenant_isolation ON catalog_supplierproductcode;

ALTER TABLE catalog_supplierproductcode NO FORCE ROW LEVEL SECURITY;
ALTER TABLE catalog_supplierproductcode DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """Cria as quatro tabelas do catálogo e põe as quatro sob RLS na mesma transação."""

    initial = True

    dependencies = [
        ("accounts", "0010_nenhum_rotulo_viaja_no_arame"),
    ]

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("short_name", models.CharField(max_length=80, verbose_name="nome curto")),
                (
                    "base_unit",
                    models.CharField(
                        choices=[("g", "grama"), ("ml", "mililitro"), ("un", "unidade")],
                        max_length=2,
                        verbose_name="unidade base",
                    ),
                ),
                (
                    "display_unit",
                    models.CharField(max_length=20, verbose_name="unidade de apresentação"),
                ),
                (
                    "display_factor",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=12,
                        verbose_name="unidades base por unidade de apresentação",
                    ),
                ),
                (
                    "min_quantity",
                    models.DecimalField(
                        decimal_places=3,
                        default=Decimal("0"),
                        max_digits=12,
                        verbose_name="mínimo, na unidade base",
                    ),
                ),
                ("track_lots", models.BooleanField(default=False, verbose_name="exige lote")),
                (
                    "expiry_kind",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("use_by", "consumir até"),
                            ("best_before", "consumir de preferência antes de"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="rótulo da validade",
                    ),
                ),
                (
                    "conservation",
                    models.CharField(
                        choices=[
                            ("ambient", "ambiente"),
                            ("chilled", "refrigerado"),
                            ("frozen", "congelado"),
                        ],
                        default="ambient",
                        max_length=10,
                        verbose_name="conservação",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
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
                "verbose_name": "artigo",
                "verbose_name_plural": "artigos",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ProductPackaging",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("label", models.CharField(max_length=60, verbose_name="rótulo")),
                (
                    "base_quantity",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=12,
                        verbose_name="unidades base por embalagem",
                    ),
                ),
                (
                    "ean",
                    models.CharField(
                        blank=True, default="", max_length=14, verbose_name="EAN/GTIN"
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="packagings",
                        to="catalog.product",
                        verbose_name="artigo",
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
                "verbose_name": "embalagem",
                "verbose_name_plural": "embalagens",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Supplier",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("name", models.CharField(max_length=200, verbose_name="nome")),
                (
                    "nif",
                    models.CharField(blank=True, default="", max_length=9, verbose_name="NIF"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
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
                "verbose_name": "fornecedor",
                "verbose_name_plural": "fornecedores",
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="SupplierProductCode",
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
                    "code",
                    models.CharField(max_length=50, verbose_name="código do fornecedor"),
                ),
                (
                    "description_raw",
                    models.CharField(
                        blank=True, default="", max_length=500, verbose_name="descrição impressa"
                    ),
                ),
                (
                    "invoice_unit",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=20,
                        verbose_name="unidade da fatura, normalizada",
                    ),
                ),
                ("learned_at", models.DateTimeField(verbose_name="aprendido em")),
                (
                    "packaging",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="+",
                        to="catalog.productpackaging",
                        verbose_name="embalagem",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="+",
                        to="catalog.product",
                        verbose_name="artigo",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_codes",
                        to="catalog.supplier",
                        verbose_name="fornecedor",
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
                "verbose_name": "código de fornecedor",
                "verbose_name_plural": "códigos de fornecedor",
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["tenant", "-created_at"], name="catalog_pro_tenant__94c803_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("short_name"),
                models.F("tenant"),
                name="catalog_product_short_name_lower_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("display_factor__gt", 0)),
                name="catalog_product_display_factor_positivo",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("min_quantity__gte", 0)),
                name="catalog_product_min_quantity_nao_negativa",
            ),
        ),
        migrations.AddIndex(
            model_name="productpackaging",
            index=models.Index(
                fields=["tenant", "-created_at"], name="catalog_pro_tenant__bef70d_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="productpackaging",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("label"),
                models.F("tenant"),
                models.F("product"),
                name="catalog_packaging_label_lower_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="productpackaging",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ean__gt", "")),
                fields=("tenant", "ean"),
                name="catalog_packaging_ean_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="productpackaging",
            constraint=models.CheckConstraint(
                condition=models.Q(("base_quantity__gt", 0)),
                name="catalog_packaging_base_quantity_positiva",
            ),
        ),
        migrations.AddIndex(
            model_name="supplier",
            index=models.Index(
                fields=["tenant", "-created_at"], name="catalog_sup_tenant__5f8a5e_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("tenant"),
                name="catalog_supplier_name_lower_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("nif__gt", "")),
                fields=("tenant", "nif"),
                name="catalog_supplier_nif_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="supplierproductcode",
            index=models.Index(
                fields=["tenant", "-created_at"], name="catalog_sup_tenant__620356_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="supplierproductcode",
            constraint=models.UniqueConstraint(
                fields=("tenant", "supplier", "code"),
                name="catalog_supplierproductcode_supplier_code_uniq",
            ),
        ),
        migrations.RunSQL(sql=APLICAR_RLS_PRODUCT, reverse_sql=REVERTER_RLS_PRODUCT),
        migrations.RunSQL(
            sql=APLICAR_RLS_PRODUCTPACKAGING, reverse_sql=REVERTER_RLS_PRODUCTPACKAGING
        ),
        migrations.RunSQL(sql=APLICAR_RLS_SUPPLIER, reverse_sql=REVERTER_RLS_SUPPLIER),
        migrations.RunSQL(
            sql=APLICAR_RLS_SUPPLIERPRODUCTCODE, reverse_sql=REVERTER_RLS_SUPPLIERPRODUCTCODE
        ),
    ]
