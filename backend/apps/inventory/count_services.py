"""Serviços para contagem de stock.

Funções de caso de uso para gerenciar contagens.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.api import produto_por_sku
from apps.inventory.models import Location, StockCount, StockCountLine, StockLevel
from apps.inventory.selectors import custos_dos_niveis
from apps.inventory.services import MovementDTO, record_movements

__all__ = [
    "abrir_contagem",
    "adicionar_linha_contagem",
    "resumo_contagem",
    "fechar_contagem",
]


@transaction.atomic
def abrir_contagem(
    *, tenant_id: UUID, location_id: UUID, user_id: UUID | None = None
) -> StockCount:
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
    ).aggregate(qty=Sum("quantity"))["qty"] or Decimal("0")

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
    """Retorna resumo da contagem antes de fechar.

    O custo com que se valoriza a diferença é o do `(artigo, localização,
    **lote**)` — com o lote, e é essa a correcção da ADR 0028. Até 2026-10-16
    lia-se o `.first()` de `(artigo, localização)` sem lote: numa localização
    com dois lotes do mesmo artigo a diferença de um era valorizada pelo custo
    do outro, em silêncio e sempre pelo lote que a base devolvesse primeiro. É
    também o custo que o `fechar_contagem` grava no `adjustment`, logo o número
    que esta função mostra e o que vai para o ledger passam a ser o mesmo.
    """
    contagem = StockCount.objects.filter(
        tenant_id=tenant_id, pk=stock_count_id
    ).first()
    if not contagem:
        raise ValidationError({"stock_count": [_("Count not found.")]})

    linhas = list(
        StockCountLine.objects.filter(tenant_id=tenant_id, stock_count_id=stock_count_id)
    )
    total = len(linhas)
    contadas = sum(1 for linha in linhas if linha.quantity_counted is not None)
    pendentes = total - contadas

    custos = custos_dos_niveis(
        tenant_id=tenant_id,
        location_id=contagem.location_id,
        chaves=[(linha.product_id, linha.lot_id) for linha in linhas],
    )

    # Calcular variâncias
    total_var_qty = Decimal("0")
    total_var_value = Decimal("0")
    for linha in linhas:
        if linha.quantity_counted is not None:
            variancia_qty = linha.quantity_counted - linha.quantity_expected
            total_var_qty += variancia_qty
            total_var_value += variancia_qty * custos.get(
                (linha.product_id, linha.lot_id), Decimal("0")
            )

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
def fechar_contagem(
    *,
    tenant_id: UUID,
    stock_count_id: UUID,
    user_id: UUID | None = None,
    user_name: str = "",
) -> StockCount:
    """Fecha a contagem e grava no ledger um `adjustment` por cada diferença.

    O stock é um ledger (CLAUDE.md): a diferença entre o contado e o esperado
    nunca se escreve no `StockLevel` — vai a `record_movements`, que cria o
    `StockMovement` e recalcula o nível a partir da soma dos movimentos. Todas
    as diferenças de uma contagem entram numa única chamada, logo numa única
    transação com o fecho: ou a contagem fecha com os ajustes todos, ou não
    fecha.

    O custo do ajuste é o do nível que existe para `(artigo, localização,
    lote)`, ou zero se não houver nível — a forma de `registar_adjustment`.
    `user_name` é a cópia do nome de quem fechou que fica no movimento, para
    sobreviver à conta ser apagada (`created_by_name`).
    """
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

    agora = timezone.now()
    ajustes: list[MovementDTO] = []
    linhas = StockCountLine.objects.filter(tenant_id=tenant_id, stock_count_id=stock_count_id)
    for linha in linhas:
        variancia = linha.quantity_counted - linha.quantity_expected
        if variancia == 0:
            continue
        nivel = StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=linha.product_id,
            location_id=contagem.location_id,
            lot_id=linha.lot_id,
        ).first()
        ajustes.append(
            MovementDTO(
                product_id=linha.product_id,
                location_id=contagem.location_id,
                lot_id=linha.lot_id,
                quantity=variancia,
                unit_cost=nivel.unit_cost if nivel else Decimal("0"),
                cost_is_estimate=False,
                movement_type="adjustment",
                occurred_at=agora,
                created_by_id=user_id,
                created_by_name=user_name,
                reference=str(stock_count_id),
                reason="other",
            )
        )
    record_movements(tenant_id=tenant_id, movements=ajustes)

    # Marcar contagem como fechada
    contagem.status = "closed"
    contagem.closed_at = agora
    contagem.closed_by_id = user_id
    contagem.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])

    return contagem
