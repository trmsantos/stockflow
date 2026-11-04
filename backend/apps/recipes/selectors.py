"""Queries de leitura do `recipes`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).

A leitura nasce com a ADR 0028: até aí o módulo só tinha `produzir`, e uma
receita só se via no ecrã que ainda não existe. O que o assistente lê é a
**ficha técnica** (ingredientes, fornada e rendimento) e, para quem pode ver
euros, o custo de ingredientes — nada disto escreve.

A ADR 0035 acrescenta duas coisas, e as duas existem para **não** haver N+1:
`listar_receitas`, que é a página do ecrã, e `arestas_do_grafo`, que responde
"que ingredientes entram nas fichas destes artigos" numa query para o conjunto
todo. O custo de uma página de receitas lê-se em lote (ver `recipes/api.py`), e
nenhuma função daqui se chama uma vez por ingrediente.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.recipes.models import Recipe, RecipeLineItem

__all__ = [
    "LIMITE_DA_PROCURA",
    "arestas_do_grafo",
    "contar_receitas_por_ingrediente",
    "ingredientes_das_receitas",
    "listar_receitas",
    "procurar_receitas",
    "receita_do_ambito",
    "receitas_dos_artigos",
]

#: O teto da procura, como no `catalog`: o resultado de uma tool cabe em 8 KB.
LIMITE_DA_PROCURA = 20


def _do_ambito(*, tenant_id: UUID) -> QuerySet[Recipe]:
    """Todas as receitas do estabelecimento, com o artigo acabado carregado."""
    return Recipe.objects.filter(tenant_id=tenant_id).select_related("product")


def _filtradas(
    *,
    tenant_id: UUID,
    q: str,
    ingrediente_id: UUID | None,
    incluir_inativas: bool,
) -> QuerySet[Recipe]:
    """O filtro comum à procura do assistente e à lista do ecrã.

    Uma função só porque são a mesma pergunta com dois tectos: *"que receitas
    casam com isto"*. Duas cópias divergiam no dia em que o `q` passasse a casar
    noutra coluna, e o assistente e o ecrã respondiam coisas diferentes à mesma
    palavra.
    """
    receitas = _do_ambito(tenant_id=tenant_id)
    if not incluir_inativas:
        receitas = receitas.filter(is_active=True)
    for token in q.split():
        receitas = receitas.filter(
            Q(product__short_name__icontains=token) | Q(product__sku__icontains=token)
        )
    if ingrediente_id is not None:
        receitas = receitas.filter(
            line_items__ingredient_product_id=ingrediente_id,
            line_items__tenant_id=tenant_id,
        ).distinct()
    return receitas


def procurar_receitas(
    *,
    tenant_id: UUID,
    q: str = "",
    ingrediente_id: UUID | None = None,
    incluir_inativas: bool = False,
    limite: int = 10,
) -> list[Recipe]:
    """As receitas que casam com `q` (nome ou SKU do acabado) e com o ingrediente.

    `ingrediente_id` é a pergunta "que receitas usam farinha" e resolve-se com
    um `filter` sobre as linhas — nunca em Python, que seria ler a tabela toda
    para descartar quase tudo.

    Inactivas ficam de fora por omissão e, quando entram, entram **marcadas**:
    uma receita inactiva não pode ser produzida, e escondê-la fazia a resposta
    "não tenho essa receita" mentir.
    """
    receitas = _filtradas(
        tenant_id=tenant_id,
        q=q,
        ingrediente_id=ingrediente_id,
        incluir_inativas=incluir_inativas,
    )
    return list(
        receitas.order_by("-is_active", "product__short_name", "id")[
            : min(limite, LIMITE_DA_PROCURA) + 1
        ]
    )


def listar_receitas(
    *,
    tenant_id: UUID,
    q: str = "",
    ingrediente_id: UUID | None = None,
    incluir_inativas: bool = False,
) -> QuerySet[Recipe]:
    """A página do `GET /recipes`: um **queryset**, para o paginador o cortar.

    Devolve queryset e não lista, ao contrário da `procurar_receitas` daqui ao
    lado: o paginador do DRF precisa de poder contar e fatiar na base de dados —
    materializar aqui era trazer as receitas todas para memória e deitar fora
    todas menos cinquenta.

    A ordem é **alfabética pelo acabado**, com as activas primeiro e o `id` a
    desempatar. O desempate não é decoração: sem ele duas receitas com o mesmo
    nome curto trocam de página entre pedidos, e o ecrã mostra a mesma linha
    duas vezes ou nenhuma.
    """
    return _filtradas(
        tenant_id=tenant_id,
        q=q,
        ingrediente_id=ingrediente_id,
        incluir_inativas=incluir_inativas,
    ).order_by("-is_active", "product__short_name", "id")


def receita_do_ambito(*, tenant_id: UUID, recipe_id: UUID) -> Recipe | None:
    """Uma receita pelo id, ou `None` se não for deste estabelecimento."""
    return _do_ambito(tenant_id=tenant_id).filter(pk=recipe_id).first()


def receitas_dos_artigos(*, tenant_id: UUID, product_ids: Sequence[UUID]) -> list[Recipe]:
    """As receitas cujo acabado é um destes artigos. Uma query, nunca N."""
    if not product_ids:
        return []
    return list(_do_ambito(tenant_id=tenant_id).filter(product_id__in=list(product_ids)))


def ingredientes_das_receitas(
    *, tenant_id: UUID, recipe_ids: Sequence[UUID]
) -> list[RecipeLineItem]:
    """As linhas de um conjunto de receitas, com o artigo ingrediente carregado."""
    if not recipe_ids:
        return []
    return list(
        RecipeLineItem.objects.filter(tenant_id=tenant_id, recipe_id__in=list(recipe_ids))
        .select_related("ingredient_product")
        .order_by("recipe_id", "created_at", "id")
    )


def arestas_do_grafo(
    *, tenant_id: UUID, product_ids: Sequence[UUID]
) -> list[tuple[UUID, UUID]]:
    """`(acabado, ingrediente)` para as fichas destes acabados. Uma query.

    É o degrau de **um** nível do grafo de semi-acabados, e existe para a guarda
    de ciclos da escrita (ADR 0035, decisão 10): percorrer o grafo transitivo
    com `receitas_dos_artigos` + `ingredientes_das_receitas` custava duas queries
    por nível e trazia objectos inteiros para comparar dois uuids.

    **Inclui as fichas inactivas, e isso é deliberado.** A leitura só cascateia
    por fichas activas — um semi-acabado arquivado não tem custo a dar —, mas um
    ciclo guardado através de uma ficha inactiva passa a ciclo real no instante
    em que alguém faz `PATCH {is_active: true}`, e nessa altura já não há
    escrita a recusar. A guarda recusa o grafo todo.
    """
    if not product_ids:
        return []
    return list(
        RecipeLineItem.objects.filter(
            tenant_id=tenant_id, recipe__product_id__in=list(product_ids)
        ).values_list("recipe__product_id", "ingredient_product_id")
    )


def contar_receitas_por_ingrediente(*, tenant_id: UUID, product_id: UUID) -> int:
    """Em quantas receitas activas este artigo entra como ingrediente."""
    return (
        RecipeLineItem.objects.filter(
            tenant_id=tenant_id, ingredient_product_id=product_id, recipe__is_active=True
        )
        .values("recipe_id")
        .distinct()
        .count()
    )
