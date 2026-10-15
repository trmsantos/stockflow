"""A porta do módulo `inventory` (ARCHITECTURE.md §3).

Fatia 2: localizações.
Fatia 3: lotes, movimentos, níveis de stock e custos.

Expõe DTOs (frozen dataclasses) e funções que outros módulos chamam via api.py.
Nenhuma escrita direta: tudo via services.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.inventory import selectors
from apps.inventory.models import Location, StockLevel
from apps.inventory.services import (
    Autor,
    MovementDTO,
    get_fefo_lot,
    get_or_create_lots,
    record_movements,
)

__all__ = [
    "ArtigoAbaixoDoMinimo",
    "Autor",
    "LocalizacaoResumo",
    "LoteAVencer",
    "LoteResumo",
    "MovimentoResumido",
    "MovimentoResumo",
    "ResumoDeMovimentos",
    "ResumoPorTipo",
    "SaldoDeStock",
    "SaldoPorLote",
    "CustoMedioDeArtigo",
    "artigos_abaixo_do_minimo",
    "criar_localizacao",
    "listar_localizacoes",
    "localizacoes_por_id",
    "lotes_a_vencer",
    "movimentos_resumidos",
    "obter_localizacao",
    "get_or_create_lots",
    "record_movements",
    "MovementDTO",
    "get_fefo_lot",
    "get_stock_level",
    "movimentos_por_periodo",
    "movimentos_por_produto",
    "saldos_por_artigo",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class LocalizacaoResumo:
    """Uma localização como os outros módulos a veem."""

    id: UUID
    name: str
    is_active: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class LoteResumo:
    """Um lote como o resto do sistema o vê."""

    id: UUID
    product_id: UUID
    code: str
    expires_at: datetime | None
    received_at: datetime


@dataclass(frozen=True, kw_only=True, slots=True)
class MovimentoResumo:
    """Um movimento do ledger de stock."""

    id: UUID
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal
    occurred_at: datetime
    created_by_name: str


@dataclass(frozen=True, kw_only=True, slots=True)
class SaldoDeStock:
    """Saldo de um artigo numa localização e lote."""

    product_id: UUID
    location_id: UUID
    lot_id: UUID | None
    quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class CustoMedioDeArtigo:
    """Custo médio ponderado de um artigo numa localização."""

    product_id: UUID
    location_id: UUID
    unit_cost: Decimal


# ---------------------------------------------------------------------------
# As leituras do assistente (ADR 0027, decisão 6). DTOs congelados: nenhum
# modelo atravessa a porta, e as quantidades vêm na unidade **base** com o par
# `display_unit`/`display_factor` ao lado, para quem lê as apresentar.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class SaldoPorLote:
    """Uma linha de saldo de um artigo: localização, lote, validade, quantidade."""

    product_id: UUID
    location_id: UUID
    location_name: str
    lot_id: UUID | None
    lot_code: str | None
    expires_at: datetime | None
    quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ArtigoAbaixoDoMinimo:
    """Um artigo cujo saldo somado está abaixo do mínimo do artigo."""

    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    min_quantity: Decimal
    saldo: Decimal
    #: `sem_stock` (saldo ≤ 0 com `StockLevel`) ou `abaixo_do_minimo`.
    estado: str


@dataclass(frozen=True, kw_only=True, slots=True)
class LoteAVencer:
    """Um lote com saldo que vence até à data pedida — ou já venceu."""

    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    #: `use_by`, `best_before` ou `""` (sem rótulo).
    expiry_kind: str
    conservation: str
    lot_id: UUID
    lot_code: str
    expires_at: datetime
    #: A data no calendário local — é por ela que se compara.
    expires_on: date
    saldo: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ResumoPorTipo:
    """Quantos movimentos de um tipo, e a quantidade com sinal."""

    movement_type: str
    n: int
    quantidade: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class MovimentoResumido:
    """Uma linha do ledger, como o assistente a lê."""

    id: UUID
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal
    cost_is_estimate: bool
    occurred_at: datetime
    location_name: str
    lot_code: str | None
    reason: str | None
    reference: str | None
    transfer_id: UUID | None
    #: A localização do outro lado de uma transferência, quando há.
    contraparte: str | None
    created_by_name: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ResumoDeMovimentos:
    """O resumo por tipo do período inteiro mais as últimas linhas."""

    resumo: tuple[ResumoPorTipo, ...]
    linhas: tuple[MovimentoResumido, ...]
    truncado: bool


def listar_localizacoes(*, tenant_id: UUID) -> tuple[LocalizacaoResumo, ...]:
    """As localizações do estabelecimento, por posição, activas ou não."""
    return tuple(
        LocalizacaoResumo(id=loc.id, name=loc.name, is_active=loc.is_active)
        for loc in selectors.listar_localizacoes(tenant_id=tenant_id)
    )


def saldos_por_artigo(
    *, tenant_id: UUID, product_id: UUID, location_id: UUID | None = None, limite: int = 50
) -> tuple[SaldoPorLote, ...] | None:
    """Os saldos de um artigo por localização e lote, em FEFO.

    `None` quando o artigo **nunca entrou** (não tem `StockLevel` nenhum); uma
    tupla — possivelmente de zeros — quando entrou. É a diferença que a resposta
    "nunca recebemos este artigo" precisa (ADR 0027).
    """
    niveis = list(
        selectors.saldos_do_artigo(
            tenant_id=tenant_id, product_id=product_id, location_id=location_id
        )[:limite]
    )
    if not niveis:
        return None
    return tuple(
        SaldoPorLote(
            product_id=nivel.product_id,
            location_id=nivel.location_id,
            location_name=nivel.location.name,
            lot_id=nivel.lot_id,
            lot_code=nivel.lot.code if nivel.lot is not None else None,
            expires_at=nivel.lot.expires_at if nivel.lot is not None else None,
            quantity=nivel.quantity,
            unit_cost=nivel.unit_cost,
        )
        for nivel in niveis
    )


def artigos_abaixo_do_minimo(
    *, tenant_id: UUID, location_id: UUID | None = None, limite: int = 50
) -> tuple[tuple[ArtigoAbaixoDoMinimo, ...], bool]:
    """Os artigos abaixo do mínimo **do artigo** (saldo somado), e se cortou."""
    linhas = selectors.artigos_abaixo_do_minimo(
        tenant_id=tenant_id, location_id=location_id, limite=limite
    )
    truncado = len(linhas) > limite
    return tuple(ArtigoAbaixoDoMinimo(**linha) for linha in linhas[:limite]), truncado


def lotes_a_vencer(
    *,
    tenant_id: UUID,
    hoje: date,
    dias: int,
    location_id: UUID | None = None,
    limite: int = 50,
) -> tuple[tuple[LoteAVencer, ...], bool]:
    """Os lotes com saldo que vencem até `hoje + dias`, vencidos incluídos, e se cortou."""
    linhas = selectors.lotes_a_vencer(
        tenant_id=tenant_id, hoje=hoje, dias=dias, location_id=location_id, limite=limite
    )
    truncado = len(linhas) > limite
    return tuple(LoteAVencer(**linha) for linha in linhas[:limite]), truncado


def movimentos_resumidos(
    *,
    tenant_id: UUID,
    product_id: UUID,
    desde: datetime,
    ate: datetime,
    tipos: Sequence[str] | None = None,
    limite: int = 20,
) -> ResumoDeMovimentos:
    """O resumo por tipo e as últimas linhas de um artigo em `[desde, ate)`."""
    dados = selectors.movimentos_resumidos(
        tenant_id=tenant_id,
        product_id=product_id,
        desde=desde,
        ate=ate,
        tipos=tipos,
        limite=limite,
    )
    return ResumoDeMovimentos(
        resumo=tuple(
            ResumoPorTipo(movement_type=tipo, n=valor["n"], quantidade=valor["quantidade"])
            for tipo, valor in dados["resumo"].items()
        ),
        linhas=tuple(MovimentoResumido(**linha) for linha in dados["linhas"]),
        truncado=dados["truncado"],
    )


def localizacoes_por_id(
    *, tenant_id: UUID, ids: Sequence[UUID]
) -> Mapping[UUID, LocalizacaoResumo]:
    """Localizações pelo ID, num mapa."""
    localizacoes = Location.objects.filter(tenant_id=tenant_id, id__in=ids)
    return {
        loc.id: LocalizacaoResumo(
            id=loc.id,
            name=loc.name,
            is_active=loc.is_active,
        )
        for loc in localizacoes
    }


def get_stock_level(
    *, tenant_id: UUID, product_id: UUID, location_id: UUID, lot_id: UUID | None = None
) -> SaldoDeStock | None:
    """Obtém o nível de stock para uma chave (product, location, lot)."""
    nivel = StockLevel.objects.filter(
        tenant_id=tenant_id,
        product_id=product_id,
        location_id=location_id,
        lot_id=lot_id,
    ).first()
    if nivel is None:
        return None
    return SaldoDeStock(
        product_id=nivel.product_id,
        location_id=nivel.location_id,
        lot_id=nivel.lot_id,
        quantity=nivel.quantity,
        unit_cost=nivel.unit_cost,
    )


def obter_localizacao(
    *, tenant_id: UUID, location_id: UUID
) -> LocalizacaoResumo | None:
    """Obtém uma localização pelo ID. Retorna None se não existe ou não está ativa."""
    localizacao = Location.objects.filter(
        tenant_id=tenant_id, id=location_id, is_active=True
    ).first()
    if localizacao is None:
        return None
    return LocalizacaoResumo(
        id=localizacao.id,
        name=localizacao.name,
        is_active=localizacao.is_active,
    )


@transaction.atomic
def criar_localizacao(
    *,
    tenant_id: UUID,
    name: str,
    position: int | None = None,
    id: UUID | None = None,
) -> LocalizacaoResumo:
    """Criar uma localização (ou retornar a existente). Consumidor: `apps/demo`.

    Se `position` é None, usa o máximo existente + 1.
    """
    from django.db.models import Max

    try:
        loc = Location.objects.get(tenant_id=tenant_id, name__iexact=name)
    except Location.DoesNotExist:
        if position is None:
            max_pos = (
                Location.objects.filter(tenant_id=tenant_id).aggregate(
                    max_pos=Max("position")
                )["max_pos"]
                or 0
            )
            position = max_pos + 1

        loc = Location.objects.create(
            id=id,
            tenant_id=tenant_id,
            name=name,
            position=position,
        )
    return LocalizacaoResumo(
        id=loc.id,
        name=loc.name,
        is_active=loc.is_active,
    )


def movimentos_por_periodo(
    *,
    tenant_id: UUID,
    year: int,
    month: int,
) -> list:
    """Obtém movimentos de um período específico (QuerySet). Consumidor: `apps/reporting`."""
    from apps.inventory.models import StockMovement

    return list(StockMovement.objects.filter(
        tenant_id=tenant_id,
        occurred_at__year=year,
        occurred_at__month=month,
    ))


def movimentos_por_produto(
    *,
    tenant_id: UUID,
    product_id: UUID,
    movement_types: list[str] | None = None,
) -> list:
    """Obtém movimentos de um produto, filtrados por tipo. Consumidor: `apps/reporting`."""
    from apps.inventory.models import StockMovement

    qs = StockMovement.objects.filter(tenant_id=tenant_id, product_id=product_id)
    if movement_types:
        qs = qs.filter(movement_type__in=movement_types)

    return list(qs)
