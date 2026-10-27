"""ViewSets para o inventário (ADR 0021, fatia 2; ADR 0022; ADR 0025, fatia 5;
ADR 0030, contagens; ADR 0034, os sete recursos de `/stock`).

Endpoints:
- GET /api/v1/locations (por position)
- POST /api/v1/locations
- PATCH /api/v1/locations/{id}
- GET /api/v1/stock/levels
- GET /api/v1/stock/summary
- GET /api/v1/stock/alerts
- GET /api/v1/stock/alerts/summary
- GET /api/v1/stock/alerts/waste
- GET /api/v1/stock/movements
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
from django.utils import timezone
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
from rest_framework.serializers import ValidationError as DRFValidationError
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import (
    CHAVE_DE_EUROS,
    Papel,
    PertenceAoTenant,
    TemPapel,
    inicio_do_dia_de_negocio,
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
from apps.inventory.models import Location, StockCount, StockLevel, StockMovement
from apps.inventory.selectors import (
    DIAS_DE_VALIDADE_DO_PAINEL,
    FILTROS_DO_NIVEL,
    PERIODOS_DE_DESPERDICIO,
    RISCOS_DO_ALERTA,
    alertas_de_stock,
    contadores_de_alertas,
    contadores_de_desperdicio,
    contagens_com_progresso,
    janela_de_desperdicio,
    linhas_da_contagem,
    linhas_de_desperdicio,
    listar_localizacoes,
    localizacoes_do_ambito,
    movimentos_do_artigo,
    niveis_de_stock,
    niveis_filtrados,
    progresso_da_contagem,
    resumo_de_stock,
    rotulos_de_referencia,
)
from apps.inventory.serializers import (
    AjusteInSerializer,
    AlertaOutSerializer,
    ConflitoDeContagemOutSerializer,
    ContagemInSerializer,
    ContagemOutSerializer,
    DesperdicioOutSerializer,
    FechoDeContagemInSerializer,
    FechoDeContagemOutSerializer,
    LinhaDeContagemInSerializer,
    LinhaDeContagemOutSerializer,
    LocalizacaoInSerializer,
    LocalizacaoOutSerializer,
    LocalizacaoPatchInSerializer,
    MovimentoOutSerializer,
    NivelDeStockOutSerializer,
    QuebraInSerializer,
    RespostaDeQuebraOutSerializer,
    ResumoDeAlertasOutSerializer,
    ResumoDeStockOutSerializer,
    StockMovementResponseSerializer,
    StockTransferResponseSerializer,
    TransferenciaInSerializer,
    compor_alerta,
    compor_contagem,
    compor_desperdicio,
    compor_fecho,
    compor_linha,
    compor_movimento,
    compor_movimento_do_ledger,
    compor_nivel,
    em_unidade_base,
    em_unidade_pedida,
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


#: Os parâmetros de caminho que as sete rotas de `/stock` aceitam, declarados
#: um a um para o `--fail-on-warn` do `pnpm gen:api` não ter nada a adivinhar.
_P_LOJA = OpenApiParameter(
    "loja",
    OpenApiTypes.UUID,
    OpenApiParameter.QUERY,
    description=(
        "Escopa a quantidade, a repartição, a validade mais próxima e o valor. "
        "**Não** escopa o `status` nem o `min_quantity`: o mínimo é por artigo "
        "e é sempre do estabelecimento."
    ),
)
_P_Q = OpenApiParameter(
    "q", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Procura no nome curto."
)
_P_FILTRO = OpenApiParameter(
    "filtro",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    enum=list(FILTROS_DO_NIVEL),
    description="`falta` é tudo o que não está `ok`; `validade` é o que entra no limiar.",
)
_P_RISCO = OpenApiParameter(
    "risco",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    enum=list(RISCOS_DO_ALERTA),
    description="Sem valor, vêm os dois motivos.",
)
_P_PERIODO = OpenApiParameter(
    "periodo",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    enum=list(PERIODOS_DE_DESPERDICIO),
    description=(
        "Janela em dias **de negócio**: `hoje` é desde o `business_day_starts_at`, "
        "`semana` são sete dias rolantes incluindo hoje."
    ),
)
_P_ARTIGO = OpenApiParameter(
    "artigo",
    OpenApiTypes.UUID,
    OpenApiParameter.QUERY,
    required=True,
    description="Obrigatório: o ledger lê-se por artigo. Sem ele é 400.",
)

#: A frase de um parâmetro de união fechada fora da união. 400 e não uma lista
#: a fingir que filtrou — é a regra que o `?status=` das contagens já segue.
DETALHE_FILTRO_INVALIDO = _("Unknown filter. Use {opcoes}.")
DETALHE_ARTIGO_OBRIGATORIO = _("The 'artigo' query parameter is required.")
DETALHE_UUID_INVALIDO = _("Not a valid UUID.")


def _uuid_do_parametro(valor: str | None) -> UUID | None:
    """O `?loja=`/`?artigo=` como UUID. Levanta `ValueError` se não for um."""
    if not valor:
        return None
    return UUID(valor)


def _recusa(detalhe: Any) -> Response:
    """400 com `detail`, a forma que o cliente já sabe ler."""
    return Response({"detail": str(detalhe)}, status=status.HTTP_400_BAD_REQUEST)


def _da_uniao(valor: str | None, *, opcoes: tuple[str, ...]) -> str | None:
    """O valor se estiver na união, `""` se ausente, `None` se for inválido."""
    if not valor:
        return ""
    return valor if valor in opcoes else None


@extend_schema_view(
    levels=extend_schema(
        operation_id="stock_levels",
        summary="Stock por artigo: saldo, mínimo, estado, validade e onde está",
        parameters=[_P_LOJA, _P_Q, _P_FILTRO],
        responses={200: NivelDeStockOutSerializer(many=True)},
    ),
    summary=extend_schema(
        operation_id="stock_summary",
        summary="Os quatro números do topo do ecrã de Stock",
        parameters=[_P_LOJA],
        responses={200: ResumoDeStockOutSerializer},
    ),
    alerts=extend_schema(
        operation_id="stock_alerts",
        summary="O que está em risco: validades a vencer e artigos em falta",
        parameters=[_P_RISCO],
        responses={200: AlertaOutSerializer(many=True)},
    ),
    alerts_summary=extend_schema(
        operation_id="stock_alerts_summary",
        summary="Os contadores do ecrã de Alertas, mais o desperdício do dia e da semana",
        responses={200: ResumoDeAlertasOutSerializer},
    ),
    alerts_waste=extend_schema(
        operation_id="stock_alerts_waste",
        summary="As linhas de quebra do dia de negócio, com quem as registou",
        parameters=[_P_PERIODO],
        responses={200: DesperdicioOutSerializer(many=True)},
    ),
)
class StockPanelViewSet(viewsets.GenericViewSet):
    """Os cinco recursos de leitura de `/stock` (ADR 0034).

    **Nenhuma destas rotas tem papel** e nenhuma passou a ter: o dinheiro aqui
    é uma coluna e não o recurso, as rotas de stock são `TODOS_OS_PAPEIS` no
    `menu.py`, e negá-las tirava o ecrã a quem mais o usa (ADR 0032, decisão
    1). O que muda por papel é o payload, e quem o decide é o
    `SemEurosParaQuemNaoVe` do `accounts.api` — um sítio só.

    ## O envelope é o do DRF, e o `_pagina` morreu

    As quatro rotas do painel devolviam `{items, total, page, page_size}` com
    `page: 1` fixo: um envelope que **não pagina** e que mente sobre o fazer
    (ADR 0034, decisão 3). Agora é `{count, next, previous, results}` com o
    `PAGE_SIZE = 50` do `base.py`, que é o que o `paginated()` do cliente
    valida. O `context` dos euros, que o `_pagina` montava, passou para o
    `get_serializer_context()` — e é por isso que continua a ser impossível
    esquecê-lo numa rota.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO
    #: Vazia e como atributo de classe: o drf-spectacular lê o `queryset` da
    #: classe fora de um pedido. Nenhuma destas rotas o usa — todas compõem a
    #: resposta a partir de um selector.
    queryset = StockLevel.objects.none()
    serializer_class = NivelDeStockOutSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        """O contexto de serialização: quem vê euros, e nada mais.

        O default do mixin é **falso**, logo esquecer este contexto esconde
        dinheiro a toda a gente em vez de o mostrar a quem não deve — a
        direcção certa para falhar.
        """
        return {**super().get_serializer_context(), CHAVE_DE_EUROS: ve_euros(self.request)}

    def _pagina_de(
        self, linhas: list[Any], serializador: type[Serializer], request: Request
    ) -> Response:
        """`{count, next, previous, results}` sobre uma lista já composta."""
        pagina = self.paginate_queryset(linhas)
        corpo = serializador(
            pagina if pagina is not None else linhas,
            many=True,
            context=self.get_serializer_context(),
        )
        if pagina is not None:
            return self.get_paginated_response(corpo.data)
        return Response(corpo.data)

    @action(detail=False, methods=["GET"], url_path="levels")
    def levels(self, request: Request) -> Response:
        """Uma linha por artigo, o pior primeiro."""
        try:
            loja = _uuid_do_parametro(request.query_params.get("loja"))
        except ValueError:
            return _recusa(DETALHE_UUID_INVALIDO)
        filtro = _da_uniao(request.query_params.get("filtro"), opcoes=FILTROS_DO_NIVEL)
        if filtro is None:
            return _recusa(
                DETALHE_FILTRO_INVALIDO.format(opcoes=" ou ".join(FILTROS_DO_NIVEL))
            )

        linhas = niveis_de_stock(
            tenant_id=request.tenant.id,
            location_id=loja,
            q=request.query_params.get("q", "").strip(),
        )
        linhas = niveis_filtrados(
            linhas, filtro=filtro, limiar_em_dias=DIAS_DE_VALIDADE_DO_PAINEL
        )
        return self._pagina_de(
            [compor_nivel(linha) for linha in linhas],
            NivelDeStockOutSerializer,
            request,
        )

    @action(detail=False, methods=["GET"], url_path="summary")
    def summary(self, request: Request) -> Response:
        """Os quatro números do topo — e cada contador é o `count` da sua lista."""
        try:
            loja = _uuid_do_parametro(request.query_params.get("loja"))
        except ValueError:
            return _recusa(DETALHE_UUID_INVALIDO)
        resumo = resumo_de_stock(tenant_id=request.tenant.id, location_id=loja)
        return Response(
            ResumoDeStockOutSerializer(
                resumo, context=self.get_serializer_context()
            ).data
        )

    @action(detail=False, methods=["GET"], url_path="alerts")
    def alerts(self, request: Request) -> Response:
        """Uma lista, dois motivos, ordenada no servidor por gravidade."""
        risco = _da_uniao(request.query_params.get("risco"), opcoes=RISCOS_DO_ALERTA)
        if risco is None:
            return _recusa(
                DETALHE_FILTRO_INVALIDO.format(opcoes=" ou ".join(RISCOS_DO_ALERTA))
            )
        alertas = alertas_de_stock(tenant_id=request.tenant.id, risco=risco)
        return self._pagina_de(
            [compor_alerta(alerta) for alerta in alertas], AlertaOutSerializer, request
        )

    @action(detail=False, methods=["GET"], url_path="alerts/summary")
    def alerts_summary(self, request: Request) -> Response:
        """Três contadores, duas janelas de desperdício e a hora do negócio.

        A hora é **dado do servidor** por estabelecimento: na pastelaria o dia
        começa no início da produção e não no fim do serviço de um restaurante
        (ADR 0029). O `wasted_since` viaja com ela para o rótulo poder dizer
        "hoje (desde as 04:00)" sem o cliente calcular nada.
        """
        inicio_do_dia = inicio_do_dia_de_negocio(tenant_id=request.tenant.id)
        agora = timezone.now()
        desde_hoje, ate = janela_de_desperdicio(
            periodo="hoje", inicio_do_dia=inicio_do_dia, agora=agora
        )
        desde_semana, _ate_semana = janela_de_desperdicio(
            periodo="semana", inicio_do_dia=inicio_do_dia, agora=agora
        )
        hoje = contadores_de_desperdicio(
            tenant_id=request.tenant.id, desde=desde_hoje, ate=ate
        )
        semana = contadores_de_desperdicio(
            tenant_id=request.tenant.id, desde=desde_semana, ate=ate
        )
        corpo = {
            **contadores_de_alertas(tenant_id=request.tenant.id),
            "expiring_within_days": DIAS_DE_VALIDADE_DO_PAINEL,
            "business_day_starts_at": inicio_do_dia.strftime("%H:%M"),
            "wasted_since": desde_hoje,
            "wasted_today_eur": hoje["valor_eur"],
            "wasted_week_eur": semana["valor_eur"],
            "wasted_today_count": hoje["n"],
            "wasted_week_count": semana["n"],
            "wasted_today_lines_without_cost": hoje["linhas_sem_custo"],
            "wasted_week_lines_without_cost": semana["linhas_sem_custo"],
        }
        return Response(
            ResumoDeAlertasOutSerializer(
                corpo, context=self.get_serializer_context()
            ).data
        )

    @action(detail=False, methods=["GET"], url_path="alerts/waste")
    def alerts_waste(self, request: Request) -> Response:
        """As linhas de quebra da janela, da mais recente para a mais antiga."""
        periodo = _da_uniao(
            request.query_params.get("periodo"), opcoes=PERIODOS_DE_DESPERDICIO
        )
        if periodo is None:
            return _recusa(
                DETALHE_FILTRO_INVALIDO.format(
                    opcoes=" ou ".join(PERIODOS_DE_DESPERDICIO)
                )
            )
        inicio_do_dia = inicio_do_dia_de_negocio(tenant_id=request.tenant.id)
        desde, ate = janela_de_desperdicio(
            periodo=periodo or "hoje",
            inicio_do_dia=inicio_do_dia,
            agora=timezone.now(),
        )
        movimentos = linhas_de_desperdicio(
            tenant_id=request.tenant.id, desde=desde, ate=ate
        )
        pagina = self.paginate_queryset(movimentos)
        corpo = DesperdicioOutSerializer(
            [compor_desperdicio(m) for m in (pagina if pagina is not None else movimentos)],
            many=True,
            context=self.get_serializer_context(),
        )
        if pagina is not None:
            return self.get_paginated_response(corpo.data)
        return Response(corpo.data)


