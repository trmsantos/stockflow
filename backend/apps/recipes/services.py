"""Casos de uso de receitas (fatia 6): produção.

Uma função por caso de uso, @transaction.atomic, nenhuma escrita fora daqui.

Fatia 6: produzir uma receita (production_out + production_in atomicamente).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.inventory.api import (
    Autor,
    LoteResumo,
    MovementDTO,
    get_or_create_lots,
    get_stock_level,
    obter_localizacao,
    record_movements,
)
from apps.recipes.models import Recipe

__all__ = [
    "produzir",
]

logger = logging.getLogger(__name__)


def _get_fefo_lots_with_stock(
    *,
    tenant_id: UUID,
    product_id: UUID,
    location_id: UUID,
) -> list[tuple[LoteResumo, Decimal]]:
    """Retorna lista de (lote DTO, quantidade disponível) ordenada por FEFO.

    Filtra apenas lotes com stock positivo na localização, usando APIs.
    """
    from apps.inventory.models import Lot

    qs = (
        Lot.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
        )
        .order_by("expires_at", "received_at")
    )

    resultado = []
    for lote in qs:
        nivel = get_stock_level(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lote.id,
        )
        if nivel is not None and nivel.quantity > Decimal("0"):
            lote_dto = LoteResumo(
                id=lote.id,
                product_id=lote.product_id,
                code=lote.code,
                expires_at=lote.expires_at,
                received_at=lote.received_at,
            )
            resultado.append((lote_dto, nivel.quantity))

    return resultado


@transaction.atomic
def produzir(
    *,
    tenant_id: UUID,
    recipe_id: UUID,
    quantity: Decimal,
    location_id: UUID,
    user: Autor,
    user_name: str = "",
) -> UUID:
    """Produzir uma receita: consome ingredientes (production_out), cria produto (production_in).

    Contrato (ADR 0026, Decisão 1):
    - Quantidade é a de produto acabado desejada.
    - Interno: multiplica por 1 / yield_factor para obter quantidade de ingredientes a consumir.
    - Atomicamente: cria production_out por cada ingrediente (FEFO), depois production_in.

    Custo unitário (ADR 0026, Decisão 2):
    - unit_cost = Σ(|production_out.qty| × production_out.unit_cost) / quantity

    Lote (ADR 0026, Decisão 5):
    - Se produto track_lots=True: novo lote único com code='__<production_id>__' (sintético)
    - Se track_lots=False: lot_id=NULL

    Argumentos:
    - tenant_id, recipe_id, quantity, location_id: IDs
    - user: User que cria a produção
    - user_name: o **nome exibido** da pertença, que fica no `created_by_name`

    ## Porque é que o `created_by_name` deixou de ser o email (ADR 0028)

    O `created_by_name` é a cópia de quem assinou que sobrevive à conta ser
    apagada, e aparece em cada linha do histórico de um artigo — que os três
    papéis lêem. Gravar lá o email punha o endereço de cada pessoa à vista de
    toda a gente que abrisse um movimento, e um email não é o nome de ninguém
    *neste* estabelecimento: o nome é o `display_name` da pertença (ADR 0007).
    `user_name` tem default vazio porque o `Autor` é um `Protocol` com `id` e
    `email` e não conhece pertenças; quem chama tem o `membership` e passa-o.

    Retorna: production_id (UUID partilhada por production_out e production_in)

    Levanta:
    - 404: receita não existe
    - 400: quantity <= 0
    - 409: receita inativa, localização inativa, stock insuficiente, yield_factor <= 0,
           receita sem ingredientes

    Transação atómica: falha em qualquer validação desfaz sem deixar movimentos parciais.
    """
    production_id = uuid.uuid4()
    now = timezone.now()

    # Validação 1: Receita existe e está ativa (404 se não existe)
    receita = Recipe.objects.filter(
        tenant_id=tenant_id, id=recipe_id, is_active=True
    ).first()
    if receita is None:
        # Pode ser "não existe" ou "está inativa" — ambos são 404
        raise ValidationError(
            _("Recipe not found or inactive."), code="recipe_not_found"
        )

    # Validação 2: Quantidade > 0 (400)
    if quantity <= Decimal("0"):
        raise ValidationError(
            _("Quantity must be greater than zero."), code="invalid_quantity"
        )

    # Validação 3: yield_factor > 0 (409 por ser erro de dados)
    if receita.yield_factor <= Decimal("0"):
        raise ValidationError(
            _("Recipe yield_factor must be greater than zero."),
            code="invalid_yield_factor",
        )

    # Validação 4: Localização existe e está ativa (409)
    localizacao = obter_localizacao(tenant_id=tenant_id, location_id=location_id)
    if localizacao is None:
        raise ValidationError(
            _("Location not found or inactive."),
            code="location_not_found",
        )

    # Validação 5: Receita tem ≥1 ingrediente (409)
    linhas = list(receita.line_items.all())
    if not linhas:
        raise ValidationError(
            _("Recipe has no ingredients."),
            code="recipe_no_ingredients",
        )

    # Quantidade de ingredientes a consumir (com yield_factor)
    quantidade_base = quantity / receita.yield_factor

    # Estrutura para os movimentos: output e input
    movements = []
    total_custo_entrada = Decimal("0")

    # Passo 1: Production_out (saída de ingredientes FEFO)
    for linha in linhas:
        ingrediente = linha.ingredient_product  # tipo: ignore[assignment]
        qty_a_consumir = linha.quantity_per_base_unit * quantidade_base

        # FEFO: encontra lotes e consome sequencialmente
        lotes_fefo = _get_fefo_lots_with_stock(
            tenant_id=tenant_id,
            product_id=ingrediente.id,
            location_id=location_id,
        )

        if not lotes_fefo:
            # Sem stock nenhum, lança erro 409
            raise ValidationError(
                _(
                    f"Insufficient stock for ingredient '{ingrediente.short_name}': "
                    f"need {qty_a_consumir} {ingrediente.base_unit}, "
                    f"but have 0."
                ),
                code="insufficient_stock",
            )

        # Consumir de cada lote até ter consumido o suficiente
        restante = qty_a_consumir
        for lote_resumo, qty_disponivel in lotes_fefo:
            if restante <= Decimal("0"):
                break

            # Quantidade a consumir deste lote
            qty_consumir_deste_lote = min(restante, qty_disponivel)

            # Buscar o nível atual do lote
            nivel = get_stock_level(
                tenant_id=tenant_id,
                product_id=ingrediente.id,
                location_id=location_id,
                lot_id=lote_resumo.id,
            )

            # Cria o movimento de saída (quantity negativa)
            movement_out = MovementDTO(
                product_id=ingrediente.id,
                location_id=location_id,
                lot_id=lote_resumo.id,
                quantity=-qty_consumir_deste_lote,  # Negativo = saída
                unit_cost=nivel.unit_cost,  # Usa o custo do lote que sai (FEFO)
                cost_is_estimate=False,
                movement_type="production_out",
                occurred_at=now,
                created_by_id=user.id,
                created_by_name=user_name,
                production_id=production_id,
                reference="",
                reason="",
            )
            movements.append(movement_out)

            # Acumula para o custo final
            total_custo_entrada += qty_consumir_deste_lote * movement_out.unit_cost

            restante -= qty_consumir_deste_lote

        # Verifica se consumiu o suficiente
        if restante > Decimal("0"):
            # Stock insuficiente
            stock_total = sum(qty for _, qty in lotes_fefo)
            raise ValidationError(
                _(
                    f"Insufficient stock for ingredient '{ingrediente.short_name}': "
                    f"need {qty_a_consumir} {ingrediente.base_unit}, "
                    f"have {stock_total}."
                ),
                code="insufficient_stock",
            )

    # Passo 2: Production_in (entrada do produto acabado)
    produto_acabado = receita.product

    # Custo unitário (ADR 0026, Decisão 2)
    unit_cost_production_in = (
        total_custo_entrada / quantity
        if quantity > Decimal("0")
        else Decimal("0")
    )

    # Lote sintético se track_lots=True
    lot_id_saida = None
    if produto_acabado.track_lots:
        # Cria lote sintético '__<production_id>__'
        lote_code = f"__{production_id}__"
        lot_ids = get_or_create_lots(
            tenant_id=tenant_id,
            items=[
                (
                    produto_acabado.id,
                    lote_code,
                    None,  # Sem validade (receita não é perecível)
                    now,
                )
            ],
        )
        lot_id_saida = lot_ids[(produto_acabado.id, lote_code)]

    # Movimento de entrada (quantity positiva)
    movement_in = MovementDTO(
        product_id=produto_acabado.id,
        location_id=location_id,
        lot_id=lot_id_saida,  # Lote sintético ou NULL
        quantity=quantity,  # Positivo = entrada
        unit_cost=unit_cost_production_in,
        cost_is_estimate=False,
        movement_type="production_in",
        occurred_at=now,
        created_by_id=user.id,
        created_by_name=user_name,
        production_id=production_id,
        reference="",
        reason="",
    )
    movements.append(movement_in)

    # Passo 3: Grava todos os movimentos atomicamente
    record_movements(tenant_id=tenant_id, movements=movements)

    logger.info(
        "Receita produzida",
        extra={
            "event": "recipes.produced",
            "recipe_id": str(recipe_id),
            "production_id": str(production_id),
            "quantity": str(quantity),
            "yield_factor": str(receita.yield_factor),
            "user_id": str(user.id),
        },
    )

    return production_id
