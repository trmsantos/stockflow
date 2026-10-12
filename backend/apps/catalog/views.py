"""ViewSets para o catálogo (ADR 0021, fatia 2; ADR 0022).

Endpoints:
- GET  /api/v1/products?q=&active=
- POST /api/v1/products
- PATCH /api/v1/products/{id}
- GET /api/v1/products/{id}/packagings
- POST /api/v1/products/{id}/packagings
- GET /api/v1/suppliers?q=
- POST /api/v1/suppliers
- PATCH /api/v1/suppliers/{id}
- GET /api/v1/suppliers/{id}/product-codes

Sem GET de recurso individual, sem DELETE, sem PATCH de embalagem.
"""

from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import PertenceAoTenant
from apps.catalog.models import Product, ProductPackaging, Supplier
from apps.catalog.selectors import (
    codigos_do_fornecedor,
    embalagens_do_produto,
    fornecedores_do_ambito,
    listar_fornecedores,
    listar_produtos,
    produtos_do_ambito,
)
from apps.catalog.serializers import (
    CodigoDeFornecedorOutSerializer,
    EmbalagemInSerializer,
    EmbalagemOutSerializer,
    FornecedorInSerializer,
    FornecedorOutSerializer,
    FornecedorPatchInSerializer,
    ProdutoInSerializer,
    ProdutoOutSerializer,
    ProdutoPatchInSerializer,
)

__all__ = ["ProdutoViewSet", "FornecedorViewSet"]

# Throttle scope
AMBITO_THROTTLE_CATALOGO = "catalogo"


