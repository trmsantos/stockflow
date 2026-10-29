"""Queries de leitura do `inventory`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from django.db.models import (
    Case,
    Count,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    Exists,
    F,
    Func,
    Max,
    OuterRef,
    Q,
    QuerySet,
    Sum,
    TextField,
    Value,
    When,
)
from django.db.models.functions import Cast
from django.utils import timezone

from apps.inventory.models import (
    Location,
    Lot,
    ProductCost,
    StockCount,
    StockCountLine,
    StockLevel,
    StockMovement,
)

__all__ = [
    "ESTADOS_DO_CUSTO",
    "CUSTO_CONHECIDO",
    "CUSTO_DESCONHECIDO",
    "CUSTO_ESTIMADO",
    "DIAS_DE_AVISO_DE_VALIDADE",
    "ESTADOS_DO_NIVEL",
    "FILTROS_DO_NIVEL",
    "GRAVIDADES",
    "GRAVIDADE_AVISO",
    "GRAVIDADE_INFO",
    "GRAVIDADE_PERIGO",
    "PERIODOS_DE_DESPERDICIO",
    "RISCOS_DO_ALERTA",
    "TIPOS_DE_VALIDADE",
    "VALIDADE_DDM",
    "VALIDADE_DLC",
    "ajustes_da_contagem",
    "alertas_de_stock",
    "artigo_tem_lote",
    "artigos_abaixo_do_minimo",
    "contadores_de_alertas",
    "contadores_de_desperdicio",
    "contagem_aberta",
    "contagens_com_progresso",
    "contagens_do_ambito",
    "progresso_da_contagem",
    "custos_de_artigo_na_localizacao",
    "custos_dos_niveis",
    "custos_medios_do_artigo",
    "desperdicio_agregado_por_motivo",
    "desperdicio_por_artigo_e_motivo",
    "e_lote_sintetico",
    "gravidade_da_validade",
    "janela_de_desperdicio",
    "linhas_da_contagem",
    "linhas_de_desperdicio",
    "listar_contagens",
    "listar_localizacoes",
    "localizacoes_do_ambito",
    "lotes_a_vencer",
    "lotes_dos_artigos",
    "movimentos_agregados_por_dia_de_negocio",
    "movimentos_agregados_por_tipo",
    "movimentos_do_artigo",
    "movimentos_do_periodo",
    "movimentos_resumidos",
    "nivel_do_artigo",
    "nivel_sem_entradas",
    "niveis_de_stock",
    "niveis_filtrados",
    "niveis_para_contagem",
    "producoes_por_periodo",
    "resumo_de_stock",
    "rotulos_de_referencia",
    "saldo_do_artigo_na_localizacao",
    "saldos_do_artigo",
    "saldos_por_artigo_ate",
    "saldos_por_artigo_na_localizacao",
    "ultima_contagem_fechada_em",
    "valor_de_stock",
    "valor_dos_ajustes_por_artigo",
]

#: Os estados de um artigo contra o seu mínimo (ADR 0027, regras de domínio):
#: `sem_stock` é saldo ≤ 0 **com** `StockLevel` — o artigo já entrou e acabou —
#: e `abaixo_do_minimo` é `0 < saldo < min`. Um artigo sem `StockLevel` nunca
#: entrou e não alarma: não se avisa de falta do que nunca houve.
SEM_STOCK = "sem_stock"
ABAIXO_DO_MINIMO = "abaixo_do_minimo"

#: A janela por omissão dos alertas de validade do painel: sete dias.
DIAS_DE_VALIDADE_DO_PAINEL = 7
#: Quantos lotes a vencer o painel lista no máximo. Um alerta é para agir, e
#: uma lista de duzentos não é accionável — o ecrã Alertas tem o resto.
LIMITE_DE_LOTES_DO_PAINEL = 200

# ===========================================================================
# Os dois relógios deste módulo, e porque é que não são um defeito (ADR 0034).
#
# **A validade é dia civil** (`timezone.localdate()`) e **o desperdício é dia
# de negócio** (`business_day_starts_at`). Os dois aparecem no mesmo ecrã e os
# dois estão certos: a lei não sabe a que horas a pastelaria abre, e o fecho do
# dia não sabe o que diz a embalagem. Às 02:00, o "hoje" do desperdício ainda é
# ontem e o "expira hoje" já é o dia novo, e as duas frases são verdadeiras ao
# mesmo tempo.
#
# Quem unificar os relógios parte uma das duas verdades: ou o lote passa a
# vencer à hora a que o patrão abre a porta, ou a quebra das 02:00 salta para o
# dia seguinte e o fecho do dia deixa de bater certo. Está escrito aqui para a
# próxima "correcção" não ser esta.
# ===========================================================================

#: Os quatro estados de uma linha do ecrã de Stock, na ordem em que a lista os
#: mostra: **o pior primeiro**. A ordem é um facto do contrato e não uma
#: preferência de ecrã — uma segunda definição de "pior" no cliente divergiria
#: da dos alertas no dia em que uma delas mudasse.
ESTADOS_DO_NIVEL: tuple[str, ...] = ("negativo", "esgotado", "baixo", "ok")

#: Os dois filtros que o ecrã de Stock envia em `?filtro=`. União fechada: um
#: terceiro valor é 400 e não uma lista a fingir que filtrou.
FILTROS_DO_NIVEL: tuple[str, str] = ("falta", "validade")

#: Os dois riscos que o ecrã de Alertas envia em `?risco=`. Mesma regra.
RISCOS_DO_ALERTA: tuple[str, str] = ("expira", "falta")

#: As duas janelas que o ecrã de Alertas pede em `?periodo=`. A fatia nasce com
#: duas de propósito, e o selector recebe `[desde, até)`: uma janela histórica
#: para uma inspeção da ASAE passa a ser **um parâmetro e não uma reescrita**.
PERIODOS_DE_DESPERDICIO: tuple[str, str] = ("hoje", "semana")

#: Quantos dias de negócio rolantes "esta semana" cobre, **incluindo hoje** —
#: igual ao `7d` do painel (ADR 0029) e nunca o mês civil.
DIAS_DA_SEMANA_DE_NEGOCIO = 7

#: As duas palavras do `expiry_kind` do `catalog`, escritas aqui porque é aqui
#: que decidem uma cor. `use_by` é **DLC** (Reg. UE 1169/2011 art. 24 e Reg. CE
#: 178/2002 art. 14(5)): passada a data o género é não seguro e não se vende.
#: `best_before` é **DDM** (DL 26/2016): passada a data ainda se vende se
#: estiver íntegro.
VALIDADE_DLC = "use_by"
VALIDADE_DDM = "best_before"
#: A união fechada que o contrato serve. Numa constante porque o
#: `ENUM_NAME_OVERRIDES` do `base.py` aponta para ela: sem um nome fixo, o
#: drf-spectacular resolve a colisão com o `kind` do `purchasing` por um sufixo
#: de hash — um nome que muda sozinho e um warning que é exit 1 no `gen:api`.
TIPOS_DE_VALIDADE: tuple[str, str] = (VALIDADE_DLC, VALIDADE_DDM)

#: As três palavras com que o cliente pinta um alerta — as do `gravidadeSchema`.
GRAVIDADE_PERIGO = "danger"
GRAVIDADE_AVISO = "warning"
GRAVIDADE_INFO = "info"
GRAVIDADES: tuple[str, str, str] = (GRAVIDADE_PERIGO, GRAVIDADE_AVISO, GRAVIDADE_INFO)

#: O corte dos "poucos dias" (ADR 0034, decisão 9). **É hipótese e está marcada
#: como tal**: não vem de lei nenhuma, vem de "dá para escoar num fim-de-semana".
#: Fica por validar com um utilizador real antes de se tratar como facto, e é a
#: candidata óbvia a mudar — por isso muda **nesta constante** e em mais lado
#: nenhum.
DIAS_DE_AVISO_DE_VALIDADE = 3


def gravidade_da_validade(*, dias: int, kind: str | None) -> str:
    """A gravidade de uma validade: **uma** função, chamada pelas duas portas.

    `dias = expires_on − hoje`, com **hoje = dia civil** (ADR 0028, não
    reaberto). A tabela é a da ADR 0034, decisão 9:

    | dias | `use_by` | `best_before` | `kind` vazio |
    |---|---|---|---|
    | `< 0` | danger | warning | danger |
    | `0` | danger | info | danger |
    | `1–3` | warning | info | warning |
    | `4–limiar` | info | info | info |

    **O tecto do `best_before` é legal e não é paleta.** Um DDM passado ainda é
    mercadoria vendável (DL 26/2016), logo nunca chega a `danger`: quem lhe
    mexer está a dizer "deita fora" sobre o que se pode vender. Um DLC que
    vence **hoje** é `danger` e não aviso — o dia em que ainda se consome é o
    dia em que se decide.

    O `kind` vazio lê-se pela coluna estrita: sub-avisar é o erro caro, e a app
    ainda não conhece a validade secundária depois de aberto (HACCP), logo já
    sub-avisa por omissão.

    **Janela ≠ corte.** O limiar de dias decide o que **aparece** na lista; esta
    função decide **como** aparece. Um lote a cinco dias entra a `info`, e é
    isso que devolve significado ao âmbar.

    Até 2026-10-27 havia duas versões disto no servidor e discordavam uma da
    outra: o `selectors.stock_alerts` dava `critical` a tudo o que tinha
    vencido (um iogurte com DDM de ontem virava alarme vermelho) e o
    `api._gravidade_da_validade` dava **aviso** a um `use_by` que vence hoje. As
    duas estavam erradas, e o cliente tinha ainda a sua.
    """
    if kind == VALIDADE_DDM:
        return GRAVIDADE_AVISO if dias < 0 else GRAVIDADE_INFO
    if dias <= 0:
        return GRAVIDADE_PERIGO
    if dias <= DIAS_DE_AVISO_DE_VALIDADE:
        return GRAVIDADE_AVISO
    return GRAVIDADE_INFO


def _dia_de_negocio_de(*, instante: datetime, inicio_do_dia: time) -> date:
    """A que dia de negócio pertence um instante. Às 02:00 ainda é ontem.

    Três linhas duplicadas do `reporting/periodos.py` **de propósito**: o
    `inventory` não pode importar o `reporting` (ADR 0029, decisão 6) e a
    alternativa — um `api.py` naquele módulo — foi recusada por extenso. O que
    paga a duplicação é o teste que corre no dia da mudança da hora e compara
    as duas implementações (`tests/test_stock_e_alertas.py`).
    """
    local = timezone.localtime(instante)
    if local.time() >= inicio_do_dia:
        return local.date()
    return local.date() - timedelta(days=1)


def _inicio_do_dia_de_negocio(*, dia: date, inicio_do_dia: time) -> datetime:
    """O instante em que o dia de negócio `dia` começa, no fuso do servidor."""
    return timezone.make_aware(datetime.combine(dia, inicio_do_dia))


def janela_de_desperdicio(
    *, periodo: str, inicio_do_dia: time, agora: datetime
) -> tuple[datetime, datetime]:
    """O `[desde, até)` de `hoje` ou `semana`, em dias **de negócio**.

    A aritmética é **de calendário**: `hoje − timedelta(days=6)` sobre a
    **data**, e só depois `combine` com a hora do estabelecimento. Um
    `agora − timedelta(days=7)` difere numa hora no domingo da mudança da hora,
    e essa hora põe um dia inteiro no balde errado — é a mesma razão que o
    cabeçalho de `reporting/periodos.py` já escreve.

    `até` é `agora` e não o fim do dia: um período a correr não promete o
    futuro.
    """
    hoje = _dia_de_negocio_de(instante=agora, inicio_do_dia=inicio_do_dia)
    dias = DIAS_DA_SEMANA_DE_NEGOCIO if periodo == "semana" else 1
    primeiro = hoje - timedelta(days=dias - 1)
    desde = _inicio_do_dia_de_negocio(dia=primeiro, inicio_do_dia=inicio_do_dia)
    return desde, agora


def localizacoes_do_ambito(*, tenant_id: UUID) -> QuerySet[Location]:
    """Todas as localizações do estabelecimento, activas ou não. A base do `get_object()`."""
    return Location.objects.filter(tenant_id=tenant_id)


def listar_localizacoes(*, tenant_id: UUID) -> QuerySet[Location]:
    """A lista do `GET /locations`: por `position`, com o nome e o `id` a desempatar.

    Sem filtro de `active`: são poucas — duas lojas e uma cozinha — e uma
    localização desactivada continua a aparecer nas linhas antigas, logo o
    cliente precisa dela para a mostrar. A ordem estável é o que faz a
    paginação não repetir linhas.
    """
    return localizacoes_do_ambito(tenant_id=tenant_id).order_by("position", "name", "id")


#: As três palavras com que este projecto fala da qualidade de um custo, e as
#: **únicas** três: são as que o porto do `agents` já serve ao `staff`
#: (`_custo` em `apps/agents/tools.py`), e uma quarta — "parcialmente
#: desconhecido", por exemplo — seria a divergência que a ADR 0032 fechou a
#: nascer outra vez. Zero é "preço desconhecido" por convenção da ADR 0024,
#: decisão 5, caso 3, e não um preço de zero euros.
#:
#: **Dívida nomeada: `CUSTO_ESTIMADO` não é alcançável nesta fatia.** O
#: `cost_is_estimate` existe no `StockMovement` (ADR 0023) e a projeção não o
#: carrega: o `StockLevel` guarda o custo e não a sua proveniência, logo o
#: painel só distingue conhecido de desconhecido. Os 201 de
#: `stock/movements/*` também não o alcançam, por consequência e não por
#: esquecimento — o `registar_waste`, o `registar_adjustment` e o
#: `registar_transfer` escrevem `cost_is_estimate=False` porque lêem o custo
#: **do nível** (ADR 0025, decisão 5), e uma saída não sabe se a entrada que a
#: pagou vinha de uma guia ou de uma fatura.
#:
#: A palavra fica na lista à mesma, e é esse o ponto: no dia em que a
#: proveniência chegar ao nível, escreve-se `estimado` e não se **inventa** uma
#: palavra nova para o mesmo facto. É a divergência que a ADR 0032 fechou e que
#: um booleano aqui reabria.
CUSTO_CONHECIDO = "conhecido"
CUSTO_ESTIMADO = "estimado"
CUSTO_DESCONHECIDO = "desconhecido"
ESTADOS_DO_CUSTO: tuple[str, str, str] = (
    CUSTO_CONHECIDO,
    CUSTO_ESTIMADO,
    CUSTO_DESCONHECIDO,
)

#: O valor de uma linha (`quantidade × custo`) precisa de mais dígitos do que
#: qualquer das duas pontas: 12,3 vezes 12,6 não cabe em 12,6.
_VALOR = DecimalField(max_digits=20, decimal_places=6)
_QUANTIDADE = DecimalField(max_digits=16, decimal_places=3)

#: Duas casas para o dinheiro, seis para um custo unitário — as do contrato.
_CENTIMO = Decimal("0.01")
_MILIONESIMO = Decimal("0.000001")

#: As colunas do artigo que todas as leituras deste módulo arrastam: o nome, o
#: `sku` e o trio que converte uma quantidade da unidade base para a de
#: apresentação. Numa constante porque são seis strings repetidas em sete
#: queries, e uma delas esquecida é um `KeyError` em produção.
_CAMPOS_DO_ARTIGO = (
    "product_id",
    "product__short_name",
    "product__sku",
    "product__base_unit",
    "product__display_unit",
    "product__display_factor",
)


def _quantidade_sem_custo() -> Sum:
    """Σ das quantidades cujo nível não tem preço. **Dentro** do `Sum`, sempre.

    É a "cobertura" da ADR 0032: diz se a subestimação do valor é de 5 % ou de
    95 % sem dizer um euro. E a razão de o `Case` viver dentro do agregado é a
    outra metade do defeito que esta fatia corrigiu — ver `stock_summary`.

    Serve também de **complemento do divisor** do custo unitário: o que sobra,
    `quantidade − sem custo`, é a quantidade que pagou o `total_value` (ver
    `_custo_unitario`).
    """
    return Sum(
        Case(
            When(unit_cost=Decimal("0"), then=F("quantity")),
            default=Value(Decimal("0")),
            output_field=_QUANTIDADE,
        ),
        output_field=_QUANTIDADE,
    )


def _custo_unitario(*, valor: Decimal, quantidade_com_custo: Decimal) -> Decimal | None:
    """O custo médio **ponderado**, ou `None` se não houver nenhum.

    O divisor é a quantidade que **contribuiu** para o `valor`, e não o saldo
    todo: `quantity − quantity_without_cost`. É a correcção de 2026-10-21 e a
    razão está medida — 30 unidades a 2,00 € mais 70 sem preço davam
    **0,60 €/un** num artigo cujo custo conhecido é 2,00 €/un, porque o
    numerador só somava a parte com preço e o denominador somava tudo. Dividir
    euros por unidades que não contribuíram com um cêntimo não é uma média de
    nada: é um número que ninguém pode usar para decidir uma compra, e nenhum
    manual, nenhum TOC e nenhum ERP o calcula. O mesmo princípio já estava
    escrito no `purchasing.selectors.linhas_com_preco_confirmado`: *"uma linha
    sem preço calculável não é um preço de zero"*.

    **A invariante da ADR 0032 sobrevive**, e é ela que fecha a reconstrução por
    aritmética: `unit_cost × (quantity − quantity_without_cost) == total_value`.
    As duas pontas do divisor são **quantidades** — ambas servidas a quem não vê
    euros —, logo esconder `unit_cost` e `total_value` continua a não deixar
    reconstruir nenhum dos dois. Mudou o divisor, não a política.

    `None` e não zero: zero é "preço desconhecido" (ADR 0024, decisão 5, caso 3)
    e seria uma afirmação sobre o preço. Com divisor a zero — um artigo em que
    **toda** a quantidade está sem preço, ou saldos com sinais que se anulam
    (uma localização a +5 e outra a −5) — não há média nenhuma.
    """
    if not quantidade_com_custo or valor == 0:
        return None
    return (valor / quantidade_com_custo).quantize(
        _MILIONESIMO, rounding=ROUND_HALF_UP
    )


def _estado_do_custo(custo: Decimal | None) -> str:
    """Conhecido ou desconhecido, nas palavras do `ESTADOS_DO_CUSTO`."""
    return CUSTO_DESCONHECIDO if not custo else CUSTO_CONHECIDO


def _linha_de_stock(
    linha: dict[str, Any], identidade: dict[str, Any]
) -> dict[str, Any]:
    """A parte comum das três rotas do painel: saldo, custo e cobertura.

    `total_value` e `unit_cost` saem daqui **sempre**; quem os tira do payload é
    o `SemEurosParaQuemNaoVe` do `accounts.api`, no serializer. Esta camada não
    conhece papéis, e é de propósito: uma query que ramificasse no papel era a
    segunda definição da política que a ADR 0032 acabou de desfazer.

    Pela mesma razão saem daqui as **duas** formas do marcador de preço
    desconhecido — a palavra (`cost_status`, exacta num lote) e a cobertura
    (`quantity_without_cost`, o que resta dizer num agregado). Quem escolhe uma
    é o serializer de cada rota: o detalhe é por lote e serve a palavra, o
    resumo soma lotes e serve a cobertura.

    O que está sem preço vale **zero no `total_value`** e não torna o total
    nulo: é a convenção que o `desperdicio_por_artigo_e_motivo` já segue — *"um
    `unit_cost` a zero sai como zero com a contagem de linhas sem custo ao
    lado"* —, e aqui o "ao lado" é a cobertura. Um total nulo escondia o valor
    que **se** conhece por causa do que não se conhece; o `unit_cost`, esse, vem
    a `None`, porque uma média de nada não é zero euros.

    **Os dois factos são diferentes e por isso têm formas diferentes**, e é a
    distinção que a ADR 0032 fez questão de manter: num artigo em que *toda* a
    quantidade está sem preço, `total_value` é `0,00` porque é mesmo a soma de
    nada — "deste artigo não se conhece um cêntimo de valor" é uma afirmação
    verdadeira e somável no painel —, e `unit_cost` vem a `None` porque "o custo
    unitário é zero" seria falsa. Quem distingue as duas é a cobertura:
    `quantity_without_cost == quantity` diz, em quantidade, que o zero é
    ausência de preço e não mercadoria oferecida.
    """
    quantidade = linha["quantidade"] or Decimal("0")
    sem_custo = linha["sem_custo"] or Decimal("0")
    valor = (linha["valor"] or Decimal("0")).quantize(_CENTIMO, rounding=ROUND_HALF_UP)
    custo = _custo_unitario(valor=valor, quantidade_com_custo=quantidade - sem_custo)
    return {
        **identidade,
        "quantity": quantidade,
        "quantity_without_cost": sem_custo,
        "cost_status": _estado_do_custo(custo),
        "unit_cost": custo,
        "total_value": valor,
    }


def _estado_do_nivel(*, saldo: Decimal, minimo: Decimal) -> str:
    """O veredicto da linha, decidido **no servidor** e sobre o estabelecimento.

    `negativo` < 0 < `esgotado` = 0; `baixo` é `0 < saldo < mínimo`; o resto é
    `ok`. Um mínimo a zero é "não há mínimo" e nunca produz `baixo`.

    **O mínimo é por artigo** (ADR 0024) e por isso este veredicto é sempre do
    estabelecimento inteiro, também quando o pedido traz `?loja=`: comparar o
    saldo de uma loja contra o mínimo de todas inventava faltas. O `?loja=`
    escopa a **quantidade** e a repartição, e o ecrã tem de escrever "mínimo do
    estabelecimento" — senão "0,4 kg · ok" lê-se como erro de cálculo.
    """
    if saldo < Decimal("0"):
        return "negativo"
    if saldo == Decimal("0"):
        return "esgotado"
    if minimo > Decimal("0") and saldo < minimo:
        return "baixo"
    return "ok"


def _validade_mais_proxima(
    *,
    tenant_id: UUID,
    location_id: UUID | None,
    hoje: date,
    product_id: UUID | None = None,
) -> dict[UUID, dict[str, Any]]:
    """Por artigo, o lote **com saldo** que vence primeiro no âmbito pedido.

    No âmbito pedido e não em todas as localizações (ADR 0034, consulta (b)):
    mostrar a validade de outra loja ao lado do saldo desta é uma frase falsa
    sobre o que está à frente de quem lê.

    Sem limite de dias: a lista de Stock mostra a validade mais próxima **haja
    ela qual for**, e quem decide se isso é um alerta é o limiar, no filtro. O
    `join` ao `StockLevel` é o que garante que o lote ainda tem mercadoria — a
    tabela `Lot` sozinha não sabe.

    O `product_id` é **mais um `WHERE`** e não um caminho novo (ADR 0034,
    adenda de 29, decisão 12): a rota de detalhe lê um artigo só e não paga a
    varredura das validades do estabelecimento inteiro para deitar fora todas
    menos uma.
    """
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id, lot__isnull=False, lot__expires_at__isnull=False
    )
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    if product_id is not None:
        niveis = niveis.filter(product_id=product_id)
    linhas = (
        niveis.values(
            "product_id",
            "product__expiry_kind",
            "lot_id",
            "lot__code",
            "lot__expires_at",
        )
        .annotate(saldo=Sum("quantity"))
        .filter(saldo__gt=Decimal("0"))
        .order_by("lot__expires_at", "lot_id")
    )
    por_artigo: dict[UUID, dict[str, Any]] = {}
    for linha in linhas:
        if linha["product_id"] in por_artigo:
            continue
        por_artigo[linha["product_id"]] = _validade(
            lot_id=linha["lot_id"],
            lot_code=linha["lot__code"],
            expires_at=linha["lot__expires_at"],
            expiry_kind=linha["product__expiry_kind"],
            hoje=hoje,
        )
    return por_artigo


def _validade(
    *,
    lot_id: UUID,
    lot_code: str | None,
    expires_at: datetime,
    expiry_kind: str | None,
    hoje: date,
) -> dict[str, Any]:
    """O bloco de validade que viaja no nível e no alerta, com a gravidade.

    `expires_at` sai como **data** e não como instante (defeito (a) da ADR
    0034): um instante tem fuso e a data da embalagem não muda com quem a lê.

    `kind` sai `None` quando o artigo não tem rótulo — o `expiry_kind` do
    `catalog` é `""` por omissão e o `tipoValidadeSchema` do cliente não aceita
    `""`. `lot_code` sai `None` num lote sintético, pela `e_lote_sintetico`:
    um `__<uuid>__` existe para o ledger ter uma chave, não para alguém o ler.

    A `severity` vem **do servidor** porque sem ela o cliente era obrigado a
    recalculá-la para pintar o trilho, e era essa a quarta definição (ADR 0034,
    decisão 9).
    """
    expires_on = timezone.localdate(expires_at)
    dias = (expires_on - hoje).days
    kind = expiry_kind or None
    return {
        "lot_id": lot_id,
        "lot_code": None if e_lote_sintetico(lot_code) else lot_code,
        "expires_at": expires_on,
        "days_away": dias,
        "kind": kind,
        "severity": gravidade_da_validade(dias=dias, kind=kind),
    }


def niveis_de_stock(
    *,
    tenant_id: UUID,
    location_id: UUID | None = None,
    q: str = "",
    product_id: UUID | None = None,
    hoje: date | None = None,
) -> list[dict[str, Any]]:
    """O ecrã de Stock: **uma linha por artigo**, nunca uma por lote.

    É o que o `/stock/summary` do servidor era até à ADR 0034 — mudou de casa
    para o `/stock/levels` e ganhou o que lhe faltava: o mínimo, o estado, a
    validade mais próxima e a repartição por localização. O grão de lote vivia
    no `by-location`/`by-product`, que morreram inteiros por não terem
    consumidor nenhum.

    ## O que o `?loja=` escopa, e o que não escopa

    Escopa a `quantity`, o `by_location`, a `nearest_expiry` e o valor — é o
    que está naquela loja. **Não** escopa o `status` nem o `min_quantity`: o
    mínimo é por artigo (ADR 0024) e compará-lo contra o saldo de uma loja
    inventava faltas. Ver `_estado_do_nivel`.

    ## A ordem, e porque é que nunca pode ser por valor

    Estado (o pior primeiro), depois `days_away` com os sem validade no fim,
    depois o nome. Nunca por valor: uma lista ordenada por euros **são** os
    euros, servida a quem não os pode ver (ADR 0032, adenda). O desempate por
    `value_eur` que o fixture fazia não atravessa.

    ## O `Case` dentro do `Sum`, e porque é que isso é segurança

    Todo o `Case` desta query vive **dentro** de um agregado. Fora dele, o
    Django põe a coluna no `GROUP BY` e um artigo com três lotes a três preços
    sai em três linhas: contar as linhas passa a dizer quantos custos distintos
    o artigo tem, que é um oráculo sobre preços sem nenhuma chave de preço no
    payload. Foi o defeito que a ADR 0032 mediu e fechou.

    ## O `product_id`, e porque é que não é uma função nova

    `GET /stock/levels/<product_id>` lê daqui (ADR 0034, adenda de 29, decisão
    12): é **mais um `WHERE`** na mesma query, para a linha do detalhe sair do
    mesmo `_nivel_de_stock`, com o mesmo `_estado_do_nivel` e a mesma
    `_validade`. Uma segunda função a compor "nível" era uma segunda definição
    de nível, que é o que a adenda proíbe por extenso.
    """
    hoje = hoje or timezone.localdate()
    niveis = StockLevel.objects.filter(tenant_id=tenant_id)
    if q:
        niveis = niveis.filter(product__short_name__icontains=q)
    if product_id is not None:
        niveis = niveis.filter(product_id=product_id)
    linhas = (
        niveis.values(
            *_CAMPOS_DO_ARTIGO,
            "product__min_quantity",
            "location_id",
            "location__name",
            "location__position",
        )
        .annotate(
            quantidade=Sum("quantity"),
            valor=Sum(F("quantity") * F("unit_cost"), output_field=_VALOR),
            sem_custo=_quantidade_sem_custo(),
        )
        .order_by("product__short_name", "product_id", "location__position", "location__name")
    )

    validades = _validade_mais_proxima(
        tenant_id=tenant_id, location_id=location_id, hoje=hoje, product_id=product_id
    )
    por_artigo: dict[UUID, dict[str, Any]] = {}
    for linha in linhas:
        artigo = por_artigo.setdefault(
            linha["product_id"],
            {
                "product": linha["product_id"],
                "short_name": linha["product__short_name"],
                "base_unit": linha["product__base_unit"],
                "display_unit": linha["product__display_unit"],
                "display_factor": linha["product__display_factor"],
                "min_quantity": linha["product__min_quantity"],
                "saldo_do_estabelecimento": Decimal("0"),
                "quantidade": Decimal("0"),
                "sem_custo": Decimal("0"),
                "valor": Decimal("0"),
                "by_location": [],
                "no_ambito": False,
            },
        )
        quantidade = linha["quantidade"] or Decimal("0")
        # O saldo do estabelecimento soma **sempre**, porque é ele que decide o
        # `status` contra o mínimo do artigo — também com `?loja=`.
        artigo["saldo_do_estabelecimento"] += quantidade
        if location_id is not None and linha["location_id"] != location_id:
            continue
        # A linha existe naquela prateleira: é isso que põe o artigo na lista,
        # e **não** a quantidade ser diferente de zero. Um artigo que entrou e
        # acabou aparece com `status: "esgotado"`, que é o que o ecrã mostra
        # primeiro; um artigo que nunca lá esteve não aparece de todo.
        artigo["no_ambito"] = True
        artigo["quantidade"] += quantidade
        artigo["sem_custo"] += linha["sem_custo"] or Decimal("0")
        artigo["valor"] += linha["valor"] or Decimal("0")
        if quantidade != Decimal("0"):
            artigo["by_location"].append(
                {
                    "location_id": linha["location_id"],
                    "location_name": linha["location__name"],
                    "quantidade": quantidade,
                }
            )

    compostas = [
        _nivel_de_stock(artigo, validade=validades.get(artigo["product"]))
        for artigo in por_artigo.values()
        if artigo["no_ambito"]
    ]
    compostas.sort(key=_ordem_do_nivel)
    return compostas


def _nivel_de_stock(
    artigo: dict[str, Any], *, validade: dict[str, Any] | None
) -> dict[str, Any]:
    """Uma linha composta: o saldo, o que ele vale e a cobertura do custo.

    `unit_cost` e `total_value` saem daqui **sempre**; quem os tira do payload
    é o `SemEurosParaQuemNaoVe`, no serializer. Esta camada não conhece papéis,
    e é de propósito: uma query que ramificasse no papel era a segunda
    definição da política que a ADR 0032 desfez.
    """
    quantidade = artigo["quantidade"]
    sem_custo = artigo["sem_custo"]
    valor = artigo["valor"].quantize(_CENTIMO, rounding=ROUND_HALF_UP)
    return {
        "product": artigo["product"],
        "short_name": artigo["short_name"],
        "base_unit": artigo["base_unit"],
        "display_unit": artigo["display_unit"],
        "display_factor": artigo["display_factor"],
        "quantidade": quantidade,
        "min_quantity": artigo["min_quantity"],
        "status": _estado_do_nivel(
            saldo=artigo["saldo_do_estabelecimento"], minimo=artigo["min_quantity"]
        ),
        "by_location": artigo["by_location"],
        "nearest_expiry": validade,
        "quantity_without_cost": sem_custo,
        "unit_cost": _custo_unitario(
            valor=valor, quantidade_com_custo=quantidade - sem_custo
        ),
        "total_value": valor,
    }


def nivel_do_artigo(
    *, tenant_id: UUID, product_id: UUID, hoje: date | None = None
) -> dict[str, Any] | None:
    """A linha de **um** artigo, ou `None` se ele não tem `StockLevel` nenhum.

    O corpo do `GET /stock/levels/<product_id>` (ADR 0034, adenda de 29,
    decisão 12). É a `niveis_de_stock` com o `product_id` posto e **não** uma
    leitura nova: a linha que sai daqui é, chave a chave, a que a lista serve
    para o mesmo artigo — e há um teste que o afirma nos dois sentidos.

    Sem `?loja=`, e isso é decisão e não omissão (decisão 16): o detalhe é
    sempre do estabelecimento inteiro, porque é do `by_location` que o
    formulário escolhe **onde** registar a quebra.

    `None` quer dizer "não há história nenhuma deste artigo neste
    estabelecimento" — nem receção, nem contagem, nem ajuste. **Não** quer
    dizer que o artigo não existe: quem sabe isso é o `catalog`, e é a view
    que lhe pergunta para distinguir o vazio (200) do erro (404).
    """
    linhas = niveis_de_stock(tenant_id=tenant_id, product_id=product_id, hoje=hoje)
    return linhas[0] if linhas else None


def nivel_sem_entradas(*, produto: Any) -> dict[str, Any]:
    """O nível de um artigo que **nunca entrou**: o mesmo nível, com zeros.

    O estado (b) da decisão 13: existe no catálogo, não tem `StockLevel`
    nenhum. Sai do **mesmo** `_nivel_de_stock` que a lista usa — com saldo
    zero, sem repartição e sem validade — para o corpo ter a forma da linha e
    não a de um segundo recurso.

    Recebe um `ProdutoResumo` do `catalog.api` (a aresta permitida), e é dele
    que vêm as **unidades**: um artigo sem entradas tem `display_unit` e
    `display_factor` como qualquer outro, logo o corpo traz a quantidade na
    unidade em que a pessoa fala e não cai para a unidade base só porque o
    saldo é zero.

    O `status` sai `"esgotado"` pelo `_estado_do_nivel`, sem ramo novo — e
    **nenhuma superfície o escreve** sobre um artigo com `never_stocked: true`
    (decisão 13): "esgotado" é uma afirmação sobre consumo, e sobre o que nunca
    entrou é falsa no sentido que importa. Quem serve a superfície lê o campo.
    """
    return _nivel_de_stock(
        {
            "product": produto.id,
            "short_name": produto.short_name,
            "base_unit": produto.base_unit,
            "display_unit": produto.display_unit,
            "display_factor": produto.display_factor,
            "min_quantity": produto.min_quantity,
            "saldo_do_estabelecimento": Decimal("0"),
            "quantidade": Decimal("0"),
            "sem_custo": Decimal("0"),
            "valor": Decimal("0"),
            "by_location": [],
        },
        validade=None,
    )


def _ordem_do_nivel(linha: dict[str, Any]) -> tuple[int, int, int, str]:
    """Estado, depois `days_away` com NULLS LAST, depois o nome. **Nunca valor.**

    O `1` antes do `days_away` é o NULLS LAST escrito à mão: uma linha sem
    validade ordena depois de todas as que têm, seja qual for o número.
    """
    validade = linha["nearest_expiry"]
    peso = (
        ESTADOS_DO_NIVEL.index(linha["status"])
        if linha["status"] in ESTADOS_DO_NIVEL
        else len(ESTADOS_DO_NIVEL)
    )
    if validade is None:
        return (peso, 1, 0, linha["short_name"])
    return (peso, 0, validade["days_away"], linha["short_name"])


def _e_a_expirar(linha: dict[str, Any], *, limiar_em_dias: int) -> bool:
    """A linha entra no filtro `validade`? O mesmo predicado do contador."""
    validade = linha["nearest_expiry"]
    return validade is not None and validade["days_away"] <= limiar_em_dias


def niveis_filtrados(
    linhas: Sequence[dict[str, Any]], *, filtro: str, limiar_em_dias: int
) -> list[dict[str, Any]]:
    """O `?filtro=falta|validade` do ecrã de Stock, no servidor.

    Vivia em JavaScript sobre `results` e com paginação a sério isso procurava
    **só nas 50 piores linhas**, calando as outras em silêncio (ADR 0034,
    decisão 2). Aqui é um predicado só, e é o **mesmo** que o `resumo_de_stock`
    usa para contar: é assim que o contador do topo é igual ao `count` da lista
    que ele filtra, por construção e não por coincidência.
    """
    if filtro == "falta":
        return [linha for linha in linhas if linha["status"] != "ok"]
    if filtro == "validade":
        return [
            linha for linha in linhas if _e_a_expirar(linha, limiar_em_dias=limiar_em_dias)
        ]
    return list(linhas)


def resumo_de_stock(
    *,
    tenant_id: UUID,
    location_id: UUID | None = None,
    hoje: date | None = None,
    limiar_em_dias: int = DIAS_DE_VALIDADE_DO_PAINEL,
) -> dict[str, Any]:
    """Os quatro números do topo do ecrã de Stock.

    Derivados da **mesma** lista que o `/stock/levels` serve, com os **mesmos**
    predicados: `below_min_count` é o `count` de `?filtro=falta` e
    `expiring_count` é o de `?filtro=validade`, no mesmo âmbito. É a invariante
    que a ADR 0034 escreveu, e tê-la por construção é o que impede a
    divergência de voltar.

    `expiring_count` conta **artigos** e o dos Alertas conta **linhas da lista
    de alertas** (lote × localização): são dois factos com dois rótulos, e cada
    um é igual à sua lista.

    `stock_value_eur` **não soma artigos com saldo negativo ou nulo**: um `Sum`
    ingénuo faria o valor do stock descer por causa de um saldo que ninguém
    tem. As linhas negativas continuam visíveis na lista com `status:
    "negativo"`, que é onde elas significam alguma coisa.
    """
    linhas = niveis_de_stock(tenant_id=tenant_id, location_id=location_id, hoje=hoje)
    valor = sum(
        (linha["total_value"] for linha in linhas if linha["quantidade"] > Decimal("0")),
        Decimal("0"),
    )
    return {
        "below_min_count": len(
            niveis_filtrados(linhas, filtro="falta", limiar_em_dias=limiar_em_dias)
        ),
        "expiring_count": len(
            niveis_filtrados(linhas, filtro="validade", limiar_em_dias=limiar_em_dias)
        ),
        "expiring_within_days": limiar_em_dias,
        "stock_value_eur": valor.quantize(_CENTIMO, rounding=ROUND_HALF_UP),
    }


# ---------------------------------------------------------------------------
# As leituras do assistente (ADR 0027, decisão 6) e dos alertas do painel
# ---------------------------------------------------------------------------
def saldos_do_artigo(
    *, tenant_id: UUID, product_id: UUID, location_id: UUID | None = None
) -> QuerySet[StockLevel]:
    """Os níveis de um artigo, por localização e lote, em ordem FEFO.

    Sem o `exclude(quantity=0)` das vistas do painel: o chamador distingue
    "nunca entrou" (zero linhas) de "entrou e acabou" (linhas a zero), e é essa
    a diferença entre `nunca_entrou: true` e um saldo de 0 (ADR 0027).
    """
    niveis = StockLevel.objects.filter(tenant_id=tenant_id, product_id=product_id)
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    return niveis.select_related("product", "location", "lot").order_by(
        F("lot__expires_at").asc(nulls_last=True), "lot__received_at", "location__position", "id"
    )


def artigos_abaixo_do_minimo(
    *, tenant_id: UUID, location_id: UUID | None = None, limite: int = 50
) -> list[dict[str, Any]]:
    """Os artigos cujo **saldo somado** está abaixo do mínimo do artigo.

    `min_quantity` é por artigo e não por loja, logo compara-se contra o `SUM`
    em todas as localizações: 3 × 400 g em três lojas contra um mínimo de
    1000 g **não** alarma. O selector antigo comparava lote a lote e dava
    exactamente esse alarme falso. Com `location_id` soma-se só essa, e quem lê
    tem de dizer que o mínimo é do artigo e não da loja.

    Excluídos: mínimo a zero (não há mínimo), inactivos, e artigos sem
    `StockLevel` nenhum (nunca entraram). Saldo ≤ 0 com `StockLevel` é
    `sem_stock`; `0 < saldo < min` é `abaixo_do_minimo`.

    Devolve `limite + 1` linhas no máximo, para o chamador saber se cortou.
    """
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id,
        product__is_active=True,
        product__min_quantity__gt=Decimal("0"),
    )
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    linhas = (
        niveis.values(*_CAMPOS_DO_ARTIGO, "product__min_quantity")
        .annotate(saldo=Sum("quantity"))
        .filter(saldo__lt=F("product__min_quantity"))
        .order_by("product__short_name", "product_id")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "min_quantity": linha["product__min_quantity"],
            "saldo": linha["saldo"],
            "estado": SEM_STOCK if linha["saldo"] <= Decimal("0") else ABAIXO_DO_MINIMO,
        }
        for linha in linhas
    ]


def lotes_a_vencer(
    *,
    tenant_id: UUID,
    hoje: date,
    dias: int,
    location_id: UUID | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Os lotes **com saldo** que vencem até `hoje + dias`, vencidos incluídos.

    Comparação por **data** e não por instante: a validade é a data impressa na
    embalagem. `hoje` é o dia **civil** nos dois chamadores — painel e
    assistente —, e a razão está no `business_day_starts_at` do `Tenant`: o
    relógio do negócio decide a que dia pertence um movimento, um total, uma
    receção ou um desperdício, e **não** decide validades. Entre as 00:00 e as
    04:00 o "hoje" do negócio ainda é ontem, e com ele a app diria "expira
    amanhã" de um lote que a ASAE já considera expirado. Até 2026-10-16 o
    assistente passava aqui o dia de negócio e o painel o civil — duas regras
    para a mesma data (ADR 0028). A janela é rolante sobre `hoje`.

    Os lotes já vencidos entram **e são marcados** pelo chamador
    (`< hoje`), porque a pergunta "o que vence esta semana" tem como pior
    resposta um lote vencido que ficou de fora por já ter vencido.

    Só lotes com saldo somado > 0: um lote consumido até ao fim não vence em
    lado nenhum. O `join` ao `StockLevel` é o que o garante; a tabela `Lot`
    sozinha não sabe se ainda há mercadoria.

    `conservation` e `expiry_kind` são dados da linha, nunca filtro. Devolve
    `limite + 1` linhas no máximo.
    """
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id,
        lot__isnull=False,
        lot__expires_at__isnull=False,
        lot__expires_at__date__lte=hoje + timedelta(days=dias),
    )
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    linhas = (
        niveis.values(
            *_CAMPOS_DO_ARTIGO,
            "product__expiry_kind",
            "product__conservation",
            "lot_id",
            "lot__code",
            "lot__expires_at",
        )
        .annotate(saldo=Sum("quantity"))
        .filter(saldo__gt=Decimal("0"))
        .order_by("lot__expires_at", "product__short_name", "lot__code")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "expiry_kind": linha["product__expiry_kind"],
            "conservation": linha["product__conservation"],
            "lot_id": linha["lot_id"],
            "lot_code": linha["lot__code"],
            "expires_at": linha["lot__expires_at"],
            "expires_on": timezone.localdate(linha["lot__expires_at"]),
            "saldo": linha["saldo"],
        }
        for linha in linhas
    ]


