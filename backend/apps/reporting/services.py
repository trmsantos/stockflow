"""Serviços de relatórios e painel.

Agregações de dados financeiros e operacionais.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from apps.catalog.api import produtos_por_id
from apps.inventory.api import MovimentoResumo

__all__ = [
    "monthly_report",
    "series_report",
    "projection_report",
]


def monthly_report(
    *,
    tenant_id: UUID,
    month: str,  # YYYY-MM
) -> dict:
    """Relatório mensal: revenue, COGS, payroll, items por dia."""
    from apps.inventory.api import movimentos_por_periodo

    try:
        year, month_num = map(int, month.split("-"))
    except (ValueError, IndexError):
        return {"error": "Invalid month format (use YYYY-MM)"}

    # Filtrar movimentos do mês via API
    movements = movimentos_por_periodo(tenant_id=tenant_id, year=year, month=month_num)

    # Receita = production_in (entrada) com custo
    revenue = Decimal("0")
    for m in movements:
        if m.movement_type == "production_in":
            revenue += m.quantity * m.unit_cost

    # COGS = production_out (saída) com custo
    cogs = Decimal("0")
    for m in movements:
        if m.movement_type == "production_out":
            cogs += m.quantity * m.unit_cost

    # Payroll: fixo (não implementado - usar 0)
    payroll = Decimal("0")

    # Items por dia (agregar manualmente)
    from collections import defaultdict
    from datetime import date

    daily_data = defaultdict(lambda: {"revenue": Decimal("0"), "cogs": Decimal("0"), "count": 0})
    for m in movements:
        day = m.occurred_at.date()
        if m.movement_type == "production_in":
            daily_data[day]["revenue"] += m.quantity * m.unit_cost
        elif m.movement_type == "production_out":
            daily_data[day]["cogs"] += m.quantity * m.unit_cost
        daily_data[day]["count"] += 1

    daily_items = sorted([
        {
            "date": str(day),
            "revenue": data["revenue"],
            "cogs": data["cogs"],
            "movement_count": data["count"],
        }
        for day, data in daily_data.items()
    ], key=lambda x: x["date"])

    return {
        "period": f"{year}-{month_num:02d}",
        "revenue": revenue,
        "cogs": cogs,
        "payroll": payroll,
        "gross_profit": revenue - cogs,
        "items": daily_items,
    }


def series_report(
    *,
    tenant_id: UUID,
    granularity: str,  # day, week, month
    month: str,  # YYYY-MM
) -> dict:
    """Série temporal de receita vs COGS."""
    from collections import defaultdict

    from apps.inventory.api import movimentos_por_periodo

    try:
        year, month_num = map(int, month.split("-"))
    except (ValueError, IndexError):
        return {"error": "Invalid month format (use YYYY-MM)"}

    if granularity not in ["day", "week", "month"]:
        return {"error": "Invalid granularity (use day, week, or month)"}

    # Filtrar movimentos do mês via API
    movements = movimentos_por_periodo(tenant_id=tenant_id, year=year, month=month_num)

    # Agregar por período (manualmente, sem ORM)
    series_dict = defaultdict(lambda: {"revenue": Decimal("0"), "cogs": Decimal("0")})

    for m in movements:
        if granularity == "day":
            period = m.occurred_at.date()
        elif granularity == "week":
            # Retornar a data de início da semana (segunda-feira)
            period = m.occurred_at.date() - __import__('datetime').timedelta(days=m.occurred_at.weekday())
        else:  # month
            # Retornar o primeiro dia do mês
            period = m.occurred_at.date().replace(day=1)

        if m.movement_type == "production_in":
            series_dict[period]["revenue"] += m.quantity * m.unit_cost
        elif m.movement_type == "production_out":
            series_dict[period]["cogs"] += m.quantity * m.unit_cost

    # Ordenar e construir resposta
    series = sorted([
        {
            "x": str(period),
            "revenue": data["revenue"],
            "cogs": data["cogs"],
            "gross_profit": data["revenue"] - data["cogs"],
        }
        for period, data in series_dict.items()
    ], key=lambda x: x["x"])

    return {
        "granularity": granularity,
        "period": f"{year}-{month_num:02d}",
        "series": series,
    }


def projection_report(*, tenant_id: UUID) -> dict:
    """Projeção de stock vs movimento real."""
    from apps.catalog.api import produtos_por_id
    from apps.inventory.api import movimentos_por_produto
    from apps.inventory.models import StockLevel

    # Obter stock levels esperados vs movimentos reais por SKU
    # Primeiro, obter todos os IDs de produtos ativos
    products_qs = __import__('apps.catalog.models', fromlist=['Product']).Product.objects.filter(
        tenant_id=tenant_id, is_active=True
    )
    product_ids = [p.id for p in products_qs]

    if not product_ids:
        return {"items": []}

    # Obter produtos em lote via API
    produtos_dict = produtos_por_id(tenant_id=tenant_id, ids=product_ids)

    items = []
    for product_id, produto in produtos_dict.items():
        # Stock atual (projetado)
        stock_levels = StockLevel.objects.filter(
            tenant_id=tenant_id, product_id=product_id
        )
        projected_qty = stock_levels.aggregate(
            total=Sum("quantity", output_field=DecimalField())
        )["total"] or Decimal("0")

        # Movimentos totais (atual) - usar API
        movimentos_in = movimentos_por_produto(
            tenant_id=tenant_id,
            product_id=product_id,
            movement_types=["receipt", "production_in", "transfer_in"],
        )
        total_in = sum(m.quantity for m in movimentos_in)

        movimentos_out = movimentos_por_produto(
            tenant_id=tenant_id,
            product_id=product_id,
            movement_types=["consumption", "waste", "adjustment", "transfer_out", "production_out"],
        )
        total_out = sum(m.quantity for m in movimentos_out)

        actual_qty = total_in + total_out  # total_out é negativo

        variance = projected_qty - actual_qty

        items.append({
            "sku": produto.sku,
            "product_name": produto.short_name,
            "projected": projected_qty,
            "actual": actual_qty,
            "variance": variance,
        })

    return {"items": sorted(items, key=lambda x: abs(x["variance"]), reverse=True)}