@extend_schema_view(
    list=extend_schema(
        operation_id="stock_movements_listar",
        summary="O ledger de um artigo, do mais recente para o mais antigo",
        parameters=[_P_ARTIGO],
        responses={200: MovimentoOutSerializer(many=True)},
    ),
    waste=extend_schema(
        operation_id="stock_movements_waste",
        summary="Registar uma quebra (FEFO na localização pedida, repartida se preciso)",
        request=QuebraInSerializer,
        responses={201: RespostaDeQuebraOutSerializer},
    ),
    adjustment=extend_schema(
        operation_id="stock_movements_adjustment",
        summary="Registar ajuste de stock",
        request=AjusteInSerializer,
        responses={201: StockMovementResponseSerializer},
    ),
    transfer=extend_schema(
        operation_id="stock_movements_transfer",
        summary="Transferir stock entre localizações",
        request=TransferenciaInSerializer,
        responses={201: StockTransferResponseSerializer},
    ),
)
class StockMovementViewSet(viewsets.GenericViewSet):
    """O ledger: uma leitura por artigo e três escritas manuais.

    Sem papel, e é a decisão 3 da ADR 0032: perder e transferir é trabalho de
    campo. O que sai do 201 é que muda — o `unit_cost` só vai a
    `owner|manager`.

    **Os corpos de entrada perderam os sufixos `_id`** (ADR 0034): `product`,
    `location`, `lot`, `from_location`, `to_location`. Nos três e não só na
    quebra — duas convenções no mesmo ViewSet é como se escreve o 400 seguinte
    —, e as mensagens de recusa do serviço nomeiam os mesmos campos.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_scope = AMBITO_THROTTLE_CATALOGO
    queryset = StockMovement.objects.none()
    serializer_class = MovimentoOutSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        """Quem vê euros neste pedido. Default falso — ver `SemEurosParaQuemNaoVe`."""
        return {**super().get_serializer_context(), CHAVE_DE_EUROS: ve_euros(self.request)}

    def _contexto(self, request: Request) -> dict[str, bool]:
        """O contexto dos 201 que ainda não passam pelo `get_serializer`."""
        return {CHAVE_DE_EUROS: ve_euros(request)}

    def list(self, request: Request, *args, **kwargs) -> Response:
        """`GET /stock/movements?artigo=<uuid>` — **obrigatório**, 400 sem ele.

        Obrigatório porque o ledger de um estabelecimento inteiro não é uma
        lista que alguém leia: a pergunta é sempre "o que aconteceu a este
        artigo", e é o ecrã do artigo que a faz.
        """
        artigo = request.query_params.get("artigo")
        if not artigo:
            return _recusa(DETALHE_ARTIGO_OBRIGATORIO)
        try:
            product_id = UUID(artigo)
        except ValueError:
            return _recusa(DETALHE_UUID_INVALIDO)

        movimentos = movimentos_do_artigo(
            tenant_id=request.tenant.id, product_id=product_id
        )
        pagina = self.paginate_queryset(movimentos)
        visiveis = list(pagina if pagina is not None else movimentos)
        rotulos = rotulos_de_referencia(
            tenant_id=request.tenant.id,
            referencias=[m.reference for m in visiveis],
        )
        corpo = MovimentoOutSerializer(
            [compor_movimento_do_ledger(m, rotulos=rotulos) for m in visiveis],
            many=True,
            context=self.get_serializer_context(),
        )
        if pagina is not None:
            return self.get_paginated_response(corpo.data)
        return Response(corpo.data)

    @action(detail=False, methods=["POST"], url_path="waste")
    def waste(self, request: Request) -> Response:
        """Registar uma quebra. O 201 é `{movements: [...]}`, **sempre lista**.

        A unidade vem no corpo e a conversão é aqui, na camada do contrato —
        o serviço fala sempre em unidade base, como nas linhas de contagem
        (ADR 0034, decisão 11).
        """
        serializer = QuebraInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        produto = produto_por_id(
            tenant_id=request.tenant.id, product_id=dados["product"]
        )
        if produto is None:
            return Response(
                {"product": [str(_("Product not found."))]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantidade_base = em_unidade_pedida(
                dados["quantity"], unidade=dados["unit"], produto=produto
            )
            movement_ids = registar_waste(
                tenant_id=request.tenant.id,
                product_id=dados["product"],
                location_id=dados["location"],
                quantity=quantidade_base,
                lot_id=dados.get("lot"),
                reason=dados["reason"],
                reason_detail=dados.get("reason_detail", ""),
                user=request.user,
                user_name=request.membership.display_name,
            )
        except DRFValidationError as erro:
            logger.warning(
                "waste_rejected",
                extra={"outcome": "validation_error", "errors": erro.detail},
            )
            return Response(erro.detail, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as erro:
            logger.warning(
                "waste_rejected",
                extra={"outcome": "validation_error", "errors": erro.message_dict},
            )
            return Response(erro.message_dict, status=status.HTTP_400_BAD_REQUEST)

        movimentos = list(
            StockMovement.objects.filter(
                tenant_id=request.tenant.id, pk__in=movement_ids
            ).select_related("product", "location", "lot")
        )
        por_id = {m.id: m for m in movimentos}
        corpo = RespostaDeQuebraOutSerializer(
            {
                # Na ordem em que o serviço os escreveu, que é a ordem FEFO: a
                # frase do ecrã nomeia os lotes por onde a quebra passou.
                "movements": [
                    compor_movimento_do_ledger(por_id[mid])
                    for mid in movement_ids
                    if mid in por_id
                ]
            },
            context=self._contexto(request),
        )
        return Response(corpo.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["POST"], url_path="adjustment")
    def adjustment(self, request: Request) -> Response:
        """Registar um ajuste de stock (POST /stock/movements/adjustment)."""
        serializer = AjusteInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        try:
            movement_id = registar_adjustment(
                tenant_id=request.tenant.id,
                product_id=dados["product"],
                location_id=dados["location"],
                quantity=dados["quantity"],
                lot_id=dados.get("lot"),
                reason=dados["reason"],
                reason_detail=dados.get("reason_detail", ""),
                user=request.user,
                user_name=request.membership.display_name,
            )
        except ValidationError as erro:
            logger.warning(
                "adjustment_rejected",
                extra={"outcome": "validation_error", "errors": erro.message_dict},
            )
            return Response(erro.message_dict, status=status.HTTP_400_BAD_REQUEST)

        movimento = StockMovement.objects.select_related("product", "location", "lot").get(
            pk=movement_id
        )
        corpo = StockMovementResponseSerializer(
            compor_movimento(movimento) | {"created_at": movimento.created_at},
            context=self._contexto(request),
        )
        return Response(corpo.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["POST"], url_path="transfer")
    def transfer(self, request: Request) -> Response:
        """Transferir stock entre localizações (POST /stock/movements/transfer)."""
        serializer = TransferenciaInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        try:
            out_id, in_id = registar_transfer(
                tenant_id=request.tenant.id,
                product_id=dados["product"],
                from_location_id=dados["from_location"],
                to_location_id=dados["to_location"],
                quantity=dados["quantity"],
                lot_id=dados.get("lot"),
                user=request.user,
                user_name=request.membership.display_name,
            )
        except ValidationError as erro:
            logger.warning(
                "transfer_rejected",
                extra={"outcome": "validation_error", "errors": erro.message_dict},
            )
            return Response(erro.message_dict, status=status.HTTP_400_BAD_REQUEST)

        movimentos = StockMovement.objects.select_related(
            "product", "location", "lot"
        ).in_bulk([out_id, in_id])
        out_movimento, in_movimento = movimentos[out_id], movimentos[in_id]

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

# ===========================================================================
# Contagem física (ADR 0030, revista pela ADR 0033). Seis rotas num ViewSet, e a
# assimetria de papéis é deliberada: **abrir e contar são de toda a gente**
# porque são o fluxo de campo e o telemóvel é do `staff`; **fechar** é de
# `owner|manager` porque escreve N movimentos irreversíveis e porque a decisão é
# o `GET /closing`, que mostra euros. A assimetria vive em `permission_classes`
# e não num botão escondido.
#
# Abrir era restrito e deixou de o ser (ADR 0033, decisão 2): a razão escrita na
# ADR 0030 não era o risco da escrita, era "ocupar a única contagem aberta do
# estabelecimento" — e com uma contagem aberta **por localização** essa escassez
# acabou. Manter a permissão era conservar a consequência de uma premissa
# revogada.
# ===========================================================================

#: Quem fecha — as duas rotas de `/closing`, e mais nenhuma desde a ADR 0033.
#: Instanciada uma vez: a fábrica cria uma subclasse a cada chamada, e duas
#: subclasses iguais em dois sítios não ajudam ninguém.
#:
#: O `tests/test_custos_de_stock.py` prende `SO_OWNER_OU_MANAGER.papeis` aos
#: `PAPEIS_QUE_VEEM_EUROS` (ADR 0032): o `reason_required_above_eur` é um oráculo
#: de preço no dia em que deixar de ser zero, e a rota que o serve tem de ser
#: exactamente a de quem já vê euros. Esta ADR não lhe toca — a constante deixa
#: de ser usada no `create` e fica só no `closing`, que é a rota que ela
#: descreve.
SO_OWNER_OU_MANAGER = TemPapel.exige(Papel.OWNER, Papel.MANAGER)

#: Os papéis a quem os euros são mostrados (ADR 0029) vivem no `accounts.api` —
#: ver `ve_euros`. Ao `staff`, o `difference_eur` **não vem na resposta**: a
#: lista é dele, os euros não. Era `null` até 2026-10-21 e a ADR 0032, decisão
#: 5, trocou-o pela chave ausente — `null` dizia ao mesmo tempo "ainda não
#: contado" e "não te é mostrado", e a ausência diz a segunda sem apagar a
#: primeira.

#: A frase **nomeia a localização**: o `code` continua `contagem_ja_aberta`
#: porque o cliente ramifica nele, e o que mudou foi o significado — "já há uma
#: aberta **aqui**" e não "já há uma aberta nesta casa" (ADR 0033, decisão 1).
DETALHE_JA_ABERTA = _("There is already an open count in %(location)s.")
DETALHE_JA_FECHADA = _("This count is already closed.")

#: Os dois estados que o `?status=` aceita. Um terceiro valor é **400** e não
#: uma lista a fingir que filtrou: o conjunto é fechado e o cliente só envia
#: estes dois.
ESTADOS_DA_CONTAGEM = ("open", "closed")
DETALHE_ESTADO_INVALIDO = _("Unknown count status. Use open or closed.")


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
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                enum=list(ESTADOS_DA_CONTAGEM),
                description=(
                    "Filtra pelo estado. Ausente traz as duas; um valor fora da "
                    "lista é 400."
                ),
            )
        ],
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
    | `POST stock/counts` | **todos** — desde a ADR 0033, decisão 2 |
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
        """Abrir e contar são de toda a gente; **fechar** é de `owner|manager`.

        O `create` saiu desta lista com a ADR 0033: abrir não escreve movimento
        nenhum, não revela euro nenhum (o 201 passa pelo `ve_euros`) e deixou de
        ocupar a única vaga do estabelecimento. O que continua a precisar do
        dono é a decisão que o `GET /closing` mostra e o `POST` assina.
        """
        if self.action == "closing":
            return [IsAuthenticated(), PertenceAoTenant(), SO_OWNER_OU_MANAGER()]
        return [IsAuthenticated(), PertenceAoTenant()]

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[StockCount]:
        """As contagens do estabelecimento ativo, com o progresso de cada uma.

        Sem o `?status=`: este é o queryset do `get_object()` das rotas
        aninhadas, e filtrá-lo por estado faria um `?status=closed` perdido no
        URL transformar uma contagem aberta em 404. O filtro da lista vive no
        `list`, que é onde ele é uma pergunta.
        """
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
        """Lista paginada de contagens, da mais recente para a mais antiga.

        `?status=open|closed` (ADR 0033, decisão 4): com várias contagens
        abertas ao mesmo tempo, "as que estão a decorrer" é uma pergunta ao
        servidor e não um `results.find(status === "open")` sobre a primeira
        página — era o rabo a abanar o cão, uma suposição de ecrã a decidir uma
        invariante de domínio.
        """
        estado = request.query_params.get("status", "")
        if estado and estado not in ESTADOS_DA_CONTAGEM:
            return Response(
                {"status": [str(DETALHE_ESTADO_INVALIDO)]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pagina = self.paginate_queryset(
            contagens_com_progresso(tenant_id=request.tenant.id, estado=estado)
        )
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
                detail=DETALHE_JA_ABERTA % {"location": erro.location_name},
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
