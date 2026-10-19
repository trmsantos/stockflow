"""As leituras do painel. **Nenhuma escreve** — e é por isso que não há `services.py`.

O nome `services.py` nesta casa significa escrita (ARCHITECTURE.md §3), e este
módulo não escreve nada: cruza o `accounts.api` e o `inventory.api` e compõe os
três payloads do painel (ADR 0029, decisão 2). Sem `models.py`, sem `api.py`,
sem migração e sem política — está coberto pela RLS sem possuir nenhuma, porque
toda a query nasce dentro do âmbito do pedido.

## A identidade, e onde é que o cêntimo se decide

> `stock_change == purchases − goods_consumed − unknown_shrinkage`

Os quatro termos são o **mesmo agregado do mesmo ledger na mesma janela**,
classificado **por tipo de movimento** e nunca por "soma de tudo o que entrou":

| Termo | Tipos | Sinal servido |
|---|---|---|
| `purchases` | `receipt` + `return` | como o ledger (uma devolução **reduz**) |
| `goods_consumed` | `consumption` + `waste` | positivo = saiu do stock |
| `unknown_shrinkage` | `adjustment` | positivo = **quebra** |
| `stock_change` | derivado dos três | positivo = encheu-se a despensa |

Fora dos quatro, **por tipo e não por fé**: `production_in`/`production_out`
(contar a produção própria era contar os ingredientes e o acabado — ADR 0014) e
`transfer_in`/`transfer_out` (mudar de sítio não é um evento económico). Os dois
pares anulam-se ao nível do tenant, mas a exclusão é por tipo: no dia em que o
painel for filtrado por loja, uma transferência deixa de se anular e esta linha
continua certa.

O arredondamento é **uma vez, à saída**. O `SUM(quantity × unit_cost)` do
Postgres é `numeric` exato e chega aqui com as seis casas do `unit_cost`;
arredonda-se cada um dos três termos a duas casas e o `stock_change` é a
subtracção **dos já arredondados**, pelo que o resíduo (≤ 1 cêntimo) cai na
linha derivada em vez de abrir uma linha "diferença" que ninguém sabe ler. Se a
identidade **antes** do arredondamento não der exactamente zero, não é
arredondamento: é um tipo mal classificado, e é isso que o teste afirma.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from uuid import UUID

from apps.inventory import api as inventory_api
from apps.reporting.periodos import Balde, Janela, JanelaDoMes, baldes, granularidade_de

__all__ = [
    "BucketOut",
    "CostComponentOut",
    "DataQualityOut",
    "MonthOut",
    "OtherCostOut",
    "PayrollPartOut",
    "PeriodOut",
    "PointOut",
    "RoleCostOut",
    "SerieOut",
    "SeriesOut",
    "SummaryOut",
    "TermosBrutos",
    "WasteByReasonOut",
    "fecho_do_mes",
    "resumo_do_periodo",
    "series_do_periodo",
]

#: Os tipos que são compra: uma receção entra, uma devolução sai e **reduz** as
#: compras no período do movimento (ADR 0014). Um mês com mais devoluções do
#: que entradas dá compras negativas, e serve-se assim: o número é verdade.
TIPOS_DE_COMPRA = ("receipt", "return")
#: O que saiu do stock para ser usado ou perdido. O desperdício é **parte** da
#: mercadoria consumida e não uma parcela a somar ao lado dela.
TIPOS_DE_CONSUMO = ("consumption", "waste")
#: A quebra que ninguém viu: o líquido dos ajustes, de contagem (ADR 0025) ou
#: manuais. Não é desperdício — é accionável sobre o processo e tem linha
#: própria (ADR 0013, decisão 7).
TIPO_DE_QUEBRA = "adjustment"
#: Os quatro que **não** são evento económico, excluídos por tipo.
TIPOS_SEM_EVENTO = ("production_in", "production_out", "transfer_in", "transfer_out")

#: O que o painel não sabe hoje, por falta de módulo e não por falta de dados:
#: sem `sales` não há receita, sem `people` não há salários, sem
#: `purchasing_othercost` não há custos fixos (ADR 0029, decisão 1). Viaja uma
#: vez, em ids; as palavras vivem no `vocabulario.ts`.
INDISPONIVEL = ("revenue", "payroll", "other_costs")

CENTIMO = Decimal("0.01")
MILESIMO = Decimal("0.001")
ZERO = Decimal("0")


def euros(valor: Decimal) -> Decimal:
    """Duas casas, meio para cima. **O único sítio onde se arredonda dinheiro.**"""
    return valor.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def fraccao(*, parte: Decimal, todo: Decimal) -> Decimal:
    """`parte/todo` com três casas, ou zero quando não há denominador.

    É o `share` do contrato: com ele a única aritmética do SVG é
    `share × píxeis`. Calcula-se sobre os valores **não arredondados**, porque
    um share é uma proporção e não um dinheiro — e nunca se soma no ecrã.
    """
    if todo == ZERO:
        return ZERO.quantize(MILESIMO)
    return (parte / todo).quantize(MILESIMO, rounding=ROUND_HALF_UP)


def repartir(*, total: Decimal, partes: Sequence[Decimal]) -> tuple[Decimal, ...]:
    """Arredonda `partes` a cêntimos de modo a que a soma **seja** `total`.

    Maior resto: cada parte desce ao cêntimo inferior e os cêntimos que faltam
    para o total vão para quem tem o maior resto. É o que faz
    `Σ(waste_by_reason) == waste_eur` e `Σ(points) == total_eur` serem
    igualdades e não aproximações — uma barra que não soma o número ao lado
    custa mais credibilidade do que um sinal trocado (ADR 0013, decisão 8).

    `ROUND_FLOOR` e não `ROUND_DOWN`: o chão tem de ser monótono também em
    baixo de zero, e uma compra negativa (nota de crédito de devolução) é um
    balde legítimo.
    """
    if not partes:
        return ()
    pisos = [parte.quantize(CENTIMO, rounding=ROUND_FLOOR) for parte in partes]
    restos = [parte - piso for parte, piso in zip(partes, pisos, strict=True)]
    em_falta = int((total - sum(pisos, ZERO)) / CENTIMO)
    if not 0 <= em_falta <= len(partes):
        # Só acontece se `total` não for a soma de `partes` — isto é, se as
        # partes tiverem deixado de cobrir o todo (um dia de negócio fora de
        # todos os baldes, um motivo filtrado). Levanta em vez de repartir o
        # que puder: um número errado em silêncio num ecrã de dinheiro é pior
        # do que um 500.
        raise ValueError(
            f"repartição impossível: {total} não é a soma de {len(partes)} partes"
        )
    ordem = sorted(range(len(partes)), key=lambda indice: (-restos[indice], indice))
    valores = list(pisos)
    for indice in ordem[:em_falta]:
        valores[indice] += CENTIMO
    return tuple(valores)


# ---------------------------------------------------------------------------
# Os DTOs do contrato. Nomes e campos são os da ADR 0013 decisão 5, letra por
# letra: os serializers lêem-nos por atributo e não os traduzem.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class PeriodOut:
    """O período resolvido, ecoado: mostrar a fronteira, não escondê-la."""

    key: str
    since: datetime
    until: datetime
    business_day_starts_at: str


@dataclass(frozen=True, kw_only=True, slots=True)
class CostComponentOut:
    """Uma parcela de custo. O cliente desenha; não compõe e não soma."""

    id: str
    amount_eur: Decimal
    share: Decimal
    is_part_of_total: bool
    part_of: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class WasteByReasonOut:
    """Quanto se perdeu por motivo, e quantas vezes."""

    reason: str
    amount_eur: Decimal
    share: Decimal
    movements: int


@dataclass(frozen=True, kw_only=True, slots=True)
class DataQualityOut:
    """O painel declara o que não sabe, e a declaração é parte do contrato."""

    consumption_registered: bool
    purchases_awaiting_invoice_eur: Decimal
    last_count_at: datetime | None
    revenue_source: str
    #: `revenue|payroll|other_costs` — o porquê dos `null`, uma vez e em ids.
    unavailable: tuple[str, ...]
    #: `normal|isento_art_53`. **Rótulo e não correcção** (ver `_qualidade`).
    vat_regime: str


@dataclass(frozen=True, kw_only=True, slots=True)
class TermosBrutos:
    """Os três termos e a variação **antes** do arredondamento.

    Não viaja no HTTP: existe para a identidade ser verificável no sítio onde é
    afirmada. `variacao` é a Σ dos cinco tipos económicos tal como o ledger os
    gravou, e tem de ser exactamente `purchases − goods_consumed −
    unknown_shrinkage`. Quando não é, há um tipo do lado errado.
    """

    purchases: Decimal
    goods_consumed: Decimal
    unknown_shrinkage: Decimal
    variacao: Decimal
    waste: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class Mercadoria:
    """Tudo o que o ledger sabe dizer sobre uma janela. Partilhado pelo resumo e pelo mês."""

    purchases_eur: Decimal
    goods_consumed_eur: Decimal
    stock_change_eur: Decimal
    waste_eur: Decimal
    unknown_shrinkage_eur: Decimal
    stock_value_eur: Decimal
    stock_value_as_of: datetime
    costs: tuple[CostComponentOut, ...]
    waste_by_reason: tuple[WasteByReasonOut, ...]
    data_quality: DataQualityOut
    bruto: TermosBrutos


@dataclass(frozen=True, kw_only=True, slots=True)
class SummaryOut:
    """`GET /reporting/summary`. **Sem total de gastos e sem resultado**, de propósito."""

    period: PeriodOut
    revenue_net_eur: Decimal | None
    revenue_gross_eur: Decimal | None
    revenue_basis: str | None
    purchases_eur: Decimal
    goods_consumed_eur: Decimal
    stock_change_eur: Decimal
    waste_eur: Decimal
    unknown_shrinkage_eur: Decimal
    goods_cost_ratio_pct: Decimal | None
    stock_value_eur: Decimal
    stock_value_as_of: datetime
    costs: tuple[CostComponentOut, ...]
    waste_by_reason: tuple[WasteByReasonOut, ...]
    data_quality: DataQualityOut
    bruto: TermosBrutos


@dataclass(frozen=True, kw_only=True, slots=True)
class PointOut:
    """Um ponto de uma série: o valor e a altura da barra."""

    value_eur: Decimal
    share: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class SerieOut:
    """Uma série do gráfico. Hoje só há uma — e a legenda diz porquê."""

    id: str
    unit: str
    total_eur: Decimal
    points: tuple[PointOut, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class BucketOut:
    """O intervalo de um ponto. Viaja **uma vez**, não por série."""

    since: datetime
    until: datetime


@dataclass(frozen=True, kw_only=True, slots=True)
class SeriesOut:
    """`GET /reporting/series`."""

    period: PeriodOut
    granularity: str
    buckets: tuple[BucketOut, ...]
    scale_max_eur: Decimal
    series: tuple[SerieOut, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class PayrollPartOut:
    """Uma parcela do custo-empresa. **Nunca construída nesta fatia** — ver `fecho_do_mes`."""

    id: str
    amount_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class RoleCostOut:
    """O custo de um cargo. Vem do `people`, que não existe."""

    role_id: UUID
    name: str
    headcount: int
    payroll_eur: Decimal
    share: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class OtherCostOut:
    """Um custo fixo mensal. Vem do `purchasing_othercost`, que não existe."""

    category: str
    amount_eur: Decimal
    note: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class MonthOut:
    """`GET /reporting/month`. Os campos de pessoal estão todos a `None` — ver o fim do ficheiro."""

    month: str
    since: datetime
    until: datetime
    business_day_starts_at: str
    closed: bool
    days_elapsed: int
    days_in_month: int
    revenue_net_eur: Decimal | None
    revenue_gross_eur: Decimal | None
    revenue_basis: str | None
    purchases_eur: Decimal
    goods_consumed_eur: Decimal
    stock_change_eur: Decimal
    waste_eur: Decimal
    unknown_shrinkage_eur: Decimal
    stock_value_eur: Decimal
    stock_value_as_of: datetime
    payroll_eur: Decimal | None
    payroll_basis: str | None
    payroll_source: str | None
    payroll_breakdown: tuple[PayrollPartOut, ...]
    roles: tuple[RoleCostOut, ...]
    other_costs: tuple[OtherCostOut, ...]
    costs: tuple[CostComponentOut, ...]
    cost_total_eur: Decimal | None
    result_eur: Decimal | None
    result_excludes: tuple[str, ...]
    goods_cost_ratio_pct: Decimal | None
    labour_cost_ratio_pct: Decimal | None
    prime_cost_pct: Decimal | None
    waste_by_reason: tuple[WasteByReasonOut, ...]
    data_quality: DataQualityOut
    bruto: TermosBrutos


# ---------------------------------------------------------------------------
# A composição
# ---------------------------------------------------------------------------
def _periodo(janela: Janela) -> PeriodOut:
    return PeriodOut(
        key=janela.key,
        since=janela.desde,
        until=janela.ate,
        business_day_starts_at=janela.inicio_do_dia.strftime("%H:%M"),
    )


def _componentes(
    parcelas: Sequence[tuple[str, Decimal, bool, str | None]],
) -> tuple[CostComponentOut, ...]:
    """A lista de parcelas, com o `share` sobre a **maior** delas.

    O denominador não é um total porque o `summary` não tem total de propósito
    (ADR 0013, decisão 6): um share sobre um número que não viaja seria uma
    divisão que o cliente não pode verificar. Com a maior parcela a 1,0 as
    barras são comparáveis entre si, que é o que a lista serve.

    Uma parcela **negativa** — o excedente de contagem — sai com `share` a zero
    e fora do total: uma barra de altura negativa não existe neste desenho, e
    somar um excedente a custos era baixar o custo com uma sobra de stock.
    """
    maior = max((abs(valor) for _, valor, _, _ in parcelas), default=ZERO)
    return tuple(
        CostComponentOut(
            id=identificador,
            amount_eur=euros(valor),
            share=(
                ZERO.quantize(MILESIMO)
                if valor < ZERO
                else fraccao(parte=valor, todo=maior)
            ),
            is_part_of_total=soma and valor >= ZERO,
            part_of=dentro_de,
        )
        for identificador, valor, soma, dentro_de in parcelas
    )


def _desperdicio_por_motivo(
    *, tenant_id: UUID, janela: Janela, total: Decimal
) -> tuple[WasteByReasonOut, ...]:
    """Os cinco motivos, do maior para o menor, a somar **exactamente** `waste_eur`.

    Sem truncatura e sem limiar: 200 g de salsa conta na mesma lista que 20 kg
    de farinha, e quem lê decide o que destaca. O `share` é sobre o total não
    arredondado; os valores são repartidos pelo maior resto, logo a soma das
    linhas é o total ao cêntimo.
    """
    linhas = inventory_api.desperdicio_agregado_por_motivo(
        tenant_id=tenant_id, desde=janela.desde, ate=janela.ate
    )
    # O ledger grava a saída a negativo; o contrato serve "positivo = perdeu-se".
    # A negação acontece **aqui**, uma vez. Um `waste` sem motivo gravado conta
    # como `other` e junta-se à linha dele: a união do contrato tem cinco
    # valores e uma sexta linha vazia não teria palavra no `vocabulario.ts`.
    acumulado: dict[str, tuple[Decimal, int]] = {}
    for linha in linhas:
        motivo = linha.reason or "other"
        valor, movimentos = acumulado.get(motivo, (ZERO, 0))
        acumulado[motivo] = (valor - linha.valor_eur, movimentos + linha.n)
    brutos = sorted(acumulado.items(), key=lambda par: (-par[1][0], par[0]))
    valores = repartir(total=euros(total), partes=[valor for _, (valor, _) in brutos])
    return tuple(
        WasteByReasonOut(
            reason=motivo,
            amount_eur=valor,
            share=fraccao(parte=bruto, todo=total),
            movements=movimentos,
        )
        for (motivo, (bruto, movimentos)), valor in zip(brutos, valores, strict=True)
    )


def _qualidade(
    *,
    tenant_id: UUID,
    bruto: TermosBrutos,
    por_estimar: Decimal,
    vat_regime: str,
) -> DataQualityOut:
    """O bloco que declara o que não se sabe.

    **O IVA é rótulo e não correcção.** Este painel não lê o `vat_regime` para
    valorizar nada: o custo de um movimento é o que lá está gravado (ADR 0014,
    e reavaliar o passado com a regra de hoje é o que ela proíbe). O regime
    viaja para o ecrã poder dizer, num estabelecimento em `isento_art_53`, que
    os valores são **sem IVA** e que o IVA suportado — que nesse regime *é*
    custo — não está incluído.

    Dívida nomeada e **a montante desta fatia**: o `purchasing/services.py`
    grava `unit_cost = line_total / quantity_received` com o `line_total`
    líquido, logo num tenant isento o custo de cada entrada fica 6 a 23% abaixo
    do real. Corrigir isso aqui seria pôr a correcção no sítio errado (e a
    repetir-se em cada leitura); corrige-se onde o custo nasce, e é por isso que
    esta linha é um comentário e não um `if`.
    """
    return DataQualityOut(
        # Zero consumo não é 100% de margem, é ausência de registo. O ecrã
        # escreve-o e não desenha o rácio (ADR 0013, decisão 7).
        consumption_registered=bruto.goods_consumed > ZERO,
        purchases_awaiting_invoice_eur=euros(por_estimar),
        last_count_at=inventory_api.ultima_contagem_fechada_em(tenant_id=tenant_id),
        # `none` e não `manual`: não há módulo de vendas. É mais fino do que o
        # `unavailable` e sobrevive ao dia em que a receita exista mas não
        # esteja registada.
        revenue_source="none",
        unavailable=INDISPONIVEL,
        vat_regime=vat_regime,
    )


def _mercadoria(*, tenant_id: UUID, janela: Janela, vat_regime: str) -> Mercadoria:
    """Os quatro termos, a decomposição e o bloco de qualidade — de um agregado só."""
    por_tipo = {
        linha.movement_type: linha
        for linha in inventory_api.movimentos_agregados_por_tipo(
            tenant_id=tenant_id, desde=janela.desde, ate=janela.ate
        )
    }

    def valor(*tipos: str) -> Decimal:
        return sum((por_tipo[tipo].valor_eur for tipo in tipos if tipo in por_tipo), ZERO)

    compras = valor(*TIPOS_DE_COMPRA)
    # O ledger grava as saídas a negativo; os dois termos servem-se positivos, e
    # a negação é **uma** por termo e acontece nesta linha e na seguinte.
    consumo = -valor(*TIPOS_DE_CONSUMO)
    quebra = -valor(TIPO_DE_QUEBRA)
    desperdicio = -valor("waste")
    bruto = TermosBrutos(
        purchases=compras,
        goods_consumed=consumo,
        unknown_shrinkage=quebra,
        # A Σ dos cinco tipos económicos: o lado esquerdo da identidade, como o
        # ledger o escreveu. Os `production_*` e os `transfer_*` ficam de fora
        # **por tipo**, e não por se assumir que se anulam.
        variacao=sum(
            (
                linha.valor_eur
                for linha in por_tipo.values()
                if linha.movement_type not in TIPOS_SEM_EVENTO
            ),
            ZERO,
        ),
        waste=desperdicio,
    )

    compras_eur = euros(compras)
    consumo_eur = euros(consumo)
    quebra_eur = euros(quebra)
    valor_de_stock = inventory_api.valor_de_stock(tenant_id=tenant_id)

    return Mercadoria(
        purchases_eur=compras_eur,
        goods_consumed_eur=consumo_eur,
        # Dos **já arredondados**: o resíduo de até um cêntimo cai na linha
        # derivada, e a identidade que o ecrã imprime fecha à vista.
        stock_change_eur=compras_eur - consumo_eur - quebra_eur,
        waste_eur=euros(desperdicio),
        unknown_shrinkage_eur=quebra_eur,
        stock_value_eur=euros(valor_de_stock.valor_eur),
        stock_value_as_of=valor_de_stock.as_of,
        costs=_componentes(
            [
                ("goods_consumed", consumo, True, None),
                # Dentro da mercadoria consumida, logo **não soma**: é
                # decomposição. "Dos quais 420 € foram desperdício."
                ("waste", desperdicio, False, "goods_consumed"),
                ("unknown_shrinkage", quebra, True, None),
                # As compras não somam com o consumo: são a **outra** base de
                # custo, e somá-las contava a mesma mercadoria duas vezes.
                ("purchases", compras, False, None),
            ]
        ),
        waste_by_reason=_desperdicio_por_motivo(
            tenant_id=tenant_id, janela=janela, total=desperdicio
        ),
        data_quality=_qualidade(
            tenant_id=tenant_id,
            bruto=bruto,
            # **Decomposição e nunca parcela**: os movimentos com custo estimado
            # já estão dentro de `purchases_eur`, porque a mercadoria entrou.
            # Sem eles a identidade não fechava, e o que falta é a fatura e não
            # a mercadoria. Hoje nenhum caminho de escrita grava
            # `cost_is_estimate=True`, logo o número é sempre `0.00` — o que
            # não se pode escrever no contrato é "está tudo faturado".
            por_estimar=(
                por_tipo["receipt"].valor_estimado_eur if "receipt" in por_tipo else ZERO
            ),
            vat_regime=vat_regime,
        ),
        bruto=bruto,
    )


def resumo_do_periodo(
    *, tenant_id: UUID, janela: Janela, vat_regime: str
) -> SummaryOut:
    """`GET /reporting/summary` — o bloco de período.

    Os três campos de receita vão a `None` e não a `"0.00"`: um zero em euros é
    um facto, e o painel desenha-o (uma barra a zero, um rácio a 0%). `None` é
    a palavra "não sei", e o porquê viaja no `unavailable` (ADR 0029, decisão
    1).
    """
    mercadoria = _mercadoria(tenant_id=tenant_id, janela=janela, vat_regime=vat_regime)
    return SummaryOut(
        period=_periodo(janela),
        revenue_net_eur=None,
        revenue_gross_eur=None,
        revenue_basis=None,
        purchases_eur=mercadoria.purchases_eur,
        goods_consumed_eur=mercadoria.goods_consumed_eur,
        stock_change_eur=mercadoria.stock_change_eur,
        waste_eur=mercadoria.waste_eur,
        unknown_shrinkage_eur=mercadoria.unknown_shrinkage_eur,
        # Sem denominador não há rácio, e é a razão certa para o `None`: o
        # consumo sobre vendas que não existem seria uma divisão por zero
        # disfarçada de 0%.
        goods_cost_ratio_pct=None,
        stock_value_eur=mercadoria.stock_value_eur,
        stock_value_as_of=mercadoria.stock_value_as_of,
        costs=mercadoria.costs,
        waste_by_reason=mercadoria.waste_by_reason,
        data_quality=mercadoria.data_quality,
        bruto=mercadoria.bruto,
    )


def _compras_por_balde(
    *, tenant_id: UUID, janela: Janela, grupos: Sequence[Balde]
) -> list[Decimal]:
    """As compras de cada balde, **não arredondadas**, do mesmo agregado do total."""
    por_dia: dict[date, Decimal] = {}
    for linha in inventory_api.movimentos_agregados_por_dia_de_negocio(
        tenant_id=tenant_id,
        desde=janela.desde,
        ate=janela.ate,
        inicio_do_dia=janela.inicio_do_dia,
    ):
        if linha.movement_type in TIPOS_DE_COMPRA:
            por_dia[linha.dia] = por_dia.get(linha.dia, ZERO) + linha.valor_eur
    return [sum((por_dia.get(dia, ZERO) for dia in grupo.dias), ZERO) for grupo in grupos]


def series_do_periodo(*, tenant_id: UUID, janela: Janela) -> SeriesOut:
    """`GET /reporting/series` — a mesma janela, intervalo a intervalo.

    **Uma série**, e é uma decisão: sem módulo de vendas a segunda seria uma
    linha a zero, que se desenha e se lê como "não se vendeu nada" (ADR 0029,
    decisão 5). A união `idDeSerieSchema` do cliente não muda e a legenda diz
    porque é que a outra não está lá.

    `Σ(points) == total_eur` é por construção e não por cuidado: o balde é a
    mesma expressão SQL que o total e a repartição é pelo maior resto. Vale
    também nos dois domingos em que o relógio muda — o balde desconta a hora do
    negócio **na hora local** (ver `inventory/selectors.py`).
    """
    granularidade = granularidade_de(janela.key)
    grupos = baldes(janela=janela, granularidade=granularidade)
    brutos = _compras_por_balde(tenant_id=tenant_id, janela=janela, grupos=grupos)
    total = sum(brutos, ZERO)
    valores = repartir(total=euros(total), partes=brutos)
    # O eixo acomoda a **maior barra**, e o módulo é o que a desenha: um balde
    # negativo (nota de crédito de devolução) é tão alto quanto um positivo.
    escala = max((abs(valor) for valor in valores), default=ZERO)
    return SeriesOut(
        period=_periodo(janela),
        granularity=granularidade,
        buckets=tuple(
            BucketOut(since=grupo.desde, until=grupo.ate) for grupo in grupos
        ),
        scale_max_eur=escala,
        series=(
            SerieOut(
                id="purchases",
                unit="eur",
                total_eur=euros(total),
                points=tuple(
                    PointOut(value_eur=valor, share=fraccao(parte=valor, todo=escala))
                    for valor in valores
                ),
            ),
        ),
    )


def fecho_do_mes(*, tenant_id: UUID, mes: JanelaDoMes, vat_regime: str) -> MonthOut:
    """`GET /reporting/month` — o fecho, com o grão do mês de negócio.

    **Metade deste payload é `None`, e isso é a decisão 1 da ADR 0029.** Sem o
    módulo `people` não há salários; sem `purchasing_othercost` não há custos
    fixos; e sem nenhum dos dois não há `cost_total_eur` nem `result_eur` — um
    total de gastos que não inclui o pessoal não é um total de gastos, e um
    resultado calculado sobre ele seria o dobro do real. As listas vêm vazias
    pela mesma razão: uma lista de exclusões de um número que não existe é
    ruído.

    O que é real serve-se a sério: a mercadoria, pelo ledger, com a mesma
    identidade do `/summary` e com a mesma janela — é o mesmo código, chamado
    com a janela do mês.
    """
    janela = mes.janela
    mercadoria = _mercadoria(tenant_id=tenant_id, janela=janela, vat_regime=vat_regime)
    return MonthOut(
        month=mes.month,
        since=mes.desde,
        until=mes.ate,
        business_day_starts_at=mes.inicio_do_dia.strftime("%H:%M"),
        closed=mes.closed,
        days_elapsed=mes.days_elapsed,
        days_in_month=mes.days_in_month,
        revenue_net_eur=None,
        revenue_gross_eur=None,
        revenue_basis=None,
        purchases_eur=mercadoria.purchases_eur,
        goods_consumed_eur=mercadoria.goods_consumed_eur,
        stock_change_eur=mercadoria.stock_change_eur,
        waste_eur=mercadoria.waste_eur,
        unknown_shrinkage_eur=mercadoria.unknown_shrinkage_eur,
        stock_value_eur=mercadoria.stock_value_eur,
        stock_value_as_of=mercadoria.stock_value_as_of,
        payroll_eur=None,
        payroll_basis=None,
        payroll_source=None,
        payroll_breakdown=(),
        roles=(),
        other_costs=(),
        costs=mercadoria.costs,
        cost_total_eur=None,
        result_eur=None,
        result_excludes=(),
        goods_cost_ratio_pct=None,
        labour_cost_ratio_pct=None,
        prime_cost_pct=None,
        waste_by_reason=mercadoria.waste_by_reason,
        data_quality=mercadoria.data_quality,
        bruto=mercadoria.bruto,
    )
