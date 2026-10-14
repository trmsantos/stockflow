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
from apps.purchasing.selectors import paginas_do_documento

__all__ = [
    "EstadoDaLeitura",
    "FronteiraDaExtracao",
    "LeituraDeDocumento",
    "LinhaLida",
    "PaginaDoDocumento",
    "fronteira_da_extracao",
    "ligar_fronteira_da_extracao",
    "paginas_do_documento",
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


def criar_documento(*, tenant_id: UUID) -> DocumentoResumo:
    """Cria um documento de fatura. Consumidor: `apps/demo`."""
    from apps.purchasing.models import InvoiceDocument

    doc = InvoiceDocument.objects.create(
        tenant_id=tenant_id,
        origin="upload",
    )
    return DocumentoResumo(id=doc.id, origin=doc.origin)


def criar_receçao(
    *, tenant_id: UUID, supplier_id: UUID, document_id: UUID | None = None, status: str = "draft"
) -> ReceçaoResumo:
    """Cria uma receção. Consumidor: `apps/demo`."""
    from django.utils import timezone

    from apps.accounts.models import Tenant
    from apps.catalog.models import Supplier
    from apps.inventory.models import Location
    from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento, Receipt

    tenant = Tenant.objects.get(id=tenant_id)
    supplier = Supplier.objects.get(id=supplier_id, tenant_id=tenant_id)

    # Usar ou criar localização padrão
    location = Location.objects.filter(tenant_id=tenant_id).first()
    if not location:
        location = Location.objects.create(
            tenant_id=tenant_id,
            name="Armazém",
            position=0,
        )

    # Se document_id não foi fornecido, criar um novo
    if document_id is None:
        doc = InvoiceDocument.objects.create(tenant_id=tenant_id, source=OrigemDoDocumento.UPLOAD)
        document_id = doc.id

    receipt = Receipt.objects.create(
        tenant=tenant,
        supplier=supplier,
        document_id=document_id,
        doc_type="FT",
        received_at=timezone.now(),
        location=location,
        confirmed_at=timezone.now() if status == "confirmed" else None,
    )
    return ReceçaoResumo(id=receipt.id, tenant_id=receipt.tenant_id, supplier_id=receipt.supplier_id)


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
    from apps.catalog.models import Product
    from apps.inventory.models import Location
    from apps.purchasing.models import Receipt, ReceiptLine

    receipt = Receipt.objects.get(id=receipt_id, tenant_id=tenant_id)
    location = receipt.location or Location.objects.filter(tenant_id=tenant_id).first()

    linha = ReceiptLine.objects.create(
        tenant_id=tenant_id,
        receipt=receipt,
        position=receipt.lines.count(),
        description=description,
        invoice_unit="un",
        quantity_invoiced=quantity,
        unit_price=unit_price,
        quantity_received=quantity,
        location=location,
        kind="goods",
        product_id=product_id,
    )
    return linha.id
