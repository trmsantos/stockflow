"""A porta do módulo `recipes` (ARCHITECTURE.md §3).

Fatia 6: produção de receitas.
ADR 0028: **leitura** — a ficha técnica, as produções recentes e os dois custos.

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

A ficha é por **uma unidade de apresentação do acabado** (um quilo de massa, uma
unidade de pastel) e traz duas colunas por ingrediente: a da lista
(`quantity_per_base_unit`, o que a receita escreve) e a do **consumo real**
(lista ÷ `yield_factor`, o que de facto sai do stock). As duas existem porque
são números diferentes e a confusão entre eles é o erro clássico do rendimento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from apps.inventory import api as inventory_api
from apps.recipes import selectors as _selectors
from apps.recipes.services import produzir

__all__ = [
    "CustoDaReceita",
    "IngredienteDaReceita",
    "ReceitaDetalhe",
    "ReceitaResumo",
    "contar_receitas_por_ingrediente",
    "procurar_receitas",
    "producoes_por_periodo",
    "produzir",
    "receita_por_artigo",
    "receita_por_id",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceitaResumo:
    """Uma receita como a lista a mostra: o acabado, o rendimento e se está em uso."""

    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    is_active: bool
    yield_factor: Decimal
    n_ingredientes: int


@dataclass(frozen=True, kw_only=True, slots=True)
class IngredienteDaReceita:
    """Um ingrediente da ficha, nas suas duas quantidades.

    `quantidade_lista` é o que a receita escreve por unidade base de acabado;
    `quantidade_real` é `lista ÷ yield_factor`, o que sai do stock para o
    acabado sair à quantidade pedida. Com rendimento 100 % são iguais.
    """

    product_id: UUID
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    quantidade_lista: Decimal
    quantidade_real: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class CustoDaReceita:
    """Os dois custos de uma receita, rotulados — e nunca um só número.

    `teorico` é `Σ(consumo real × CMP actual)` numa localização: o que **custaria
    hoje**. `incompleto` fica a `True` quando algum ingrediente não tem CMP
    (zero é "preço desconhecido", ADR 0024), e aí o teórico está por baixo do
    real sem que isso seja uma poupança.

    `real` é o `unit_cost` do `production_in` da **última produção**: o que
    custou de facto, com os custos gravados no momento (ADR 0026, decisão 2).
    Nunca se recalcula o passado com os preços de hoje (ADR 0014).
    """

    location_id: UUID | None
    location_name: str
    teorico: Decimal | None
    incompleto: bool
    ingredientes_sem_custo: int
    real: Decimal | None
    real_em: datetime | None


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceitaDetalhe:
    """A ficha técnica inteira: o resumo, os ingredientes e os custos."""

    resumo: ReceitaResumo
    ingredientes: tuple[IngredienteDaReceita, ...]
    custos: tuple[CustoDaReceita, ...]


def _resumo(receita: object, *, n_ingredientes: int) -> ReceitaResumo:
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


def receita_por_id(*, tenant_id: UUID, recipe_id: UUID) -> ReceitaDetalhe | None:
    """A ficha técnica de uma receita, com ingredientes e custos por localização."""
    receita = _selectors.receita_do_ambito(tenant_id=tenant_id, recipe_id=recipe_id)
    if receita is None:
        return None
    linhas = _selectors.ingredientes_das_receitas(tenant_id=tenant_id, recipe_ids=[receita.id])
    rendimento = receita.yield_factor if receita.yield_factor > 0 else Decimal("1")
    ingredientes = tuple(
        IngredienteDaReceita(
            product_id=linha.ingredient_product_id,
            product_name=linha.ingredient_product.short_name,
            sku=linha.ingredient_product.sku,
            base_unit=linha.ingredient_product.base_unit,
            display_unit=linha.ingredient_product.display_unit,
            display_factor=linha.ingredient_product.display_factor,
            quantidade_lista=linha.quantity_per_base_unit,
            quantidade_real=linha.quantity_per_base_unit / rendimento,
        )
        for linha in linhas
    )
    return ReceitaDetalhe(
        resumo=_resumo(receita, n_ingredientes=len(linhas)),
        ingredientes=ingredientes,
        custos=_custos(tenant_id=tenant_id, receita=receita, ingredientes=ingredientes),
    )


def _custos(
    *, tenant_id: UUID, receita: object, ingredientes: tuple[IngredienteDaReceita, ...]
) -> tuple[CustoDaReceita, ...]:
    """O teórico por localização e o real da última produção.

    Uma linha por localização que tenha CMP de pelo menos um ingrediente, mais
    a linha "sem localização" quando só há o real. Sem localizações com custo e
    sem produções, devolve vazio — e quem lê diz "ainda não sei o custo".
    """
    cmps: dict[UUID, dict[UUID, Decimal]] = {}
    for ingrediente in ingredientes:
        for custo in inventory_api.custos_medios_por_artigo(
            tenant_id=tenant_id, product_id=ingrediente.product_id
        ):
            cmps.setdefault(custo.location_id, {})[ingrediente.product_id] = custo.unit_cost
    nomes = {
        loc.id: loc.name for loc in inventory_api.listar_localizacoes(tenant_id=tenant_id)
    }
    real, real_em = _ultima_producao(tenant_id=tenant_id, product_id=receita.product_id)
    custos: list[CustoDaReceita] = []
    for location_id, por_artigo in cmps.items():
        teorico = Decimal("0")
        sem_custo = 0
        for ingrediente in ingredientes:
            unitario = por_artigo.get(ingrediente.product_id, Decimal("0"))
            if unitario <= 0:
                sem_custo += 1
                continue
            teorico += ingrediente.quantidade_real * unitario
        custos.append(
            CustoDaReceita(
                location_id=location_id,
                location_name=nomes.get(location_id, ""),
                teorico=teorico,
                incompleto=sem_custo > 0,
                ingredientes_sem_custo=sem_custo,
                real=real,
                real_em=real_em,
            )
        )
    if not custos and real is not None:
        custos.append(
            CustoDaReceita(
                location_id=None,
                location_name="",
                teorico=None,
                incompleto=True,
                ingredientes_sem_custo=len(ingredientes),
                real=real,
                real_em=real_em,
            )
        )
    return tuple(sorted(custos, key=lambda c: c.location_name))


#: Até onde se procura a "última produção" para o custo real. Um ano: mais
#: antigo do que isso é um custo que já não diz nada sobre o de hoje.
_JANELA_DO_CUSTO_REAL = timedelta(days=365)


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
