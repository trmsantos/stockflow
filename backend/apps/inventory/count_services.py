"""Serviços para contagem de stock.

Funções de caso de uso para gerenciar contagens.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.api import produto_por_sku
from apps.inventory.models import Location, StockCount, StockCountLine, StockLevel

__all__ = [
    "abrir_contagem",
    "adicionar_linha_contagem",
    "resumo_contagem",
    "fechar_contagem",
]


@transaction.atomic
def abrir_contagem(*, tenant_id: UUID, location_id: UUID, user_id: UUID | None = None) -> StockCount:
    """Abre uma nova contagem em uma localização."""
    # Verificar se localização existe
    location = Location.objects.filter(tenant_id=tenant_id, pk=location_id).first()
    if not location:
        raise ValidationError({"location": [_("Location not found.")]})

    contagem = StockCount.objects.create(
        tenant_id=tenant_id,
        location_id=location_id,
        status="open",
        created_by_id=user_id,
    )
    return contagem


@transaction.atomic
def adicionar_linha_contagem(
    *,
    tenant_id: UUID,
    stock_count_id: UUID,
    sku: str,
    quantity_counted: Decimal,
    zone: str | None = None,
) -> StockCountLine:
    """Adiciona uma linha à contagem usando SKU."""
    # Verificar se contagem existe e está aberta
    contagem = StockCount.objects.filter(
        tenant_id=tenant_id, pk=stock_count_id, status="open"
    ).first()
    if not contagem:
        raise ValidationError({"stock_count": [_("Count not found or already closed.")]})

    # Buscar produto por SKU via API
    produto = produto_por_sku(tenant_id=tenant_id, sku=sku)
    if not produto:
        raise ValidationError({"sku": [_("Product not found.")]})

    # Obter quantidade esperada do stock
    quantidade_esperada = StockLevel.objects.filter(
        tenant_id=tenant_id,
        location_id=contagem.location_id,
        product_id=produto.id,
    ).aggregate(qty=sum("quantity"))["qty"] or Decimal("0")

    # Criar linha
    linha = StockCountLine.objects.create(
        tenant_id=tenant_id,
        stock_count_id=stock_count_id,
        product_id=produto.id,
        quantity_expected=quantidade_esperada,
        quantity_counted=quantity_counted,
        zone=zone or "",
    )
    return linha


def resumo_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> dict:
    """Retorna resumo da contagem antes de fechar."""
    contagem = StockCount.objects.filter(
        tenant_id=tenant_id, pk=stock_count_id
    ).first()
    if not contagem:
        raise ValidationError({"stock_count": [_("Count not found.")]})

    linhas = StockCountLine.objects.filter(
        tenant_id=tenant_id, stock_count_id=stock_count_id
    )
    total = linhas.count()
    contadas = linhas.filter(quantity_counted__isnull=False).count()
    pendentes = total - contadas

    # Calcular variâncias
    total_var_qty = Decimal("0")
    total_var_value = Decimal("0")
    for linha in linhas:
        if linha.quantity_counted is not None:
            variancia_qty = linha.quantity_counted - linha.quantity_expected
            total_var_qty += variancia_qty
            # Obter custo unitário
            stock_level = StockLevel.objects.filter(
                tenant_id=tenant_id,
                product_id=linha.product_id,
                location_id=contagem.location_id,
            ).first()
            if stock_level:
                total_var_value += variancia_qty * stock_level.unit_cost

    can_close = pendentes == 0

    return {
        "total_lines": total,
        "lines_counted": contadas,
        "lines_pending": pendentes,
        "total_variance_qty": total_var_qty,
        "total_variance_value": total_var_value,
        "can_close": can_close,
    }


@transaction.atomic
def fechar_contagem(*, tenant_id: UUID, stock_count_id: UUID, user_id: UUID | None = None) -> StockCount:
    """Fecha a contagem e cria movimentos de ajuste."""
    contagem = StockCount.objects.filter(
        tenant_id=tenant_id, pk=stock_count_id, status="open"
    ).first()
    if not contagem:
        raise ValidationError({"stock_count": [_("Count not found or already closed.")]})

    # Validar que todas as linhas foram contadas
    resumo = resumo_contagem(tenant_id=tenant_id, stock_count_id=stock_count_id)
    if not resumo["can_close"]:
        raise ValidationError({
            "stock_count": [_("Cannot close: some lines are not yet counted.")]
        })

    # Criar movimentos de ajuste para variâncias
    from apps.inventory.services import record_movement
    linhas = StockCountLine.objects.filter(stock_count_id=stock_count_id)
    for linha in linhas:
        if linha.quantity_counted != linha.quantity_expected:
            variancia = linha.quantity_counted - linha.quantity_expected
            if variancia != 0:
                # Criar movimento de ajuste (ledger)
                record_movement(
                    tenant_id=tenant_id,
                    product_id=linha.product_id,
                    location_id=contagem.location_id,
                    lot_id=linha.lot_id,
                    movement_type="adjustment",
                    quantity=variancia,
                    reason="other",
                    reason_detail=f"Contagem #{stock_count_id}",
                    reference=str(stock_count_id),
                    created_by_id=user_id,
                )

    # Marcar contagem como fechada
    contagem.status = "closed"
    contagem.closed_at = timezone.now()
    contagem.closed_by_id = user_id
    contagem.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])

    return contagem
