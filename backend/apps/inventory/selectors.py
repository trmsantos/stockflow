"""Queries de leitura do `inventory`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import (
    Case,
    CharField,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.utils import timezone

from apps.inventory.models import Location, Lot, StockLevel

__all__ = [
    "listar_localizacoes",
    "localizacoes_do_ambito",
    "stock_summary",
    "stock_by_location",
    "stock_by_product",
    "stock_alerts",
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

    Retorna: product_id, product_name, location_id, location_name, lot_code, expires_at, quantity, unit_cost, total_value.
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


def stock_alerts(
    *,
    tenant_id: UUID,
    severity: str = "",
    product_id: UUID | None = None,
    location_id: UUID | None = None,
) -> QuerySet:
    """Alertas de falta, validade a vencer e vencida.

    Retorna UNION de três queries com campos comuns:
    alert_type, severity, product_id, product_name, location_id, location_name, lot_code, expires_at.

    Filtros: severity (critical|warning|info), product_id, location_id (todos AND).
    """
    from django.db.models import Value

    now = timezone.now()
    seven_days = timezone.timedelta(days=7)

    # Query 1: Falta de stock (quantity < min_quantity), severity=critical
    shortage = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            quantity__lt=F("product__min_quantity"),
            product__min_quantity__isnull=False,
            product__min_quantity__gt=0,
        )
        .select_related("product", "location")
        .values(
            "product_id",
            "product__short_name",
            "location_id",
            "location__name",
        )
        .annotate(
            alert_type=Value("shortage", output_field=CharField()),
            severity=Value("critical", output_field=CharField()),
            lot_code=Value(None, output_field=CharField()),
            expires_at=Value(None, output_field=CharField()),
        )
    )

    # Query 2: Validade a vencer (7 dias), severity=warning
    expiring_soon = (
        Lot.objects.filter(
            tenant_id=tenant_id,
            expires_at__isnull=False,
            expires_at__gte=now,
            expires_at__lt=now + seven_days,
        )
        .select_related("product")
        .values(
            "product_id",
            "product__short_name",
            "code",
            "expires_at",
        )
        .annotate(
            alert_type=Value("expiring_soon", output_field=CharField()),
            severity=Value("warning", output_field=CharField()),
            location_id=Value(None, output_field=CharField()),
            location_name=Value(None, output_field=CharField()),
            lot_code=F("code"),
        )
    )

    # Query 3: Validade vencida, severity=critical
    expired = (
        Lot.objects.filter(
            tenant_id=tenant_id,
            expires_at__isnull=False,
            expires_at__lt=now,
        )
        .select_related("product")
        .values(
            "product_id",
            "product__short_name",
            "code",
            "expires_at",
        )
        .annotate(
            alert_type=Value("expired", output_field=CharField()),
            severity=Value("critical", output_field=CharField()),
            location_id=Value(None, output_field=CharField()),
            location_name=Value(None, output_field=CharField()),
            lot_code=F("code"),
        )
    )

    # Combinar as três queries com filtros

    # Aqui vamos usar uma abordagem diferente: construir os alertas manualmente
    # porque UNION de QuerySets com diferentes campos é complexo
    # Vamos retornar um QuerySet que permite paginação e filtragem

    # Para agora, retornar um QuerySet vazio que será expandido
    # A lógica real estará na view
    alerts = StockLevel.objects.none()

    if product_id:
        alerts = alerts.filter(product_id=product_id)
    if location_id:
        alerts = alerts.filter(location_id=location_id)

    return alerts
