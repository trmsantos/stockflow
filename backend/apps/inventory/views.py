"""ViewSets para o inventário (ADR 0021, fatia 2; ADR 0022; ADR 0024, fatia 4).

Endpoints:
- GET /api/v1/locations (por position)
- POST /api/v1/locations
- PATCH /api/v1/locations/{id}
- GET /api/v1/stock/summary
- GET /api/v1/stock/by-location
- GET /api/v1/stock/by-product
- GET /api/v1/stock/alerts
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import F, Max, QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import PertenceAoTenant
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.inventory.selectors import (
    listar_localizacoes,
    localizacoes_do_ambito,
    stock_by_location,
    stock_by_product,
    stock_summary,
)
from apps.inventory.serializers import (
    AdjustmentSerializer,
    AlertSerializer,
    LocalizacaoInSerializer,
    LocalizacaoOutSerializer,
    LocalizacaoPatchInSerializer,
    StockDetailSerializer,
    StockMovementResponseSerializer,
    StockSummarySerializer,
    TransferSerializer,
    WasteSerializer,
)
from apps.inventory.services import (
    registar_adjustment,
    registar_transfer,
    registar_waste,
)

__all__ = ["LocalizacaoViewSet", "StockPanelViewSet", "StockMovementViewSet"]

logger = logging.getLogger(__name__)

# Throttle scope (reutiliza do catalog)
AMBITO_THROTTLE_CATALOGO = "catalogo"


@extend_schema_view(
    list=extend_schema(
        operation_id="localizacoes_listar",
        summary="Localizações do estabelecimento (por posição)",
    ),
    create=extend_schema(
        operation_id="localizacoes_criar",
        summary="Criar uma localização",
    ),
    partial_update=extend_schema(
        operation_id="localizacoes_atualizar",
        summary="Atualizar localização",
    ),
)
class LocalizacaoViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Localizações do inventário."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    queryset = Location.objects.none()
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[Location]:
        """Localizações do estabelecimento ativo."""
        return localizacoes_do_ambito(tenant_id=self.request.tenant.id)

    def get_serializer_class(self):
        """Escolher serializer por acção."""
        if self.action == "create":
            return LocalizacaoInSerializer
        elif self.action == "partial_update":
            return LocalizacaoPatchInSerializer
        return LocalizacaoOutSerializer

    def list(self, request: Request, *args, **kwargs) -> Response:
        """Lista paginada de localizações, ordenadas por posição."""
        queryset = listar_localizacoes(tenant_id=request.tenant.id)
        page = self.paginate_queryset(queryset)
        serializer = LocalizacaoOutSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Criar uma localização."""
        serializer = LocalizacaoInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        position = serializer.validated_data.get("position")
        if position is None:
            max_pos = (
                Location.objects.filter(tenant_id=request.tenant.id).aggregate(
                    max_pos=Max("position")
                )["max_pos"]
                or 0
            )
            position = max_pos + 1

        localizacao = Location.objects.create(
            tenant_id=request.tenant.id,
            name=serializer.validated_data["name"],
            position=position,
        )

        out_ser = LocalizacaoOutSerializer(localizacao)
        return Response(out_ser.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """PATCH uma localização."""
        localizacao = self.get_object()
        serializer = LocalizacaoPatchInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for field, value in serializer.validated_data.items():
            setattr(localizacao, field, value)
        localizacao.save()

        out_ser = LocalizacaoOutSerializer(localizacao)
        return Response(out_ser.data, status=status.HTTP_200_OK)


@extend_schema_view(
    summary=extend_schema(
        operation_id="stock_summary",
        summary="Resumo de stock agregado por produto",
    ),
    by_location=extend_schema(
        operation_id="stock_by_location",
        summary="Stock por (product, lot) em localização",
    ),
    by_product=extend_schema(
        operation_id="stock_by_product",
        summary="Stock por (location, lot) desse produto",
    ),
    alerts=extend_schema(
        operation_id="stock_alerts",
        summary="Alertas de falta, validade a vencer e vencida",
    ),
)
class StockPanelViewSet(viewsets.ViewSet):
    """Painel de stock: queries read-only ao ledger (ADR 0024)."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO
    page_size = 50

    def get_throttles(self) -> list[BaseThrottle]:
        """Sem throttle extra em leitura."""
        return super().get_throttles()

    @extend_schema(responses={200: StockSummarySerializer(many=True)})
    @action(detail=False, methods=["GET"], url_path="summary")
    def summary(self, request: Request) -> Response:
        """Resumo de stock agregado por produto."""
        location_id = request.query_params.get("location_id")

        if location_id:
            try:
                location_id = UUID(location_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid location_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        queryset = stock_summary(tenant_id=request.tenant.id, location_id=location_id)
        items = list(queryset)
        serializer = StockSummarySerializer(items, many=True)

        return Response(
            {
                "items": serializer.data,
                "total": len(items),
                "page": 1,
                "page_size": self.page_size,
            }
        )

    @extend_schema(responses={200: StockDetailSerializer(many=True)})
    @action(detail=False, methods=["GET"], url_path="by-location")
    def by_location(self, request: Request) -> Response:
        """Stock por (product, lot) nessa localização."""
        location_id = request.query_params.get("location_id")
        search_text = request.query_params.get("search_text", "")

        if not location_id:
            return Response(
                {"detail": "location_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            location_id = UUID(location_id)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid location_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = stock_by_location(
            tenant_id=request.tenant.id,
            location_id=location_id,
            search_text=search_text,
        )
        items = list(queryset)
        serializer = StockDetailSerializer(items, many=True)

        return Response(
            {
                "items": serializer.data,
                "total": len(items),
                "page": 1,
                "page_size": self.page_size,
            }
        )

    @extend_schema(responses={200: StockDetailSerializer(many=True)})
    @action(detail=False, methods=["GET"], url_path="by-product")
    def by_product(self, request: Request) -> Response:
        """Stock por (location, lot) desse produto."""
        product_id = request.query_params.get("product_id")
        search_text = request.query_params.get("search_text", "")

        if not product_id:
            return Response(
                {"detail": "product_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            import uuid
            product_id = uuid.UUID(product_id)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid product_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = stock_by_product(
            tenant_id=request.tenant.id,
            product_id=product_id,
            search_text=search_text,
        )
        items = list(queryset)
        serializer = StockDetailSerializer(items, many=True)

        return Response(
            {
                "items": serializer.data,
                "total": len(items),
                "page": 1,
                "page_size": self.page_size,
            }
        )

    @extend_schema(responses={200: AlertSerializer(many=True)})
    @action(detail=False, methods=["GET"], url_path="alerts")
    def alerts(self, request: Request) -> Response:
        """Alertas de falta, validade a vencer e vencida."""
        severity = request.query_params.get("severity", "")
        product_id = request.query_params.get("product_id")
        location_id = request.query_params.get("location_id")

        # Parse UUIDs
        if product_id:
            try:
                product_id = UUID(product_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid product_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if location_id:
            try:
                location_id = UUID(location_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid location_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Construir alertas
        alerts_data = self._build_alerts(
            request.tenant.id,
            severity=severity,
            product_id=product_id,
            location_id=location_id,
        )

        serializer = AlertSerializer(alerts_data, many=True)

        return Response(
            {
                "items": serializer.data,
                "total": len(alerts_data),
                "page": 1,
                "page_size": self.page_size,
            }
        )

    def _build_alerts(
        self,
        tenant_id,
        severity: str = "",
        product_id=None,
        location_id=None,
    ) -> list:
        """Construir alertas de falta, validade a vencer e vencida."""
        now = timezone.now()
        seven_days = timezone.timedelta(days=7)
        alerts = []

        # Query 1: Falta de stock
        shortage_qs = (
            StockLevel.objects.filter(
                tenant_id=tenant_id,
                quantity__gt=Decimal("0"),
                product__min_quantity__isnull=False,
                product__min_quantity__gt=0,
            )
            .exclude(quantity__gte=F("product__min_quantity"))
            .select_related("product", "location")
        )

        if product_id:
            shortage_qs = shortage_qs.filter(product_id=product_id)
        if location_id:
            shortage_qs = shortage_qs.filter(location_id=location_id)

        for level in shortage_qs:
            if not severity or severity == "critical":
                alerts.append(
                    {
                        "alert_type": "shortage",
                        "severity": "critical",
                        "product_id": level.product_id,
                        "product_name": level.product.short_name,
                        "location_id": level.location_id,
                        "location_name": level.location.name,
                        "lot_code": None,
                        "expires_at": None,
                    }
                )

        # Query 2: Validade a vencer (7 dias)
        expiring_qs = (
            Lot.objects.filter(
                tenant_id=tenant_id,
                expires_at__isnull=False,
                expires_at__gte=now,
                expires_at__lt=now + seven_days,
            )
            .select_related("product")
        )

        if product_id:
            expiring_qs = expiring_qs.filter(product_id=product_id)

        for lot in expiring_qs:
            if not severity or severity == "warning":
                alerts.append(
                    {
                        "alert_type": "expiring_soon",
                        "severity": "warning",
                        "product_id": lot.product_id,
                        "product_name": lot.product.short_name,
                        "location_id": None,
                        "location_name": None,
                        "lot_code": lot.code,
                        "expires_at": lot.expires_at,
                    }
                )

        # Query 3: Validade vencida
        expired_qs = (
            Lot.objects.filter(
                tenant_id=tenant_id,
                expires_at__isnull=False,
                expires_at__lt=now,
            )
            .select_related("product")
        )

        if product_id:
            expired_qs = expired_qs.filter(product_id=product_id)

        for lot in expired_qs:
            if not severity or severity == "critical":
                alerts.append(
                    {
                        "alert_type": "expired",
                        "severity": "critical",
                        "product_id": lot.product_id,
                        "product_name": lot.product.short_name,
                        "location_id": None,
                        "location_name": None,
                        "lot_code": lot.code,
                        "expires_at": lot.expires_at,
                    }
                )

        return alerts


@extend_schema_view(
    waste=extend_schema(
        operation_id="stock_movements_waste",
        summary="Registar desperdício",
        request=WasteSerializer,
        responses={201: StockMovementResponseSerializer},
    ),
    adjustment=extend_schema(
        operation_id="stock_movements_adjustment",
        summary="Registar ajuste de stock",
        request=AdjustmentSerializer,
        responses={201: StockMovementResponseSerializer},
    ),
    transfer=extend_schema(
        operation_id="stock_movements_transfer",
        summary="Transferir stock entre localizações",
        request=TransferSerializer,
        responses={201: StockMovementResponseSerializer},
    ),
)
class StockMovementViewSet(viewsets.ViewSet):
    """Endpoints para criar movimentos de stock manuais (desperdício, ajuste, transferência)."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    @action(detail=False, methods=["POST"], url_path="waste")
    def waste(self, request: Request) -> Response:
        """Registar um desperdício (POST /stock/movements/waste)."""
        serializer = WasteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            movement_id = registar_waste(
                tenant_id=request.tenant.id,
                product_id=serializer.validated_data["product_id"],
                location_id=serializer.validated_data["location_id"],
                quantity=serializer.validated_data["quantity"],
                lot_id=serializer.validated_data.get("lot_id"),
                reason=serializer.validated_data["reason"],
                reason_detail=serializer.validated_data.get("reason_detail"),
                user=request.user,
            )

            # Recuperar movimento criado
            movimento = StockMovement.objects.get(pk=movement_id)
            response_data = {
                "movement_id": movimento.id,
                "product_name": movimento.product.short_name,
                "location_name": movimento.location.name,
                "lot_code": movimento.lot.code if movimento.lot else None,
                "quantity": abs(movimento.quantity),
                "unit_cost": movimento.unit_cost,
                "created_at": movimento.created_at,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            logger.warning(
                "waste_rejected",
                extra={"outcome": "validation_error", "errors": e.detail},
            )
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                "waste_failed",
                extra={"outcome": "error", "error": str(e)},
                exc_info=True,
            )
            return Response(
                {"detail": "Erro ao registar desperdício"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["POST"], url_path="adjustment")
    def adjustment(self, request: Request) -> Response:
        """Registar um ajuste de stock (POST /stock/movements/adjustment)."""
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            movement_id = registar_adjustment(
                tenant_id=request.tenant.id,
                product_id=serializer.validated_data["product_id"],
                location_id=serializer.validated_data["location_id"],
                quantity=serializer.validated_data["quantity"],
                lot_id=serializer.validated_data.get("lot_id"),
                reason=serializer.validated_data["reason"],
                reason_detail=serializer.validated_data.get("reason_detail"),
                user=request.user,
            )

            # Recuperar movimento criado
            movimento = StockMovement.objects.get(pk=movement_id)
            response_data = {
                "movement_id": movimento.id,
                "product_name": movimento.product.short_name,
                "location_name": movimento.location.name,
                "lot_code": movimento.lot.code if movimento.lot else None,
                "quantity": abs(movimento.quantity),
                "unit_cost": movimento.unit_cost,
                "created_at": movimento.created_at,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            logger.warning(
                "adjustment_rejected",
                extra={"outcome": "validation_error", "errors": e.detail},
            )
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                "adjustment_failed",
                extra={"outcome": "error", "error": str(e)},
                exc_info=True,
            )
            return Response(
                {"detail": "Erro ao registar ajuste"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["POST"], url_path="transfer")
    def transfer(self, request: Request) -> Response:
        """Transferir stock entre localizações (POST /stock/movements/transfer)."""
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            out_id, in_id = registar_transfer(
                tenant_id=request.tenant.id,
                product_id=serializer.validated_data["product_id"],
                from_location_id=serializer.validated_data["from_location_id"],
                to_location_id=serializer.validated_data["to_location_id"],
                quantity=serializer.validated_data["quantity"],
                lot_id=serializer.validated_data.get("lot_id"),
                user=request.user,
            )

            # Recuperar movimentos criados
            out_movimento = StockMovement.objects.get(pk=out_id)
            in_movimento = StockMovement.objects.get(pk=in_id)

            response_data = {
                "transfer_id": out_movimento.transfer_id,
                "movements": [
                    {
                        "movement_id": out_movimento.id,
                        "type": "transfer_out",
                        "product_name": out_movimento.product.short_name,
                        "location_name": out_movimento.location.name,
                        "lot_code": out_movimento.lot.code if out_movimento.lot else None,
                        "quantity": abs(out_movimento.quantity),
                        "unit_cost": out_movimento.unit_cost,
                    },
                    {
                        "movement_id": in_movimento.id,
                        "type": "transfer_in",
                        "product_name": in_movimento.product.short_name,
                        "location_name": in_movimento.location.name,
                        "lot_code": in_movimento.lot.code if in_movimento.lot else None,
                        "quantity": in_movimento.quantity,
                        "unit_cost": in_movimento.unit_cost,
                    },
                ],
                "created_at": out_movimento.created_at,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            logger.warning(
                "transfer_rejected",
                extra={"outcome": "validation_error", "errors": e.detail},
            )
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                "transfer_failed",
                extra={"outcome": "error", "error": str(e)},
                exc_info=True,
            )
            return Response(
                {"detail": "Erro ao registar transferência"},
                status=status.HTTP_400_BAD_REQUEST,
            )
