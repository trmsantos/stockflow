"""A porta do módulo `recipes` (ARCHITECTURE.md §3).

Fatia 6: produção de receitas.
ADR 0028: **leitura** — a ficha técnica, as produções recentes e os dois custos.
ADR 0035, fatia A: a ficha é por **fornada**, o custo teórico é **um** número do
estabelecimento, e o custo de cada ingrediente é uma **escada de cinco degraus**.

Expõe DTOs (frozen dataclasses) e funções que outros módulos chamam via api.py.
Nenhuma escrita direta: tudo via services.py.

## O que a ADR 0028 muda aqui

Até 2026-10-16 esta porta expunha uma função — `produzir` — e o contrato do
import-linter proibia `agents → recipes` (ADR 0027, decisão 5: "`recipes` fica
fora"). O dono pediu que o assistente responda sobre receitas (quem usa farinha,
qual é a ficha, o que se produziu ontem), e a 0028 revoga esse "fica fora": a
aresta passa a `agents → recipes.api`, e **só** leitura atravessa — a lista
fechada do registo de tools é o que o garante, porque o import-linter não sabe
dizer "só leitura".

## Unidades e dinheiro

Como nas outras portas: as quantidades vêm na unidade **base** do artigo, com
`display_unit` e `display_factor` ao lado para quem lê as apresentar. Nenhuma
conversão acontece aqui.

A ficha é por **fornada** (ADR 0035, decisão 8): o `batch_size` diz quanto
acabado sai de uma execução, e cada linha traz duas colunas — a da lista
(`quantidade_lista`, o que a receita escreve **para a fornada**) e a do **consumo
real** (lista ÷ `yield_factor`, o que de facto sai do stock). As duas existem
porque são números diferentes e a confusão entre elas é o erro clássico do
rendimento.

*(O cabeçalho que aqui estava dizia "a ficha é por **uma unidade de apresentação**
do acabado" enquanto o DTO ao lado dizia "por unidade **base**" e a implementação
seguia o segundo: num artigo com base em gramas e apresentação em quilos as duas
frases diferiam por **mil vezes** no custo. Nenhuma das duas sobreviveu à decisão
8, e o cabeçalho corrigiu-se com o resto — ADR 0035, "Defeitos nomeados".)*

## O custo, e porque é **um** número e não uma linha por localização

O `_custos()` devolvia uma linha por localização e calculava cada uma com
`por_artigo.get(product_id, 0)`: um ingrediente sem CMP naquela localização era
**saltado em silêncio**. Numa pastelaria com Armazém e Cozinha a farinha está num
e o creme no outro, logo **todas** as linhas saíam incompletas e **todas** por
baixo. A ADR 0035, decisão 3, revoga essa forma: há **uma** definição, que é o
mesmo `unit_cost` que o ecrã de Stock mostra, do estabelecimento inteiro, pela
mesma função. Nenhum degrau da escada lê o `inventory_productcost`, que é por
loja e reinstalava em silêncio o que a decisão revogou.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.utils import timezone

from apps.inventory import api as inventory_api
from apps.inventory.api import (
    CUSTO_CONHECIDO,
    CUSTO_DESCONHECIDO,
    CUSTO_ESTIMADO,
    ESTADOS_DO_CUSTO,
)
from apps.recipes import selectors as _selectors
from apps.recipes.services import produzir

__all__ = [
    "CUSTO_CONHECIDO",
    "CUSTO_DESCONHECIDO",
    "CUSTO_ESTIMADO",
    "ESTADOS_DO_CUSTO",
    "PROFUNDIDADE_MAXIMA",
    "CustoDaReceita",
    "IngredienteDaReceita",
    "ReceitaDetalhe",
    "ReceitaResumo",
    "contar_receitas_por_ingrediente",
    "fichas_das_receitas",
    "procurar_receitas",
    "producoes_por_periodo",
    "produzir",
    "receita_por_artigo",
    "receita_por_id",
]

#: Até onde se procura a "última produção" para o custo real, e até onde se lê o
#: último preço do ledger no degrau 3 da escada. Um ano: mais antigo do que isso
#: é um custo que já não diz nada sobre o de hoje.
_JANELA_DO_CUSTO_REAL = timedelta(days=365)

#: Quantos níveis de semi-acabado a leitura cascateia (`inventory-domain` §4, e
#: ADR 0035, decisão 10, degrau 4). Três é o tecto do domínio: massa folhada →
#: base de pastel → pastel de nata. Mais do que isto é quase sempre erro de
#: dados.
#:
#: **É também a rede da terminação**, e é a única: a avaliação gasta um
#: orçamento que começa aqui e desce estritamente a cada ficha que abre, logo a
#: recursão é estrutural sobre um inteiro que decresce e pára sempre — com
#: ciclos nos dados ou sem eles. Ver `_custos_dos_ingredientes`, que explica
#: porque é que o conjunto de visitados que aqui estava **não** servia para
#: isto e calculava a menos.
PROFUNDIDADE_MAXIMA = 3


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceitaResumo:
    """Uma receita como a lista a mostra: o acabado, a fornada e o rendimento."""

    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    is_active: bool
    #: Quanto acabado sai de **uma** fornada, na unidade base (ADR 0035, d8).
    batch_size: Decimal
    yield_factor: Decimal
    n_ingredientes: int


@dataclass(frozen=True, kw_only=True, slots=True)
class IngredienteDaReceita:
    """Um ingrediente da ficha, nas suas duas quantidades e com o seu custo.

    `quantidade_lista` é o que a receita escreve **para uma fornada**;
    `quantidade_real` é `lista ÷ yield_factor`, o que sai do stock para a fornada
    sair à quantidade pedida. Com rendimento 100 % são iguais.

    `unit_cost` é o custo de uma unidade base deste ingrediente pela escada da
    decisão 10, e `cost_status` diz com que certeza — `conhecido` só no primeiro
    degrau. `None` com `desconhecido` quer dizer uma coisa só: *não há número
    nenhum*, e é o que o ecrã imprime como "—".

    `is_active` é do **artigo** e não da linha: um artigo arquivado dentro de uma
    ficha activa aceita-se e assinala-se (ADR 0035). Quem recusa é a produção, na
    fatia B — arquivar um artigo não pode partir a gravação de uma ficha que já o
    continha.
    """

    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    is_active: bool
    quantidade_lista: Decimal
    quantidade_real: Decimal
    unit_cost: Decimal | None
    line_cost: Decimal | None
    cost_status: str


@dataclass(frozen=True, kw_only=True, slots=True)
class CustoDaReceita:
    """O custo de ingredientes de uma ficha: **um** número, do estabelecimento.

    Nunca "custo do prato" (ADR 0035, decisão 9): é o *food cost*, só matéria, e
    chamar-lhe custo do prato era falso por um factor de 2 a 4 numa pastelaria,
    onde a mão-de-obra domina um produto com 20 cêntimos de matéria.

    Três números, e os três derivam do mesmo numerador por arredondar:

    * `batch_cost` = Σ(`line_cost`) — o que a **fornada** custa;
    * `unit_cost` = `batch_cost ÷ batch_size` — por unidade **base** do acabado;
    * `display_cost` = `unit_cost × display_factor` — por unidade de
      **apresentação**, que é a pergunta do dono (*"quanto me custa um pastel"*).

    A divisão é **no fim** (decisão 8): dividir por linha e somar dá um total
    diferente do da fornada, e o dono vai somar à mão. O arredondamento é só na
    saída, no serializer.

    `cost_status` é o agregado: **nunca** `conhecido` se alguma linha não o for,
    `desconhecido` só quando **nenhuma** linha tem custo — e aí os três euros
    saem `None`, que é a afirmação verdadeira. `ingredients_without_cost` é uma
    **contagem** e não um euro, logo vai para os três papéis; é uma cobertura
    mais fraca do que a `quantity_without_cost` da ADR 0032 — um ingrediente em
    dez pode ser 90 % do custo — e não há forma melhor sem revelar euros. É por
    isso que o `cost_status` **por linha** existe ao lado.

    `real` é o `unit_cost` do `production_in` da **última produção**: o que custou
    de facto, com os custos gravados no momento (ADR 0026, decisão 2). Nunca se
    recalcula o passado com os preços de hoje (ADR 0014). **Não entra no contrato
    HTTP da fatia A** (decisão 2): sem produções seria `null` em 100 % das
    linhas, e uma coluna de "—" no dia do lançamento ensina o dono que a coluna
    está partida. Fica aqui porque o assistente já o serve desde a ADR 0028, e
    só se calcula no caminho de **detalhe** — na lista seria uma leitura por
    receita, que é o N+1 que a decisão 3 matou.
    """

    batch_cost: Decimal | None
    unit_cost: Decimal | None
    display_cost: Decimal | None
    cost_status: str
    ingredients_without_cost: int
    real: Decimal | None
    real_em: datetime | None


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceitaDetalhe:
    """A ficha técnica inteira: o resumo, os ingredientes e o custo."""

    resumo: ReceitaResumo
    ingredientes: tuple[IngredienteDaReceita, ...]
    custo: CustoDaReceita


@dataclass(frozen=True, kw_only=True, slots=True)
class _CustoDeIngrediente:
    """O que a escada devolve por artigo: um número e a certeza dele."""

    unit_cost: Decimal | None
    cost_status: str


def _resumo(receita: Any, *, n_ingredientes: int) -> ReceitaResumo:
    produto = receita.product
    return ReceitaResumo(
        id=receita.id,
        product_id=receita.product_id,
        product_name=produto.short_name,
        sku=produto.sku,
        base_unit=produto.base_unit,
        display_unit=produto.display_unit,
        display_factor=produto.display_factor,
        is_active=receita.is_active,
        batch_size=receita.batch_size,
        yield_factor=receita.yield_factor,
        n_ingredientes=n_ingredientes,
    )


def procurar_receitas(
    *,
    tenant_id: UUID,
    q: str = "",
    ingrediente_id: UUID | None = None,
    incluir_inativas: bool = False,
    limite: int = 10,
) -> tuple[tuple[ReceitaResumo, ...], bool]:
    """As receitas que casam com a procura, e se a lista cortou.

    `ingrediente_id` responde "que receitas usam farinha"; `q` casa no nome
    curto ou no SKU do **acabado**.
    """
    receitas = _selectors.procurar_receitas(
        tenant_id=tenant_id,
        q=q,
        ingrediente_id=ingrediente_id,
        incluir_inativas=incluir_inativas,
        limite=limite,
    )
    truncado = len(receitas) > limite
    receitas = receitas[:limite]
    linhas = _selectors.ingredientes_das_receitas(
        tenant_id=tenant_id, recipe_ids=[r.id for r in receitas]
    )
    quantas: dict[UUID, int] = {}
    for linha in linhas:
        quantas[linha.recipe_id] = quantas.get(linha.recipe_id, 0) + 1
    return (
        tuple(_resumo(r, n_ingredientes=quantas.get(r.id, 0)) for r in receitas),
        truncado,
    )


def receita_por_artigo(*, tenant_id: UUID, product_id: UUID) -> ReceitaResumo | None:
    """A receita que produz este artigo, ou `None`. O acabado é único por receita."""
    receitas = _selectors.receitas_dos_artigos(tenant_id=tenant_id, product_ids=[product_id])
    if not receitas:
        return None
    linhas = _selectors.ingredientes_das_receitas(
        tenant_id=tenant_id, recipe_ids=[receitas[0].id]
    )
    return _resumo(receitas[0], n_ingredientes=len(linhas))


def contar_receitas_por_ingrediente(*, tenant_id: UUID, product_id: UUID) -> int:
    """Em quantas receitas activas este artigo entra como ingrediente."""
    return _selectors.contar_receitas_por_ingrediente(
        tenant_id=tenant_id, product_id=product_id
    )


def fichas_das_receitas(
    *, tenant_id: UUID, receitas: Sequence[Any], agora: datetime | None = None
) -> tuple[ReceitaDetalhe, ...]:
    """As fichas de uma **página** de receitas, com o custo calculado em lote.

    É esta a função que o `GET /recipes` e o `GET /recipes/<id>` usam, e é uma só
    de propósito: a linha da lista tem de ser a mesma coisa que o cabeçalho da
    ficha, por construção e não por coincidência (é o argumento da ADR 0034,
    adenda de 29, decisão 14, aplicado aqui).

    **A escada corre em lote, não por linha** (ADR 0035, decisão 10): duas
    leituras para as linhas de todas as receitas da página, e depois a escada uma
    vez sobre o conjunto de **todos** os ingredientes — não um degrau por
    ingrediente. A decisão 3 matou um N+1 e isto não o reabre.

    Não calcula o custo **real** (o da última produção): isso é por receita e
    seria uma leitura por linha da lista. Quem o quer é o `receita_por_id`.
    """
    receitas = list(receitas)
    if not receitas:
        return ()
    agora = agora or timezone.now()
    linhas = _selectors.ingredientes_das_receitas(
        tenant_id=tenant_id, recipe_ids=[r.id for r in receitas]
    )
    por_receita: dict[UUID, list[Any]] = {r.id: [] for r in receitas}
    for linha in linhas:
        por_receita.setdefault(linha.recipe_id, []).append(linha)

    custos = _custos_dos_ingredientes(
        tenant_id=tenant_id,
        product_ids=[linha.ingredient_product_id for linha in linhas],
        desde=agora - _JANELA_DO_CUSTO_REAL,
    )
    fichas = []
    for receita in receitas:
        suas = por_receita.get(receita.id, [])
        ingredientes = _ingredientes(receita=receita, linhas=suas, custos=custos)
        fichas.append(
            ReceitaDetalhe(
                resumo=_resumo(receita, n_ingredientes=len(suas)),
                ingredientes=ingredientes,
                custo=_agregar(receita=receita, ingredientes=ingredientes),
            )
        )
    return tuple(fichas)


def receita_por_id(*, tenant_id: UUID, recipe_id: UUID) -> ReceitaDetalhe | None:
    """A ficha técnica de uma receita, com ingredientes e custo.

    Uma receita **inactiva** responde como qualquer outra: mercadoria que
    existiu continua auditável, e esconder a ficha fazia "não tenho essa
    receita" mentir.
    """
    receita = _selectors.receita_do_ambito(tenant_id=tenant_id, recipe_id=recipe_id)
    if receita is None:
        return None
    ficha = fichas_das_receitas(tenant_id=tenant_id, receitas=[receita])[0]
    real, real_em = _ultima_producao(tenant_id=tenant_id, product_id=receita.product_id)
    return ReceitaDetalhe(
        resumo=ficha.resumo,
        ingredientes=ficha.ingredientes,
        custo=CustoDaReceita(
            batch_cost=ficha.custo.batch_cost,
            unit_cost=ficha.custo.unit_cost,
            display_cost=ficha.custo.display_cost,
            cost_status=ficha.custo.cost_status,
            ingredients_without_cost=ficha.custo.ingredients_without_cost,
            real=real,
            real_em=real_em,
        ),
    )


# ---------------------------------------------------------------------------
# A escada dos cinco degraus (ADR 0035, decisão 10)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class _GrafoDoCusto:
    """O que a leitura em largura trouxe da base de dados, já em memória.

    `custos` são os degraus 1 a 3 por artigo — o que o `inventory` sabe;
    `fichas` leva do **artigo acabado** à ficha **activa** dele; `linhas` leva
    da ficha às linhas dela, com o artigo ingrediente já carregado. Depois
    disto a escada não volta a tocar na base de dados: o degrau 4 avalia-se
    inteiro sobre estas três tabelas.
    """

    custos: Mapping[UUID, _CustoDeIngrediente]
    fichas: Mapping[UUID, Any]
    linhas: Mapping[UUID, tuple[Any, ...]]


#: O degrau 5 em forma de valor: não há número nenhum. É o que um artigo que o
#: grafo não alcançou vale, e é diferente de zero — zero seria uma afirmação
#: falsa sobre o preço.
_SEM_CUSTO = _CustoDeIngrediente(unit_cost=None, cost_status=CUSTO_DESCONHECIDO)


def _custos_dos_ingredientes(
    *, tenant_id: UUID, product_ids: Sequence[UUID], desde: datetime
) -> Mapping[UUID, _CustoDeIngrediente]:
    """O custo de cada ingrediente, pela escada, **para o conjunto todo de uma vez**.

    | # | quando | número | palavra |
    |---|---|---|---|
    | 1 | há quantidade com custo e **toda** tem preço | o `unit_cost` do stock | `conhecido` |
    | 2 | há quantidade com custo e parte não tem preço | o mesmo | `estimado` |
    | 3 | não há quantidade com custo | o último `unit_cost > 0` do ledger | `estimado` |
    | 4 | nada no ledger, mas o artigo tem **ficha activa** | o custo dessa ficha | `estimado` |
    | 5 | nada disto | nenhum — `None` | `desconhecido` |

    Os degraus 1 a 3 são do `inventory` e saem da sua porta em **duas** queries
    (`custos_de_artigos`): é lá que vive o que é um custo de stock, e é a mesma
    função que o ecrã de Stock usa — quem compara a ficha com o `/stock` vê o
    mesmo número (decisão 3).

    O degrau 4 é daqui, porque é aqui que vive o que é uma ficha.

    ## Ler em largura, avaliar por artigo — e porque são duas fases

    A **leitura** continua a ser por níveis e em lote (`_carregar_o_grafo`): um
    nível é uma chamada à porta do `inventory` mais duas leituras de fichas,
    para o conjunto inteiro dos artigos desse nível. É o que mata o N+1 que a
    decisão 3 matou, e o número de queries não cresce com o número de fichas da
    página. A **avaliação** (`_custo_pela_escada`) passou a ser por artigo,
    sobre o grafo já em memória e sem tocar na base de dados.

    Eram a mesma coisa, e isso tinha um defeito **medido contra o servidor**: o
    conjunto de visitados que impedia ciclos levava o **lote inteiro do nível**
    antes de descer. Dois semi-acabados **irmãos** no mesmo lote, com um a
    depender do outro — a Massa leva Creme, e o Bolo leva Massa **e** Creme —
    davam o dependente por `desconhecido`: a mesma ficha valia 0,03 € dentro da
    Tarte e nada dentro do Bolo, e a contribuição dela desaparecia da soma em
    silêncio, que é a família do *zero mentiroso* que a ADR 0034 fechou no
    ledger. Na lista era pior, porque o lote cobre os ingredientes de **todas**
    as receitas da página: o custo de uma ficha dependia de quem lhe calhasse ao
    lado e mudava entre a lista e o detalhe. **Irmãos não formam ciclo entre si**
    — o que forma ciclo é um caminho —, e separar as duas fases é o que torna a
    avaliação indiferente a quem está no lote.

    ## Terminação, e porque não depende da guarda de escrita

    A rede é o **orçamento de profundidade**: cada artigo avalia-se com um
    orçamento que começa em `PROFUNDIDADE_MAXIMA` e desce **estritamente** a
    cada ficha que se abre; a zero, a escada fica no degrau 3 e não expande
    mais. A recursão é estrutural sobre um inteiro que decresce, logo termina
    sempre — e termina sem olhar aos dados, que é o ponto: um ciclo no grafo é
    sempre erro de dados e a escrita recusa-o (`services.py`), mas **a guarda de
    escrita só vale até à última escrita** e esta leitura corre sobre dados
    escritos antes dela. Um ciclo gravado dá um número truncado — na prática
    `desconhecido`, que é a resposta certa para dados em ciclo — e nunca uma
    recursão infinita.

    Daí sai a propriedade que o defeito acima pedia: o custo de um artigo é uma
    função pura do par `(artigo, orçamento)`, e os artigos pedidos aqui têm
    todos o mesmo orçamento. Não depende do caminho, nem dos irmãos, nem da
    página — a mesma ficha vale o mesmo dentro de duas receitas diferentes, e na
    lista o mesmo que no detalhe.

    ## O que o degrau 4 devolve quando a sub-ficha está ela própria incompleta

    Devolve o que ela sabe, e o rótulo **nunca** é `conhecido`: um semi-acabado
    com um ingrediente sem preço dá um número por baixo, e quem o recebe fica
    `estimado` por construção. O que ele **não** faz é somar ao
    `ingredients_without_cost` de quem está acima — a cobertura mede a ficha que
    se está a ler, não o grafo todo. É a mesma fraqueza que a decisão 6 já nomeia
    para a cobertura, um nível mais abaixo.
    """
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return {}
    grafo = _carregar_o_grafo(tenant_id=tenant_id, product_ids=ids, desde=desde)
    memoria: dict[tuple[UUID, int], _CustoDeIngrediente] = {}
    return {
        product_id: _custo_pela_escada(
            product_id=product_id,
            orcamento=PROFUNDIDADE_MAXIMA,
            grafo=grafo,
            memoria=memoria,
        )
        for product_id in ids
    }


def _carregar_o_grafo(
    *, tenant_id: UUID, product_ids: Sequence[UUID], desde: datetime
) -> _GrafoDoCusto:
    """Em largura e por níveis: tudo o que a escada pode vir a precisar, de uma vez.

    Por nível: uma chamada a `custos_de_artigos` (duas queries, nunca N) para os
    artigos **novos** desse nível e, para os que saírem `desconhecido`, as fichas
    activas deles e as linhas delas — duas queries para o conjunto todo. Com a
    `PROFUNDIDADE_MAXIMA` a limitar os níveis, o total é um número fixo de
    queries, seja a página de uma receita ou de cinquenta.

    **Um artigo carrega-se uma vez só, no nível mais raso onde aparece.** Esta
    dedupe é de *carregamento* e não de avaliação, e é por isso que é segura: o
    que a base de dados sabe sobre um artigo não depende de por onde se lá
    chegou — ao contrário do custo dele, que era precisamente o que o defeito
    confundia.

    O horizonte chega e sobra: expandem-se fichas em `PROFUNDIDADE_MAXIMA`
    níveis e o último só traz custos. Um artigo descoberto ao nível N só é
    alcançável na avaliação com orçamento `PROFUNDIDADE_MAXIMA - N` ou menos
    (o nível é o caminho mais curto até ele), logo o que o último nível descobre
    nunca chega a precisar de ficha.
    """
    custos: dict[UUID, _CustoDeIngrediente] = {}
    fichas: dict[UUID, Any] = {}
    por_ficha: dict[UUID, list[Any]] = {}
    por_pedir = list(dict.fromkeys(product_ids))
    for nivel in range(PROFUNDIDADE_MAXIMA + 1):
        if not por_pedir:
            break
        for product_id, custo in inventory_api.custos_de_artigos(
            tenant_id=tenant_id, product_ids=por_pedir, desde=desde
        ).items():
            custos[product_id] = _CustoDeIngrediente(
                unit_cost=custo.unit_cost, cost_status=custo.cost_status
            )
        if nivel == PROFUNDIDADE_MAXIMA:
            break
        por_expandir = [
            product_id
            for product_id in por_pedir
            if custos[product_id].cost_status == CUSTO_DESCONHECIDO
        ]
        do_nivel = [
            receita
            for receita in _selectors.receitas_dos_artigos(
                tenant_id=tenant_id, product_ids=por_expandir
            )
            if receita.is_active
        ]
        linhas = _selectors.ingredientes_das_receitas(
            tenant_id=tenant_id, recipe_ids=[receita.id for receita in do_nivel]
        )
        for receita in do_nivel:
            fichas[receita.product_id] = receita
            por_ficha.setdefault(receita.id, [])
        for linha in linhas:
            por_ficha[linha.recipe_id].append(linha)
        por_pedir = list(
            dict.fromkeys(
                linha.ingredient_product_id
                for linha in linhas
                if linha.ingredient_product_id not in custos
            )
        )
    return _GrafoDoCusto(
        custos=custos,
        fichas=fichas,
        linhas={recipe_id: tuple(suas) for recipe_id, suas in por_ficha.items()},
    )


def _custo_pela_escada(
    *,
    product_id: UUID,
    orcamento: int,
    grafo: _GrafoDoCusto,
    memoria: dict[tuple[UUID, int], _CustoDeIngrediente],
) -> _CustoDeIngrediente:
    """O custo de **um** artigo: os degraus 1 a 3 e, se faltarem, a ficha dele.

    Função pura de `(artigo, orçamento)` sobre o grafo já carregado: não lê a
    base de dados, não conhece os irmãos e não conhece o caminho por onde se
    chegou aqui. É essa pureza que faz a mesma ficha valer o mesmo dentro de
    duas receitas diferentes, e na lista o mesmo que no detalhe.

    O `orcamento` desce a cada ficha aberta e, a zero, a escada fica no degrau 3
    — é a terminação, e é estrutural. A `memoria` é só velocidade: com a chave a
    ser o par inteiro, lembrar não muda nenhuma resposta.
    """
    base = grafo.custos.get(product_id, _SEM_CUSTO)
    if base.cost_status != CUSTO_DESCONHECIDO or orcamento <= 0:
        return base
    ficha = grafo.fichas.get(product_id)
    if ficha is None:
        return base
    lembrado = memoria.get((product_id, orcamento))
    if lembrado is not None:
        return lembrado
    linhas = grafo.linhas.get(ficha.id, ())
    de_baixo = {
        linha.ingredient_product_id: _custo_pela_escada(
            product_id=linha.ingredient_product_id,
            orcamento=orcamento - 1,
            grafo=grafo,
            memoria=memoria,
        )
        for linha in linhas
    }
    agregado = _agregar(
        receita=ficha,
        ingredientes=_ingredientes(receita=ficha, linhas=linhas, custos=de_baixo),
    )
    # Sempre **estimado**: é o custo teórico de outra ficha, não um preço pago.
    # Nunca `conhecido`, mesmo que a sub-ficha o fosse.
    resultado = (
        base
        if agregado.unit_cost is None
        else _CustoDeIngrediente(unit_cost=agregado.unit_cost, cost_status=CUSTO_ESTIMADO)
    )
    memoria[(product_id, orcamento)] = resultado
    return resultado


def _ingredientes(
    *, receita: Any, linhas: Sequence[Any], custos: Mapping[UUID, _CustoDeIngrediente]
) -> tuple[IngredienteDaReceita, ...]:
    """As linhas de uma ficha, já com as duas quantidades e o custo de cada uma."""
    rendimento = receita.yield_factor if receita.yield_factor > 0 else Decimal("1")
    saida = []
    for linha in linhas:
        artigo = linha.ingredient_product
        real = linha.quantity_per_base_unit / rendimento
        custo = custos.get(linha.ingredient_product_id)
        unitario = custo.unit_cost if custo is not None else None
        saida.append(
            IngredienteDaReceita(
                product_id=linha.ingredient_product_id,
                product_name=artigo.short_name,
                sku=artigo.sku,
                base_unit=artigo.base_unit,
                display_unit=artigo.display_unit,
                display_factor=artigo.display_factor,
                is_active=artigo.is_active,
                quantidade_lista=linha.quantity_per_base_unit,
                quantidade_real=real,
                unit_cost=unitario,
                line_cost=None if unitario is None else real * unitario,
                cost_status=custo.cost_status if custo is not None else CUSTO_DESCONHECIDO,
            )
        )
    return tuple(saida)


def _agregar(
    *, receita: Any, ingredientes: Sequence[IngredienteDaReceita]
) -> CustoDaReceita:
    """Σ(linhas) ÷ fornada, com a divisão no fim e sem arredondar pelo caminho.

    `real` e `real_em` saem `None`: quem os preenche é o `receita_por_id`, que é
    o único caminho onde custam uma leitura por receita.
    """
    fornada = receita.batch_size if receita.batch_size > 0 else Decimal("1")
    total = Decimal("0")
    com_custo = 0
    conhecidos = 0
    sem_custo = 0
    for ingrediente in ingredientes:
        if ingrediente.line_cost is None:
            sem_custo += 1
            continue
        com_custo += 1
        if ingrediente.cost_status == CUSTO_CONHECIDO:
            conhecidos += 1
        total += ingrediente.line_cost
    if com_custo == 0:
        # Nenhuma linha tem custo — e uma ficha **sem linhas** cai aqui pelo
        # mesmo caminho, que é a afirmação certa: não há número nenhum.
        return CustoDaReceita(
            batch_cost=None,
            unit_cost=None,
            display_cost=None,
            cost_status=CUSTO_DESCONHECIDO,
            ingredients_without_cost=sem_custo,
            real=None,
            real_em=None,
        )
    unitario = total / fornada
    factor = receita.product.display_factor or Decimal("1")
    return CustoDaReceita(
        batch_cost=total,
        unit_cost=unitario,
        display_cost=unitario * factor,
        # Nunca `conhecido` se alguma linha não o for (decisão 10, degrau 2):
        # com parte do stock sem preço o CMP está **por baixo**, e dizer
        # `conhecido` afirmava uma precisão que a ficha não tem.
        cost_status=(
            CUSTO_CONHECIDO
            if conhecidos == len(ingredientes) and ingredientes
            else CUSTO_ESTIMADO
        ),
        ingredients_without_cost=sem_custo,
        real=None,
        real_em=None,
    )


def _ultima_producao(
    *, tenant_id: UUID, product_id: UUID
) -> tuple[Decimal | None, datetime | None]:
    """O `unit_cost` e a data do `production_in` mais recente deste acabado."""
    agora = timezone.now()
    producoes, _ = inventory_api.producoes_por_periodo(
        tenant_id=tenant_id,
        desde=agora - _JANELA_DO_CUSTO_REAL,
        ate=agora,
        limite=50,
    )
    for producao in producoes:
        if producao.product_id == product_id:
            return producao.unit_cost, producao.occurred_at
    return None, None


def producoes_por_periodo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 20
) -> tuple[tuple[inventory_api.ProducaoResumo, ...], bool]:
    """As produções do período, pela porta do `inventory` (é lá que o ledger está).

    Está aqui e não só no `inventory` porque é a esta porta que se pergunta por
    produções: quem lê quer o nome do acabado e o id da receita ao lado, e a
    receita é deste módulo. O `inventory` não sabe o que é uma receita.
    """
    return inventory_api.producoes_por_periodo(
        tenant_id=tenant_id, desde=desde, ate=ate, limite=limite
    )
