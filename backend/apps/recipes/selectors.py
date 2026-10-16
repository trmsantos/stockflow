"""Queries de leitura do `recipes`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).

A leitura nasce com a ADR 0028: até aí o módulo só tinha `produzir`, e uma
receita só se via no ecrã que ainda não existe. O que o assistente lê é a
**ficha técnica** (ingredientes e rendimento) e, para quem pode ver euros, os
dois custos — nada disto escreve.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.recipes.models import Recipe, RecipeLineItem

__all__ = [
    "contar_receitas_por_ingrediente",
    "ingredientes_das_receitas",
    "procurar_receitas",
    "receita_do_ambito",
    "receitas_dos_artigos",
]

#: O teto da procura, como no `catalog`: o resultado de uma tool cabe em 8 KB.
LIMITE_DA_PROCURA = 20


def _do_ambito(*, tenant_id: UUID) -> QuerySet[Recipe]:
    """Todas as receitas do estabelecimento, com o artigo acabado carregado."""
    return Recipe.objects.filter(tenant_id=tenant_id).select_related("product")


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
    return list(
        receitas.order_by("-is_active", "product__short_name", "id")[
            : min(limite, LIMITE_DA_PROCURA) + 1
        ]
    )


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
