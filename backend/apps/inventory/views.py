"""ViewSets para o inventário (ADR 0021, fatia 2; ADR 0022; ADR 0024, fatia 4;
ADR 0025, fatia 5; ADR 0030, contagens).

Endpoints:
- GET /api/v1/locations (por position)
- POST /api/v1/locations
- PATCH /api/v1/locations/{id}
- GET /api/v1/stock/summary
- GET /api/v1/stock/by-location
- GET /api/v1/stock/by-product
- GET /api/v1/stock/alerts
- POST /api/v1/stock/movements/{waste,adjustment,transfer}
- GET|POST /api/v1/stock/counts
- GET|POST /api/v1/stock/counts/{id}/lines
- GET|POST /api/v1/stock/counts/{id}/closing
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Max, QuerySet
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import (
    CHAVE_DE_EUROS,
    Papel,
    PertenceAoTenant,
    TemPapel,
    membership_atual,
    ve_euros,
)
from apps.catalog.api import produto_por_id
from apps.inventory.count_services import (
    CODIGO_CONTAGEM_FECHADA,
    CODIGO_CONTAGEM_JA_ABERTA,
    ContagemFechada,
    ContagemJaAberta,
    abrir_contagem,
    fechar_contagem,
    planear_fecho,
    registar_linha_contagem,
)
from apps.inventory.models import Location, StockCount, StockMovement
from apps.inventory.selectors import (
    contagens_com_progresso,
    linhas_da_contagem,
    listar_localizacoes,
    localizacoes_do_ambito,
    progresso_da_contagem,
    stock_alerts,
    stock_by_location,
    stock_by_product,
    stock_summary,
)
from apps.inventory.serializers import (
    AdjustmentSerializer,
    AlertSerializer,
    ConflitoDeContagemOutSerializer,
    ContagemInSerializer,
    ContagemOutSerializer,
    FechoDeContagemInSerializer,
    FechoDeContagemOutSerializer,
    LinhaDeContagemInSerializer,
    LinhaDeContagemOutSerializer,
    LocalizacaoInSerializer,
    LocalizacaoOutSerializer,
    LocalizacaoPatchInSerializer,
    StockDetailSerializer,
    StockMovementResponseSerializer,
    StockSummarySerializer,
    StockTransferResponseSerializer,
    TransferSerializer,
    WasteSerializer,
    compor_contagem,
    compor_fecho,
    compor_linha,
    compor_movimento,
    em_unidade_base,
    zona_da_localizacao,
)
from apps.inventory.services import (
    registar_adjustment,
    registar_transfer,
    registar_waste,
)

__all__ = [
    "ContagemViewSet",
    "LocalizacaoViewSet",
    "StockPanelViewSet",
    "StockMovementViewSet",
]

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
    """Painel de stock: queries read-only ao ledger (ADR 0024, ADR 0032).

    **Nenhuma destas rotas tem papel** e nenhuma passou a ter: o dinheiro aqui é
    uma coluna e não o recurso, as rotas de stock são `TODOS_OS_PAPEIS` no
    `menu.py`, e negá-las tirava o ecrã a quem mais o usa (ADR 0032, decisão 1).
    O que muda por papel é o payload, e quem o decide é o
    `SemEurosParaQuemNaoVe` do `accounts.api` — um sítio só.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO
    page_size = 50

    def get_throttles(self) -> list[BaseThrottle]:
        """Sem throttle extra em leitura."""
        return super().get_throttles()

    def _contexto(self, request: Request) -> dict[str, bool]:
        """O contexto de serialização: quem vê euros, e nada mais.

        O default do mixin é **falso**, logo esquecer este contexto esconde
        dinheiro a toda a gente em vez de o mostrar a quem não deve — a direcção
        certa para falhar.
        """
        return {CHAVE_DE_EUROS: ve_euros(request)}

    def _pagina(
        self,
        items: list[dict[str, Any]],
        serializador: type[Serializer],
        request: Request,
    ) -> Response:
        """O envelope `{items,total,page,page_size}` das quatro rotas do painel.

        Existe para o `context` não poder ser esquecido numa delas: as quatro
        passam por aqui e o contexto é montado num sítio só.
        """
        serializer = serializador(items, many=True, context=self._contexto(request))
        return Response(
            {
                "items": serializer.data,
                "total": len(items),
                "page": 1,
                "page_size": self.page_size,
            }
        )

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

        items = stock_summary(tenant_id=request.tenant.id, location_id=location_id)
        return self._pagina(items, StockSummarySerializer, request)

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

        items = stock_by_location(
            tenant_id=request.tenant.id,
            location_id=location_id,
            search_text=search_text,
        )
        return self._pagina(items, StockDetailSerializer, request)

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

        items = stock_by_product(
            tenant_id=request.tenant.id,
            product_id=product_id,
            search_text=search_text,
        )
        return self._pagina(items, StockDetailSerializer, request)

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

        alerts_data = stock_alerts(
            tenant_id=request.tenant.id,
            severity=severity,
            product_id=product_id,
            location_id=location_id,
        )
        return self._pagina(alerts_data, AlertSerializer, request)


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
        responses={201: StockTransferResponseSerializer},
    ),
)
class StockMovementViewSet(viewsets.ViewSet):
    """Endpoints para criar movimentos de stock manuais (desperdício, ajuste, transferência).

    Sem papel, e é a decisão 3 da ADR 0032: perder e transferir é trabalho de
    campo. O que sai do 201 é que mudou — o `unit_cost` só vai a `owner|manager`
    —, e **a resposta passa agora por um serializer**. Até 2026-10-21 as três
    montavam um `dict` e devolviam-no: o `StockMovementResponseSerializer` só
    existia no `extend_schema`, nenhum mixin lhes chegava, e no caso da
    transferência o schema declarado nem descrevia o corpo que sai.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def _contexto(self, request: Request) -> dict[str, bool]:
        """Quem vê euros neste pedido. Default falso — ver `SemEurosParaQuemNaoVe`."""
        return {CHAVE_DE_EUROS: ve_euros(request)}

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
                reason_detail=serializer.validated_data.get("reason_detail", ""),
                user=request.user,
                user_name=request.membership.display_name,
            )

            movimento = StockMovement.objects.get(pk=movement_id)
            corpo = StockMovementResponseSerializer(
                compor_movimento(movimento) | {"created_at": movimento.created_at},
                context=self._contexto(request),
            )
            return Response(corpo.data, status=status.HTTP_201_CREATED)

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
                reason_detail=serializer.validated_data.get("reason_detail", ""),
                user=request.user,
                user_name=request.membership.display_name,
            )

            movimento = StockMovement.objects.get(pk=movement_id)
            corpo = StockMovementResponseSerializer(
                compor_movimento(movimento) | {"created_at": movimento.created_at},
                context=self._contexto(request),
            )
            return Response(corpo.data, status=status.HTTP_201_CREATED)

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
                user_name=request.membership.display_name,
            )

            out_movimento = StockMovement.objects.get(pk=out_id)
            in_movimento = StockMovement.objects.get(pk=in_id)

            corpo = StockTransferResponseSerializer(
                {
                    "transfer_id": out_movimento.transfer_id,
                    "movements": [
                        compor_movimento(out_movimento) | {"type": "transfer_out"},
                        compor_movimento(in_movimento) | {"type": "transfer_in"},
                    ],
                    "created_at": out_movimento.created_at,
                },
                context=self._contexto(request),
            )
            return Response(corpo.data, status=status.HTTP_201_CREATED)

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


# ===========================================================================
# Contagem física (ADR 0030). Seis rotas num ViewSet, e a assimetria de papéis
# é deliberada: **contar é de toda a gente** porque é o fluxo de campo e o
# telemóvel é do `staff`; abrir e fechar são de `owner|manager` porque fechar
# escreve N movimentos irreversíveis e abrir ocupa a única contagem aberta do
# estabelecimento. A assimetria vive em `permission_classes` e não num botão
# escondido.
# ===========================================================================

#: Quem abre e quem fecha. Instanciada uma vez: a fábrica cria uma subclasse a
#: cada chamada, e três subclasses iguais em três sítios não ajudam ninguém.
SO_OWNER_OU_MANAGER = TemPapel.exige(Papel.OWNER, Papel.MANAGER)

#: Os papéis a quem os euros são mostrados (ADR 0029) vivem no `accounts.api` —
#: ver `ve_euros`. Ao `staff`, o `difference_eur` **não vem na resposta**: a
#: lista é dele, os euros não. Era `null` até 2026-10-21 e a ADR 0032, decisão
#: 5, trocou-o pela chave ausente — `null` dizia ao mesmo tempo "ainda não
#: contado" e "não te é mostrado", e a ausência diz a segunda sem apagar a
#: primeira.

DETALHE_JA_ABERTA = _("There is already an open count in this establishment.")
DETALHE_JA_FECHADA = _("This count is already closed.")


class PaginacaoDasLinhas(PageNumberPagination):
    """200 por página: a página tem de **cobrir a contagem inteira**.

    O ecrã não tem paginador, e uma lista truncada é uma contagem errada que
    ninguém vê (ADR 0030, decisão 6a). Acima de 200 o `?page=` existe e o
    paginador passa a ser trabalho de frontend. Sem `page_size_query_param`: o
    tamanho é do contrato e não de quem chama.
    """

    page_size = 200


def _resposta_de_validacao(erro: ValidationError) -> Response:
    """400 na forma por campo do DRF, a partir de um `ValidationError` do Django.

    O DRF não converte o `ValidationError` do `django.core.exceptions`:
    deixá-lo subir era um 500 numa recusa de validação.
    """
    return Response(
        getattr(erro, "message_dict", {"detail": erro.messages}),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _conflito(*, code: str, detail: str, contagem_id) -> Response:
    """409 com `code` para ramificar, `detail` para ler e `id` para navegar."""
    return Response(
        {"code": code, "detail": str(detail), "id": contagem_id},
        status=status.HTTP_409_CONFLICT,
    )


@extend_schema_view(
    list=extend_schema(
        operation_id="contagens_listar",
        summary="Contagens do estabelecimento, da mais recente para a mais antiga",
        responses={200: ContagemOutSerializer(many=True)},
    ),
    create=extend_schema(
        operation_id="contagens_abrir",
        summary="Abrir uma contagem numa localização",
        request=ContagemInSerializer,
        responses={
            201: ContagemOutSerializer,
            409: ConflitoDeContagemOutSerializer,
        },
    ),
)
class ContagemViewSet(viewsets.GenericViewSet):
    """As seis rotas de uma contagem física.

    | rota | quem |
    |---|---|
    | `GET stock/counts` | todos |
    | `POST stock/counts` | owner, manager |
    | `GET stock/counts/{id}/lines` | todos |
    | `POST stock/counts/{id}/lines` | **todos** — o staff conta no telemóvel |
    | `GET stock/counts/{id}/closing` | owner, manager |
    | `POST stock/counts/{id}/closing` | owner, manager |

    O `get_queryset` filtra pelo estabelecimento do pedido, logo o `id` de outro
    tenant é **404** e não 403: 403 confirmaria que o objeto existe a quem o não
    pode ver (SECURITY.md §5). A RLS é a primeira rede e isto é a segunda.
    """

    serializer_class = ContagemOutSerializer
    #: Vazia e como atributo de classe, não porque alguém a use — o
    #: `get_queryset` abaixo substitui-a sempre — mas porque o drf-spectacular
    #: lê o `queryset` da classe, fora de um pedido, para tipar o `{id}` do
    #: caminho. Sem ela o `self.request.tenant` não existe, a derivação falha e
    #: o schema sai com um warning, que é exit 1 no `pnpm gen:api`.
    queryset = StockCount.objects.none()
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def get_permissions(self):
        """Contar é de toda a gente; abrir e fechar são de `owner|manager`."""
        if self.action in {"create", "closing"}:
            return [IsAuthenticated(), PertenceAoTenant(), SO_OWNER_OU_MANAGER()]
        return [IsAuthenticated(), PertenceAoTenant()]

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[StockCount]:
        """As contagens do estabelecimento ativo, com o progresso de cada uma."""
        return contagens_com_progresso(tenant_id=self.request.tenant.id)

    def _ve_euros(self, request: Request) -> bool:
        """Este pedido pode ver euros? A regra é do papel e vive no `accounts`."""
        return ve_euros(request)

    def _contexto(self, request: Request) -> dict[str, bool]:
        """O contexto que o `SemEurosParaQuemNaoVe` lê para decidir o payload.

        Tem de ser passado **em todas** as instâncias, incluindo as do `/closing`
        — que é de `owner|manager` e portanto vê sempre: sem contexto o default
        do mixin é falso e o `difference_eur` desaparecia do corpo de quem tem
        todo o direito a ele.
        """
        return {CHAVE_DE_EUROS: self._ve_euros(request)}

    def _nome_de_quem_conta(self, request: Request) -> str:
        """O nome da **pertença**, que é o que fica copiado na linha.

        Nunca o email: um email no registo de quem contou é lido depois por
        qualquer colega (é a mesma regra do `created_by_name` do ledger).
        """
        pertenca = membership_atual(request)
        return pertenca.display_name if pertenca else ""

    def list(self, request: Request, *args, **kwargs) -> Response:
        """Lista paginada de contagens, da mais recente para a mais antiga."""
        pagina = self.paginate_queryset(self.get_queryset())
        ve_euros = self._ve_euros(request)
        corpo = [
            compor_contagem(
                contagem,
                counted_lines=contagem.n_contadas,
                total_lines=contagem.n_linhas,
                ve_euros=ve_euros,
            )
            for contagem in pagina
        ]
        return self.get_paginated_response(ContagemOutSerializer(corpo, many=True).data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Abre a contagem de uma localização, com as linhas já materializadas."""
        entrada = ContagemInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            contagem = abrir_contagem(
                tenant_id=request.tenant.id,
                location_id=entrada.validated_data["location"],
                user_id=request.user.id,
            )
        except ContagemJaAberta as erro:
            return _conflito(
                code=CODIGO_CONTAGEM_JA_ABERTA,
                detail=DETALHE_JA_ABERTA,
                contagem_id=erro.contagem_id,
            )
        except ValidationError as erro:
            return _resposta_de_validacao(erro)

        progresso = progresso_da_contagem(
            tenant_id=request.tenant.id, stock_count_id=contagem.pk
        )
        corpo = compor_contagem(
            contagem,
            counted_lines=progresso["n_contadas"],
            total_lines=progresso["n_linhas"],
            ve_euros=self._ve_euros(request),
        )
        return Response(
            ContagemOutSerializer(corpo).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        methods=["GET"],
        operation_id="contagens_linhas_listar",
        summary="As linhas de uma contagem, na ordem do servidor",
        parameters=[
            OpenApiParameter(
                "zona",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Filtra pelo `slug` da zona. Um slug desconhecido dá página vazia.",
            )
        ],
        responses={200: LinhaDeContagemOutSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        operation_id="contagens_linha_registar",
        summary="Registar o que se contou de um artigo",
        request=LinhaDeContagemInSerializer,
        responses={
            200: LinhaDeContagemOutSerializer,
            409: ConflitoDeContagemOutSerializer,
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="lines")
    def lines(self, request: Request, pk=None) -> Response:
        """As linhas da contagem: percorrer a lista (GET) e contar (POST)."""
        contagem = self.get_object()
        if request.method == "POST":
            return self._registar_linha(request, contagem)
        return self._listar_linhas(request, contagem)

    def _listar_linhas(self, request: Request, contagem: StockCount) -> Response:
        """A lista inteira, com `position` pela ordem do servidor e euros por papel.

        O paginador é instanciado aqui e não é o da classe: a lista das
        contagens vive com as 50 por página do `base.py` e esta precisa de 200,
        que é o número que cobre a contagem inteira. `self.paginate_queryset`
        usaria o mesmo nos dois, e a contagem de 60 artigos saía truncada aos
        50 — a lista truncada que ninguém vê (ADR 0030, decisão 6a).
        """
        linhas = linhas_da_contagem(
            tenant_id=request.tenant.id, stock_count_id=contagem.pk
        )
        posicoes = {linha.id: indice for indice, linha in enumerate(linhas)}
        zona = zona_da_localizacao(contagem.location)
        pedida = request.query_params.get("zona")
        if pedida is not None and pedida != zona["slug"]:
            linhas = []
        valores = self._valores_por_linha(request, contagem)
        paginador = PaginacaoDasLinhas()
        corpo = [
            compor_linha(
                linha,
                position=posicoes[linha.id],
                zona=zona,
                difference_eur=valores.get(linha.id) if valores is not None else None,
            )
            for linha in paginador.paginate_queryset(linhas, request, view=self)
        ]
        return paginador.get_paginated_response(
            LinhaDeContagemOutSerializer(
                corpo, many=True, context=self._contexto(request)
            ).data
        )

    def _registar_linha(self, request: Request, contagem: StockCount) -> Response:
        """Upsert por artigo: a última observação ganha, e diz quem a fez.

        O `quantity` do corpo vem na **unidade de contagem** — a mesma que a
        linha publica em `count_unit` e em que o campo do ecrã está rotulado — e
        é aqui que se converte para a do ledger. O serviço fala sempre em unidade
        base; o contrato HTTP fala na unidade de quem conta.
        """
        entrada = LinhaDeContagemInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        produto = produto_por_id(
            tenant_id=request.tenant.id, product_id=entrada.validated_data["product"]
        )
        try:
            linha = registar_linha_contagem(
                tenant_id=request.tenant.id,
                contagem=contagem,
                product_id=entrada.validated_data["product"],
                quantity=em_unidade_base(
                    entrada.validated_data["quantity"], produto=produto
                ),
                user_name=self._nome_de_quem_conta(request),
            )
        except ContagemFechada as erro:
            return _conflito(
                code=CODIGO_CONTAGEM_FECHADA,
                detail=DETALHE_JA_FECHADA,
                contagem_id=erro.contagem_id,
            )
        except ValidationError as erro:
            return _resposta_de_validacao(erro)

        linhas = linhas_da_contagem(
            tenant_id=request.tenant.id, stock_count_id=contagem.pk
        )
        posicoes = {outra.id: indice for indice, outra in enumerate(linhas)}
        valores = self._valores_por_linha(request, contagem)
        corpo = compor_linha(
            linha,
            position=posicoes.get(linha.id, 0),
            zona=zona_da_localizacao(contagem.location),
            difference_eur=valores.get(linha.id) if valores is not None else None,
        )
        return Response(
            LinhaDeContagemOutSerializer(corpo, context=self._contexto(request)).data,
            status=status.HTTP_200_OK,
        )

    def _valores_por_linha(self, request: Request, contagem: StockCount):
        """Os euros de cada linha, ou `None` quando o papel não os vê.

        `None` e não um dicionário vazio: "não te é mostrado" e "não tem
        diferença" são duas coisas, e aqui dentro distinguem-se — no contrato
        distinguem-se também, desde que a ADR 0032 deu a primeira à **ausência**
        da chave e deixou o `null` a dizer só a segunda.

        O que isto poupa não é cosmético: para quem não vê euros nem se chega a
        chamar o `planear_fecho`. O mixin apagaria a chave na mesma, mas o
        trabalho de a calcular era feito à mesma.
        """
        if not self._ve_euros(request):
            return None
        previsto = planear_fecho(tenant_id=request.tenant.id, contagem=contagem)
        return previsto.valor_por_linha

    @extend_schema(
        methods=["GET"],
        operation_id="contagens_fecho_prever",
        summary="O que o fecho vai escrever, sem escrever nada",
        responses={200: FechoDeContagemOutSerializer},
    )
    @extend_schema(
        methods=["POST"],
        operation_id="contagens_fechar",
        summary="Fechar a contagem e gravar os ajustes no ledger",
        request=FechoDeContagemInSerializer,
        responses={
            200: FechoDeContagemOutSerializer,
            409: ConflitoDeContagemOutSerializer,
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="closing")
    def closing(self, request: Request, pk=None) -> Response:
        """A pré-visualização (GET) e o fecho (POST), pelo mesmo algoritmo."""
        contagem = self.get_object()
        if request.method == "POST":
            entrada = FechoDeContagemInSerializer(data=request.data)
            entrada.is_valid(raise_exception=True)
            try:
                contagem = fechar_contagem(
                    tenant_id=request.tenant.id,
                    contagem=contagem,
                    reason=entrada.validated_data["reason"],
                    user_id=request.user.id,
                    user_name=self._nome_de_quem_conta(request),
                )
            except ContagemFechada as erro:
                return _conflito(
                    code=CODIGO_CONTAGEM_FECHADA,
                    detail=DETALHE_JA_FECHADA,
                    contagem_id=erro.contagem_id,
                )
            except ValidationError as erro:
                return _resposta_de_validacao(erro)

        previsto = planear_fecho(tenant_id=request.tenant.id, contagem=contagem)
        return Response(
            FechoDeContagemOutSerializer(
                compor_fecho(previsto), context=self._contexto(request)
            ).data,
            status=status.HTTP_200_OK,
        )
