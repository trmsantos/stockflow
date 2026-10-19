"""Os três endpoints do painel (ADR 0013, decisão 5; ADR 0029, decisão 3).

- `GET /api/v1/reporting/summary?period=today|7d|30d|month|prev_month`
- `GET /api/v1/reporting/series?period=…`
- `GET /api/v1/reporting/month?month=YYYY-MM`

## As três levam o mesmo gate, e isso é a correcção desta fatia

`[IsAuthenticated, PertenceAoTenant, TemPapel.exige(Papel.OWNER)]` — **nas
três**, não só no `/month`. A ADR 0013 tinha o `/summary` e o `/series` em
`{owner, manager}` porque o painel vivia no Início; desde que saiu para uma rota
própria o painel inteiro é do dono, o `menu.py` já declara `painel = {owner}` e
o cliente já não dispara os pedidos de quem não o é.

A recusa é **403 com o `detail` do DRF e sem `code` novo** (decisão 6). Não é
200 com blocos ausentes: um 200 parcial torna "não podes ver" indistinguível de
"não há nada" — e um estabelecimento sem movimentos e uma conta `staff`
precisam de ecrãs opostos. O 403 é a rede do deep link e da pertença revogada
com a página aberta, que a ADR 0007 fez ser verificada **por pedido**.

## Views finas, e o que isso quer dizer aqui

Resolvem a janela (`periodos.py`), chamam uma leitura (`selectors.py`) e
serializam. Nenhuma aritmética de euros vive neste ficheiro: a identidade dos
três termos, o arredondamento e os sinais estão todos do outro lado, onde há
testes a apontar-lhes.

Com âmbito, como tudo o que não declara o contrário: nenhuma destas views leva
`tenant_scope_exempt`, e é essa ausência que as torna normais.
"""

from __future__ import annotations

from datetime import time

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import Papel, PertenceAoTenant, TemPapel, definicoes_do_ambito
from apps.reporting import periodos, selectors
from apps.reporting.serializers import (
    PERIODOS,
    FechoDoMesOutSerializer,
    RecusaDoPainelOutSerializer,
    ResumoDoPeriodoOutSerializer,
    SeriesDoPeriodoOutSerializer,
)

__all__ = ["FechoDoMesView", "ResumoDoPeriodoView", "SeriesDoPeriodoView"]

#: O período por omissão quando o parâmetro não vem. É o mesmo que o ecrã abre
#: e o mesmo que o servidor de fixtures servia — a janela mais curta que ainda
#: mostra uma tendência.
PERIODO_POR_OMISSAO = "7d"

PARAMETRO_DO_PERIODO = OpenApiParameter(
    "period",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    required=False,
    enum=PERIODOS,
    description="A janela a resolver. Por omissão, `7d`.",
)
PARAMETRO_DO_MES = OpenApiParameter(
    "month",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    required=True,
    description="O mês de negócio, em `YYYY-MM`.",
)


class AmbitoSemEstabelecimento(RuntimeError):
    """O âmbito do pedido não vê o seu próprio estabelecimento.

    Não é um caminho de cliente: o `TenantMiddleware` já confirmou a pertença
    **dentro** do âmbito, logo a linha do `accounts_tenant` é legível. Se isto
    levantar, é um defeito nosso e um 500 é a resposta honesta — servir um
    painel com uma hora de dia de negócio inventada seria pior.
    """