def movimentos_resumidos(
    *,
    tenant_id: UUID,
    product_id: UUID,
    desde: datetime,
    ate: datetime,
    tipos: Sequence[str] | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    """O resumo por tipo e as últimas `limite` linhas de um artigo em `[desde, ate)`.

    O resumo é um `GROUP BY movement_type` com `n` e a quantidade **com sinal**,
    e cobre o período inteiro; as linhas são as `limite` mais recentes e vêm
    com `truncado` quando há mais. As transferências vêm com a contraparte — a
    localização do outro movimento do mesmo `transfer_id` — para a resposta
    poder dizer "da Loja para o Armazém" em vez de duas linhas soltas.
    """
    movimentos = StockMovement.objects.filter(
        tenant_id=tenant_id, product_id=product_id, occurred_at__gte=desde, occurred_at__lt=ate
    )
    if tipos:
        movimentos = movimentos.filter(movement_type__in=list(tipos))
    resumo = {
        linha["movement_type"]: {"n": linha["n"], "quantidade": linha["quantidade"]}
        for linha in movimentos.values("movement_type")
        .annotate(n=Count("id"), quantidade=Sum("quantity"))
        .order_by("movement_type")
    }
    ultimos = list(
        movimentos.select_related("location", "lot").order_by("-occurred_at", "-created_at", "-id")[
            : limite + 1
        ]
    )
    truncado = len(ultimos) > limite
    ultimos = ultimos[:limite]

    transfer_ids = {m.transfer_id for m in ultimos if m.transfer_id is not None}
    contrapartes: dict[tuple[UUID, str], str] = {}
    if transfer_ids:
        pares = StockMovement.objects.filter(
            tenant_id=tenant_id, transfer_id__in=transfer_ids
        ).select_related("location")
        for par in pares:
            contrapartes[(par.transfer_id, par.movement_type)] = par.location.name

    linhas = []
    for m in ultimos:
        contraparte = None
        if m.transfer_id is not None:
            outro = "transfer_in" if m.movement_type == "transfer_out" else "transfer_out"
            contraparte = contrapartes.get((m.transfer_id, outro))
        linhas.append(
            {
                "id": m.id,
                "movement_type": m.movement_type,
                "quantity": m.quantity,
                "unit_cost": m.unit_cost,
                "cost_is_estimate": m.cost_is_estimate,
                "occurred_at": m.occurred_at,
                "location_name": m.location.name,
                "lot_code": m.lot.code if m.lot is not None else None,
                "reason": m.reason,
                "reference": m.reference,
                "transfer_id": m.transfer_id,
                "contraparte": contraparte,
                "created_by_name": m.created_by_name,
            }
        )
    return {"resumo": resumo, "linhas": linhas, "truncado": truncado}


def _alertas_de_validade(
    *, tenant_id: UUID, hoje: date, limiar_em_dias: int
) -> list[dict[str, Any]]:
    """Um alerta por **lote × localização** com saldo, até `hoje + limiar`.

    Por lote **e** localização, e não por lote: um lote transferido tem saldo
    em duas prateleiras, e agregá-lo punha o `location` a `null` — o `POST` de
    quebra da linha levaria `""`, que é 400, e o alerta deixava de ser
    accionável, que é a única coisa que ele tem. É por isso que o `id` é
    `expiry:<lot_id>:<location_id>` e não `expiry:<lot_id>`, que colidia.

    Os vencidos entram e ficam no topo: a pior resposta a "o que vence esta
    semana" é um lote vencido que ficou de fora por já ter vencido.
    """
    linhas = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            lot__isnull=False,
            lot__expires_at__isnull=False,
            lot__expires_at__date__lte=hoje + timedelta(days=limiar_em_dias),
        )
        .values(
            *_CAMPOS_DO_ARTIGO,
            "product__expiry_kind",
            "lot_id",
            "lot__code",
            "lot__expires_at",
            "location_id",
            "location__name",
        )
        .annotate(
            saldo=Sum("quantity"),
            valor=Sum(F("quantity") * F("unit_cost"), output_field=_VALOR),
            sem_custo=_quantidade_sem_custo(),
        )
        .filter(saldo__gt=Decimal("0"))
        .order_by("lot__expires_at", "product__short_name", "lot_id")
    )
    alertas = []
    for linha in linhas:
        validade = _validade(
            lot_id=linha["lot_id"],
            lot_code=linha["lot__code"],
            expires_at=linha["lot__expires_at"],
            expiry_kind=linha["product__expiry_kind"],
            hoje=hoje,
        )
        saldo = linha["saldo"] or Decimal("0")
        valor = (linha["valor"] or Decimal("0")).quantize(
            _CENTIMO, rounding=ROUND_HALF_UP
        )
        custo = _custo_unitario(
            valor=valor,
            quantidade_com_custo=saldo - (linha["sem_custo"] or Decimal("0")),
        )
        alertas.append(
            {
                "id": f"expiry:{linha['lot_id']}:{linha['location_id']}",
                "product": linha["product_id"],
                "short_name": linha["product__short_name"],
                "base_unit": linha["product__base_unit"],
                "display_unit": linha["product__display_unit"],
                "display_factor": linha["product__display_factor"],
                "reason": "expiry",
                "severity": validade["severity"],
                "location_id": linha["location_id"],
                "location_name": linha["location__name"],
                "quantidade": saldo,
                "lot": validade,
                "threshold_days": limiar_em_dias,
                "min_quantity": None,
                "value_eur": valor,
                "cost_status": _estado_do_custo(custo),
            }
        )
    return alertas


