"""Os casos de uso do catálogo. **Única forma de escrever.**

Uma função por caso de uso, cada uma `@transaction.atomic` (um savepoint dentro
da transação do pedido — ARCHITECTURE.md §4.6). Sem outbox: esta fatia não emite
evento nenhum (ADR 0022, decisão 4 — *"um evento sem subscritor é um contrato
escrito ao contrário"*).

| Função | Quem a chama |
|---|---|
| `criar_produto` | `POST /products`, e o `apps/demo` pelo `api.py` |
| `actualizar_produto` | `PATCH /products/<id>` |
| `criar_embalagem` | `POST /products/<id>/packagings`, o `packaging` inline do `POST /products`, e o demo |
| `criar_fornecedor` | `POST /suppliers`, e o demo |
| `actualizar_fornecedor` | `PATCH /suppliers/<id>` |
| `memorizar_correspondencias` | `purchasing.confirmar_rececao`, pelo `api.py` |

## As recusas são `ValidationError` por campo, e a base de dados é a rede

O serializer já recusou a forma (tamanhos, escolhas, unicidade sem caixa) com a
frase certa debaixo do campo certo. Aqui repete-se o que é **invariante de
domínio** — a coerência da apresentação com a tabela de unidades, a unicidade,
o factor positivo — porque este ficheiro também é chamado sem serializer nenhum
(o `apps/demo`, pelo `api.py`), e um invariante que só vive no transporte não é
invariante. O `IntegrityError` fica como segunda rede para a corrida entre dois
pedidos: a constraint é a regra, e o `except` é só a forma de responder 400 em
vez de 500.

## `id` opcional, e idempotência por `id`

`criar_produto`, `criar_embalagem` e `criar_fornecedor` aceitam um `id`. É o que
o `apps/demo` usa para os uuid estáveis do `aurora.ts` — e com `id`, uma linha
que já exista **neste tenant** com esse uuid é devolvida em vez de recriada, que
é o que torna o semeador repetível sobre o mesmo estabelecimento. Um uuid que
exista noutro tenant é invisível daqui (RLS) e colide na chave primária: a
`IntegrityError` sobe, porque não há resposta certa a dar por ele.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.ean import ean_valido, normalizar_ean
from apps.catalog.models import (
    Conservacao,
    Product,
    ProductPackaging,
    RotuloDeValidade,
    Supplier,
    SupplierProductCode,
    UnidadeBase,
)
from apps.catalog.nif import nif_valido, normalizar_nif
from apps.catalog.unidades import ApresentacaoIncoerente, verificar_apresentacao

__all__ = [
    "CAMPOS_DO_FORNECEDOR",
    "CAMPOS_DO_PRODUTO",
    "CodigoAprendido",
    "EmbalagemNova",
    "actualizar_fornecedor",
    "actualizar_produto",
    "criar_embalagem",
    "criar_fornecedor",
    "criar_produto",
    "memorizar_correspondencias",
    "normalizar_codigo",
]

logger = logging.getLogger(__name__)

#: O que o `PATCH /products/<id>` pode escrever. **Sem `base_unit`** (mudar a
#: unidade base muda o significado de todo o histórico) e **sem `min_quantity`**
#: (Q4: coluna sem escritor nesta fatia). Uma chave fora desta lista é recusada
#: pelo serviço, e não ignorada — ignorar um campo é mentir a quem o enviou.
CAMPOS_DO_PRODUTO: frozenset[str] = frozenset(
    {
        "short_name",
        "sku",
        "display_unit",
        "display_factor",
        "track_lots",
        "expiry_kind",
        "conservation",
        "is_active",
    }
)

#: O que o `PATCH /suppliers/<id>` pode escrever.
CAMPOS_DO_FORNECEDOR: frozenset[str] = frozenset({"name", "nif", "is_active"})

DETALHE_NOME_DUPLICADO = _("There is already an item with this name in this establishment.")
DETALHE_SKU_DUPLICADO = _("There is already an item with this SKU in this establishment.")
DETALHE_ROTULO_DUPLICADO = _("This item already has a packaging with this label.")
DETALHE_EAN_DUPLICADO = _("Another packaging in this establishment already has this EAN.")
DETALHE_EAN_INVALIDO = _(
    "An EAN has 8, 12, 13 or 14 digits and a valid check digit. This one does not."
)
DETALHE_FORNECEDOR_DUPLICADO = _(
    "There is already a supplier with this name in this establishment."
)
DETALHE_NIF_DUPLICADO = _("Another supplier in this establishment already has this NIF.")
DETALHE_NIF_INVALIDO = _(
    "A NIF has nine digits and a valid check digit. This one does not."
)
DETALHE_FACTOR_POSITIVO = _("The factor has to be greater than zero.")
DETALHE_OBRIGATORIO = _("This field is required.")
DETALHE_DEMASIADO_LONGO = _("At most {limite} characters.")
DETALHE_ESCOLHA = _("Not one of the allowed values.")
DETALHE_CAMPO_FORA_DO_CONTRATO = _("This field cannot be changed here.")
DETALHE_ARTIGO_DESCONHECIDO = _("This item does not exist in this establishment.")
DETALHE_FORNECEDOR_DESCONHECIDO = _("This supplier does not exist in this establishment.")


@dataclass(frozen=True, kw_only=True, slots=True)
class EmbalagemNova:
    """A primeira embalagem de um artigo, no mesmo pedido que o cria.

    É *"o gesto da linha desconhecida"* (contrato, `ProdutoIn.packaging`): a
    fatura traz um artigo que o catálogo não tem, e a pessoa cria artigo e
    embalagem num diálogo só. Os dois nascem na mesma transação, ou nenhum.
    """

    label: str
    base_quantity: Decimal
    ean: str = ""


@dataclass(frozen=True, kw_only=True, slots=True)
class CodigoAprendido:
    """Uma linha confirmada que ensina `(código → artigo, embalagem, unidade)`."""

    code: str
    description_raw: str
    product_id: UUID
    packaging_id: UUID | None
    invoice_unit: str


def normalizar_codigo(texto: str | None) -> str:
    """`strip` + maiúsculas, **mantendo os zeros à esquerda** (§4.7).

    É a chave exacta da memória: `"0042"` e `"42"` são códigos diferentes num
    fornecedor que imprime zeros, e removê-los era fundir dois artigos.
    """
    return (texto or "").strip().upper()


# ---------------------------------------------------------------------------
# Artigos
# ---------------------------------------------------------------------------
@transaction.atomic
def criar_produto(
    *,
    tenant_id: UUID,
    short_name: str,
    base_unit: str,
    display_unit: str,
    display_factor: Decimal,
    track_lots: bool = False,
    expiry_kind: str | None = None,
    conservation: str = Conservacao.AMBIENT,
    sku: str | None = None,
    packaging: EmbalagemNova | None = None,
    id: UUID | None = None,
) -> Product:
    """Cria o artigo e, se vier, a sua primeira embalagem — na mesma transação.

    `expiry_kind` aceita `None` e guarda `""`: o contrato diz `null`, a coluna
    diz texto vazio (`DJ001`), e a tradução acontece aqui para o `api.py` e o
    serializer falarem a língua do contrato.
    """
    if id is not None:
        existente = Product.objects.filter(tenant_id=tenant_id, pk=id).first()
        if existente is not None:
            return existente

    campos = _validar_produto(
        tenant_id=tenant_id,
        short_name=short_name,
        base_unit=base_unit,
        display_unit=display_unit,
        display_factor=display_factor,
        expiry_kind=expiry_kind,
        conservation=conservation,
        sku=sku,
    )
    try:
        with transaction.atomic():
            produto = Product.objects.create(
                tenant_id=tenant_id,
                track_lots=track_lots,
                **({"id": id} if id is not None else {}),
                **campos,
            )
    except IntegrityError as erro:
        raise _duplicado("short_name", DETALHE_NOME_DUPLICADO) from erro

    if packaging is not None:
        criar_embalagem(
            tenant_id=tenant_id,
            produto=produto,
            label=packaging.label,
            base_quantity=packaging.base_quantity,
            ean=packaging.ean,
        )
    logger.info("artigo criado", extra={"event": "catalogo.artigo", "outcome": "criado"})
    return produto


@transaction.atomic
def actualizar_produto(*, tenant_id: UUID, produto: Product, campos: Mapping[str, object]) -> Product:
    """`PATCH`: só os campos de `CAMPOS_DO_PRODUTO`, e só os que vieram.

    Relê a linha **trancada** antes de a alterar: entre o `get_object()` da view e
    esta linha outro pedido pode ter mudado a mesma coisa, e dois `PATCH`
    simultâneos ao mesmo artigo têm de ficar em fila e não a sobrepor-se.

    Uma chave fora do contrato (`base_unit`, `min_quantity`, ou qualquer outra)
    é 400 por campo, não um silêncio: o cliente que a mandou tem de saber que
    ela não entrou.
    """
    fora = sorted(set(campos) - CAMPOS_DO_PRODUTO)
    if fora:
        raise ValidationError({campo: [DETALHE_CAMPO_FORA_DO_CONTRATO] for campo in fora})

    bloqueado = (
        Product.objects.select_for_update().filter(tenant_id=tenant_id, pk=produto.pk).get()
    )

    # Check if trying to change track_lots when stock exists
    if "track_lots" in campos and bloqueado.track_lots != bool(campos["track_lots"]):
        # Verificar se existe stock via import local (tipo checking acima)
        if _tem_stock(tenant_id=tenant_id, product_id=bloqueado.pk):
            raise ValidationError({
                "track_lots": [_("Cannot change lot tracking when stock exists.")]
            })

    validados = _validar_produto(
        tenant_id=tenant_id,
        short_name=str(campos.get("short_name", bloqueado.short_name)),
        base_unit=bloqueado.base_unit,
        display_unit=str(campos.get("display_unit", bloqueado.display_unit)),
        display_factor=Decimal(str(campos.get("display_factor", bloqueado.display_factor))),
        expiry_kind=_texto_ou_nulo(campos.get("expiry_kind", bloqueado.expiry_kind)),
        conservation=str(campos.get("conservation", bloqueado.conservation)),
        sku=_texto_ou_nulo(campos.get("sku", bloqueado.sku)),
        excluir_pk=bloqueado.pk,
    )
    for nome, valor in validados.items():
        setattr(bloqueado, nome, valor)
    if "track_lots" in campos:
        bloqueado.track_lots = bool(campos["track_lots"])
    if "is_active" in campos:
        bloqueado.is_active = bool(campos["is_active"])
    try:
        with transaction.atomic():
            bloqueado.save(
                update_fields=[*validados, "track_lots", "is_active", "updated_at"]
            )
    except IntegrityError as erro:
        raise _duplicado("short_name", DETALHE_NOME_DUPLICADO) from erro
    return bloqueado


@transaction.atomic
def criar_embalagem(
    *,
    tenant_id: UUID,
    produto: Product,
    label: str,
    base_quantity: Decimal,
    ean: str | None = "",
    id: UUID | None = None,
) -> ProductPackaging:
    """Uma embalagem do artigo. O `ean` é normalizado (só dígitos) e validado.

    O artigo vem como instância porque quem chama já o tem — a view pelo
    `get_object()`, o `criar_produto` acabou de o criar — e porque é o que
    garante que a embalagem fica no **mesmo** tenant que o artigo.
    """
    if produto.tenant_id != tenant_id:
        raise ValidationError({"product": [DETALHE_ARTIGO_DESCONHECIDO]})
    if id is not None:
        existente = ProductPackaging.objects.filter(tenant_id=tenant_id, pk=id).first()
        if existente is not None:
            return existente

    rotulo = _texto(label, campo="label", limite=60)
    if base_quantity <= 0:
        raise ValidationError({"base_quantity": [DETALHE_FACTOR_POSITIVO]})
    codigo = normalizar_ean(ean)
    if ean and not ean_valido(ean):
        raise ValidationError({"ean": [DETALHE_EAN_INVALIDO]})
    if (
        ProductPackaging.objects.filter(tenant_id=tenant_id, product=produto, label__iexact=rotulo)
        .exists()
    ):
        raise ValidationError({"label": [DETALHE_ROTULO_DUPLICADO]})
    if codigo and ProductPackaging.objects.filter(tenant_id=tenant_id, ean=codigo).exists():
        raise ValidationError({"ean": [DETALHE_EAN_DUPLICADO]})
    try:
        with transaction.atomic():
            embalagem = ProductPackaging.objects.create(
                tenant_id=tenant_id,
                product=produto,
                label=rotulo,
                base_quantity=base_quantity,
                ean=codigo,
                **({"id": id} if id is not None else {}),
            )
    except IntegrityError as erro:
        # Duas constraints podem ter ganho a corrida; a frase vai para o campo
        # mais provável, e a base de dados continua a ser a que decide.
        raise _duplicado("label", DETALHE_ROTULO_DUPLICADO) from erro
    return embalagem


# ---------------------------------------------------------------------------
# Fornecedores
# ---------------------------------------------------------------------------
@transaction.atomic
def criar_fornecedor(
    *, tenant_id: UUID, name: str, nif: str | None = "", id: UUID | None = None
) -> Supplier:
    """Um fornecedor, com o NIF normalizado e validado (quando existe)."""
    if id is not None:
        existente = Supplier.objects.filter(tenant_id=tenant_id, pk=id).first()
        if existente is not None:
            return existente
    campos = _validar_fornecedor(tenant_id=tenant_id, name=name, nif=nif)
    try:
        with transaction.atomic():
            fornecedor = Supplier.objects.create(
                tenant_id=tenant_id, **({"id": id} if id is not None else {}), **campos
            )
    except IntegrityError as erro:
        raise _duplicado("name", DETALHE_FORNECEDOR_DUPLICADO) from erro
    return fornecedor


@transaction.atomic
def actualizar_fornecedor(
    *, tenant_id: UUID, fornecedor: Supplier, campos: Mapping[str, object]
) -> Supplier:
    """`PATCH`: `name`, `nif`, `is_active`. Relido sob lock, como o artigo."""
    fora = sorted(set(campos) - CAMPOS_DO_FORNECEDOR)
    if fora:
        raise ValidationError({campo: [DETALHE_CAMPO_FORA_DO_CONTRATO] for campo in fora})

    bloqueado = (
        Supplier.objects.select_for_update().filter(tenant_id=tenant_id, pk=fornecedor.pk).get()
    )
    validados = _validar_fornecedor(
        tenant_id=tenant_id,
        name=str(campos.get("name", bloqueado.name)),
        nif=_texto_ou_nulo(campos.get("nif", bloqueado.nif)),
        excluir_pk=bloqueado.pk,
    )
    for nome, valor in validados.items():
        setattr(bloqueado, nome, valor)
    if "is_active" in campos:
        bloqueado.is_active = bool(campos["is_active"])
    try:
        with transaction.atomic():
            bloqueado.save(update_fields=[*validados, "is_active", "updated_at"])
    except IntegrityError as erro:
        raise _duplicado("name", DETALHE_FORNECEDOR_DUPLICADO) from erro
    return bloqueado


# ---------------------------------------------------------------------------
# A memória (fornecedor, código) → artigo
# ---------------------------------------------------------------------------
@transaction.atomic
def memorizar_correspondencias(
    *, tenant_id: UUID, supplier_id: UUID, itens: Sequence[CodigoAprendido]
) -> int:
    """Upsert por `(fornecedor, código)`; a última confirmação ganha. Devolve quantas escreveu.

    As regras do §4.7, todas aqui para o chamador não as poder esquecer:

    * o código é normalizado (`strip`, maiúsculas, zeros à esquerda mantidos), e
      um código vazio **não ensina**;
    * **dentro da mesma chamada**, o mesmo código com artigos diferentes é um
      conflito e esse código não se aprende — memorizar um dos dois ao acaso era
      um artigo errado à segunda fatura;
    * o artigo e a embalagem têm de existir **neste** tenant, e a embalagem tem
      de ser do artigo. O que não cumprir é ignorado, com log: a confirmação de
      uma receção não pode falhar por uma memória que não se consegue escrever.

    Uma query de escrita (`bulk_create` com `update_conflicts`), porque uma
    receção pode ter duzentas linhas e isto corre dentro da transação que a
    confirma.
    """
    if not Supplier.objects.filter(tenant_id=tenant_id, pk=supplier_id).exists():
        raise ValidationError({"supplier": [DETALHE_FORNECEDOR_DESCONHECIDO]})

    por_codigo: dict[str, CodigoAprendido] = {}
    conflituosos: set[str] = set()
    for item in itens:
        codigo = normalizar_codigo(item.code)
        if not codigo:
            continue
        anterior = por_codigo.get(codigo)
        if anterior is not None and anterior.product_id != item.product_id:
            conflituosos.add(codigo)
        por_codigo[codigo] = item
    for codigo in conflituosos:
        por_codigo.pop(codigo, None)
    if not por_codigo:
        return 0

    artigos = set(
        Product.objects.filter(
            tenant_id=tenant_id, pk__in={item.product_id for item in por_codigo.values()}
        ).values_list("pk", flat=True)
    )
    embalagens = dict(
        ProductPackaging.objects.filter(
            tenant_id=tenant_id,
            pk__in={item.packaging_id for item in por_codigo.values() if item.packaging_id},
        ).values_list("pk", "product_id")
    )
    agora = timezone.now()
    linhas: list[SupplierProductCode] = []
    for codigo, item in por_codigo.items():
        if item.product_id not in artigos:
            logger.info(
                "código não aprendido: artigo desconhecido",
                extra={"event": "catalogo.memoria", "outcome": "ignorado"},
            )
            continue
        embalagem_id = item.packaging_id
        if embalagem_id is not None and embalagens.get(embalagem_id) != item.product_id:
            embalagem_id = None
        linhas.append(
            SupplierProductCode(
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                product_id=item.product_id,
                packaging_id=embalagem_id,
                code=codigo,
                description_raw=(item.description_raw or "")[:500],
                invoice_unit=(item.invoice_unit or "")[:20],
                learned_at=agora,
            )
        )
    if not linhas:
        return 0
    SupplierProductCode.objects.bulk_create(
        linhas,
        update_conflicts=True,
        unique_fields=["tenant", "supplier", "code"],
        update_fields=[
            "product",
            "packaging",
            "description_raw",
            "invoice_unit",
            "learned_at",
            "updated_at",
        ],
    )
    logger.info(
        "correspondências memorizadas",
        extra={"event": "catalogo.memoria", "outcome": "ok", "count": len(linhas)},
    )
    return len(linhas)


# ---------------------------------------------------------------------------
# Privado: funções auxiliares
# ---------------------------------------------------------------------------
def _tem_stock(*, tenant_id: UUID, product_id: UUID) -> bool:
    """Verifica se existe stock para um produto (validação privada)."""
    from apps.inventory.models import StockLevel
    return StockLevel.objects.filter(tenant_id=tenant_id, product_id=product_id).exists()


# ---------------------------------------------------------------------------
# Privado: as validações de domínio
# ---------------------------------------------------------------------------
def _validar_produto(
    *,
    tenant_id: UUID,
    short_name: str,
    base_unit: str,
    display_unit: str,
    display_factor: Decimal,
    expiry_kind: str | None,
    conservation: str,
    sku: str | None = None,
    excluir_pk: UUID | None = None,
) -> dict[str, object]:
    """Os invariantes do artigo, como `ValidationError` por campo. Devolve os campos limpos."""
    erros: dict[str, list[object]] = {}
    nome = short_name.strip()
    apresentacao = display_unit.strip()
    codigo = (sku or nome).strip()  # SKU defaults to short_name if not provided
    if not nome:
        erros["short_name"] = [DETALHE_OBRIGATORIO]
    elif len(nome) > 80:
        erros["short_name"] = [DETALHE_DEMASIADO_LONGO.format(limite=80)]
    if base_unit not in UnidadeBase.values:
        erros["base_unit"] = [DETALHE_ESCOLHA]
    if not apresentacao:
        erros["display_unit"] = [DETALHE_OBRIGATORIO]
    elif len(apresentacao) > 20:
        erros["display_unit"] = [DETALHE_DEMASIADO_LONGO.format(limite=20)]
    if display_factor <= 0:
        erros["display_factor"] = [DETALHE_FACTOR_POSITIVO]
    if len(codigo) > 80:
        erros["sku"] = [DETALHE_DEMASIADO_LONGO.format(limite=80)]
    rotulo = expiry_kind or ""
    if rotulo not in ("", *RotuloDeValidade.values):
        erros["expiry_kind"] = [DETALHE_ESCOLHA]
    if conservation not in Conservacao.values:
        erros["conservation"] = [DETALHE_ESCOLHA]
    if erros:
        raise ValidationError(erros)

    try:
        verificar_apresentacao(
            base_unit=base_unit, display_unit=apresentacao, display_factor=display_factor
        )
    except ApresentacaoIncoerente as incoerencia:
        raise ValidationError({incoerencia.campo: [incoerencia.mensagem]}) from incoerencia

    duplicados = Product.objects.filter(tenant_id=tenant_id, short_name__iexact=nome)
    if excluir_pk is not None:
        duplicados = duplicados.exclude(pk=excluir_pk)
    if duplicados.exists():
        raise ValidationError({"short_name": [DETALHE_NOME_DUPLICADO]})

    sku_duplicado = Product.objects.filter(tenant_id=tenant_id, sku__iexact=codigo)
    if excluir_pk is not None:
        sku_duplicado = sku_duplicado.exclude(pk=excluir_pk)
    if sku_duplicado.exists():
        raise ValidationError({"sku": [DETALHE_SKU_DUPLICADO]})

    return {
        "short_name": nome,
        "sku": codigo,
        "base_unit": base_unit,
        "display_unit": apresentacao,
        "display_factor": display_factor,
        "expiry_kind": rotulo,
        "conservation": conservation,
    }


def _validar_fornecedor(
    *, tenant_id: UUID, name: str, nif: str | None, excluir_pk: UUID | None = None
) -> dict[str, object]:
    """Os invariantes do fornecedor: nome único sem caixa, NIF válido e único quando existe."""
    nome = _texto(name, campo="name", limite=200)
    contribuinte = normalizar_nif(nif)
    if contribuinte and not nif_valido(contribuinte):
        raise ValidationError({"nif": [DETALHE_NIF_INVALIDO]})

    duplicados = Supplier.objects.filter(tenant_id=tenant_id, name__iexact=nome)
    if excluir_pk is not None:
        duplicados = duplicados.exclude(pk=excluir_pk)
    if duplicados.exists():
        raise ValidationError({"name": [DETALHE_FORNECEDOR_DUPLICADO]})
    if contribuinte:
        mesmo_nif = Supplier.objects.filter(tenant_id=tenant_id, nif=contribuinte)
        if excluir_pk is not None:
            mesmo_nif = mesmo_nif.exclude(pk=excluir_pk)
        if mesmo_nif.exists():
            raise ValidationError({"nif": [DETALHE_NIF_DUPLICADO]})
    return {"name": nome, "nif": contribuinte}


def _texto(valor: str | None, *, campo: str, limite: int) -> str:
    """Um texto obrigatório, sem espaços à volta e dentro do limite da coluna."""
    limpo = (valor or "").strip()
    if not limpo:
        raise ValidationError({campo: [DETALHE_OBRIGATORIO]})
    if len(limpo) > limite:
        raise ValidationError({campo: [DETALHE_DEMASIADO_LONGO.format(limite=limite)]})
    return limpo


def _texto_ou_nulo(valor: object) -> str | None:
    return None if valor is None else str(valor)


def _duplicado(campo: str, detalhe: object) -> ValidationError:
    """A outra metade da corrida ganhou: a constraint recusou. 400 e não 500."""
    logger.info(
        "escrita recusada pela constraint",
        extra={"event": "catalogo.escrita", "outcome": "duplicado"},
    )
    return ValidationError({campo: [detalhe]})
