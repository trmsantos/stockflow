"""Queries de leitura do `inventory`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1). Nesta fatia há uma tabela só, a localização; o ledger
é a fatia 3.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from apps.inventory.models import Location

__all__ = ["listar_localizacoes", "localizacoes_do_ambito"]


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