def _alertas_de_falta(*, tenant_id: UUID, hoje: date) -> list[dict[str, Any]]:
    """Um alerta por artigo cujo `status` não é `ok`, no estabelecimento inteiro.

    **A mesma projeção que o ecrã de Stock lê**, e não um segundo cálculo de
    "em falta": se este recalculasse, o número do Stock e o dos Alertas
    divergiam no dia em que um dos dois mudasse — e o dono descobria-o antes de
    nós. Sem localização, porque o mínimo é do artigo e vale sobre o
    consolidado: uma loja a apontar aqui era uma precisão que o dado não tem.

    O euro é **o que custa voltar ao mínimo** e não o que lá está: num alerta
    de validade o valor é o que se arrisca perder, aqui é o que se vai gastar,
    e o ecrã diz qual dos dois é.
    """
    alertas = []
    for linha in niveis_de_stock(tenant_id=tenant_id, hoje=hoje):
        if linha["status"] == "ok":
            continue
        a_repor = max(Decimal("0"), linha["min_quantity"] - linha["quantidade"])
        custo = linha["unit_cost"]
        alertas.append(
            {
                "id": f"missing:{linha['product']}",
                "product": linha["product"],
                "short_name": linha["short_name"],
                "base_unit": linha["base_unit"],
                "display_unit": linha["display_unit"],
                "display_factor": linha["display_factor"],
                "reason": "missing",
                "severity": (
                    GRAVIDADE_AVISO if linha["status"] == "baixo" else GRAVIDADE_PERIGO
                ),
                "location_id": None,
                "location_name": None,
                "quantidade": linha["quantidade"],
                "lot": None,
                "threshold_days": None,
                "min_quantity": linha["min_quantity"],
                "value_eur": (
                    (a_repor * custo).quantize(_CENTIMO, rounding=ROUND_HALF_UP)
                    if custo is not None
                    else Decimal("0")
                ),
                "cost_status": _estado_do_custo(custo),
            }
        )
    return alertas


