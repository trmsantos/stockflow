"""As quatro tabelas do artigo e de quem o vende (ADR 0021, fatia 2; ADR 0022).

| Tabela | O que é |
|---|---|
| `catalog_product` | **o que um artigo é**: nome curto, unidade base, apresentação, se exige lote |
| `catalog_productpackaging` | uma embalagem do artigo, e quantas unidades base vale **uma** |
| `catalog_supplier` | quem o vende, com o NIF validado |
| `catalog_supplierproductcode` | a memória `(fornecedor, código) → artigo`, aprendida ao confirmar |

A frase-teste da decisão 1 da ADR 0021 decide o que está aqui: *"se é verdade
sobre o artigo independentemente de quem o vendeu, é do `catalog`"*. Por isso a
**taxa de IVA não está aqui** (é da linha do documento), o **custo não está
aqui** (é do movimento) e a **validade não está aqui** (é do lote) — só o seu
*rótulo*, `expiry_kind`, que é propriedade do artigo (Q7 do dono).

## O que não entra, e é decisão

* **`count_unit`** (Q5): a forma da terceira unidade — texto mais factor, ou FK à
  embalagem — fica por decidir e só tem leitor na sessão da contagem. Uma
  coluna sem leitor numa migração que não se edita é um compromisso tomado às
  escuras;
* **`min_quantity` tem coluna e não tem escritor** (Q4): um mínimo por artigo,
  na unidade base, default 0. O `ProdutoPatchIn` não a tem; o dia em que
  tiver, é um campo e não uma migração.

Nenhum destes modelos é registado no admin (ADR 0007).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models.functions import Lower

from apps.shared.models import TenantModel

__all__ = [
    "Conservacao",
    "Product",
    "ProductPackaging",
    "RotuloDeValidade",
    "Supplier",
    "SupplierProductCode",
    "UnidadeBase",
]


class UnidadeBase(models.TextChoices):
    """As três unidades base, uma por dimensão (`catalog/unidades.py`).

    Fechada de propósito: tudo o que o ledger soma está numa destas três, e é a
    tabela de sinónimos que traduz o que a fatura imprime para cá. Mudar a
    unidade base de um artigo muda o significado de todo o seu histórico, e é
    por isso que o `ProdutoPatchIn` não a tem.
    """

    GRAMA = "g", "grama"
    MILILITRO = "ml", "mililitro"
    UNIDADE = "un", "unidade"


class RotuloDeValidade(models.TextChoices):
    """`use_by` é limite legal, `best_before` é qualidade — e é do artigo (Q7).

    Quem recebe não o escolhe: o morango é sempre "consumir até" e a farinha
    sempre "consumir de preferência antes de". A fixture do frontend punha isto
    no lote, e corrige-se (ADR 0022).
    """

    USE_BY = "use_by", "consumir até"
    BEST_BEFORE = "best_before", "consumir de preferência antes de"


class Conservacao(models.TextChoices):
    """A classe de conservação, que é o que decide a temperatura a registar.

    Duas interessam ao HACCP (`chilled` e `frozen`) e a receção regista uma
    temperatura **por classe presente** (ADR 0022, decisão 5). `ambient` é o
    default e é o que um artigo sem artigo nenhum (uma linha de vasilhame) tem.
    """

    AMBIENT = "ambient", "ambiente"
    CHILLED = "chilled", "refrigerado"
    FROZEN = "frozen", "congelado"


class Product(TenantModel):
    """Um artigo: como o staff lhe chama, em que unidade se conta, e o que exige.

    ## `short_name` e não a descrição da fatura

    É *"como o staff lhe chama, não a descrição da fatura"* — a descrição vive
    na linha do documento, muda de fornecedor para fornecedor, e é a memória
    `(fornecedor, código)` que liga as duas. A unicidade é **sem caixa**
    (`Lower`), porque "Manteiga" e "manteiga" são o mesmo artigo e o segundo
    seria uma duplicação que só se descobre numa contagem.

    ## `sku` é único por tenant, mas só quando existe

    SKU (Stock Keeping Unit): um código canónico do artigo, sem caixa (`Lower`)
    como o nome, para busca rápida e integração com sistemas externos. O serviço
    preenche-o com o `short_name` quando vem vazio, logo pela API nunca fica em
    branco — mas a coluna é `""` e não NULL (`DJ001`), e uma unicidade **total**
    sobre `""` fazia o segundo artigo criado sem SKU no mesmo tenant rebentar na
    base de dados. A unicidade é por isso **parcial**, `where sku <> ''`, na
    forma da do `ean` em `ProductPackaging`: em branco em quantos artigos for
    preciso, único quando existe. Pode ser editado independentemente do nome.

    ## `display_unit` + `display_factor`

    A unidade em que o ecrã mostra e o factor para a base: farinha em `g` com
    apresentação em `kg` ×1000. O `catalog/unidades.py` não deixa o par mentir
    sobre a tabela — `"kg"` com factor 500 é recusado — e deixa livre o que não
    é unidade (`"saco"`, `"bloco"`), que é para isso que a apresentação existe.

    ## `expiry_kind` é texto vazio e não NULL

    O contrato diz `null`, a coluna diz `""`: o `DJ001` do ruff recusa `null=True`
    num campo de texto e o `CLAUDE.md` não deixa suprimir uma regra. O serializer
    traduz nos dois sentidos, como o `qr_payload` da fatia 1. Não se perde
    informação: `""` é "sem rótulo", e um rótulo vazio não existe.

    ## `is_active`, e nunca `DELETE`

    Um artigo com histórico não se apaga: as linhas de receção e, na fatia 3,
    os movimentos apontam-lhe com `RESTRICT`. Desactivar é a única saída, e a
    receção recusa um artigo inactivo (`artigo_inativo`).
    """

    short_name = models.CharField(max_length=80, verbose_name="nome curto")
    sku = models.CharField(
        max_length=80, default="", blank=True, verbose_name="SKU (identificador único)"
    )
    base_unit = models.CharField(
        max_length=2, choices=UnidadeBase.choices, verbose_name="unidade base"
    )
    display_unit = models.CharField(max_length=20, verbose_name="unidade de apresentação")
    display_factor = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="unidades base por unidade de apresentação",
    )
    min_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0"),
        verbose_name="mínimo, na unidade base",
    )
    track_lots = models.BooleanField(default=False, verbose_name="exige lote")
    expiry_kind = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=RotuloDeValidade.choices,
        verbose_name="rótulo da validade",
    )
    conservation = models.CharField(
        max_length=10,
        choices=Conservacao.choices,
        default=Conservacao.AMBIENT,
        verbose_name="conservação",
    )
    is_active = models.BooleanField(default=True, verbose_name="ativo")

    class Meta(TenantModel.Meta):
        verbose_name = "artigo"
        verbose_name_plural = "artigos"
        constraints = [
            models.UniqueConstraint(
                Lower("short_name"), "tenant", name="catalog_product_short_name_lower_uniq"
            ),
            models.UniqueConstraint(
                Lower("sku"),
                "tenant",
                condition=~models.Q(sku=""),
                name="catalog_product_sku_lower_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(display_factor__gt=0),
                name="catalog_product_display_factor_positivo",
            ),
            models.CheckConstraint(
                condition=models.Q(min_quantity__gte=0),
                name="catalog_product_min_quantity_nao_negativa",
            ),
        ]

    def __str__(self) -> str:
        return self.short_name


class ProductPackaging(TenantModel):
    """Uma embalagem do artigo: "caixa 12×1 L", e quantas unidades base vale **uma**.

    É o que converte uma linha de fatura em stock sem adivinhar: `3 caixas` ×
    `base_quantity` = unidades base. O factor usado numa receção é guardado em
    **snapshot** na linha (`base_per_invoice_unit`), porque a embalagem é
    editável e uma conversão histórica que mude quando alguém corrige um rótulo
    reescreve quantidades que já foram ao ledger (ADR 0021).

    O `ean` é texto vazio e não NULL (`DJ001`), e a unicidade parcial
    `(tenant, ean) where ean <> ''` é o que o deixa em branco em quantas
    embalagens for preciso e único quando existe — é a segunda chave de match ao
    semear uma receção (§4.7).

    `CASCADE` do artigo: uma embalagem sem artigo não é nada. Mas o artigo não
    se apaga (ver `Product`), logo na prática esta cascata nunca corre.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="packagings",
        verbose_name="artigo",
    )
    label = models.CharField(max_length=60, verbose_name="rótulo")
    base_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="unidades base por embalagem"
    )
    ean = models.CharField(max_length=14, blank=True, default="", verbose_name="EAN/GTIN")

    class Meta(TenantModel.Meta):
        verbose_name = "embalagem"
        verbose_name_plural = "embalagens"
        constraints = [
            models.UniqueConstraint(
                Lower("label"),
                "tenant",
                "product",
                name="catalog_packaging_label_lower_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant", "ean"],
                condition=models.Q(ean__gt=""),
                name="catalog_packaging_ean_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(base_quantity__gt=0),
                name="catalog_packaging_base_quantity_positiva",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class Supplier(TenantModel):
    """Quem vende. O NIF é validado à entrada e único quando existe.

    `nif` é texto vazio e não NULL (`DJ001`): o Makro do seed não tem NIF no
    catálogo porque a fatura simplificada foi passada ao NIF do sócio, e a
    unicidade parcial `where nif <> ''` é o que permite N fornecedores sem NIF
    e nenhum NIF repetido.

    Dívida nomeada na ADR 0021: o NIF de um fornecedor tem a mesma natureza do
    NIF do tenant — a frutaria do mercado é um ENI — e fica em claro até à
    sessão da encriptação de campo, que vai ter de cobrir também a imagem da
    fatura onde o mesmo NIF está impresso.
    """

    name = models.CharField(max_length=200, verbose_name="nome")
    nif = models.CharField(max_length=9, blank=True, default="", verbose_name="NIF")
    is_active = models.BooleanField(default=True, verbose_name="ativo")

    class Meta(TenantModel.Meta):
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "tenant", name="catalog_supplier_name_lower_uniq"
            ),
            models.UniqueConstraint(
                fields=["tenant", "nif"],
                condition=models.Q(nif__gt=""),
                name="catalog_supplier_nif_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SupplierProductCode(TenantModel):
    """A memória `(fornecedor, código) → artigo`: o que faz o match ser exacto à segunda fatura.

    Aprende-se **na confirmação** de uma receção, nunca na revisão da linha
    (ADR 0022, decisão 3): memoriza-se o que ficou confirmado, não o que ainda
    pode mudar. A chave é exacta — `code` em maiúsculas, com os zeros à esquerda
    — e uma linha sem código impresso não casa nem ensina.

    `invoice_unit` entrou pela emenda do `domain-expert` (§4.1): é a unidade,
    normalizada, com que o código foi aprendido. Ao semear a receção seguinte, a
    embalagem e o factor só se pré-preenchem se a unidade da linha nova for a
    mesma — sem isto, o mesmo código a mudar de `UN` para `CX` dava ×50 em
    silêncio.

    `description_raw` é o rótulo do que estava impresso na vez em que se
    aprendeu, e **nunca chave**: casar por texto solto é um artigo errado à
    segunda fatura. `learned_at` é a última confirmação que o escreveu — o
    upsert actualiza-o.

    `RESTRICT` no artigo e na embalagem (ADR 0021, decisão 5): apagar um artigo
    com memória é recusado, mas a cascata do tenant leva tudo.
    """

    supplier = models.ForeignKey(
        "catalog.Supplier",
        on_delete=models.CASCADE,
        related_name="product_codes",
        verbose_name="fornecedor",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name="artigo",
    )
    packaging = models.ForeignKey(
        "catalog.ProductPackaging",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="embalagem",
    )
    code = models.CharField(max_length=50, verbose_name="código do fornecedor")
    description_raw = models.CharField(
        max_length=500, blank=True, default="", verbose_name="descrição impressa"
    )
    invoice_unit = models.CharField(
        max_length=20, blank=True, default="", verbose_name="unidade da fatura, normalizada"
    )
    learned_at = models.DateTimeField(verbose_name="aprendido em")

    class Meta(TenantModel.Meta):
        verbose_name = "código de fornecedor"
        verbose_name_plural = "códigos de fornecedor"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "supplier", "code"],
                name="catalog_supplierproductcode_supplier_code_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} → {self.product_id}"
