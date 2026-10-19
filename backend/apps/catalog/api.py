"""A porta do módulo `catalog` (ARCHITECTURE.md §3, ADR 0021, fatia 2).

É o único ficheiro do `catalog` que outro módulo pode importar. Expõe:

1. **DTOs congelados** (`kw_only`, `slots`) que refletem as três tabelas principais.
2. **Funções em lote** que recebem IDs pela porta (nunca `select_related` de fora).
3. **Funções de escrita** (`criar_*`) para o seed da demonstração.
4. **A memória** (`correspondencias`, `memorizar_correspondencias`).

Nada de ORM (QuerySets, modelos) sai daqui: tudo congelado e serializado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (
    Product,
    ProductPackaging,
    Supplier,
    SupplierProductCode,
)
from apps.catalog.selectors import codigos_do_produto as _codigos_do_produto
from apps.catalog.selectors import embalagens_do_produto as _embalagens_do_produto
from apps.catalog.selectors import procurar_fornecedores as _procurar_fornecedores
from apps.catalog.selectors import procurar_produtos as _procurar_produtos

__all__ = [
    "CodigoDeFornecedorResumo",
    "Correspondencia",
    "CorrespondenciaAprendida",
    "EmbalagemResumo",
    "FornecedorResumo",
    "ProdutoResumo",
    "codigos_por_artigo",
    "correspondencias",
    "embalagens_por_artigo",
    "criar_embalagem",
    "criar_fornecedor",
    "criar_produto",
    "embalagens_por_id",
    "fornecedor_por_nif",
    "fornecedores_por_id",
    "memorizar_correspondencias",
    "normalizar_nif",
    "normalizar_unidade",
    "procurar_artigos",
    "procurar_fornecedores",
    "produto_por_id",
    "produto_por_sku",
    "produtos_por_id",
]


# ---------------------------------------------------------------------------
# DTOs. Congelados e com `slots`.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class ProdutoResumo:
    """Um artigo como os outros módulos o veem.

    O `sku` é o código canónico por tenant (único sem caixa quando existe —
    ver `Product`), e é por ele que as contagens e o `reporting` nomeiam o
    artigo. Tem default porque o helper do semeador, mais abaixo, constrói o
    resumo sem o ler.
    """

    id: UUID
    short_name: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    track_lots: bool
    expiry_kind: str | None
    conservation: str
    is_active: bool
    sku: str = ""
    #: O mínimo do artigo, na unidade base; `0` é "sem mínimo" (ADR 0027,
    #: decisão 6). Default pela razão do `sku`: o semeador constrói o resumo
    #: sem o ler.
    min_quantity: Decimal = Decimal("0")


def _resumo_do_produto(p: Product) -> ProdutoResumo:
    """O `ProdutoResumo` de uma linha. Uma construção, em vez de cinco cópias."""
    return ProdutoResumo(
        id=p.id,
        short_name=p.short_name,
        base_unit=p.base_unit,
        display_unit=p.display_unit,
        display_factor=p.display_factor,
        track_lots=p.track_lots,
        expiry_kind=p.expiry_kind or None,
        conservation=p.conservation,
        is_active=p.is_active,
        sku=p.sku,
        min_quantity=p.min_quantity,
    )


def _resumo_do_fornecedor(f: Supplier) -> FornecedorResumo:
    return FornecedorResumo(id=f.id, name=f.name, nif=f.nif, is_active=f.is_active)


@dataclass(frozen=True, kw_only=True, slots=True)
class EmbalagemResumo:
    """Uma embalagem como os outros módulos a veem."""

    id: UUID
    product_id: UUID
    label: str
    base_quantity: Decimal
    ean: str


@dataclass(frozen=True, kw_only=True, slots=True)
class FornecedorResumo:
    """Um fornecedor como os outros módulos o veem."""

    id: UUID
    name: str
    nif: str
    is_active: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class CodigoDeFornecedorResumo:
    """Como **um** fornecedor nomeia um artigo: o código e a descrição que imprime.

    É a memória da ADR 0021 lida pelo artigo e não pelo fornecedor, que é a
    direcção que a ficha do artigo precisa ("a Makro chama-lhe 7734, FARINHA T65
    SACO 25KG"). Sem NIF: a ficha de um artigo não é sítio para o número de
    contribuinte de ninguém.
    """

    supplier_id: UUID
    supplier_name: str
    code: str
    description_raw: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Correspondencia:
    """Um match (fornecedor, código) → artigo, lido na memória."""

    supplier_id: UUID
    code: str
    product_id: UUID
    packaging_id: UUID | None


@dataclass(frozen=True, kw_only=True, slots=True)
class CorrespondenciaAprendida:
    """Um match a guardar após confirmação de receção (upsert)."""

    code: str
    description_raw: str
    product_id: UUID
    packaging_id: UUID | None


# ---------------------------------------------------------------------------
# Leitura em lote (nunca `select_related` de fora).
# ---------------------------------------------------------------------------
def produtos_por_id(
    *, tenant_id: UUID, ids: Sequence[UUID]
) -> Mapping[UUID, ProdutoResumo]:
    """Artigos pelo ID, num mapa."""
    artigos = Product.objects.filter(tenant_id=tenant_id, id__in=ids)
    return {p.id: _resumo_do_produto(p) for p in artigos}


def procurar_artigos(*, tenant_id: UUID, q: str, limite: int = 10) -> tuple[ProdutoResumo, ...]:
    """A procura do assistente (ADR 0027, decisão 6): nome ou SKU, por tokens.

    Activos primeiro e inactivos marcados (`is_active`), nunca escondidos. O
    limite é cortado a 20 no selector.
    """
    return tuple(
        _resumo_do_produto(p) for p in _procurar_produtos(tenant_id=tenant_id, q=q, limite=limite)
    )


def procurar_fornecedores(
    *, tenant_id: UUID, q: str, limite: int = 10
) -> tuple[FornecedorResumo, ...]:
    """A procura de fornecedores do assistente: nome por tokens, NIF exacto."""
    return tuple(
        _resumo_do_fornecedor(f)
        for f in _procurar_fornecedores(tenant_id=tenant_id, q=q, limite=limite)
    )


def embalagens_por_artigo(*, tenant_id: UUID, product_id: UUID) -> tuple[EmbalagemResumo, ...]:
    """As embalagens de um artigo, pela ordem em que foram criadas (ADR 0028).

    "Saco de 25 kg", "caixa de 12" — é o que permite ao assistente responder
    "em que embalagens é que isto vem" sem o modelo ter de converter nada: a
    `base_quantity` vem na unidade base e quem lê apresenta-a.
    """
    return tuple(
        EmbalagemResumo(
            id=e.id,
            product_id=e.product_id,
            label=e.label,
            base_quantity=e.base_quantity,
            ean=e.ean,
        )
        for e in _embalagens_do_produto(tenant_id=tenant_id, product_id=product_id)
    )


def codigos_por_artigo(
    *, tenant_id: UUID, product_id: UUID, limite: int = 20
) -> tuple[CodigoDeFornecedorResumo, ...]:
    """Os códigos de fornecedor aprendidos para um artigo (ADR 0028)."""
    return tuple(
        CodigoDeFornecedorResumo(
            supplier_id=linha.supplier_id,
            supplier_name=linha.supplier.name,
            code=linha.code,
            description_raw=linha.description_raw,
        )
        for linha in _codigos_do_produto(tenant_id=tenant_id, product_id=product_id)[:limite]
    )


def embalagens_por_id(
    *, tenant_id: UUID, ids: Sequence[UUID]
) -> Mapping[UUID, EmbalagemResumo]:
    """Embalagens pelo ID, num mapa."""
    embalagens = ProductPackaging.objects.filter(tenant_id=tenant_id, id__in=ids)
    return {
        e.id: EmbalagemResumo(
            id=e.id,
            product_id=e.product_id,
            label=e.label,
            base_quantity=e.base_quantity,
            ean=e.ean,
        )
        for e in embalagens
    }


def fornecedores_por_id(
    *, tenant_id: UUID, ids: Sequence[UUID]
) -> Mapping[UUID, FornecedorResumo]:
    """Fornecedores pelo ID, num mapa."""
    fornecedores = Supplier.objects.filter(tenant_id=tenant_id, id__in=ids)
    return {
        f.id: FornecedorResumo(
            id=f.id,
            name=f.name,
            nif=f.nif,
            is_active=f.is_active,
        )
        for f in fornecedores
    }


def fornecedor_por_nif(*, tenant_id: UUID, nif: str) -> FornecedorResumo | None:
    """Fornecedor pelo NIF (normalizado), ou None."""
    try:
        f = Supplier.objects.get(tenant_id=tenant_id, nif=nif)
        return FornecedorResumo(
            id=f.id,
            name=f.name,
            nif=f.nif,
            is_active=f.is_active,
        )
    except Supplier.DoesNotExist:
        return None


def produto_por_id(*, tenant_id: UUID, product_id: UUID) -> ProdutoResumo | None:
    """Artigo pelo ID, ou None."""
    try:
        return _resumo_do_produto(Product.objects.get(tenant_id=tenant_id, id=product_id))
    except Product.DoesNotExist:
        return None


def produto_por_sku(*, tenant_id: UUID, sku: str) -> ProdutoResumo | None:
    """Artigo pelo SKU (insensível à caixa), ou None."""
    try:
        return _resumo_do_produto(Product.objects.get(tenant_id=tenant_id, sku__iexact=sku.strip()))
    except Product.DoesNotExist:
        return None


def correspondencias(
    *, tenant_id: UUID, supplier_id: UUID, codes: Sequence[str]
) -> Mapping[str, Correspondencia]:
    """Memória (fornecedor, código) → artigo, num mapa por código."""
    linhas = SupplierProductCode.objects.filter(
        tenant_id=tenant_id, supplier_id=supplier_id, code__in=codes
    )
    return {
        linha.code: Correspondencia(
            supplier_id=linha.supplier_id,
            code=linha.code,
            product_id=linha.product_id,
            packaging_id=linha.packaging_id,
        )
        for linha in linhas
    }


# ---------------------------------------------------------------------------
# Escrita.
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
    conservation: str = "ambient",
    id: UUID | None = None,
) -> ProdutoResumo:
    """Criar um artigo (ou retornar o existente). Consumidor: `apps/demo`."""
    try:
        p = Product.objects.get(tenant_id=tenant_id, short_name__iexact=short_name)
    except Product.DoesNotExist:
        p = Product.objects.create(
            id=id,
            tenant_id=tenant_id,
            short_name=short_name,
            sku=short_name,
            base_unit=base_unit,
            display_unit=display_unit,
            display_factor=display_factor,
            track_lots=track_lots,
            expiry_kind=expiry_kind or "",
            conservation=conservation,
        )
    return ProdutoResumo(
        id=p.id,
        short_name=p.short_name,
        base_unit=p.base_unit,
        display_unit=p.display_unit,
        display_factor=p.display_factor,
        track_lots=p.track_lots,
        expiry_kind=p.expiry_kind or None,
        conservation=p.conservation,
        is_active=p.is_active,
    )


@transaction.atomic
def criar_embalagem(
    *,
    tenant_id: UUID,
    product_id: UUID,
    label: str,
    base_quantity: Decimal,
    ean: str | None = None,
    id: UUID | None = None,
) -> EmbalagemResumo:
    """Criar uma embalagem de um artigo. Consumidor: `apps/demo`."""
    e = ProductPackaging.objects.create(
        id=id,
        tenant_id=tenant_id,
        product_id=product_id,
        label=label,
        base_quantity=base_quantity,
        ean=ean or "",
    )
    return EmbalagemResumo(
        id=e.id,
        product_id=e.product_id,
        label=e.label,
        base_quantity=e.base_quantity,
        ean=e.ean,
    )


@transaction.atomic
def criar_fornecedor(
    *,
    tenant_id: UUID,
    name: str,
    nif: str | None = None,
    id: UUID | None = None,
) -> FornecedorResumo:
    """Criar um fornecedor (ou retornar o existente). Consumidor: `apps/demo`."""
    try:
        f = Supplier.objects.get(tenant_id=tenant_id, name__iexact=name)
    except Supplier.DoesNotExist:
        f = Supplier.objects.create(
            id=id,
            tenant_id=tenant_id,
            name=name,
            nif=nif or "",
        )
    return FornecedorResumo(
        id=f.id,
        name=f.name,
        nif=f.nif,
        is_active=f.is_active,
    )


@transaction.atomic
def memorizar_correspondencias(
    *,
    tenant_id: UUID,
    supplier_id: UUID,
    itens: Sequence[CorrespondenciaAprendida],
) -> int:
    """Upsert da memória (fornecedor, código) → artigo.

    Cada item é guardado com a hora actual no `learned_at`. Se o mesmo
    (supplier, code) aparece duas vezes no lote, vence o último. Devolve o
    número de linhas criadas/actualizadas.
    """
    agora = timezone.now()
    updates = []
    for item in itens:
        updates.append(
            SupplierProductCode(
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                product_id=item.product_id,
                packaging_id=item.packaging_id,
                code=item.code,
                description_raw=item.description_raw,
                learned_at=agora,
            )
        )

    # Upsert: CREATE OR UPDATE com os índices unicos
    # Django não tem upsert nativo, logo usamos raw SQL com o dialect do Postgres
    if not updates:
        return 0

    # bulk_create com `update_conflicts` está em Django 4.1+
    from django.db import connection

    cursor = connection.cursor()

    # INSERT com ON CONFLICT (tenant, supplier, code) DO UPDATE
    sql = """
    INSERT INTO catalog_supplierproductcode
        (id, tenant_id, supplier_id, product_id, packaging_id,
         code, description_raw, learned_at, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (tenant_id, supplier_id, code)
    DO UPDATE SET
        product_id = EXCLUDED.product_id,
        packaging_id = EXCLUDED.packaging_id,
        description_raw = EXCLUDED.description_raw,
        learned_at = EXCLUDED.learned_at,
        updated_at = EXCLUDED.updated_at
    """

    rows = []
    for item in updates:
        rows.append(
            (
                item.id,
                item.tenant_id,
                item.supplier_id,
                item.product_id,
                item.packaging_id,
                item.code,
                item.description_raw,
                item.learned_at,
                timezone.now(),
                timezone.now(),
            )
        )

    cursor.executemany(sql, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Normalizações (importadas por otros módulos).
# ---------------------------------------------------------------------------
def normalizar_nif(nif: str) -> str:
    """Normalizar NIF: maiúsculas, alfanuméricos só, retirar PT inicial."""
    nif = nif.upper().strip()
    # Retirar "PT" inicial se seguido de 9 dígitos
    if nif.startswith("PT") and len(nif) == 11 and nif[2:].isdigit():
        nif = nif[2:]
    return nif


def normalizar_unidade(unidade: str) -> str:
    """Normalizar unidade: NFKD sem acentos, maiúsculas, sem espaços/ponto final."""
    import unicodedata

    # NFKD (decomposição de compatibilidade)
    nfd = unicodedata.normalize("NFKD", unidade)
    # Remover acentos (caracteres de combinação)
    sem_acentos = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Maiúsculas, sem espaços, sem ponto final
    return sem_acentos.upper().strip().rstrip(".")