class _PainelView(APIView):
    """O que as três partilham: o gate, o relógio do negócio e o regime de IVA."""

    permission_classes = [IsAuthenticated, PertenceAoTenant, TemPapel.exige(Papel.OWNER)]

    def _estabelecimento(self, request: Request) -> tuple[time, str]:
        """A hora a que o dia de negócio começa e o regime de IVA, numa leitura só."""
        definicoes = definicoes_do_ambito(tenant_id=request.tenant.id)
        if definicoes is None:
            raise AmbitoSemEstabelecimento(str(request.tenant.id))
        return definicoes.business_day_starts_at, definicoes.vat_regime

    def _periodo(self, request: Request) -> str:
        """O `period` pedido, validado contra a união fechada.

        400 na mesma forma do 403 — `detail` e nada mais —, porque o cliente não
        tem aqui ramos para distinguir: o parâmetro já é validado em Zod na
        rota, e um valor fora da lista só chega por um link escrito à mão.
        """
        pedido = request.query_params.get("period", PERIODO_POR_OMISSAO)
        if pedido not in PERIODOS:
            raise ValidationError({"detail": f"Período desconhecido: {pedido!r}."})
        return pedido


class ResumoDoPeriodoView(_PainelView):
    """`GET /reporting/summary` — a mercadoria do período, e o que não se sabe."""

    @extend_schema(
        operation_id="reporting_resumo",
        summary="O resumo do período (painel de gestão)",
        parameters=[PARAMETRO_DO_PERIODO],
        responses={
            status.HTTP_200_OK: ResumoDoPeriodoOutSerializer,
            status.HTTP_400_BAD_REQUEST: RecusaDoPainelOutSerializer,
            status.HTTP_403_FORBIDDEN: RecusaDoPainelOutSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        inicio_do_dia, vat_regime = self._estabelecimento(request)
        janela = periodos.janela_do_periodo(
            key=self._periodo(request),
            inicio_do_dia=inicio_do_dia,
            agora=timezone.now(),
        )
        resumo = selectors.resumo_do_periodo(
            tenant_id=request.tenant.id, janela=janela, vat_regime=vat_regime
        )
        return Response(ResumoDoPeriodoOutSerializer(resumo).data)


class SeriesDoPeriodoView(_PainelView):
    """`GET /reporting/series` — os baldes do gráfico, com `Σ(points) == total_eur`."""

    @extend_schema(
        operation_id="reporting_series",
        summary="A mesma janela, intervalo a intervalo",
        parameters=[PARAMETRO_DO_PERIODO],
        responses={
            status.HTTP_200_OK: SeriesDoPeriodoOutSerializer,
            status.HTTP_400_BAD_REQUEST: RecusaDoPainelOutSerializer,
            status.HTTP_403_FORBIDDEN: RecusaDoPainelOutSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        inicio_do_dia, _ = self._estabelecimento(request)
        janela = periodos.janela_do_periodo(
            key=self._periodo(request),
            inicio_do_dia=inicio_do_dia,
            agora=timezone.now(),
        )
        series = selectors.series_do_periodo(tenant_id=request.tenant.id, janela=janela)
        return Response(SeriesDoPeriodoOutSerializer(series).data)


class FechoDoMesView(_PainelView):
    """`GET /reporting/month?month=YYYY-MM` — o mês de negócio, não o mês fiscal."""

    @extend_schema(
        operation_id="reporting_mes",
        summary="O fecho de um mês de negócio",
        parameters=[PARAMETRO_DO_MES],
        responses={
            status.HTTP_200_OK: FechoDoMesOutSerializer,
            status.HTTP_400_BAD_REQUEST: RecusaDoPainelOutSerializer,
            status.HTTP_403_FORBIDDEN: RecusaDoPainelOutSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        inicio_do_dia, vat_regime = self._estabelecimento(request)
        pedido = request.query_params.get("month", "")
        try:
            mes = periodos.janela_do_mes(
                mes=pedido,
                inicio_do_dia=inicio_do_dia,
                agora=timezone.now(),
            )
        except ValueError as erro:
            raise ValidationError(
                {"detail": "O mês pede-se em `YYYY-MM`."}
            ) from erro
        fecho = selectors.fecho_do_mes(
            tenant_id=request.tenant.id, mes=mes, vat_regime=vat_regime
        )
        return Response(FechoDoMesOutSerializer(fecho).data)