def _ordem_do_alerta(alerta: dict[str, Any]) -> tuple[int, int, int, str]:
    """Gravidade, depois `days_away` com NULLS LAST, depois o nome. Nunca valor.

    Dentro da mesma gravidade, quem tem relógio vem antes: um lote que expira
    hoje é mais urgente do que uma prateleira vazia, que espera pela próxima
    entrega. O desempate por `value_eur` que o fixture fazia **não** atravessa
    — uma lista ordenada por euros são os euros (ADR 0032, adenda).
    """
    peso = (
        GRAVIDADES.index(alerta["severity"])
        if alerta["severity"] in GRAVIDADES
        else len(GRAVIDADES)
    )
    if alerta["lot"] is None:
        return (peso, 1, 0, alerta["short_name"])
    return (peso, 0, alerta["lot"]["days_away"], alerta["short_name"])


def alertas_de_stock(
    *,
    tenant_id: UUID,
    risco: str = "",
    hoje: date | None = None,
    limiar_em_dias: int = DIAS_DE_VALIDADE_DO_PAINEL,
) -> list[dict[str, Any]]:
    """O ecrã de Alertas: **uma** lista, dois motivos, ordenada no servidor.

    `risco=expira` traz só as validades, `risco=falta` só as faltas, e sem
    parâmetro vêm as duas. O vocabulário é o do cliente (`danger|warning|info`,
    `expiry|missing`): esta é a lista que o utilizador vê, e traduzi-la duas
    vezes era criar a divergência outra vez.

    As validades estão no calendário **civil** (`timezone.localdate()`) e o
    desperdício, na rota ao lado, no dia **de negócio**. Ver o bloco dos dois
    relógios no topo deste ficheiro antes de "corrigir" um deles.
    """
    hoje = hoje or timezone.localdate()
    alertas: list[dict[str, Any]] = []
    if risco != "falta":
        alertas += _alertas_de_validade(
            tenant_id=tenant_id, hoje=hoje, limiar_em_dias=limiar_em_dias
        )
    if risco != "expira":
        alertas += _alertas_de_falta(tenant_id=tenant_id, hoje=hoje)
    alertas.sort(key=_ordem_do_alerta)
    return alertas


