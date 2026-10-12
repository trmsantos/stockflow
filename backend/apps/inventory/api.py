"""A porta do módulo `inventory` (ARCHITECTURE.md §3, ADR 0021, fatia 2).

Nesta fatia: apenas a localização. O ledger (movimentos, lotes, projeções) vem
na fatia 3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.inventory.models import Location

__all__ = [
    "LocalizacaoResumo",
    "criar_localizacao",
    "localizacoes_por_id",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class LocalizacaoResumo:
    """Uma localização como os outros módulos a veem."""

    id: UUID
    name: str
    is_active: bool


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


@transaction.atomic
def criar_localizacao(
    *,
    tenant_id: UUID,
    name: str,
    position: int | None = None,
    id: UUID | None = None,
) -> LocalizacaoResumo:
    """Criar uma localização. Consumidor: `apps/demo`.

    Se `position` é None, usa o máximo existente + 1.
    """
    from django.db.models import Max

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
