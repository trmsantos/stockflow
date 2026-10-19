"""A porta do módulo `inventory` (ARCHITECTURE.md §3).

Fatia 2: localizações.
Fatia 3: lotes, movimentos, níveis de stock e custos.

Expõe DTOs (frozen dataclasses) e funções que outros módulos chamam via api.py.
Nenhuma escrita direta: tudo via services.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.inventory import selectors
from apps.inventory.models import Location, StockCountLine, StockLevel
from apps.inventory.services import (
    Autor,
    MovementDTO,
    get_fefo_lot,
    get_or_create_lots,
    record_movements,
)

__all__ = [
    "AgregadoDeDesperdicio",
    "AgregadoDeMovimentos",
    "AgregadoDiarioDeMovimentos",
    "AlertaResumo",
    "ArtigoAbaixoDoMinimo",
    "Autor",
    "ContagemDetalhe",
    "ContagemResumo",
    "CustoPorLocalizacao",
    "DesperdicioPorArtigo",
    "IngredienteProduzido",
    "LinhaDeContagem",
    "LocalizacaoResumo",
    "ProducaoResumo",
    "ResumoDeAlertas",
    "ResumoDeDesperdicio",
    "contagem_por_id",
    "custos_medios_por_artigo",
    "desperdicio_recente",
    "listar_contagens",
    "producoes_por_periodo",
    "resumo_de_alertas",
    "LoteAVencer",
    "LoteResumo",
    "MovimentoResumido",
    "MovimentoResumo",
    "ResumoDeMovimentos",
    "ResumoPorTipo",
    "SaldoDeStock",
    "SaldoPorLote",
    "CustoMedioDeArtigo",
    "ValorDeStock",
    "artigos_abaixo_do_minimo",
    "criar_localizacao",
    "desperdicio_agregado_por_motivo",
    "listar_localizacoes",
    "localizacoes_por_id",
    "lotes_a_vencer",
    "movimentos_agregados_por_dia_de_negocio",
    "movimentos_agregados_por_tipo",
    "movimentos_resumidos",
    "obter_localizacao",
    "get_or_create_lots",
    "record_movements",
    "MovementDTO",
    "get_fefo_lot",
    "get_stock_level",
    "saldos_por_artigo",
    "ultima_contagem_fechada_em",
    "valor_de_stock",
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


# ===========================================================================
# Os agregados do painel (ADR 0029, decisão 2).
#
# Substituem o par `movimentos_por_periodo`/`movimentos_por_produto`, que
# devolvia **instâncias ORM** através da fronteira — uma porta que deixa passar
# um modelo é uma fronteira que só existe no papel, e o consumidor delas (o
# antigo `reporting/services.py`) iterava o ledger em Python, que é o que a
# ADR 0013 decisão 5 proíbe. Estas devolvem DTOs congelados e o `GROUP BY`
# acontece no Postgres.
#
# **Duas promessas que quem lê tem de conhecer**, e são as que permitem que a
# identidade da ADR 0013 decisão 4 feche ao cêntimo:
#
#   * **nada vem arredondado.** `SUM(quantity × unit_cost)` é `numeric` exato;
#     o arredondamento a duas casas é apresentação e faz-se uma vez, à saída de
#     quem lê;
#   * **nada vem com o sinal lido.** Uma saída é negativa aqui, porque é
#     negativa no ledger. Quem serve "positivo = quebra" nega uma vez, no seu
#     lado. O `DesperdicioPorArtigo` acima é o outro contrato — esse promete
#     valores positivos — e a diferença está escrita nos dois sítios de
#     propósito.
# ===========================================================================
@dataclass(frozen=True, kw_only=True, slots=True)
class AgregadoDeMovimentos:
    """Σ de um tipo de movimento numa janela, como o ledger o gravou."""

    movement_type: str
    n: int
    quantidade: Decimal
    valor_eur: Decimal
    #: A parte de `valor_eur` cujo custo ainda não tem fatura atrás
    #: (`cost_is_estimate`). É **decomposição e nunca parcela**: já está dentro
    #: do `valor_eur`, porque a mercadoria entrou.
    valor_estimado_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class AgregadoDiarioDeMovimentos:
    """O mesmo agregado com o balde do **dia de negócio** ao lado do tipo."""

    dia: date
    movement_type: str
    n: int
    quantidade: Decimal
    valor_eur: Decimal
    valor_estimado_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class AgregadoDeDesperdicio:
    """Σ dos `waste` de uma janela por motivo. Sem truncatura: são cinco."""

    #: `expired`, `spoiled`, `prep_loss`, `breakage`, `other` — ou `""` quando
    #: o movimento ficou sem motivo.
    reason: str
    n: int
    quantidade: Decimal
    valor_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ValorDeStock:
    """O valor do stock **a um instante**, com o instante ao lado.

    `as_of` não é cromado: o valor é `Σ(saldo × CMP)` lido agora, logo no fecho
    de um mês passado o número é o de hoje e o ecrã tem de o poder dizer.
    """

    valor_eur: Decimal
    as_of: datetime


def movimentos_agregados_por_tipo(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> tuple[AgregadoDeMovimentos, ...]:
    """Σ do ledger em `[desde, ate)`, uma linha por tipo de movimento presente."""
    return tuple(
        AgregadoDeMovimentos(**linha)
        for linha in selectors.movimentos_agregados_por_tipo(
            tenant_id=tenant_id, desde=desde, ate=ate
        )
    )


def movimentos_agregados_por_dia_de_negocio(
    *, tenant_id: UUID, desde: datetime, ate: datetime, inicio_do_dia: time
) -> tuple[AgregadoDiarioDeMovimentos, ...]:
    """O mesmo, com o balde do dia de negócio — `Σ(dias) == janela` por construção."""
    return tuple(
        AgregadoDiarioDeMovimentos(**linha)
        for linha in selectors.movimentos_agregados_por_dia_de_negocio(
            tenant_id=tenant_id, desde=desde, ate=ate, inicio_do_dia=inicio_do_dia
        )
    )


def desperdicio_agregado_por_motivo(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> tuple[AgregadoDeDesperdicio, ...]:
    """Σ dos `waste` de `[desde, ate)` por motivo, sem corte e sem limiar."""
    return tuple(
        AgregadoDeDesperdicio(**linha)
        for linha in selectors.desperdicio_agregado_por_motivo(
            tenant_id=tenant_id, desde=desde, ate=ate
        )
    )


def valor_de_stock(*, tenant_id: UUID) -> ValorDeStock:
    """`Σ(saldo × CMP)` de todas as localizações, e o instante em que foi lido."""
    return ValorDeStock(
        valor_eur=selectors.valor_de_stock(tenant_id=tenant_id),
        as_of=timezone.now(),
    )


def ultima_contagem_fechada_em(*, tenant_id: UUID) -> datetime | None:
    """Quando a última contagem **fechada** fechou. `None` se nunca houve nenhuma."""
    return selectors.ultima_contagem_fechada_em(tenant_id=tenant_id)


# ===========================================================================
# As leituras da ADR 0028: contagens, alertas, desperdício, produções, CMP.
# DTOs congelados, quantidades na unidade **base** com `display_unit` e
# `display_factor` ao lado. Nenhum modelo atravessa a porta.
# ===========================================================================
@dataclass(frozen=True, kw_only=True, slots=True)
class ContagemResumo:
    """Uma contagem como a lista a mostra: onde, quando, em que estado e quanto falta."""

    id: UUID
    location_id: UUID
    location_name: str
    #: `open` ou `closed`. É a coluna, não uma derivação.
    status: str
    started_at: datetime
    closed_at: datetime | None
    created_by_name: str
    closed_by_name: str
    n_linhas: int
    n_contadas: int
    n_por_contar: int


@dataclass(frozen=True, kw_only=True, slots=True)
class LinhaDeContagem:
    """Uma linha de contagem: o que o sistema esperava e o que a pessoa contou.

    `quantity_counted` a `None` é **por contar** e nunca zero: zero é "contei e
    não havia nada", que é uma diferença e não uma pendência.

    `unit_cost` é o do `(artigo, localização, lote)` — com o lote, que é a
    correcção da ADR 0028 — e serve para valorizar a diferença. Quem lê só o
    mostra a quem pode ver euros.
    """

    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    lot_id: UUID | None
    #: `None` quando não há lote **ou** quando o lote é sintético (`__…__`).
    lot_code: str | None
    zone: str
    quantity_expected: Decimal
    quantity_counted: Decimal | None
    unit_cost: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ContagemDetalhe:
    """Uma contagem inteira: o resumo, as linhas e os ajustes que o fecho gravou."""

    resumo: ContagemResumo
    linhas: tuple[LinhaDeContagem, ...]
    truncado: bool
    #: Quantos `adjustment` o fecho gravou, o seu valor e quando. Zero numa
    #: contagem aberta: ela ainda não mexeu no stock.
    ajustes: int
    ajustes_eur: Decimal
    ajustes_em: datetime | None


@dataclass(frozen=True, kw_only=True, slots=True)
class AlertaResumo:
    """Uma linha de alerta, já com o tipo e a gravidade que o painel usa."""

    tipo: str
    gravidade: str
    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    lot_code: str | None
    expires_on: date | None
    dias: int | None
    saldo: Decimal | None
    min_quantity: Decimal | None


@dataclass(frozen=True, kw_only=True, slots=True)
class DesperdicioPorArtigo:
    """Σ dos `waste` de um artigo por motivo no período, com o valor gravado."""

    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    reason: str
    n: int
    #: Positiva: é o que **se perdeu**, e o sinal do ledger já foi lido.
    quantidade: Decimal
    valor_eur: Decimal
    linhas_sem_custo: int


@dataclass(frozen=True, kw_only=True, slots=True)
class ResumoDeDesperdicio:
    """O desperdício de um período: as linhas, o total e se a lista cortou."""

    desde: datetime
    ate: datetime
    linhas: tuple[DesperdicioPorArtigo, ...]
    total_eur: Decimal
    truncado: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class ResumoDeAlertas:
    """O que o ecrã Alertas calcula, pela porta: falta, validade e desperdício."""

    falta: tuple[AlertaResumo, ...]
    validade: tuple[AlertaResumo, ...]
    desperdicio: ResumoDeDesperdicio | None
    truncado: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class IngredienteProduzido:
    """Um ingrediente que saiu numa produção (`production_out`)."""

    product_id: UUID
    product_name: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    quantidade: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ProducaoResumo:
    """Uma produção: o par `production_out`/`production_in` do mesmo `production_id`."""

    production_id: UUID
    occurred_at: datetime
    location_name: str
    created_by_name: str
    product_id: UUID | None
    product_name: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    quantidade: Decimal
    #: O custo real daquela produção, gravado no momento (ADR 0026, decisão 2).
    unit_cost: Decimal
    ingredientes: tuple[IngredienteProduzido, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class CustoPorLocalizacao:
    """O custo médio ponderado de um artigo numa localização. Zero é desconhecido."""

    location_id: UUID
    location_name: str
    unit_cost: Decimal


#: A janela de validade dos alertas: sete dias, como no painel.
DIAS_DE_VALIDADE = selectors.DIAS_DE_VALIDADE_DO_PAINEL


def _gravidade_da_validade(lote: LoteAVencer, *, hoje: date) -> str:
    """Vencido com "consumir até" é crítico; o resto é aviso ou informação."""
    dias = (lote.expires_on - hoje).days
    if dias < 0:
        return "critico" if lote.expiry_kind == "use_by" else "aviso"
    if dias == 0:
        return "aviso" if lote.expiry_kind == "use_by" else "info"
    return "info"


def _resumo_de_contagem(
    contagem: object, *, linhas: list[StockCountLine] | None = None
) -> ContagemResumo:
    """O `ContagemResumo` de uma linha, com as contagens de linhas já feitas."""
    if linhas is None:
        agregado = StockCountLine.objects.filter(
            tenant_id=contagem.tenant_id, stock_count_id=contagem.id
        ).aggregate(
            total=Count("id"), contadas=Count("id", filter=Q(quantity_counted__isnull=False))
        )
        total = agregado["total"] or 0
        contadas = agregado["contadas"] or 0
    else:
        total = len(linhas)
        contadas = sum(1 for linha in linhas if linha.quantity_counted is not None)
    return ContagemResumo(
        id=contagem.id,
        location_id=contagem.location_id,
        location_name=contagem.location.name,
        status=contagem.status,
        started_at=contagem.started_at,
        closed_at=contagem.closed_at,
        created_by_name=getattr(contagem.created_by, "email", "") or "",
        closed_by_name=getattr(contagem.closed_by, "email", "") or "",
        n_linhas=total,
        n_contadas=contadas,
        n_por_contar=total - contadas,
    )


def listar_contagens(
    *, tenant_id: UUID, estado: str = "", limite: int = 20
) -> tuple[tuple[ContagemResumo, ...], bool]:
    """As contagens por estado (`open`/`closed`), e se a lista cortou."""
    contagens = selectors.listar_contagens(tenant_id=tenant_id, estado=estado, limite=limite)
    truncado = len(contagens) > limite
    return tuple(_resumo_de_contagem(c) for c in contagens[:limite]), truncado


def contagem_por_id(
    *, tenant_id: UUID, stock_count_id: UUID, limite: int = 60
) -> ContagemDetalhe | None:
    """Uma contagem com as suas linhas, ou `None` se não existir neste tenant."""
    contagem = selectors.contagens_do_ambito(tenant_id=tenant_id).filter(pk=stock_count_id).first()
    if contagem is None:
        return None
    linhas = selectors.linhas_da_contagem(tenant_id=tenant_id, stock_count_id=stock_count_id)
    custos = selectors.custos_dos_niveis(
        tenant_id=tenant_id,
        location_id=contagem.location_id,
        chaves=[(linha.product_id, linha.lot_id) for linha in linhas],
    )
    ajustes = selectors.ajustes_da_contagem(tenant_id=tenant_id, stock_count_id=stock_count_id)
    return ContagemDetalhe(
        resumo=_resumo_de_contagem(contagem, linhas=linhas),
        linhas=tuple(
            LinhaDeContagem(
                id=linha.id,
                product_id=linha.product_id,
                product_name=linha.product.short_name,
                sku=linha.product.sku,
                base_unit=linha.product.base_unit,
                display_unit=linha.product.display_unit,
                display_factor=linha.product.display_factor,
                lot_id=linha.lot_id,
                lot_code=(
                    None
                    if linha.lot is None or selectors.e_lote_sintetico(linha.lot.code)
                    else linha.lot.code
                ),
                zone=linha.zone or "",
                quantity_expected=linha.quantity_expected,
                quantity_counted=linha.quantity_counted,
                unit_cost=custos.get((linha.product_id, linha.lot_id), Decimal("0")),
            )
            for linha in linhas[:limite]
        ),
        truncado=len(linhas) > limite,
        ajustes=ajustes["n"],
        ajustes_eur=ajustes["valor_eur"],
        ajustes_em=ajustes["ultimo_em"],
    )


def desperdicio_recente(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 30
) -> ResumoDeDesperdicio:
    """Σ dos `waste` de `[desde, ate)` por artigo e motivo. Sem limiar."""
    linhas = selectors.desperdicio_por_artigo_e_motivo(
        tenant_id=tenant_id, desde=desde, ate=ate, limite=limite
    )
    truncado = len(linhas) > limite
    itens = tuple(DesperdicioPorArtigo(**linha) for linha in linhas[:limite])
    return ResumoDeDesperdicio(
        desde=desde,
        ate=ate,
        linhas=itens,
        total_eur=sum((item.valor_eur for item in itens), Decimal("0")),
        truncado=truncado,
    )


def resumo_de_alertas(
    *,
    tenant_id: UUID,
    hoje: date,
    tipo: str = "todos",
    gravidade: str = "",
    desperdicio_desde: datetime | None = None,
    desperdicio_ate: datetime | None = None,
    limite: int = 30,
) -> ResumoDeAlertas:
    """O que o ecrã Alertas calcula, pela porta (ADR 0028).

    `hoje` é o dia **civil**: as validades são a data impressa na embalagem e
    não se deslocam pelo relógio do negócio. O desperdício é o outro lado — os
    `waste` de um período de dias **de negócio**, que quem chama delimita.
    """
    falta: tuple[AlertaResumo, ...] = ()
    validade: tuple[AlertaResumo, ...] = ()
    truncado = False
    if tipo in ("falta", "todos"):
        linhas, cortou = artigos_abaixo_do_minimo(tenant_id=tenant_id, limite=limite)
        truncado = truncado or cortou
        falta = tuple(
            AlertaResumo(
                tipo="falta",
                gravidade="critico" if linha.estado == selectors.SEM_STOCK else "aviso",
                product_id=linha.product_id,
                product_name=linha.product_name,
                sku=linha.sku,
                base_unit=linha.base_unit,
                display_unit=linha.display_unit,
                display_factor=linha.display_factor,
                lot_code=None,
                expires_on=None,
                dias=None,
                saldo=linha.saldo,
                min_quantity=linha.min_quantity,
            )
            for linha in linhas
        )
    if tipo in ("validade", "todos"):
        lotes, cortou = lotes_a_vencer(
            tenant_id=tenant_id, hoje=hoje, dias=DIAS_DE_VALIDADE, limite=limite
        )
        truncado = truncado or cortou
        validade = tuple(
            AlertaResumo(
                tipo="validade",
                gravidade=_gravidade_da_validade(lote, hoje=hoje),
                product_id=lote.product_id,
                product_name=lote.product_name,
                sku=lote.sku,
                base_unit=lote.base_unit,
                display_unit=lote.display_unit,
                display_factor=lote.display_factor,
                lot_code=lote.lot_code,
                expires_on=lote.expires_on,
                dias=(lote.expires_on - hoje).days,
                saldo=lote.saldo,
                min_quantity=None,
            )
            for lote in lotes
        )
    desperdicio = None
    if tipo in ("desperdicio", "todos") and desperdicio_desde and desperdicio_ate:
        desperdicio = desperdicio_recente(
            tenant_id=tenant_id, desde=desperdicio_desde, ate=desperdicio_ate, limite=limite
        )
        truncado = truncado or desperdicio.truncado
    if gravidade:
        falta = tuple(linha for linha in falta if linha.gravidade == gravidade)
        validade = tuple(linha for linha in validade if linha.gravidade == gravidade)
    return ResumoDeAlertas(
        falta=falta, validade=validade, desperdicio=desperdicio, truncado=truncado
    )


def producoes_por_periodo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 20
) -> tuple[tuple[ProducaoResumo, ...], bool]:
    """As produções de `[desde, ate)`, uma por `production_id`, e se cortou."""
    linhas = selectors.producoes_por_periodo(
        tenant_id=tenant_id, desde=desde, ate=ate, limite=limite
    )
    truncado = len(linhas) > limite
    return (
        tuple(
            ProducaoResumo(
                production_id=linha["production_id"],
                occurred_at=linha["occurred_at"],
                location_name=linha["location_name"],
                created_by_name=linha["created_by_name"],
                product_id=linha["product_id"],
                product_name=linha["product_name"],
                base_unit=linha["base_unit"],
                display_unit=linha["display_unit"],
                display_factor=linha["display_factor"],
                quantidade=linha["quantidade"],
                unit_cost=linha["unit_cost"],
                ingredientes=tuple(
                    IngredienteProduzido(**ingrediente) for ingrediente in linha["ingredientes"]
                ),
            )
            for linha in linhas[:limite]
        ),
        truncado,
    )


def custos_medios_por_artigo(
    *, tenant_id: UUID, product_id: UUID
) -> tuple[CustoPorLocalizacao, ...]:
    """O CMP de um artigo por localização. Zero é "preço desconhecido" (ADR 0024)."""
    return tuple(
        CustoPorLocalizacao(
            location_id=linha["location_id"],
            location_name=linha["location_name"],
            unit_cost=linha["unit_cost"],
        )
        for linha in selectors.custos_medios_do_artigo(tenant_id=tenant_id, product_id=product_id)
    )