def contadores_de_alertas(
    *,
    tenant_id: UUID,
    hoje: date | None = None,
    limiar_em_dias: int = DIAS_DE_VALIDADE_DO_PAINEL,
) -> dict[str, int]:
    """`expiring_count` e `missing_count`, cada um igual ao `count` da sua lista.

    Contam **linhas da lista** e não lotes: com o alerta a ser por lote ×
    localização, "lotes" nem sequer estava bem definido (ADR 0034, adenda, a
    correcção à decisão 5). São duas listas, logo são dois números — e é por
    isso que o `expiring_count` daqui difere do do ecrã de Stock, que conta
    **artigos**.
    """
    alertas = alertas_de_stock(
        tenant_id=tenant_id, hoje=hoje, limiar_em_dias=limiar_em_dias
    )
    return {
        "expiring_count": sum(1 for a in alertas if a["reason"] == "expiry"),
        "missing_count": sum(1 for a in alertas if a["reason"] == "missing"),
    }


def linhas_de_desperdicio(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> QuerySet[StockMovement]:
    """As **linhas** de quebra de `[desde, até)`, da mais recente para a mais antiga.

    Linhas e não agregado, e é a fronteira com o `reporting` escrita (ADR 0034,
    decisão 4): *o `reporting` agrega o negócio num período e é do dono; o
    `inventory` lista o ledger para quem age sobre ele.* Esta lista fica ao
    lado do botão que a cria e tem de chegar ao `staff`.

    `[desde, até)` e não `periodo`: acrescentar uma janela histórica para uma
    inspeção passa a ser um parâmetro, e não uma reescrita.
    """
    return (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            movement_type="waste",
            occurred_at__gte=desde,
            occurred_at__lt=ate,
        )
        .select_related("product", "location", "lot")
        .order_by("-occurred_at", "-created_at", "-id")
    )