@extend_schema_view(
    list=extend_schema(
        operation_id="produtos_listar",
        summary="Artigos do estabelecimento",
        parameters=[
            OpenApiParameter(
                name="q",
                description="Procurar por nome curto",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="active",
                description="Filtrar por estado (true/false/null)",
                required=False,
                type=bool,
            ),
        ],
    ),
    create=extend_schema(
        operation_id="produtos_criar",
        summary="Criar um artigo com embalagem opcional",
    ),
    partial_update=extend_schema(
        operation_id="produtos_atualizar",
        summary="Atualizar artigo (sem base_unit, sem min_quantity)",
    ),
)
class ProdutoViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Artigos do catálogo."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    queryset = Product.objects.none()
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[Product]:
        """Artigos do estabelecimento ativo."""
        return produtos_do_ambito(tenant_id=self.request.tenant.id)

    def get_serializer_class(self):
        """Escolher serializer por acção."""
        if self.action == "create":
            return ProdutoInSerializer
        elif self.action == "partial_update":
            return ProdutoPatchInSerializer
        return ProdutoOutSerializer

    def list(self, request: Request, *args, **kwargs) -> Response:
        """Lista paginada de artigos."""
        q = request.query_params.get("q", "")
        active = request.query_params.get("active")
        if active is not None:
            active = active.lower() == "true"

        queryset = listar_produtos(
            tenant_id=request.tenant.id,
            q=q,
            active=active,
        )
        page = self.paginate_queryset(queryset)
        serializer = ProdutoOutSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Criar um artigo com embalagem opcional aninhada."""
        serializer = ProdutoInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        produto = Product.objects.create(
            tenant_id=request.tenant.id,
            short_name=serializer.validated_data["short_name"],
            base_unit=serializer.validated_data["base_unit"],
            display_unit=serializer.validated_data["display_unit"],
            display_factor=serializer.validated_data["display_factor"],
            track_lots=serializer.validated_data.get("track_lots", False),
            expiry_kind=serializer.validated_data.get("expiry_kind", ""),
            conservation=serializer.validated_data.get("conservation", "ambient"),
        )

        # Embalagem opcional
        if "packaging" in serializer.validated_data and serializer.validated_data["packaging"]:
            pkg = serializer.validated_data["packaging"]
            ProductPackaging.objects.create(
                tenant_id=request.tenant.id,
                product=produto,
                label=pkg["label"],
                base_quantity=pkg["base_quantity"],
                ean=pkg.get("ean", ""),
            )

        out_ser = ProdutoOutSerializer(produto)
        return Response(out_ser.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """PATCH um artigo."""
        produto = self.get_object()
        serializer = ProdutoPatchInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for field, value in serializer.validated_data.items():
            setattr(produto, field, value)
        produto.save()

        out_ser = ProdutoOutSerializer(produto)
        return Response(out_ser.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="produto_embalagens_listar",
        summary="Embalagens de um artigo",
    )
    @action(detail=True, methods=["get"], url_path="packagings")
    def packagings(self, request: Request, pk=None) -> Response:
        """GET /products/{id}/packagings — embalagens do artigo."""
        produto = self.get_object()
        embalagens = embalagens_do_produto(
            tenant_id=request.tenant.id,
            product_id=produto.id,
        )
        page = self.paginate_queryset(embalagens)
        serializer = EmbalagemOutSerializer(
            page if page is not None else embalagens,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        operation_id="produto_embalagem_criar",
        summary="Criar embalagem de um artigo",
    )
    @action(detail=True, methods=["post"], url_path="packagings")
    def create_packaging(self, request: Request, pk=None) -> Response:
        """POST /products/{id}/packagings — criar embalagem."""
        produto = self.get_object()
        serializer = EmbalagemInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        embalagem = ProductPackaging.objects.create(
            tenant_id=request.tenant.id,
            product=produto,
            label=serializer.validated_data["label"],
            base_quantity=serializer.validated_data["base_quantity"],
            ean=serializer.validated_data.get("ean", ""),
        )

        out_ser = EmbalagemOutSerializer(embalagem)
        return Response(out_ser.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        operation_id="fornecedores_listar",
        summary="Fornecedores do estabelecimento",
        parameters=[
            OpenApiParameter(
                name="q",
                description="Procurar por nome",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="active",
                description="Filtrar por estado",
                required=False,
                type=bool,
            ),
        ],
    ),
    create=extend_schema(
        operation_id="fornecedores_criar",
        summary="Criar um fornecedor",
    ),
    partial_update=extend_schema(
        operation_id="fornecedores_atualizar",
        summary="Atualizar fornecedor",
    ),
)
class FornecedorViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Fornecedores do catálogo."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    queryset = Supplier.objects.none()
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[Supplier]:
        """Fornecedores do estabelecimento ativo."""
        return fornecedores_do_ambito(tenant_id=self.request.tenant.id)

    def get_serializer_class(self):
        """Escolher serializer por acção."""
        if self.action == "create":
            return FornecedorInSerializer
        elif self.action == "partial_update":
            return FornecedorPatchInSerializer
        return FornecedorOutSerializer

    def list(self, request: Request, *args, **kwargs) -> Response:
        """Lista paginada de fornecedores."""
        q = request.query_params.get("q", "")
        active = request.query_params.get("active")
        if active is not None:
            active = active.lower() == "true"

        queryset = listar_fornecedores(
            tenant_id=request.tenant.id,
            q=q,
            active=active,
        )
        page = self.paginate_queryset(queryset)
        serializer = FornecedorOutSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Criar um fornecedor."""
        serializer = FornecedorInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fornecedor = Supplier.objects.create(
            tenant_id=request.tenant.id,
            name=serializer.validated_data["name"],
            nif=serializer.validated_data.get("nif", ""),
        )

        out_ser = FornecedorOutSerializer(fornecedor)
        return Response(out_ser.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """PATCH um fornecedor."""
        fornecedor = self.get_object()
        serializer = FornecedorPatchInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for field, value in serializer.validated_data.items():
            setattr(fornecedor, field, value)
        fornecedor.save()

        out_ser = FornecedorOutSerializer(fornecedor)
        return Response(out_ser.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="fornecedor_codigos_listar",
        summary="Códigos de um fornecedor (memória)",
    )
    @action(detail=True, methods=["get"], url_path="product-codes")
    def product_codes(self, request: Request, pk=None) -> Response:
        """GET /suppliers/{id}/product-codes — memória do fornecedor."""
        fornecedor = self.get_object()
        codigos = codigos_do_fornecedor(
            tenant_id=request.tenant.id,
            supplier_id=fornecedor.id,
        )
        page = self.paginate_queryset(codigos)
        serializer = CodigoDeFornecedorOutSerializer(
            page if page is not None else codigos,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
