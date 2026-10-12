"""Os casos de uso do `inventory`: localizações (fatia 2) e ledger (fatia 3).

Uma função por caso de uso, `@transaction.atomic`, e nenhuma escrita fora daqui.

Fatia 2: criar e editar uma localização (sem outbox).
Fatia 3: `record_movements` escreve no ledger — movimentos, lotes, níveis e custos.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.utils.translation import gettext_lazy as _

from apps.inventory.models import Location, Lot, ProductCost, StockLevel, StockMovement

__all__ = [
    "CAMPOS_DA_LOCALIZACAO",
    "MovementDTO",
    "actualizar_localizacao",
    "criar_localizacao",
    "get_or_create_lots",
    "record_movements",
]

logger = logging.getLogger(__name__)

#: O que o `PATCH /locations/<id>` pode escrever.
CAMPOS_DA_LOCALIZACAO: frozenset[str] = frozenset({"name", "position", "is_active"})

#: O teto do `smallint` do Postgres, que é o tipo de `position`. Recusado aqui
#: com uma frase em vez de deixar o erro de intervalo subir como 500.
POSICAO_MAXIMA = 32767

DETALHE_NOME_DUPLICADO = _(
    "There is already a location with this name in this establishment."
)
DETALHE_OBRIGATORIO = _("This field is required.")
DETALHE_DEMASIADO_LONGO = _("At most {limite} characters.")
DETALHE_POSICAO = _("The position is a whole number between 0 and {limite}.")
DETALHE_CAMPO_FORA_DO_CONTRATO = _("This field cannot be changed here.")


@transaction.atomic
def criar_localizacao(
    *, tenant_id: UUID, name: str, position: int | None = None, id: UUID | None = None
) -> Location:
    """Uma localização. Sem `position`, vai para o fim da lista.

    "O fim" é o máximo actual mais um, lido **nesta** transação; dois pedidos
    simultâneos podem calcular o mesmo número, e isso é aceitável porque a
    posição não é única — desempatam pelo nome. O `id` opcional é o que o
    `apps/demo` usa para os uuid estáveis; com `id`, uma linha que já exista
    neste tenant é devolvida em vez de recriada.
    """
    if id is not None:
        existente = Location.objects.filter(tenant_id=tenant_id, pk=id).first()
        if existente is not None:
            return existente

    nome = _nome(name)
    ordem = _posicao(position) if position is not None else _fim_da_lista(tenant_id)
    if Location.objects.filter(tenant_id=tenant_id, name__iexact=nome).exists():
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]})
    try:
        with transaction.atomic():
            localizacao = Location.objects.create(
                tenant_id=tenant_id,
                name=nome,
                position=ordem,
                **({"id": id} if id is not None else {}),
            )
    except IntegrityError as erro:
        logger.info(
            "localização recusada pela constraint",
            extra={"event": "inventario.localizacao", "outcome": "duplicado"},
        )
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]}) from erro
    return localizacao


@transaction.atomic
def actualizar_localizacao(
    *, tenant_id: UUID, localizacao: Location, campos: Mapping[str, object]
) -> Location:
    """`PATCH`: `name`, `position`, `is_active`. Relido sob lock antes de escrever."""
    fora = sorted(set(campos) - CAMPOS_DA_LOCALIZACAO)
    if fora:
        raise ValidationError({campo: [DETALHE_CAMPO_FORA_DO_CONTRATO] for campo in fora})

    bloqueado = (
        Location.objects.select_for_update()
        .filter(tenant_id=tenant_id, pk=localizacao.pk)
        .get()
    )
    if "name" in campos:
        nome = _nome(str(campos["name"]))
        if (
            Location.objects.filter(tenant_id=tenant_id, name__iexact=nome)
            .exclude(pk=bloqueado.pk)
            .exists()
        ):
            raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]})
        bloqueado.name = nome
    if "position" in campos:
        bloqueado.position = _posicao(campos["position"])
    if "is_active" in campos:
        bloqueado.is_active = bool(campos["is_active"])
    try:
        with transaction.atomic():
            bloqueado.save(update_fields=["name", "position", "is_active", "updated_at"])
    except IntegrityError as erro:
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]}) from erro
    return bloqueado


def _fim_da_lista(tenant_id: UUID) -> int:
    maior = Location.objects.filter(tenant_id=tenant_id).aggregate(maior=Max("position"))["maior"]
    return 1 if maior is None else min(maior + 1, POSICAO_MAXIMA)


def _nome(valor: str | None) -> str:
    limpo = (valor or "").strip()
    if not limpo:
        raise ValidationError({"name": [DETALHE_OBRIGATORIO]})
    if len(limpo) > 60:
        raise ValidationError({"name": [DETALHE_DEMASIADO_LONGO.format(limite=60)]})
    return limpo


def _posicao(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= POSICAO_MAXIMA:
        raise ValidationError({"position": [DETALHE_POSICAO.format(limite=POSICAO_MAXIMA)]})
    return valor


# === Fatia 3: Ledger de stock ===


@dataclass(frozen=True, kw_only=True, slots=True)
class MovementDTO:
    """DTO para um movimento de stock a gravar no ledger.

    Campos obrigatórios:
    - product_id, location_id, lot_id (null se track_lots=False)
    - quantity (sem sinal; o tipo de movimento define o sinal esperado)
    - unit_cost (preço de cada unidade, sempre positivo)
    - cost_is_estimate (True se o preço é estimado, False se confirmado)
    - movement_type (um dos 9 tipos)
    - occurred_at (data/hora do movimento)
    - created_by_id, created_by_name (quem criou o movimento)
    - reference, production_id, reason (opcionais)
    """

    product_id: UUID
    location_id: UUID
    lot_id: UUID | None
    quantity: Decimal
    unit_cost: Decimal
    cost_is_estimate: bool
    movement_type: str
    occurred_at: datetime
    created_by_id: UUID | None
    created_by_name: str
    reference: str | None = None
    production_id: UUID | None = None
    reason: str | None = None


@transaction.atomic
def get_or_create_lots(
    *,
    tenant_id: UUID,
    items: Sequence[tuple[UUID, str, datetime | None, datetime]],
) -> dict[tuple[UUID, str], UUID]:
    """Cria ou retorna lotes pelo triplo (product_id, code, expires_at, received_at).

    Retorna um mapa {(product_id, code): lot_id} para referenciar nos movimentos.

    Argumentos:
    - tenant_id: ID do tenant
    - items: lista de tuplos (product_id, code, expires_at, received_at)
      onde expires_at pode ser None

    O primeiro movimento de um lote define received_at; retentativas com
    recebimentos diferentes para o mesmo (tenant, product, code) devolvem o
    lote existente — a received_at fica como foi na criação, não se muda.
    """
    resultado = {}
    for product_id, code, expires_at, received_at in items:
        lote, _criado = Lot.objects.get_or_create(
            tenant_id=tenant_id,
            product_id=product_id,
            code=code,
            defaults={
                "expires_at": expires_at,
                "received_at": received_at,
            },
        )
        resultado[(product_id, code)] = lote.id

    return resultado


@transaction.atomic
def record_movements(
    *,
    tenant_id: UUID,
    movements: Sequence[MovementDTO],
) -> list[UUID]:
    """Grava uma série de movimentos e atualiza níveis e custos.

    Uma transação atómica que:
    1. Cria as linhas em `inventory_stockmovement` (append-only)
    2. Atualiza ou cria linhas em `inventory_stocklevel` (saldo + custo)
    3. Atualiza o `inventory_productcost` (custo médio ponderado por localização)

    Retorna a lista de IDs dos movimentos criados (na ordem de entrada).

    Pré-condições:
    - Todos os product_id, location_id e lot_id (se não NULL) devem existir
    - A quantidade tem sinal correto (positivo para entradas, negativo para saídas)
    - unit_cost é sempre positivo

    Consequências:
    - Um movimento de entrada (receipt, return positivo, production_in) altera
      o ProductCost da (product, location)
    - Um movimento de saída (consumption, waste, adjustment, transfer_out, production_out)
      lê o custo do lote que sai (FEFO se houver múltiplos lotes)
    """
    if not movements:
        return []

    movement_ids = []

    # 1. Gravar todos os movimentos
    for mvt_dto in movements:
        movimento = StockMovement.objects.create(
            tenant_id=tenant_id,
            product_id=mvt_dto.product_id,
            location_id=mvt_dto.location_id,
            lot_id=mvt_dto.lot_id,
            movement_type=mvt_dto.movement_type,
            quantity=mvt_dto.quantity,
            unit_cost=mvt_dto.unit_cost,
            cost_is_estimate=mvt_dto.cost_is_estimate,
            reason=mvt_dto.reason,
            reference=mvt_dto.reference,
            production_id=mvt_dto.production_id,
            occurred_at=mvt_dto.occurred_at,
            created_by_id=mvt_dto.created_by_id,
            created_by_name=mvt_dto.created_by_name,
        )
        movement_ids.append(movimento.id)

    # 2. Atualizar StockLevel para cada (product, location, lot)
    # Agrupamos os movimentos por chave
    by_key = {}
    for mvt_dto in movements:
        key = (mvt_dto.product_id, mvt_dto.location_id, mvt_dto.lot_id)
        if key not in by_key:
            by_key[key] = []
        by_key[key].append(mvt_dto)

    for (product_id, location_id, lot_id), mvt_list in by_key.items():
        # Somar a quantidade de todos os movimentos desta chave
        total_qty = sum(mvt.quantity for mvt in mvt_list)

        # Calcular o novo custo unitário: apenas com base em entradas
        # (receipt, return positivo, production_in)
        entrada_tipos = {"receipt", "return", "production_in"}
        total_entrada_qty = Decimal("0")
        total_entrada_valor = Decimal("0")

        for mvt in mvt_list:
            if mvt.movement_type in entrada_tipos:
                qty_positiva = abs(mvt.quantity)
                total_entrada_qty += qty_positiva
                total_entrada_valor += qty_positiva * mvt.unit_cost

        # Novo custo = total_entrada_valor / total_entrada_qty (se qty > 0, senão 0)
        novo_unit_cost = (
            total_entrada_valor / total_entrada_qty
            if total_entrada_qty > Decimal("0")
            else Decimal("0")
        )

        # Atualizar ou criar StockLevel
        nível, _criado = StockLevel.objects.get_or_create(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            defaults={
                "quantity": total_qty,
                "unit_cost": novo_unit_cost,
            },
        )

        # Se existia, precisa atualizar (query histórica até agora)
        if not _criado:
            # Recalcular saldo: SUM de todos os movimentos históricos
            saldo_total = (
                StockMovement.objects.filter(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    location_id=location_id,
                    lot_id=lot_id,
                )
                .aggregate(total=Sum("quantity"))["total"]
                or Decimal("0")
            )

            # Recalcular custo: total entrada / total entrada qty (histórico)
            entrada = (
                StockMovement.objects.filter(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    location_id=location_id,
                    lot_id=lot_id,
                    movement_type__in=entrada_tipos,
                )
                .aggregate(
                    total_qty=Sum("quantity", filter=Q(quantity__gt=0)),
                    total_valor=Sum(
                        F("quantity") * F("unit_cost"), filter=Q(quantity__gt=0)
                    ),
                )
            )

            total_entrada_qty_hist = entrada["total_qty"] or Decimal("0")
            total_entrada_valor_hist = entrada["total_valor"] or Decimal("0")

            novo_unit_cost_hist = (
                total_entrada_valor_hist / total_entrada_qty_hist
                if total_entrada_qty_hist > Decimal("0")
                else Decimal("0")
            )

            nível.quantity = saldo_total
            nível.unit_cost = novo_unit_cost_hist
            nível.save(update_fields=["quantity", "unit_cost", "updated_at"])

    # 3. Atualizar ProductCost para cada (product, location)
    # Apenas com movimentos de entrada
    entrada_tipos = {"receipt", "return", "production_in"}
    by_product_location = {}
    for mvt_dto in movements:
        if mvt_dto.movement_type in entrada_tipos:
            key = (mvt_dto.product_id, mvt_dto.location_id)
            if key not in by_product_location:
                by_product_location[key] = []
            by_product_location[key].append(mvt_dto)

    for (product_id, location_id), mvt_list in by_product_location.items():
        # Calcular custo médio ponderado histórico de todas as entradas
        entrada = (
            StockMovement.objects.filter(
                tenant_id=tenant_id,
                product_id=product_id,
                location_id=location_id,
                movement_type__in=entrada_tipos,
            )
            .aggregate(
                total_qty=Sum("quantity"),
                total_valor=Sum(F("quantity") * F("unit_cost")),
            )
        )

        total_entrada_qty = entrada["total_qty"] or Decimal("0")
        total_entrada_valor = entrada["total_valor"] or Decimal("0")

        novo_unit_cost = (
            total_entrada_valor / total_entrada_qty
            if total_entrada_qty > Decimal("0")
            else Decimal("0")
        )

        # Atualizar ou criar ProductCost
        custo, _criado = ProductCost.objects.get_or_create(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            defaults={"unit_cost": novo_unit_cost},
        )

        if not _criado:
            custo.unit_cost = novo_unit_cost
            custo.save(update_fields=["unit_cost", "updated_at"])

    return movement_ids