def contadores_de_desperdicio(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> dict[str, Any]:
    """Quantas quebras, quanto valeram e quantas não têm preço, numa janela.

    ## Porque é que o `COUNT` tem de viver num `aggregate()` e nunca num `values()`

    Um `COUNT(id)` não reconstrói um custo unitário: a reconstrução que a ADR
    0032 fechou é sempre uma **divisão** (`value_eur ÷ quantity`), e uma
    contagem não tem euros em ponta nenhuma. **Mas só enquanto ficar fora de um
    `values().annotate()` que inclua `unit_cost`** — agrupar a contagem por
    custo unitário serve o custo unitário na chave do grupo, e a fuga volta
    pela mesma porta com outro nome. É o defeito exacto que a ADR 0032 mediu no
    `stock_summary`, e há um teste que lê o SQL (`test_stock_e_alertas.py`).

    A **cobertura** entra pela régua da ADR 0032: `linhas_sem_custo` são
    **linhas e não euros**, iguais para os três papéis. Sem isso, "7 quebras
    hoje" e "7 quebras hoje, 4 sem preço conhecido" são a mesma frase.
    """
    agregado = StockMovement.objects.filter(
        tenant_id=tenant_id,
        movement_type="waste",
        occurred_at__gte=desde,
        occurred_at__lt=ate,
    ).aggregate(
        n=Count("id"),
        valor=Sum(F("quantity") * F("unit_cost"), output_field=_VALOR),
        sem_custo=Count("id", filter=Q(unit_cost=Decimal("0"))),
    )
    return {
        # Positivo: uma quebra está no ledger a negativo porque é uma saída, e
        # "deitaste fora −12,40 €" não é uma frase.
        "valor_eur": abs(agregado["valor"] or Decimal("0")).quantize(
            _CENTIMO, rounding=ROUND_HALF_UP
        ),
        "n": agregado["n"] or 0,
        "linhas_sem_custo": agregado["sem_custo"] or 0,
    }


def movimentos_do_artigo(*, tenant_id: UUID, product_id: UUID) -> QuerySet[StockMovement]:
    """O ledger de um artigo, do mais recente para o mais antigo.

    `occurred_at` e nunca `created_at` para ordenar (ADR 0013, decisão 8): uma
    receção lançada na segunda-feira com a mercadoria entrada no sábado é do
    sábado. Os dois desempates que se seguem existem para a paginação não
    repetir nem perder linhas quando dois movimentos partilham o instante — o
    par de uma transferência partilha-o sempre.
    """
    return (
        StockMovement.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related("product", "location", "lot")
        .order_by("-occurred_at", "-created_at", "-id")
    )


def rotulos_de_referencia(
    *, tenant_id: UUID, referencias: Iterable[str]
) -> dict[str, tuple[str, str]]:
    """`{referência: (tipo, rótulo)}` para as que este módulo sabe nomear.

    O `reference` de um `adjustment` de fecho é o **id cru da contagem**
    (`fechar_contagem` grava `reference=str(stock_count_id)`), e o ecrã dizia
    "texto curto, para mostrar" — imprimiria um uuid. **Não se muda o que se
    grava**: há um índice parcial em `inv_stockmv_tenant_ref_idx` e dois
    lookups por essa string (`ajustes_da_contagem`, `valor_dos_ajustes_por_artigo`).
    O que se serve são dois campos novos, e o ecrã imprime o rótulo.

    Só nomeia o que é **deste** módulo: a contagem é modelo do próprio
    `inventory`, logo dizer "Contagem de 24/10, Armazém" não obriga ninguém a
    saber como o `purchasing` chama um documento. O que vier de fora fica sem
    rótulo, e sem rótulo o ecrã não imprime nada.
    """
    candidatos = set()
    for referencia in referencias:
        if not referencia:
            continue
        try:
            candidatos.add(UUID(referencia))
        except (ValueError, AttributeError, TypeError):
            continue
    if not candidatos:
        return {}
    contagens = StockCount.objects.filter(
        tenant_id=tenant_id, pk__in=candidatos
    ).select_related("location")
    rotulos: dict[str, tuple[str, str]] = {}
    for contagem in contagens:
        quando = timezone.localdate(contagem.closed_at or contagem.started_at)
        rotulos[str(contagem.pk)] = (
            "contagem",
            f"Contagem de {quando:%d/%m}, {contagem.location.name}",
        )
    return rotulos


# ---------------------------------------------------------------------------
# As leituras da ADR 0028: contagens, desperdício, produções e custo médio.
# Nenhuma escreve, e nenhuma devolve ORM a quem chama pela porta — o `api.py`
# congela tudo em DTOs.
# ---------------------------------------------------------------------------
def e_lote_sintetico(codigo: str | None) -> bool:
    """O `code` deste lote é um sintético (`__…__`) e não um lote de verdade?

    Um lote sintético nasce em dois sítios — a confirmação de uma receção de um
    artigo sem lote impresso e a produção de uma receita (ADR 0023 e 0026) — e
    existe para o ledger ter uma chave, não para alguém o ler. Quem o mostra diz
    "sem lote".
    """
    return bool(codigo) and codigo.startswith("__") and codigo.endswith("__")


def contagens_do_ambito(*, tenant_id: UUID) -> QuerySet[StockCount]:
    """Todas as contagens do estabelecimento, com a localização carregada."""
    return StockCount.objects.filter(tenant_id=tenant_id).select_related("location")


def listar_contagens(
    *, tenant_id: UUID, estado: str = "", limite: int = 20
) -> list[StockCount]:
    """As contagens por estado: `open` primeiro pelo início, `closed` pelo fecho.

    Devolve `limite + 1` linhas no máximo, para quem chama saber se cortou. Uma
    contagem aberta ordena-se pela data em que começou (a mais antiga é a que
    está esquecida) e uma fechada pela data em que fechou, mais recente
    primeiro — são duas perguntas diferentes.
    """
    contagens = contagens_do_ambito(tenant_id=tenant_id)
    if estado:
        contagens = contagens.filter(status=estado)
    if estado == "open":
        contagens = contagens.order_by("started_at", "id")
    else:
        contagens = contagens.order_by(F("closed_at").desc(nulls_last=True), "-started_at", "id")
    return list(contagens[: limite + 1])


def contagens_com_progresso(
    *, tenant_id: UUID, estado: str = ""
) -> QuerySet[StockCount]:
    """A lista do `GET /stock/counts`: a mais recente primeiro, com o progresso.

    O "12 de 34" do topo vem de duas agregações sobre o mesmo `LEFT JOIN` e não
    de uma query por contagem — uma lista de vinte contagens não paga vinte
    idas à base. O `id` desempata para a paginação não repetir linhas.

    O `estado` é o `?status=open|closed` da rota (ADR 0033, decisão 4): com
    várias contagens abertas ao mesmo tempo, "as que estão a decorrer" passou a
    ser uma pergunta a sério, e o cliente deixa de a responder com um
    `results.find(status === "open")` sobre a primeira página. Vazio é "todas"
    — quem chama valida o valor, porque um estado que não existe é uma recusa e
    não uma lista a fingir que filtrou.
    """
    contagens = contagens_do_ambito(tenant_id=tenant_id)
    if estado:
        contagens = contagens.filter(status=estado)
    return contagens.annotate(
        n_linhas=Count("lines"),
        n_contadas=Count("lines", filter=Q(lines__quantity_counted__isnull=False)),
    ).order_by("-started_at", "-id")


def progresso_da_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> dict[str, int]:
    """Quantas linhas tem esta contagem e quantas já foram contadas."""
    agregado = StockCountLine.objects.filter(
        tenant_id=tenant_id, stock_count_id=stock_count_id
    ).aggregate(
        n_linhas=Count("id"),
        n_contadas=Count("id", filter=Q(quantity_counted__isnull=False)),
    )
    return {
        "n_linhas": agregado["n_linhas"] or 0,
        "n_contadas": agregado["n_contadas"] or 0,
    }


def contagem_aberta(*, tenant_id: UUID, location_id: UUID) -> StockCount | None:
    """A contagem aberta **desta localização**, se houver — e há no máximo uma.

    O máximo é da base e não desta função: `inventory_stockcount_uma_aberta_por_local`
    é um índice único parcial (ADR 0030, decisão 2; ADR 0033, decisão 1). Aqui
    serve para dizer ao ecrã **qual** é a que já está aberta ali quando a segunda
    tentativa dá 409 — e com várias localizações abertas ao mesmo tempo, esse
    `id` passou a ser a única forma de lá chegar.

    A lista das abertas do estabelecimento não vive aqui: é o `GET
    /stock/counts?status=open`, servido pelo `contagens_com_progresso`.
    """
    return (
        contagens_do_ambito(tenant_id=tenant_id)
        .filter(status="open", location_id=location_id)
        .first()
    )


def linhas_da_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> list[StockCountLine]:
    """As linhas de uma contagem, com artigo e lote carregados, pelo nome do artigo.

    A ordem é a do **catálogo** e é ela que dá o `position` de cada linha na
    resposta: o `position` não é coluna, é o índice nesta ordenação (ADR 0030,
    decisão 4). É dívida nomeada — o guião diz "nunca alfabética" e a ordem do
    percurso só existe quando as zonas existirem.

    A `zone` saiu da ordenação porque ninguém a escreve: nesta fatia a zona *é*
    a localização (decisão 3), e ordenar por uma coluna constante é ruído.
    """
    return list(
        StockCountLine.objects.filter(tenant_id=tenant_id, stock_count_id=stock_count_id)
        .select_related("product", "lot")
        .order_by("product__short_name", "id")
    )


def niveis_para_contagem(
    *, tenant_id: UUID, location_id: UUID, product_ids: Sequence[UUID]
) -> dict[UUID, list[StockLevel]]:
    """Os níveis de cada artigo **nesta localização**, por lote e em ordem FEFO.

    Sem `exclude(quantity=0)`: um nível a zero não recebe nem dá quantidade, mas
    é ele que traz o `unit_cost` com que uma sobra nesse lote se valoriza — e
    excluí-lo era voltar a valorizar a zero em silêncio, que é o defeito que a
    ADR 0030 manda corrigir.

    A ordem é a do FEFO (validade primeiro, `NULLS LAST`, depois a data de
    receção), que é a ordem por que uma falta sai. Quem precisa do "mais
    recente" para uma sobra reordena a lista — a chave é a mesma e está aqui
    numa query só.
    """
    if not product_ids:
        return {}
    niveis = (
        StockLevel.objects.filter(
            tenant_id=tenant_id, location_id=location_id, product_id__in=product_ids
        )
        .select_related("lot")
        .order_by(
            F("lot__expires_at").asc(nulls_last=True), "lot__received_at", "lot_id", "id"
        )
    )
    por_artigo: dict[UUID, list[StockLevel]] = {}
    for nivel in niveis:
        por_artigo.setdefault(nivel.product_id, []).append(nivel)
    return por_artigo


def lotes_dos_artigos(
    *, tenant_id: UUID, product_ids: Sequence[UUID]
) -> dict[UUID, list[Lot]]:
    """Os lotes de cada artigo, do mais recente para o mais antigo.

    É a rede de recurso de uma sobra: um artigo cujo lote não tem nível **nesta**
    localização (entrou noutra, ou o nível foi para zero e desapareceu) continua
    a ter lote, e inventar um sintético por cima de um lote a sério partia a
    rastreabilidade. Os sintéticos ficam de fora porque não são lote nenhum.
    """
    if not product_ids:
        return {}
    lotes = Lot.objects.filter(tenant_id=tenant_id, product_id__in=product_ids).order_by(
        "-received_at", "-id"
    )
    por_artigo: dict[UUID, list[Lot]] = {}
    for lote in lotes:
        if e_lote_sintetico(lote.code):
            continue
        por_artigo.setdefault(lote.product_id, []).append(lote)
    return por_artigo


def artigo_tem_lote(*, tenant_id: UUID, product_id: UUID) -> bool:
    """O artigo tem algum lote **a sério** registado neste estabelecimento?

    Os sintéticos (`__<product_id>__`) não contam: eles existem para o ledger ter
    uma chave num artigo sem rastreio, e um artigo com `track_lots=True` que só
    os tenha não tem rastreabilidade nenhuma. É esta a pergunta que o `POST
    /lines` faz antes de recusar contar (ADR 0030, segunda ronda, resposta 4).
    """
    codigos = Lot.objects.filter(tenant_id=tenant_id, product_id=product_id).values_list(
        "code", flat=True
    )
    return any(not e_lote_sintetico(codigo) for codigo in codigos)


def custos_de_artigo_na_localizacao(
    *, tenant_id: UUID, location_id: UUID, product_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """O `ProductCost` de cada artigo nesta localização, numa query.

    O segundo degrau do custo de um ajuste de contagem: sem nível para o lote
    escolhido, vale a média ponderada de `(artigo, localização)` (ADR 0023,
    decisão 1). Sem ela, o custo é zero — e aí o movimento vai marcado como
    estimativa, porque zero euros de diferença é uma afirmação e não um facto.
    """
    if not product_ids:
        return {}
    custos = ProductCost.objects.filter(
        tenant_id=tenant_id, location_id=location_id, product_id__in=product_ids
    ).values_list("product_id", "unit_cost")
    return dict(custos)


def saldos_por_artigo_na_localizacao(
    *, tenant_id: UUID, location_id: UUID
) -> list[dict[str, Any]]:
    """Os artigos com stock **nesta** localização e o saldo somado de cada um.

    É a lista com que uma contagem nasce (ADR 0030, decisão 4). Entra o artigo
    que tem pelo menos um nível com quantidade diferente de zero; o `expected`
    é a soma de **todos** os seus níveis nesta localização, incluindo os que
    estão a zero e os negativos — a soma é o que o sistema diz que lá está.

    Um artigo sem nível nenhum não entra: nunca passou por aqui, e uma linha a
    zero para cada artigo do catálogo faria da contagem um inventário do
    catálogo em vez do da prateleira. Quem conta um artigo que não está na lista
    acrescenta-o pelo `POST /lines`.
    """
    com_movimento = (
        StockLevel.objects.filter(tenant_id=tenant_id, location_id=location_id)
        .exclude(quantity=Decimal("0"))
        .values_list("product_id", flat=True)
        .distinct()
    )
    return list(
        StockLevel.objects.filter(
            tenant_id=tenant_id, location_id=location_id, product_id__in=com_movimento
        )
        .values("product_id")
        .annotate(saldo=Sum("quantity"))
        .order_by("product_id")
    )


def saldos_por_artigo_ate(
    *, tenant_id: UUID, location_id: UUID, cortes: Mapping[UUID, datetime]
) -> dict[UUID, Decimal]:
    """O saldo de cada artigo nesta localização **até ao instante de corte dele**.

    `Σ(quantity)` dos movimentos com `occurred_at ≤ corte`, e é a base contra a
    qual o fecho de uma contagem escreve o ajuste (ADR 0033, adenda): o que os
    livros diziam na hora em que alguém olhou para a prateleira.

    Três coisas que não são detalhe:

    * **lê-se o ledger e não o `StockLevel`.** O nível é a projeção de *todos*
      os movimentos, sem hora; é o número de agora, e o de agora é a única base
      que ninguém observou;
    * **o corte é por `occurred_at`**, nunca por `created_at` nem pela ordem de
      inserção. Uma fatura fotografada às 11h com data de entrega às 7h entra na
      base de uma contagem das 8h, e é esse o caso que obriga a recalcular isto
      no fecho em vez de o gravar quando a linha se escreve;
    * **o empate entra** (`≤`): um movimento com a hora exacta da observação
      aconteceu até à observação, e quem contou viu-o.

    Um corte por artigo numa query só: cada artigo tem o seu `counted_at` (a
    farinha contou-se às 6h12 e o açúcar às 6h20) e a condição vai num `OR` por
    par `(artigo, corte)`. Os artigos são distintos entre si, logo nenhuma linha
    de movimento conta para o corte de outro artigo. Um artigo sem movimento
    nenhum **não vem** no resultado; quem lê trata a ausência como zero, que é o
    que o ledger diz de quem nunca entrou.
    """
    if not cortes:
        return {}
    condicao = Q()
    for product_id, corte in cortes.items():
        condicao |= Q(product_id=product_id, occurred_at__lte=corte)
    somas = (
        StockMovement.objects.filter(tenant_id=tenant_id, location_id=location_id)
        .filter(condicao)
        .values("product_id")
        .annotate(saldo=Sum("quantity"))
    )
    return {soma["product_id"]: soma["saldo"] for soma in somas}


def saldo_do_artigo_na_localizacao(
    *, tenant_id: UUID, location_id: UUID, product_id: UUID
) -> Decimal:
    """A soma dos níveis de um artigo nesta localização. `0` se nunca entrou.

    O `expected` de uma linha que nasce no `POST /lines` — o artigo que apareceu
    e não estava na lista. Zero é o que o ledger diz de um artigo que nunca
    entrou, e é por isso que a diferença dele é um `adjustment` positivo e nunca
    um `receipt`: uma receção tem fornecedor, documento e preço.
    """
    return StockLevel.objects.filter(
        tenant_id=tenant_id, location_id=location_id, product_id=product_id
    ).aggregate(saldo=Sum("quantity"))["saldo"] or Decimal("0")


def custos_dos_niveis(
    *, tenant_id: UUID, location_id: UUID, chaves: Sequence[tuple[UUID, UUID | None]]
) -> dict[tuple[UUID, UUID | None], Decimal]:
    """O `unit_cost` de cada `(artigo, lote)` nesta localização, numa query.

    A chave inclui o **lote**, e é essa a correcção da ADR 0028: o
    `resumo_contagem` lia `.first()` de `(artigo, localização)` sem lote, e numa
    localização com dois lotes do mesmo artigo valorizava a diferença de um pelo
    custo do outro — em silêncio, e sempre pelo lote que a base devolvesse
    primeiro.
    """
    if not chaves:
        return {}
    produtos = {produto_id for produto_id, _ in chaves}
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id, location_id=location_id, product_id__in=produtos
    ).values("product_id", "lot_id", "unit_cost")
    return {(nivel["product_id"], nivel["lot_id"]): nivel["unit_cost"] for nivel in niveis}


def ajustes_da_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> dict[str, Any]:
    """Os `adjustment` que o fecho de uma contagem gravou: quantos, quando e quanto.

    A ligação é o `reference` do movimento, que o `fechar_contagem` grava com o
    id da contagem (ADR 0025). Uma contagem aberta não tem nenhum — e é isso
    que permite dizer "esta contagem ainda não mexeu no stock".
    """
    linhas = StockMovement.objects.filter(
        tenant_id=tenant_id, movement_type="adjustment", reference=str(stock_count_id)
    ).values("quantity", "unit_cost", "occurred_at")
    n = 0
    valor = Decimal("0")
    quando: datetime | None = None
    for linha in linhas:
        n += 1
        valor += abs(linha["quantity"]) * linha["unit_cost"]
        if quando is None or linha["occurred_at"] > quando:
            quando = linha["occurred_at"]
    return {"n": n, "valor_eur": valor, "ultimo_em": quando}


def valor_dos_ajustes_por_artigo(
    *, tenant_id: UUID, stock_count_id: UUID
) -> dict[UUID, Decimal]:
    """O valor com sinal dos `adjustment` que o fecho gravou, por artigo.

    Depois de fechar, o `difference_eur` de uma linha deixa de ser uma previsão:
    é o que ficou no ledger, e lê-se de lá pela `reference`. Recalculá-lo contra
    os níveis de hoje daria um número diferente do que foi gravado, e a
    divergência só apareceria a quem fosse somar as duas coisas à mão.

    Por artigo e não por linha porque o movimento não guarda o id da linha — a
    ligação é `(contagem, artigo)`, que é única desde a ADR 0030.
    """
    linhas = StockMovement.objects.filter(
        tenant_id=tenant_id, movement_type="adjustment", reference=str(stock_count_id)
    ).values("product_id", "quantity", "unit_cost")
    por_artigo: dict[UUID, Decimal] = {}
    for linha in linhas:
        valor = linha["quantity"] * linha["unit_cost"]
        por_artigo[linha["product_id"]] = por_artigo.get(
            linha["product_id"], Decimal("0")
        ) + valor
    return por_artigo


def desperdicio_por_artigo_e_motivo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 50
) -> list[dict[str, Any]]:
    """Σ dos `waste` de `[desde, ate)`, por artigo e motivo, com o valor em euros.

    Resumo e não lista de movimentos, e **sem limiar**: um desperdício de 200 g
    de salsa conta na mesma linha que o de 20 kg de farinha, e quem lê decide o
    que destaca. O valor é `|quantidade| × unit_cost` **do movimento** (ADR
    0014: qualquer agregado se valoriza pelo custo gravado na linha, nunca pelo
    custo de hoje), e um `unit_cost` a zero sai como zero com a contagem de
    linhas sem custo ao lado.
    """
    linhas = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            movement_type="waste",
            occurred_at__gte=desde,
            occurred_at__lt=ate,
        )
        .values(*_CAMPOS_DO_ARTIGO, "reason")
        .annotate(
            n=Count("id"),
            quantidade=Sum("quantity"),
            valor=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField()),
            sem_custo=Count("id", filter=Q(unit_cost=Decimal("0"))),
        )
        .order_by("product__short_name", "reason")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "reason": linha["reason"] or "",
            "n": linha["n"],
            # **Positiva**: um `waste` está no ledger com a quantidade a
            # negativo, porque é uma saída, e "perdeu-se −2 kg" não é uma
            # frase. O sinal lê-se aqui, uma vez, como já se lia no valor — o
            # DTO `DesperdicioPorArtigo` promete-o e até 2026-10-16 só o valor
            # o cumpria.
            "quantidade": abs(linha["quantidade"] or Decimal("0")),
            "valor_eur": abs(linha["valor"] or Decimal("0")),
            "linhas_sem_custo": linha["sem_custo"],
        }
        for linha in linhas
    ]


