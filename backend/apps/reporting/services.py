"""Serviços de relatórios e painel.

Agregações de dados financeiros e operacionais.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from apps.catalog.models import Product
from apps.inventory.models import StockMovement

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
    try:
        year, month_num = map(int, month.split("-"))
    except (ValueError, IndexError):
        return {"error": "Invalid month format (use YYYY-MM)"}

    # Filtrar movimentos do mês
    movements = StockMovement.objects.filter(
        tenant_id=tenant_id,
        occurred_at__year=year,
        occurred_at__month=month_num,
    )

    # Receita = production_in (entrada) com custo
    revenue_movements = movements.filter(movement_type="production_in")
    revenue = revenue_movements.aggregate(
        total=Sum(
            F("quantity") * F("unit_cost"),
            output_field=DecimalField(),
        )
    )["total"] or Decimal("0")

    # COGS = production_out (saída) com custo
    cogs_movements = movements.filter(movement_type="production_out")
    cogs = cogs_movements.aggregate(
        total=Sum(
            F("quantity") * F("unit_cost"),
            output_field=DecimalField(),
        )
    )["total"] or Decimal("0")

    # Payroll: fixo (não implementado - usar 0)
    payroll = Decimal("0")

    # Items por dia
    daily_items = (
        movements.annotate(date=TruncDate("occurred_at"))
        .values("date")
        .annotate(
            daily_revenue=Sum(
                F("quantity") * F("unit_cost"),
                filter=Q(movement_type="production_in"),
                output_field=DecimalField(),
            ),
            daily_cogs=Sum(
                F("quantity") * F("unit_cost"),
                filter=Q(movement_type="production_out"),
                output_field=DecimalField(),
            ),
            movement_count=Count("id"),
        )
        .order_by("date")
    )

    return {
        "period": f"{year}-{month_num:02d}",
        "revenue": revenue,
        "cogs": cogs,
        "payroll": payroll,
        "gross_profit": revenue - cogs,
        "items": [
            {
                "date": str(item["date"]),
                "revenue": item["daily_revenue"] or Decimal("0"),
                "cogs": item["daily_cogs"] or Decimal("0"),
                "movement_count": item["movement_count"],
            }
            for item in daily_items
        ],
    }


def series_report(
    *,
    tenant_id: UUID,
    granularity: str,  # day, week, month
    month: str,  # YYYY-MM
) -> dict:
    """Série temporal de receita vs COGS."""
    try:
        year, month_num = map(int, month.split("-"))
    except (ValueError, IndexError):
        return {"error": "Invalid month format (use YYYY-MM)"}

    if granularity not in ["day", "week", "month"]:
        return {"error": "Invalid granularity (use day, week, or month)"}

    # Selecionar função de truncamento
    trunc_func = {
        "day": TruncDate,
        "week": TruncWeek,
        "month": TruncMonth,
    }[granularity]

    # Filtrar movimentos do mês
    movements = StockMovement.objects.filter(
        tenant_id=tenant_id,
        occurred_at__year=year,
        occurred_at__month=month_num,
    )

    # Agregar por período
    series_data = (
        movements.annotate(period=trunc_func("occurred_at"))
        .values("period")
        .annotate(
            revenue=Sum(
                F("quantity") * F("unit_cost"),
                filter=Q(movement_type="production_in"),
                output_field=DecimalField(),
            ),
            cogs=Sum(
                F("quantity") * F("unit_cost"),
                filter=Q(movement_type="production_out"),
                output_field=DecimalField(),
            ),
        )
        .order_by("period")
    )

    return {
        "granularity": granularity,
        "period": f"{year}-{month_num:02d}",
        "series": [
            {
                "x": str(item["period"]),
                "revenue": item["revenue"] or Decimal("0"),
                "cogs": item["cogs"] or Decimal("0"),
                "gross_profit": (item["revenue"] or Decimal("0")) - (item["cogs"] or Decimal("0")),
            }
            for item in series_data
        ],
    }


def projection_report(*, tenant_id: UUID) -> dict:
    """Projeção de stock vs movimento real."""
    # Obter stock levels esperados vs movimentos reais por SKU
    products = Product.objects.filter(tenant_id=tenant_id, is_active=True)

    items = []
    for produto in products:
        from apps.inventory.models import StockLevel

        # Stock atual (projetado)
        stock_levels = StockLevel.objects.filter(
            tenant_id=tenant_id, product_id=produto.pk
        )
        projected_qty = stock_levels.aggregate(
            total=Sum("quantity", output_field=DecimalField())
        )["total"] or Decimal("0")

        # Movimentos totais (atual)
        total_in = (
            StockMovement.objects.filter(
                tenant_id=tenant_id,
                product_id=produto.pk,
                movement_type__in=["receipt", "production_in", "transfer_in"],
            ).aggregate(total=Sum("quantity", output_field=DecimalField()))["total"]
            or Decimal("0")
        )
        total_out = (
            StockMovement.objects.filter(
                tenant_id=tenant_id,
                product_id=produto.pk,
                movement_type__in=["consumption", "waste", "adjustment", "transfer_out", "production_out"],
            ).aggregate(total=Sum("quantity", output_field=DecimalField()))["total"]
            or Decimal("0")
        )
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
