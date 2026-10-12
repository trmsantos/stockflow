"""A porta do módulo `inventory` (ARCHITECTURE.md §3).

Fatia 2: localizações.
Fatia 3: lotes, movimentos, níveis de stock e custos.

Expõe DTOs (frozen dataclasses) e funções que outros módulos chamam via api.py.
Nenhuma escrita direta: tudo via services.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.inventory.models import Location
from apps.inventory.services import MovementDTO, get_or_create_lots, record_movements

__all__ = [
    "LocalizacaoResumo",
    "LoteResumo",
    "MovimentoResumo",
    "SaldoDeStock",
    "CustoMedioDeArtigo",
    "criar_localizacao",
    "localizacoes_por_id",
    "get_or_create_lots",
    "record_movements",
    "MovementDTO",
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
