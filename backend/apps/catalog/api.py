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

__all__ = [
    "Correspondencia",
    "CorrespondenciaAprendida",
    "EmbalagemResumo",
    "FornecedorResumo",
    "ProdutoResumo",
    "correspondencias",
    "criar_embalagem",
    "criar_fornecedor",
    "criar_produto",
    "embalagens_por_id",
    "fornecedor_por_nif",
    "fornecedores_por_id",
    "memorizar_correspondencias",
    "normalizar_nif",
    "normalizar_unidade",
    "produto_por_id",
    "produto_por_sku",
    "produtos_por_id",
]


# ---------------------------------------------------------------------------
# DTOs. Congelados e com `slots`.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class ProdutoResumo:
    """Um artigo como os outros módulos o veem."""

    id: UUID
    short_name: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    track_lots: bool
    expiry_kind: str | None
    conservation: str
    is_active: bool


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
    return {
        p.id: ProdutoResumo(
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
        for p in artigos
    }


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
        p = Product.objects.get(tenant_id=tenant_id, id=product_id)
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
    except Product.DoesNotExist:
        return None


def produto_por_sku(*, tenant_id: UUID, sku: str) -> ProdutoResumo | None:
    """Artigo pelo SKU (insensível à caixa), ou None."""
    try:
        p = Product.objects.get(tenant_id=tenant_id, sku__iexact=sku.strip())
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
