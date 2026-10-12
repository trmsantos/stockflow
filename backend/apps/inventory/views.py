"""ViewSets para o inventário (ADR 0021, fatia 2; ADR 0022).

Nesta fatia: localizações apenas.

Endpoints:
- GET /api/v1/locations (por position)
- POST /api/v1/locations
- PATCH /api/v1/locations/{id}
"""

from __future__ import annotations

from django.db.models import Max, QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import PertenceAoTenant
from apps.inventory.models import Location
from apps.inventory.selectors import listar_localizacoes, localizacoes_do_ambito
from apps.inventory.serializers import (
    LocalizacaoInSerializer,
    LocalizacaoOutSerializer,
    LocalizacaoPatchInSerializer,
)

__all__ = ["LocalizacaoViewSet"]

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
