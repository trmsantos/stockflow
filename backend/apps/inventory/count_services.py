"""Os casos de uso de uma contagem física (ADR 0030).

Quatro funções e uma regra que as atravessa: **o stock é um ledger**. Uma
contagem não reescreve um nível — ao fechar, cada diferença entra como um
`adjustment` e é `record_movements` que recalcula o `StockLevel` a partir da
soma dos movimentos (CLAUDE.md, ADR 0023).

* `abrir_contagem` materializa a lista: uma linha por artigo com nível não-zero
  na localização, com o `expected` congelado nesse instante (decisão 4).
* `registar_linha_contagem` é um **upsert por artigo** — a última observação
  substitui a anterior e nunca se somam duas (decisão 4 e 6c).
* `planear_fecho` é a pré-visualização, e é **a mesma função** que o fecho usa
  para decidir o que escrever. Se fossem duas, o previsto e o gravado
  divergiam, e é exactamente esse o defeito que a ADR manda fechar.
* `fechar_contagem` grava **N movimentos, um por lote** — não um por linha: o
  ledger, o nível e o custo são todos por lote (ADR 0023, decisão 1).

## Como é que uma diferença por artigo se reparte por lotes

A linha é por artigo porque é assim que se conta ("há 3 kg de farinha naquela
prateleira", não "há 1,2 kg do lote A e 1,8 kg do lote B"). O ledger é por lote.
A repartição é a resposta do `domain-expert`, e os dois sentidos não são
simétricos:

* **Falta** (contado < esperado): sai por **FEFO**, em cascata para o lote
  seguinte quando excede o saldo do primeiro — a mesma ordem por que o `waste` e
  o `transfer_out` saem. O que faltou na prateleira é, na melhor hipótese, o que
  estava lá há mais tempo.
* **Sobra** (contado > esperado): entra no **lote mais recente com saldo**, e
  nunca por FEFO. Inflacionar o lote a expirar cria um alerta de validade falso
  hoje e uma quebra `expired` amanhã que nunca aconteceu.
* **Esperado negativo** (o ledger ficou a dever): a sobra repõe primeiro os
  lotes negativos, até os zerar, e só o excedente vai ao lote recente. Nenhum
  nível fica com o sinal invertido por causa de uma contagem. A ADR 0012 fica
  intacta: isto não bloqueia nada, só escolhe para onde a quantidade vai.

## O custo, e a regressão que ele corrige

O custo de cada ajuste é o `unit_cost` do nível do trio
`(artigo, localização, **lote escolhido**)`. Até esta fatia, o `fechar_contagem`
procurava o nível com `lot_id = NULL` e, não o achando, valorizava a **zero, em
silêncio** — e com `track_lots=False` não o acha nunca, porque o nível vive no
lote sintético `__<product_id>__`. Sem nível, o custo desce um degrau para o
`ProductCost` de `(artigo, localização)`; sem ele, é zero e o movimento vai
marcado com `cost_is_estimate=True`, porque "zero euros de diferença" é uma
afirmação e não um facto.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.api import produto_por_id
from apps.inventory import selectors
from apps.inventory.models import Location, Lot, StockCount, StockCountLine, StockLevel
from apps.inventory.services import MovementDTO, record_movements

__all__ = [
    "CODIGO_CONTAGEM_FECHADA",
    "CODIGO_CONTAGEM_JA_ABERTA",
    "MAXIMO_DA_JUSTIFICACAO",
    "MOTIVO_OBRIGATORIO_ACIMA_DE_EUR",
    "ROTULO_DE_QUEM_FECHA",
    "AjusteDeContagem",
    "ContagemFechada",
    "ContagemJaAberta",
    "FechoPrevisto",
    "abrir_contagem",
    "ao_centimo",
    "fechar_contagem",
    "planear_fecho",
    "registar_linha_contagem",
]

logger = logging.getLogger(__name__)

#: Os dois códigos de conflito desta fatia. Estáveis, porque o cliente ramifica
#: neles: o `contagem_ja_aberta` leva quem tentou abrir a segunda até à que já
#: está aberta, em vez de lhe dizer "erro".
CODIGO_CONTAGEM_JA_ABERTA = "contagem_ja_aberta"
CODIGO_CONTAGEM_FECHADA = "contagem_fechada"

#: O rótulo de quem fecha — texto, não permissão. A permissão está em
#: `permission_classes` com `TemPapel.exige(...)`; isto é o que o ecrã mostra.
ROTULO_DE_QUEM_FECHA = _("Owner or manager")

#: O limiar acima do qual o motivo é obrigatório. **Zero**, e o campo continua a
#: viajar: a justificação é sempre obrigatória (ADR 0030, segunda ronda de
#: respostas do dono, nº 5) e o ecrã mostra o limiar em vez de o esconder num
#: painel de configurações. Se o dono voltar atrás, muda-se este número e mais
#: nada.
#:
#: **E muda-se mais uma coisa: quem o vê.** A zero isto é um oráculo morto —
#: "obrigatório acima de 0 €" não diz nada sobre preço nenhum. Com um limiar
#: ≠ 0 servido a quem não vê euros, cada fecho passa a limitar um custo ("esta
#: diferença vale mais de X €"), e repetido artigo a artigo reconstrói o preço
#: sem nunca mostrar um euro. Hoje não chega lá porque as duas rotas de
#: `/closing` são de `owner|manager`, que são os `PAPEIS_QUE_VEEM_EUROS`; o
#: `FechoDeContagemOutSerializer` tem a nota completa e o
#: `test_o_limiar_do_fecho_nao_chega_a_quem_nao_ve_euros` prende as duas listas.
#: Quem mexer neste número sem ler isto abre a fuga com uma linha (ADR 0032).
MOTIVO_OBRIGATORIO_ACIMA_DE_EUR = Decimal("0")

#: O comprimento máximo da justificação, igual ao da coluna e ao do schema Zod.
MAXIMO_DA_JUSTIFICACAO = 200

CENTIMO = Decimal("0.01")

DETALHE_LOCALIZACAO = _("Location not found or inactive.")
DETALHE_ARTIGO = _("This item does not exist in this establishment.")
DETALHE_SEM_LOTE = _(
    "This item is tracked by lot and has no lot recorded yet. Record the goods "
    "receipt before counting it."
)
DETALHE_SEM_JUSTIFICACAO = _("Write why this count is being closed.")


def ao_centimo(valor: Decimal) -> Decimal:
    """Arredonda ao cêntimo, meia unidade para cima. Dinheiro não tem mais casas."""
    return valor.quantize(CENTIMO, rounding=ROUND_HALF_UP)


class ContagemJaAberta(Exception):
    """Já há uma contagem aberta neste estabelecimento — 409, com o `id` dela.

    Levantada a partir do `IntegrityError` do índice único parcial e não de um
    `filter().exists()`: dois telemóveis a carregar em "começar" no mesmo
    instante veem os dois zero abertas e inserem os dois (ADR 0030, decisão 2).
    """

    def __init__(self, *, contagem_id: UUID | None) -> None:
        self.contagem_id = contagem_id
        super().__init__(CODIGO_CONTAGEM_JA_ABERTA)


class ContagemFechada(Exception):
    """A contagem já está fechada — 409. Não se reabre, não se conta, não se fecha duas vezes."""

    def __init__(self, *, contagem_id: UUID) -> None:
        self.contagem_id = contagem_id
        super().__init__(CODIGO_CONTAGEM_FECHADA)


@dataclass(frozen=True, kw_only=True, slots=True)
class AjusteDeContagem:
    """Um movimento que o fecho vai gravar: **um por lote**, nunca um por linha.

    `lot_id` a `None` quer dizer "o lote ainda não existe": é o sintético
    `__<product_id>__` de um artigo sem rastreio que nunca entrou, e o fecho
    cria-o antes de gravar. A pré-visualização não escreve nada, logo tem de
    conseguir descrever esse caso sem o criar.
    """

    line_id: UUID
    product_id: UUID
    lot_id: UUID | None
    quantity: Decimal
    unit_cost: Decimal
    cost_is_estimate: bool

    @property
    def valor_eur(self) -> Decimal:
        """O valor com sinal: negativo é perda, positivo é ganho."""
        return self.quantity * self.unit_cost


@dataclass(frozen=True, kw_only=True, slots=True)
class FechoPrevisto:
    """O que o fecho vai escrever — ou, numa contagem fechada, o que escreveu.

    Numa contagem **aberta** os números saem do plano: é uma previsão, e é a
    mesma que o `fechar_contagem` executa. Numa contagem **fechada** saem do
    ledger, pela `reference` dos movimentos: depois de fechar, a verdade é o que
    ficou gravado e não um recálculo contra níveis que entretanto mudaram.
    """

    contagem: StockCount
    linhas: tuple[StockCountLine, ...]
    ajustes: tuple[AjusteDeContagem, ...]
    #: `line_id` → valor em euros da diferença daquela linha, com sinal e ao
    #: cêntimo. Só as linhas contadas com diferença lá estão.
    valor_por_linha: Mapping[UUID, Decimal]
    total_lines: int
    counted_lines: int
    #: Os nomes dos artigos por contar, na ordem das linhas. É o que o ecrã usa
    #: para dizer "Fechar com N por contar" em vez de desligar o botão.
    por_contar: tuple[str, ...]
    loss_eur: Decimal
    gain_eur: Decimal

    @property
    def net_eur(self) -> Decimal:
        """`ganho − perda`, com sinal."""
        return self.gain_eur - self.loss_eur

    @property
    def reason_required(self) -> bool:
        """Hoje é sempre verdade, e o limiar continua a viajar para o ecrã o mostrar."""
        return self.loss_eur + self.gain_eur >= MOTIVO_OBRIGATORIO_ACIMA_DE_EUR


# ---------------------------------------------------------------------------
# Abrir
# ---------------------------------------------------------------------------
@transaction.atomic
def abrir_contagem(
    *, tenant_id: UUID, location_id: UUID, user_id: UUID | None = None
) -> StockCount:
    """Abre a contagem de uma localização e materializa as linhas.

    Uma linha por **artigo** (não por lote) com nível não-zero naquela
    localização, com `expected` igual à soma dos seus lotes nesse instante. É o
    que o ecrã assume de ponta a ponta: contar é percorrer uma lista que já
    existe, e o `total_lines` existe antes de se contar o primeiro artigo.

    Levanta `ContagemJaAberta` se o estabelecimento já tiver uma aberta — da
    base, pelo índice único parcial, e não de uma verificação prévia que duas
    inserções simultâneas atravessariam as duas.
    """
    localizacao = Location.objects.filter(
        tenant_id=tenant_id, pk=location_id, is_active=True
    ).first()
    if localizacao is None:
        raise ValidationError({"location": [DETALHE_LOCALIZACAO]})

    try:
        with transaction.atomic():
            contagem = StockCount.objects.create(
                tenant_id=tenant_id,
                location=localizacao,
                status="open",
                created_by_id=user_id,
            )
    except IntegrityError as erro:
        aberta = selectors.contagem_aberta(tenant_id=tenant_id)
        logger.info(
            "contagem recusada: já há uma aberta",
            extra={"event": "inventario.contagem", "outcome": "ja_aberta"},
        )
        raise ContagemJaAberta(contagem_id=aberta.id if aberta else None) from erro

    saldos = selectors.saldos_por_artigo_na_localizacao(
        tenant_id=tenant_id, location_id=location_id
    )
    StockCountLine.objects.bulk_create(
        [
            StockCountLine(
                tenant_id=tenant_id,
                stock_count=contagem,
                product_id=saldo["product_id"],
                lot=None,
                quantity_expected=saldo["saldo"],
                quantity_counted=None,
            )
            for saldo in saldos
        ]
    )
    logger.info(
        "contagem aberta",
        extra={"event": "inventario.contagem", "outcome": "aberta", "n_linhas": len(saldos)},
    )
    return contagem


# ---------------------------------------------------------------------------
# Contar
# ---------------------------------------------------------------------------
@transaction.atomic
def registar_linha_contagem(
    *,
    tenant_id: UUID,
    contagem: StockCount,
    product_id: UUID,
    quantity: Decimal,
    user_name: str = "",
) -> StockCountLine:
    """Regista o que se contou de um artigo. **Upsert por `(contagem, artigo)`.**

    Duas pessoas a contar o mesmo artigo deixam **uma** linha com o último valor
    — nunca a soma dos dois números —, e a linha guarda quem foi o último e
    quando, para a divergência ser visível em vez de silenciosa. Repetir o mesmo
    `POST` depois de um timeout não conta duas vezes, que é o modo de falha real
    de contar em pé com 3G.

    Um artigo que **não estava na lista** entra por aqui: a linha nasce com o
    `expected` tirado nesse momento e congelado — zero, se o artigo nunca entrou
    —, e a diferença dele é um `adjustment` positivo e nunca um `receipt`, que
    tem fornecedor, documento e preço. Não há transferência implícita: se o
    artigo estiver noutra localização, ela fica como está.

    Recusa um artigo com `track_lots=True` e **sem lote registado** (ADR 0030,
    segunda ronda, resposta 4): a rastreabilidade não nasce partida numa
    contagem, e quem está a contar passa pela receção.
    """
    aberta = (
        StockCount.objects.select_for_update()
        .filter(tenant_id=tenant_id, pk=contagem.pk, status="open")
        .first()
    )
    if aberta is None:
        raise ContagemFechada(contagem_id=contagem.pk)

    produto = produto_por_id(tenant_id=tenant_id, product_id=product_id)
    if produto is None:
        raise ValidationError({"product": [DETALHE_ARTIGO]})
    if produto.track_lots and not selectors.artigo_tem_lote(
        tenant_id=tenant_id, product_id=product_id
    ):
        raise ValidationError({"product": [DETALHE_SEM_LOTE]})

    agora = timezone.now()
    linha = (
        StockCountLine.objects.filter(
            tenant_id=tenant_id, stock_count_id=aberta.pk, product_id=product_id, lot=None
        )
        .select_for_update()
        .first()
    )
    if linha is None:
        esperado = selectors.saldo_do_artigo_na_localizacao(
            tenant_id=tenant_id, location_id=aberta.location_id, product_id=product_id
        )
        try:
            with transaction.atomic():
                return StockCountLine.objects.create(
                    tenant_id=tenant_id,
                    stock_count=aberta,
                    product_id=product_id,
                    lot=None,
                    quantity_expected=esperado,
                    quantity_counted=quantity,
                    counted_at=agora,
                    counted_by_name=user_name,
                )
        except IntegrityError:
            # Duas pessoas a contar o mesmo artigo que não estava na lista, no
            # mesmo instante: a base arbitra e quem perder relê e actualiza. O
            # `expected` que fica é o da linha que ganhou a corrida — congelado
            # uma vez, como manda a ADR 0029.
            linha = StockCountLine.objects.select_for_update().get(
                tenant_id=tenant_id, stock_count_id=aberta.pk, product_id=product_id, lot=None
            )

    linha.quantity_counted = quantity
    linha.counted_at = agora
    linha.counted_by_name = user_name
    linha.save(
        update_fields=["quantity_counted", "counted_at", "counted_by_name", "updated_at"]
    )
    return linha


# ---------------------------------------------------------------------------
# Planear o fecho — a mesma função que o fecho executa
# ---------------------------------------------------------------------------
def planear_fecho(*, tenant_id: UUID, contagem: StockCount) -> FechoPrevisto:
    """O que o fecho vai escrever, sem escrever nada.

    É esta função que o `GET /closing` serve **e** que o `fechar_contagem`
    executa: se fossem duas, o `difference_eur` da pré-visualização e a soma dos
    movimentos gravados divergiam, e a divergência só apareceria a quem fosse
    somar as duas coisas à mão.

    Numa contagem já fechada o plano não se recalcula: os valores vêm do ledger,
    pela `reference` dos movimentos.
    """
    linhas = selectors.linhas_da_contagem(tenant_id=tenant_id, stock_count_id=contagem.pk)
    contadas = [linha for linha in linhas if linha.quantity_counted is not None]
    por_contar = tuple(
        linha.product.short_name for linha in linhas if linha.quantity_counted is None
    )

    if contagem.status == "closed":
        valores = selectors.valor_dos_ajustes_por_artigo(
            tenant_id=tenant_id, stock_count_id=contagem.pk
        )
        valor_por_linha = {
            linha.id: ao_centimo(valores[linha.product_id])
            for linha in contadas
            if linha.product_id in valores
        }
        ajustes: tuple[AjusteDeContagem, ...] = ()
    else:
        ajustes = _planear_ajustes(tenant_id=tenant_id, contagem=contagem, linhas=contadas)
        por_linha: dict[UUID, Decimal] = {}
        for ajuste in ajustes:
            por_linha[ajuste.line_id] = por_linha.get(ajuste.line_id, Decimal("0")) + (
                ajuste.valor_eur
            )
        valor_por_linha = {
            line_id: ao_centimo(valor) for line_id, valor in por_linha.items()
        }

    perda = sum((-v for v in valor_por_linha.values() if v < 0), Decimal("0"))
    ganho = sum((v for v in valor_por_linha.values() if v > 0), Decimal("0"))
    return FechoPrevisto(
        contagem=contagem,
        linhas=tuple(linhas),
        ajustes=ajustes,
        valor_por_linha=valor_por_linha,
        total_lines=len(linhas),
        counted_lines=len(contadas),
        por_contar=por_contar,
        loss_eur=ao_centimo(perda),
        gain_eur=ao_centimo(ganho),
    )


def _planear_ajustes(
    *, tenant_id: UUID, contagem: StockCount, linhas: Sequence[StockCountLine]
) -> tuple[AjusteDeContagem, ...]:
    """A repartição de cada diferença pelos lotes. Nenhuma escrita, nenhum efeito."""
    com_diferenca = [
        linha
        for linha in linhas
        if linha.quantity_counted is not None
        and linha.quantity_counted != linha.quantity_expected
    ]
    if not com_diferenca:
        return ()

    artigos = [linha.product_id for linha in com_diferenca]
    niveis = selectors.niveis_para_contagem(
        tenant_id=tenant_id, location_id=contagem.location_id, product_ids=artigos
    )
    lotes = selectors.lotes_dos_artigos(tenant_id=tenant_id, product_ids=artigos)
    custos = selectors.custos_de_artigo_na_localizacao(
        tenant_id=tenant_id, location_id=contagem.location_id, product_ids=artigos
    )

    ajustes: list[AjusteDeContagem] = []
    for linha in com_diferenca:
        diferenca = linha.quantity_counted - linha.quantity_expected
        do_artigo = niveis.get(linha.product_id, [])
        # Um nível sem lote é legado (as receções escrevem sempre lote, nem que
        # seja o sintético) e **nunca** é alvo: era aí que o custo se perdia.
        alvos = [nivel for nivel in do_artigo if nivel.lot_id is not None]
        if diferenca < 0:
            reparticao = _repartir_falta(alvos=alvos, em_falta=-diferenca)
        else:
            reparticao = _repartir_sobra(
                alvos=alvos, lotes=lotes.get(linha.product_id, []), a_mais=diferenca
            )
        por_lote = {nivel.lot_id: nivel for nivel in alvos}
        custo_do_artigo = custos.get(linha.product_id, Decimal("0"))
        for lot_id, quantidade in reparticao:
            if quantidade == 0:
                continue
            unit_cost, estimado = _custo_do_lote(
                nivel=por_lote.get(lot_id), custo_do_artigo=custo_do_artigo
            )
            ajustes.append(
                AjusteDeContagem(
                    line_id=linha.id,
                    product_id=linha.product_id,
                    lot_id=lot_id,
                    quantity=quantidade,
                    unit_cost=unit_cost,
                    cost_is_estimate=estimado,
                )
            )
    return tuple(ajustes)


def _repartir_falta(
    *, alvos: Sequence[StockLevel], em_falta: Decimal
) -> list[tuple[UUID | None, Decimal]]:
    """A falta sai por FEFO, em cascata, e nenhum lote passa a dever o que não tinha."""
    restante = em_falta
    saidas: list[tuple[UUID | None, Decimal]] = []
    for nivel in alvos:
        if restante <= 0:
            break
        if nivel.quantity <= 0:
            continue
        sai = min(restante, nivel.quantity)
        saidas.append((nivel.lot_id, -sai))
        restante -= sai
    if restante > 0:
        # O saldo dos lotes não chega para a falta — o `expected` da linha foi
        # congelado antes de alguém mexer no stock. O resto sai do primeiro lote
        # do FEFO, que fica negativo, e isso é deliberado: a ADR 0012 proíbe
        # bloquear, e um nível negativo é um alerta visível em vez de uma recusa
        # que chega depois do facto.
        primeiro = alvos[0].lot_id if alvos else None
        saidas.append((primeiro, -restante))
    return _somar_por_lote(saidas)


def _repartir_sobra(
    *, alvos: Sequence[StockLevel], lotes: Sequence[Lot], a_mais: Decimal
) -> list[tuple[UUID | None, Decimal]]:
    """A sobra repõe os negativos e vai ao lote **mais recente**, nunca ao FEFO."""
    restante = a_mais
    entradas: list[tuple[UUID | None, Decimal]] = []
    for nivel in alvos:
        if restante <= 0:
            break
        if nivel.quantity >= 0:
            continue
        repoe = min(restante, -nivel.quantity)
        entradas.append((nivel.lot_id, repoe))
        restante -= repoe
    if restante > 0:
        entradas.append((_lote_mais_recente(alvos=alvos, lotes=lotes), restante))
    return _somar_por_lote(entradas)


def _lote_mais_recente(
    *, alvos: Sequence[StockLevel], lotes: Sequence[Lot]
) -> UUID | None:
    """Onde entra uma sobra: o lote mais recente **com saldo**, e os recursos a seguir.

    Por esta ordem: o mais recente com saldo positivo; se nenhum tiver, o mais
    recente com nível nesta localização (está a zero, mas existe e traz custo);
    se não houver nível nenhum, o lote mais recente do artigo (entrou noutra
    localização); e só então `None`, que o fecho materializa como lote sintético.
    """
    def recencia(nivel: StockLevel) -> tuple:
        return (nivel.lot.received_at, str(nivel.lot_id))

    com_saldo = [n for n in alvos if n.quantity > 0 and n.lot is not None]
    if com_saldo:
        return max(com_saldo, key=recencia).lot_id
    com_nivel = [n for n in alvos if n.lot is not None]
    if com_nivel:
        return max(com_nivel, key=recencia).lot_id
    if lotes:
        # Já vêm do mais recente para o mais antigo.
        return lotes[0].id
    return None


def _custo_do_lote(
    *, nivel: StockLevel | None, custo_do_artigo: Decimal
) -> tuple[Decimal, bool]:
    """O custo de uma unidade da diferença, e se é estimativa.

    Três degraus: o `unit_cost` do nível do lote escolhido (o custo a sério); o
    `ProductCost` de `(artigo, localização)` quando não há nível ou quando ele
    nunca viu uma entrada; e zero, marcado como estimativa, quando não há nem
    uma coisa nem outra. O segundo e o terceiro são estimativas porque não são o
    custo **daquele** lote.
    """
    if nivel is not None and nivel.unit_cost > 0:
        return nivel.unit_cost, False
    if custo_do_artigo > 0:
        return custo_do_artigo, True
    return Decimal("0"), True


def _somar_por_lote(
    parcelas: Sequence[tuple[UUID | None, Decimal]],
) -> list[tuple[UUID | None, Decimal]]:
    """Uma parcela por lote, na ordem em que apareceram: **um movimento por lote**."""
    somado: dict[UUID | None, Decimal] = {}
    ordem: list[UUID | None] = []
    for lot_id, quantidade in parcelas:
        if lot_id not in somado:
            ordem.append(lot_id)
            somado[lot_id] = Decimal("0")
        somado[lot_id] += quantidade
    return [(lot_id, somado[lot_id]) for lot_id in ordem]


# ---------------------------------------------------------------------------
# Fechar
# ---------------------------------------------------------------------------
@transaction.atomic
def fechar_contagem(
    *,
    tenant_id: UUID,
    contagem: StockCount,
    reason: str,
    user_id: UUID | None = None,
    user_name: str = "",
) -> StockCount:
    """Fecha a contagem e grava um `adjustment` por lote, numa transação só.

    **Fechar com linhas por contar é permitido** (ADR 0030, decisão 5): o guião
    §4 proíbe o contrário, porque quem conta inventa números para o botão
    acender. Uma linha nunca contada gera **zero** movimentos — ausência de
    observação não é diferença de zero —, e a contagem conta na mesma para o
    `last_count_at` do painel: contou-se parte, e isso é mais do que não contar.

    A justificação é **sempre obrigatória** e sem limiar (segunda ronda de
    respostas do dono): o risco nomeado é a frase vazia, e a alternativa era um
    limiar por calibrar.

    Ou fecha com os ajustes todos, ou não fecha: o `record_movements` e a escrita
    do estado estão na mesma transação.
    """
    justificacao = (reason or "").strip()
    if not justificacao:
        raise ValidationError({"reason": [DETALHE_SEM_JUSTIFICACAO]})

    aberta = (
        StockCount.objects.select_for_update()
        .select_related("location")
        .filter(tenant_id=tenant_id, pk=contagem.pk, status="open")
        .first()
    )
    if aberta is None:
        raise ContagemFechada(contagem_id=contagem.pk)

    previsto = planear_fecho(tenant_id=tenant_id, contagem=aberta)
    agora = timezone.now()
    movimentos = [
        MovementDTO(
            product_id=ajuste.product_id,
            location_id=aberta.location_id,
            lot_id=_lote_para_gravar(
                tenant_id=tenant_id, ajuste=ajuste, momento=agora
            ),
            quantity=ajuste.quantity,
            unit_cost=ajuste.unit_cost,
            cost_is_estimate=ajuste.cost_is_estimate,
            movement_type="adjustment",
            occurred_at=agora,
            created_by_id=user_id,
            created_by_name=user_name,
            reference=str(aberta.pk),
            reason="other",
        )
        for ajuste in previsto.ajustes
    ]
    record_movements(tenant_id=tenant_id, movements=movimentos)

    aberta.status = "closed"
    aberta.closed_at = agora
    aberta.closed_by_id = user_id
    aberta.closing_reason = justificacao[:MAXIMO_DA_JUSTIFICACAO]
    aberta.save(
        update_fields=["status", "closed_at", "closed_by", "closing_reason", "updated_at"]
    )
    logger.info(
        "contagem fechada",
        extra={
            "event": "inventario.contagem",
            "outcome": "fechada",
            "n_movimentos": len(movimentos),
            "n_por_contar": len(previsto.por_contar),
        },
    )
    return aberta


def _lote_para_gravar(*, tenant_id: UUID, ajuste: AjusteDeContagem, momento) -> UUID:
    """O lote do movimento, criando o sintético quando o plano não achou nenhum.

    Só acontece num artigo que **nunca entrou** nesta casa: não tem nível, não
    tem lote, e a diferença é tudo o que se contou. O sintético `__<id>__` é a
    chave que o ledger exige (ADR 0023, decisão 7, caso 5) e não é um lote que
    alguém leia — quem o mostra diz "sem lote".
    """
    if ajuste.lot_id is not None:
        return ajuste.lot_id
    lote, _criado = Lot.objects.get_or_create(
        tenant_id=tenant_id,
        product_id=ajuste.product_id,
        code=f"__{ajuste.product_id}__",
        defaults={"received_at": momento},
    )
    return lote.id