def producoes_por_periodo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 20
) -> list[dict[str, Any]]:
    """As produções de `[desde, ate)`, uma por `production_id`, mais recente primeiro.

    Uma produção é o par que a ADR 0026 grava: N `production_out` (os
    ingredientes que saíram, em FEFO) e **um** `production_in` (o acabado que
    entrou), todos com o mesmo `production_id`. É por ele que se agrupa, porque
    é o único laço que o ledger tem entre as duas pontas.

    O `unit_cost` do `production_in` é o custo real daquela produção, gravado no
    momento (ADR 0026, decisão 2): é o número que se compara com o teórico da
    ficha, e não se recalcula a partir dos custos de hoje.
    """
    movimentos = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            production_id__isnull=False,
            occurred_at__gte=desde,
            occurred_at__lt=ate,
        )
        .select_related("product", "location")
        .order_by("-occurred_at", "id")
    )
    producoes: dict[UUID, dict[str, Any]] = {}
    for movimento in movimentos:
        producao = producoes.setdefault(
            movimento.production_id,
            {
                "production_id": movimento.production_id,
                "occurred_at": movimento.occurred_at,
                "location_name": movimento.location.name,
                "created_by_name": movimento.created_by_name,
                "product_id": None,
                "product_name": "",
                "base_unit": "",
                "display_unit": "",
                "display_factor": Decimal("1"),
                "quantidade": Decimal("0"),
                "unit_cost": Decimal("0"),
                "ingredientes": [],
            },
        )
        if movimento.movement_type == "production_in":
            producao["product_id"] = movimento.product_id
            producao["product_name"] = movimento.product.short_name
            producao["base_unit"] = movimento.product.base_unit
            producao["display_unit"] = movimento.product.display_unit
            producao["display_factor"] = movimento.product.display_factor
            producao["quantidade"] = movimento.quantity
            producao["unit_cost"] = movimento.unit_cost
            producao["occurred_at"] = movimento.occurred_at
        elif movimento.movement_type == "production_out":
            producao["ingredientes"].append(
                {
                    "product_id": movimento.product_id,
                    "product_name": movimento.product.short_name,
                    "base_unit": movimento.product.base_unit,
                    "display_unit": movimento.product.display_unit,
                    "display_factor": movimento.product.display_factor,
                    "quantidade": abs(movimento.quantity),
                    "unit_cost": movimento.unit_cost,
                }
            )
    ordenadas = sorted(producoes.values(), key=lambda p: p["occurred_at"], reverse=True)
    return ordenadas[: limite + 1]


