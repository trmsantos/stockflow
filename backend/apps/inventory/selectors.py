"""Queries de leitura do `inventory`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import (
    Case,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)

from apps.inventory.models import Location, StockLevel

__all__ = [
    "listar_localizacoes",
    "localizacoes_do_ambito",
    "stock_summary",
    "stock_by_location",
    "stock_by_product",
]


def localizacoes_do_ambito(*, tenant_id: UUID) -> QuerySet[Location]:
    """Todas as localizações do estabelecimento, activas ou não. A base do `get_object()`."""
    return Location.objects.filter(tenant_id=tenant_id)


def listar_localizacoes(*, tenant_id: UUID) -> QuerySet[Location]:
    """A lista do `GET /locations`: por `position`, com o nome e o `id` a desempatar.

    Sem filtro de `active`: são poucas — duas lojas e uma cozinha — e uma
    localização desactivada continua a aparecer nas linhas antigas, logo o
    cliente precisa dela para a mostrar. A ordem estável é o que faz a
    paginação não repetir linhas.
    """
    return localizacoes_do_ambito(tenant_id=tenant_id).order_by("position", "name", "id")


def stock_summary(
    *, tenant_id: UUID, location_id: UUID | None = None
) -> QuerySet:
    """Saldo agregado por produto (com ou sem localização).

    Retorna: product_id, product_name, quantity (SUM), unit_cost, total_value.
    Filtra por: quantity != 0.
    """
    qs = (
        StockLevel.objects.filter(tenant_id=tenant_id)
        .exclude(quantity=Decimal("0"))
        .select_related("product", "lot")
        .values("product_id", "product__short_name")
        .annotate(
            product_name=F("product__short_name"),
            total_quantity=Sum("quantity"),
            avg_unit_cost=Case(
                When(quantity__gt=0, then=F("unit_cost")),
                default=Value(Decimal("0")),
                output_field=DecimalField(),
            ),
        )
    )

    if location_id:
        qs = qs.filter(location_id=location_id)

    return qs.order_by("product__short_name")


def stock_by_location(
    *, tenant_id: UUID, location_id: UUID, search_text: str = ""
) -> QuerySet:
    """Saldo por (product, lot) nessa localização, ordenado por FEFO.

    Retorna: product_id, product_name, lot_code, expires_at, quantity, unit_cost, total_value.
    FEFO: expires_at ASC NULLS LAST, received_at ASC.
    """
    qs = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            location_id=location_id,
        )
        .exclude(quantity=Decimal("0"))
        .select_related("product", "lot")
        .values(
            "product_id",
            "product__short_name",
            "lot__code",
            "lot__expires_at",
            "lot__received_at",
            "unit_cost",
        )
        .annotate(
            product_name=F("product__short_name"),
            lot_code=F("lot__code"),
            expires_at=F("lot__expires_at"),
            received_at=F("lot__received_at"),
        )
    )

    if search_text:
        qs = qs.filter(
            Q(product__short_name__icontains=search_text)
            | Q(lot__code__icontains=search_text)
        )

    return qs.order_by("lot__expires_at", "lot__received_at")


def stock_by_product(
    *, tenant_id: UUID, product_id: UUID, search_text: str = ""
) -> QuerySet:
    """Saldo por (location, lot) desse produto, ordenado por FEFO.

    Retorna: product_id, product_name, location_id, location_name, lot_code, expires_at,
    quantity, unit_cost, total_value.
    """
    qs = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
        )
        .exclude(quantity=Decimal("0"))
        .select_related("product", "location", "lot")
        .values(
            "product_id",
            "product__short_name",
            "location_id",
            "location__name",
            "lot__code",
            "lot__expires_at",
            "lot__received_at",
            "unit_cost",
        )
        .annotate(
            product_name=F("product__short_name"),
            location_name=F("location__name"),
            lot_code=F("lot__code"),
            expires_at=F("lot__expires_at"),
            received_at=F("lot__received_at"),
        )
    )

    if search_text:
        qs = qs.filter(
            Q(location__name__icontains=search_text)
            | Q(lot__code__icontains=search_text)
        )

    return qs.order_by("lot__expires_at", "lot__received_at")
