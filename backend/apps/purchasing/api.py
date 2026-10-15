"""A porta do módulo `purchasing` (ARCHITECTURE.md §3).

Único ficheiro deste módulo que outro módulo pode importar. Hoje tem **dois**
consumidores — o `apps/agents/` e o `apps/demo/` — e expõe:

1. **As páginas de um documento como DTO congelado** (para `agents`);
2. **A forma de "o que o modelo leu"** (para `agents`);
3. **O porto da extração** (para `agents`);
4. **Funções de criação de documentos e receções** (para `demo`).

Reexportação e não definição: cada nome vive no ficheiro onde pertence
(`models.py`, `extracao.py`, `selectors.py`, `services.py`) e este é só a porta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.purchasing.extracao import (
    FronteiraDaExtracao,
    LeituraDeDocumento,
    LinhaLida,
    PaginaDoDocumento,
    fronteira_da_extracao,
    ligar_fronteira_da_extracao,
)
from apps.purchasing.models import EstadoDaLeitura
from apps.purchasing.selectors import compras_confirmadas as _compras_confirmadas
from apps.purchasing.selectors import paginas_do_documento

__all__ = [
    "ComprasPorArtigo",
    "ComprasPorFornecedor",
    "ComprasResumo",
    "EstadoDaLeitura",
    "FronteiraDaExtracao",
    "LeituraDeDocumento",
    "LinhaLida",
    "PaginaDoDocumento",
    "fronteira_da_extracao",
    "ligar_fronteira_da_extracao",
    "paginas_do_documento",
    "compras_confirmadas",
    "criar_documento",
    "criar_receçao",
    "adicionar_linha_recepção",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class DocumentoResumo:
    """Um documento como o demo o vê."""

    id: UUID
    origin: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceçaoResumo:
    """Uma receção como o demo a vê."""

    id: UUID
    tenant_id: UUID
    supplier_id: UUID


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasPorFornecedor:
    """O total comprado a um fornecedor no período. `None` é "sem fornecedor"."""

    supplier_id: UUID | None
    supplier_name: str
    total_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasPorArtigo:
    """O total comprado de um artigo no período. `None` é "linha sem artigo"."""

    product_id: UUID | None
    product_name: str
    total_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasResumo:
    """As compras confirmadas de um período, agregadas por `received_at` (ADR 0027).

    `total_eur` é **sem IVA**, líquido de desconto, com as notas de crédito a
    subtrair. `documentos_sem_preco` são as guias de remessa, que contam 0 e
    ficam contadas para a resposta não dizer "gastou 0 €".
    """

    total_eur: Decimal
    por_fornecedor: tuple[ComprasPorFornecedor, ...]
    por_artigo: tuple[ComprasPorArtigo, ...]
    documentos: int
    documentos_sem_preco: int
    linhas_sem_custo: int


def compras_confirmadas(
    *,
    tenant_id: UUID,
    desde: datetime,
    ate: datetime,
    supplier_id: UUID | None = None,
    product_id: UUID | None = None,
) -> ComprasResumo:
    """As compras confirmadas recebidas em `[desde, ate)`. Consumidor: `apps/agents`."""
    dados = _compras_confirmadas(
        tenant_id=tenant_id, desde=desde, ate=ate, supplier_id=supplier_id, product_id=product_id
    )
    return ComprasResumo(
        total_eur=dados["total_eur"],
        por_fornecedor=tuple(ComprasPorFornecedor(**f) for f in dados["por_fornecedor"]),
        por_artigo=tuple(ComprasPorArtigo(**p) for p in dados["por_artigo"]),
        documentos=dados["documentos"],
        documentos_sem_preco=dados["documentos_sem_preco"],
        linhas_sem_custo=dados["linhas_sem_custo"],
    )


def criar_documento(*, tenant_id: UUID) -> DocumentoResumo:
    """Cria um documento de fatura. Consumidor: `apps/demo`."""
    from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento

    doc = InvoiceDocument.objects.create(tenant_id=tenant_id, source=OrigemDoDocumento.UPLOAD)
    return DocumentoResumo(id=doc.id, origin=doc.source)


def criar_receçao(
    *,
    tenant_id: UUID,
    supplier_id: UUID,
    location_id: UUID,
    document_id: UUID | None = None,
    status: str = "draft",
) -> ReceçaoResumo:
    """Cria uma receção com cabeçalho mínimo. Consumidor: `apps/demo`.

    Só por ids: fornecedor e localização são de outros módulos e a fronteira
    (import-linter) não deixa importar os modelos deles — a FK valida a existência.
    """
    from django.utils import timezone

    from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento, Receipt

    if document_id is None:
        doc = InvoiceDocument.objects.create(tenant_id=tenant_id, source=OrigemDoDocumento.UPLOAD)
        document_id = doc.id

    receipt = Receipt.objects.create(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        document_id=document_id,
        doc_type="FT",
        received_at=timezone.now(),
        location_id=location_id,
        confirmed_at=timezone.now() if status == "confirmed" else None,
    )
    return ReceçaoResumo(
        id=receipt.id, tenant_id=receipt.tenant_id, supplier_id=receipt.supplier_id
    )


def adicionar_linha_recepção(
    *,
    tenant_id: UUID,
    receipt_id: UUID,
    product_id: UUID,
    quantity: Decimal,
    unit_price: Decimal,
    description: str = "",
) -> UUID:
    """Adiciona uma linha a uma receção. Consumidor: `apps/demo`."""
    from apps.purchasing.models import Receipt, ReceiptLine

    receipt = Receipt.objects.get(id=receipt_id, tenant_id=tenant_id)

    linha = ReceiptLine.objects.create(
        tenant_id=tenant_id,
        receipt=receipt,
        position=receipt.lines.count(),
        description=description,
        invoice_unit="un",
        quantity_invoiced=quantity,
        unit_price=unit_price,
        quantity_received=quantity,
        location_id=receipt.location_id,
        kind="goods",
        product_id=product_id,
    )
    return linha.id