def custos_medios_do_artigo(*, tenant_id: UUID, product_id: UUID) -> list[dict[str, Any]]:
    """O CMP de um artigo por localização (`inventory_productcost`), por posição.

    Zero é "preço desconhecido" e não "de graça" (ADR 0024): o artigo entrou
    sem preço — uma guia de remessa — ou nunca entrou. Quem lê diz a palavra.
    """
    return [
        {
            "product_id": custo.product_id,
            "location_id": custo.location_id,
            "location_name": custo.location.name,
            "unit_cost": custo.unit_cost,
        }
        for custo in ProductCost.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related("location")
        .order_by("location__position", "location__name")
    ]


# ===========================================================================
# Os agregados do painel (ADR 0029). **Tudo em SQL**: a ADR 0013 decisão 5
# proíbe um ciclo em Python sobre o ledger, e não é estilo — doze meses de
# movimentos de um tenant são dezenas de milhares de linhas a atravessar a
# fronteira para somar cinco números.
#
# Nenhuma destas funções arredonda. `SUM(quantity * unit_cost)` é `numeric`
# exato no Postgres e é assim que sai: o arredondamento é uma decisão de
# apresentação e vive **uma vez**, à saída do `reporting` (ADR 0013, decisão 4).
# Arredondar por movimento ou num passo intermédio é como a identidade dos três
# termos deixa de fechar ao cêntimo.
#
# O **sinal** também não se lê aqui: o que sai é o que o ledger gravou (uma
# saída é negativa). Quem serve "positivo = quebra" nega uma vez, no seu
# `selectors.py`. Duas inversões em sítios diferentes são um sinal trocado à
# espera de acontecer.
# ===========================================================================


def _dia_de_negocio(*, inicio_do_dia: time) -> Cast:
    """O balde do **dia de negócio** de `occurred_at`, como expressão SQL.

    Com o dia a começar às 04:00, um `waste` das 02:00 pertence ao dia
    anterior. A expressão é
    `(occurred_at AT TIME ZONE <fuso>) - <início>`, lida como data — e
    `::date` sobre um `timestamp` **é** o `date_trunc('day', …)` que a ADR 0013
    decisão 8 escreve, com o resultado já no tipo certo: um dia de negócio é
    uma data e não um instante.

    Três coisas que dependem da ordem das operações e por isso ficam escritas:

    * o desconto da hora é **na hora local**, depois do `AT TIME ZONE`. Em UTC,
      o domingo de março tem 23 horas e o de outubro 25: um movimento das 04:30
      locais do dia em que o relógio adianta cairia no dia de negócio anterior,
      e o `Σ(dias) == mês` continuaria a fechar a mentir;
    * é a **mesma** expressão que o agregado do total não usa — o total é a
      janela inteira —, logo os baldes particionam exatamente a janela e a soma
      deles *é* o total, em vez de se aproximar dele;
    * nada é interpolado em SQL: o fuso e o deslocamento viajam como parâmetros
      (`%s`). O `Cast` do fuso para `text` existe porque `AT TIME ZONE $1` sem
      tipo é ambíguo para o Postgres (há uma sobrecarga que recebe `interval`).
    """
    deslocamento = timedelta(
        hours=inicio_do_dia.hour,
        minutes=inicio_do_dia.minute,
        seconds=inicio_do_dia.second,
    )
    local = Func(
        F("occurred_at"),
        Cast(Value(timezone.get_current_timezone_name()), output_field=TextField()),
        template="(%(expressions)s)",
        arg_joiner=" AT TIME ZONE ",
        output_field=DateTimeField(),
    )
    return Cast(
        Func(
            local,
            Value(deslocamento, output_field=DurationField()),
            template="(%(expressions)s)",
            arg_joiner=" - ",
            output_field=DateTimeField(),
        ),
        output_field=DateField(),
    )


def _valor_do_movimento() -> Sum:
    """`SUM(quantity × unit_cost)` — o custo **gravado**, nunca o de hoje (ADR 0014)."""
    return Sum(F("quantity") * F("unit_cost"), output_field=DecimalField())


def _valor_estimado() -> Sum:
    """O mesmo, só sobre as linhas cujo custo ainda não tem fatura atrás."""
    return Sum(
        F("quantity") * F("unit_cost"),
        filter=Q(cost_is_estimate=True),
        output_field=DecimalField(),
    )


def movimentos_do_periodo(*, tenant_id: UUID, desde: datetime, ate: datetime) -> QuerySet:
    """A janela `[desde, ate)` do ledger, por `occurred_at`. A base dos agregados.

    `occurred_at` e nunca `created_at` (ADR 0013, decisão 8): uma receção
    lançada na segunda-feira com a mercadoria entrada no sábado é do sábado, e
    uma fatura não tem hora.
    """
    return StockMovement.objects.filter(
        tenant_id=tenant_id, occurred_at__gte=desde, occurred_at__lt=ate
    )


def movimentos_agregados_por_tipo(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> list[dict[str, Any]]:
    """Um `GROUP BY movement_type` da janela: quantos, quanto e quanto por estimar.

    Devolve **uma linha por tipo presente**, com os valores como o ledger os
    gravou. Quem lê classifica os tipos; esta função não sabe o que é uma
    compra.
    """
    return [
        {
            "movement_type": linha["movement_type"],
            "n": linha["n"],
            "quantidade": linha["quantidade"] or Decimal("0"),
            "valor_eur": linha["valor"] or Decimal("0"),
            "valor_estimado_eur": linha["valor_estimado"] or Decimal("0"),
        }
        for linha in movimentos_do_periodo(tenant_id=tenant_id, desde=desde, ate=ate)
        .values("movement_type")
        .annotate(n=Count("id"), quantidade=Sum("quantity"))
        .annotate(valor=_valor_do_movimento(), valor_estimado=_valor_estimado())
        .order_by("movement_type")
    ]


def movimentos_agregados_por_dia_de_negocio(
    *, tenant_id: UUID, desde: datetime, ate: datetime, inicio_do_dia: time
) -> list[dict[str, Any]]:
    """O mesmo agregado, com o balde do dia de negócio ao lado do tipo.

    A soma dos dias **é** o total da janela: o filtro é o mesmo e o balde é uma
    partição dele (ADR 0013, decisão 8). Um dia sem movimentos não tem linha —
    quem desenha o gráfico é que sabe quantas barras quer.
    """
    return [
        {
            "dia": linha["dia"],
            "movement_type": linha["movement_type"],
            "n": linha["n"],
            "quantidade": linha["quantidade"] or Decimal("0"),
            "valor_eur": linha["valor"] or Decimal("0"),
            "valor_estimado_eur": linha["valor_estimado"] or Decimal("0"),
        }
        for linha in movimentos_do_periodo(tenant_id=tenant_id, desde=desde, ate=ate)
        .annotate(dia=_dia_de_negocio(inicio_do_dia=inicio_do_dia))
        .values("dia", "movement_type")
        .annotate(n=Count("id"), quantidade=Sum("quantity"))
        .annotate(valor=_valor_do_movimento(), valor_estimado=_valor_estimado())
        .order_by("dia", "movement_type")
    ]


def desperdicio_agregado_por_motivo(
    *, tenant_id: UUID, desde: datetime, ate: datetime
) -> list[dict[str, Any]]:
    """Σ dos `waste` da janela por motivo. **Cinco linhas, sem truncatura.**

    O `desperdicio_por_artigo_e_motivo` corta a lista porque serve uma resposta
    a uma pessoa; este é um total, e um total truncado é um total errado. São
    cinco motivos: não há lista para cortar.
    """
    return [
        {
            "reason": linha["reason"] or "",
            "n": linha["n"],
            "quantidade": linha["quantidade"] or Decimal("0"),
            "valor_eur": linha["valor"] or Decimal("0"),
        }
        for linha in movimentos_do_periodo(tenant_id=tenant_id, desde=desde, ate=ate)
        .filter(movement_type="waste")
        .values("reason")
        .annotate(n=Count("id"), quantidade=Sum("quantity"))
        .annotate(valor=_valor_do_movimento())
        .order_by("reason")
    ]


def valor_de_stock(*, tenant_id: UUID) -> Decimal:
    """`Σ(quantidade × CMP)` dos níveis de stock — **instantâneo a agora**.

    Base diferente da do fluxo: o fluxo vale ao custo gravado em cada movimento
    (ADR 0014) e isto vale ao custo médio de hoje, porque é o que está lá. Não
    se deriva a variação de stock pela diferença de dois instantâneos, e não se
    serve um "valor de abertura" — quem lê imprime a data a que isto foi lido.
    """
    agregado = StockLevel.objects.filter(tenant_id=tenant_id).aggregate(
        valor=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField())
    )
    return agregado["valor"] or Decimal("0")


def ultima_contagem_fechada_em(*, tenant_id: UUID) -> datetime | None:
    """`MAX(closed_at)` das contagens fechadas **com alguma linha contada**.

    Fechadas e não iniciadas: é o fecho que gera os `adjustment`, logo é o fecho
    que explica a quebra desconhecida. `None` é "nunca se contou", e o painel
    escreve-o — zero quebra sem contagem não é boa notícia, é ausência de
    medição (ADR 0013, decisão 7).

    **Com alguma linha contada**, desde a ADR 0033 (decisão do dono de
    2026-10-21): essa ADR tornou o fecho a forma de limpar uma contagem aberta
    por engano, e uma contagem sem nada contado passaria a dizer ao painel que a
    arca foi contada hoje sem ninguém lá ter ido — no número que existe
    precisamente para saber o que falta contar. Uma contagem **parcial** conta:
    contou-se parte, e isso é mais do que não contar (ADR 0030, decisão 5).

    `EXISTS` e não um `JOIN` com `DISTINCT`: a pergunta é "houve pelo menos
    uma", e a base pára na primeira linha em vez de somar as trezentas.
    """
    contadas = StockCountLine.objects.filter(
        tenant_id=tenant_id,
        stock_count_id=OuterRef("pk"),
        quantity_counted__isnull=False,
    )
    return (
        StockCount.objects.filter(tenant_id=tenant_id, status="closed")
        .filter(Exists(contadas))
        .aggregate(ultima=Max("closed_at"))["ultima"]
    )
