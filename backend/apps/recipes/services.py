"""Casos de uso de receitas: escrever a ficha técnica e produzir a partir dela.

Uma função por caso de uso, `@transaction.atomic`, nenhuma escrita fora daqui.

* **Fatia A (ADR 0035):** `criar_receita` e `actualizar_receita` — a ficha
  técnica, por **fornada**, com as linhas a viajar **dentro do corpo** e por
  substituição total.
* **Fatia 6 (ADR 0026):** `produzir` — `production_out` por ingrediente, em FEFO,
  mais o `production_in` do acabado, tudo no mesmo átomo.

## Zero eventos e zero tarefas

Uma ficha técnica é uma **definição** e não um facto do ledger: não há evento de
outbox, não há Celery e não há efeito secundário nenhum a disparar daqui. A ADR
0026 já tinha decidido que nem a produção emite evento.

## O que a escrita recusa, e o que não é trabalho dela

Recusa o que só se vê com a base de dados à frente: um **ciclo** no grafo
transitivo de receitas, um artigo que já tem ficha (409), um ingrediente que não
é legível neste estabelecimento. O resto — `quantity > 0`, `lines` não vazio,
ingrediente repetido, a unidade de entrada — é forma do contrato e vive no
serializer, que responde 400 por campo. Os números voltam a ser verificados aqui
porque esta é a rede de baixo: um chamador futuro que não seja o HTTP não passa
pelo serializer.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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
from apps.recipes import selectors as _selectors
from apps.recipes.models import Recipe, RecipeLineItem

__all__ = [
    "CODIGO_CICLO",
    "CODIGO_RECEITA_JA_EXISTE",
    "LinhaDaFicha",
    "ReceitaJaExiste",
    "actualizar_receita",
    "criar_receita",
    "produzir",
]

logger = logging.getLogger(__name__)

#: O código que o cliente lê para ramificar. `ciclo_de_receitas` é 400 (o corpo
#: está errado) e `receita_ja_existe` é 409 (o corpo está certo, o mundo é que
#: já tem uma) — ver `recipes/views.py`.
CODIGO_CICLO = "ciclo_de_receitas"
CODIGO_RECEITA_JA_EXISTE = "receita_ja_existe"

DETALHE_CICLO = _(
    "This product is an ingredient of itself, directly or through another recipe."
)
DETALHE_SEM_LINHAS = _("A recipe needs at least one ingredient.")
DETALHE_FORNADA = _("Batch size must be greater than zero.")
DETALHE_RENDIMENTO = _("Yield factor must be greater than zero.")
DETALHE_QUANTIDADE = _("Each ingredient needs a quantity greater than zero.")
DETALHE_REPETIDO = _("The same ingredient cannot appear twice in a recipe.")


@dataclass(frozen=True, kw_only=True, slots=True)
class LinhaDaFicha:
    """Uma linha da ficha como o serviço a recebe: já em unidade **base**.

    A conversão da unidade de quem escreve ("500 g", "0,5 kg") para a do ledger
    acontece antes, na camada que fala o contrato HTTP — é a mesma fronteira que
    o `inventory` usa para uma linha de contagem. O serviço fala sempre em
    unidade base, e é isso que os seus testes afirmam.

    `quantity` é **por fornada** (ADR 0035, decisão 8).
    """

    ingredient_id: UUID
    quantity: Decimal


class ReceitaJaExiste(Exception):
    """O artigo já tem ficha. Leva o `id` da que existe, para o ecrã lá chegar.

    `Recipe.product` é `OneToOneField`, logo a segunda inserção é um
    `IntegrityError` — e um "erro" sem o id era mandar quem tentou de volta para
    uma lista para procurar à mão o que o servidor já sabia. É o precedente do
    409 da contagem já aberta (ADR 0030, decisão 2).
    """

    def __init__(self, *, recipe_id: UUID) -> None:
        super().__init__(str(recipe_id))
        self.recipe_id = recipe_id


def _validar_numeros(
    *,
    batch_size: Decimal | None,
    yield_factor: Decimal | None,
    linhas: Sequence[LinhaDaFicha] | None,
) -> None:
    """A rede de baixo dos quatro números do contrato. 400, por campo.

    Repete o que o serializer já recusou de propósito: o serializer serve o HTTP
    e esta função serve o domínio, e a invariante não pode depender de quem
    chama. O `CheckConstraint` do `batch_size` é a terceira rede, na base de
    dados, onde nenhuma escrita futura lhe escapa.
    """
    erros: dict[str, list[object]] = {}
    if batch_size is not None and batch_size <= Decimal("0"):
        erros["batch_size"] = [DETALHE_FORNADA]
    if yield_factor is not None and yield_factor <= Decimal("0"):
        erros["yield_factor"] = [DETALHE_RENDIMENTO]
    if linhas is not None:
        if not linhas:
            erros["lines"] = [DETALHE_SEM_LINHAS]
        elif any(linha.quantity <= Decimal("0") for linha in linhas):
            erros["lines"] = [DETALHE_QUANTIDADE]
        elif len({linha.ingredient_id for linha in linhas}) != len(linhas):
            erros["lines"] = [DETALHE_REPETIDO]
    if erros:
        raise ValidationError(erros)


def _recusar_ciclos(
    *, tenant_id: UUID, acabado_id: UUID, ingredientes: Sequence[UUID]
) -> None:
    """400 se o acabado estiver em qualquer ponto do seu grafo transitivo.

    O caso directo — um artigo ingrediente de si próprio — é o primeiro passo e
    não um caso especial. O caso que ninguém vê é o transitivo: folhada usa
    aparas, aparas usam folhada, e o custo de qualquer uma delas passa a não
    existir.

    **Um ciclo no grafo é sempre erro de dados** (ADR 0035, decisão 10). O
    reaproveitamento real não é ciclo: as aparas de folhada voltam como *outro*
    artigo e o pão de ontem vira pão ralado, que é outro artigo.

    Percorre por **níveis**, uma query por nível (`arestas_do_grafo`), e termina
    pelo conjunto de visitados — que é limitado pelo número de artigos do
    estabelecimento. **Sem tecto de profundidade**, ao contrário da leitura: a
    leitura corta aos três níveis porque mais do que isso não acrescenta número,
    e aqui a pergunta é se existe um caminho, a qualquer distância.
    """
    vistos = set(ingredientes)
    if acabado_id in vistos:
        raise ValidationError({"lines": [DETALHE_CICLO]}, code=CODIGO_CICLO)
    fronteira = set(vistos)
    while fronteira:
        seguinte: set[UUID] = set()
        for _de, para in _selectors.arestas_do_grafo(
            tenant_id=tenant_id, product_ids=sorted(fronteira)
        ):
            if para == acabado_id:
                raise ValidationError({"lines": [DETALHE_CICLO]}, code=CODIGO_CICLO)
            if para not in vistos:
                vistos.add(para)
                seguinte.add(para)
        fronteira = seguinte


def _escrever_linhas(
    *, tenant_id: UUID, receita: Recipe, linhas: Sequence[LinhaDaFicha]
) -> None:
    """Substituição **total**: apaga as que lá estão e escreve as que vieram.

    A ficha é um documento e não uma colecção (ADR 0035, decisão 4): escreve-se
    de uma vez, num formulário com um botão de gravar. O `unique_together
    (recipe, ingredient_product)` torna isto naturalmente idempotente.

    Dentro do átomo de quem chama: um `delete` sem o `bulk_create` a seguir era
    uma ficha vazia, que é um custo zero e não um custo ausente.
    """
    RecipeLineItem.objects.filter(tenant_id=tenant_id, recipe=receita).delete()
    RecipeLineItem.objects.bulk_create(
        [
            RecipeLineItem(
                tenant_id=tenant_id,
                recipe=receita,
                ingredient_product_id=linha.ingredient_id,
                quantity_per_base_unit=linha.quantity,
            )
            for linha in linhas
        ]
    )


@transaction.atomic
def criar_receita(
    *,
    tenant_id: UUID,
    product_id: UUID,
    batch_size: Decimal,
    yield_factor: Decimal,
    is_active: bool,
    linhas: Sequence[LinhaDaFicha],
) -> Recipe:
    """A ficha técnica de um artigo acabado, com as suas linhas, de uma vez.

    `batch_size` e as quantidades das linhas vêm na unidade **base** do artigo
    respectivo — a conversão é de quem fala HTTP.

    Levanta `ReceitaJaExiste` (409) se o artigo já tiver ficha, e
    `ValidationError` (400) para os números e para os ciclos. O artigo e os
    ingredientes já foram confirmados como legíveis neste estabelecimento por
    quem chama; o que não existir aqui dá `IntegrityError` e sobe, porque é um
    erro de programação e não uma recusa de domínio.
    """
    _validar_numeros(batch_size=batch_size, yield_factor=yield_factor, linhas=linhas)
    _recusar_ciclos(
        tenant_id=tenant_id,
        acabado_id=product_id,
        ingredientes=[linha.ingredient_id for linha in linhas],
    )
    existente = Recipe.objects.filter(
        tenant_id=tenant_id, product_id=product_id
    ).values_list("id", flat=True).first()
    if existente is not None:
        raise ReceitaJaExiste(recipe_id=existente)
    try:
        # O `savepoint` é o que permite apanhar o `IntegrityError` sem deixar a
        # transacção de fora num estado abortado: a corrida entre o `filter`
        # acima e este `create` é curta mas existe, e perdê-la tem de dar o
        # mesmo 409 e não um 500.
        with transaction.atomic():
            receita = Recipe.objects.create(
                tenant_id=tenant_id,
                product_id=product_id,
                batch_size=batch_size,
                yield_factor=yield_factor,
                is_active=is_active,
            )
    except IntegrityError:
        existente = Recipe.objects.filter(
            tenant_id=tenant_id, product_id=product_id
        ).values_list("id", flat=True).first()
        if existente is None:
            raise
        raise ReceitaJaExiste(recipe_id=existente) from None
    _escrever_linhas(tenant_id=tenant_id, receita=receita, linhas=linhas)
    logger.info(
        "Ficha técnica criada",
        extra={
            "event": "recipes.created",
            "recipe_id": str(receita.id),
            "product_id": str(product_id),
            "n_linhas": len(linhas),
        },
    )
    return receita


@transaction.atomic
def actualizar_receita(
    *,
    tenant_id: UUID,
    receita: Recipe,
    batch_size: Decimal | None = None,
    yield_factor: Decimal | None = None,
    is_active: bool | None = None,
    linhas: Sequence[LinhaDaFicha] | None = None,
) -> Recipe:
    """Altera a ficha. `None` é **ausente** e não "pôr a nulo".

    `linhas=None` não toca nas linhas; `linhas=[...]` **substitui-as todas**
    (ADR 0035, decisão 4) — é a única parte do contrato que não se adivinha, e
    por isso está escrita na ADR e aqui.

    O `product` **não** é alterável e não é argumento: é a identidade da ficha.
    Mudar o acabado é outra ficha, e deixá-lo mudar fazia o custo de ontem
    passar a ser de outro produto sem ninguém ver.

    Last-write-wins em silêncio: duas edições concorrentes e a segunda ganha. É
    risco baixo na fatia A, onde só `owner|manager` escreve e o `staff` lê; a
    corrida a sério é na fatia B, e está nomeada lá.
    """
    _validar_numeros(batch_size=batch_size, yield_factor=yield_factor, linhas=linhas)
    if linhas is not None:
        _recusar_ciclos(
            tenant_id=tenant_id,
            acabado_id=receita.product_id,
            ingredientes=[linha.ingredient_id for linha in linhas],
        )
    campos: list[str] = []
    if batch_size is not None:
        receita.batch_size = batch_size
        campos.append("batch_size")
    if yield_factor is not None:
        receita.yield_factor = yield_factor
        campos.append("yield_factor")
    if is_active is not None:
        receita.is_active = is_active
        campos.append("is_active")
    if campos:
        # `updated_at` à mão porque o `update_fields` não arrasta o `auto_now`.
        receita.updated_at = timezone.now()
        receita.save(update_fields=[*campos, "updated_at"])
    if linhas is not None:
        _escrever_linhas(tenant_id=tenant_id, receita=receita, linhas=linhas)
    logger.info(
        "Ficha técnica alterada",
        extra={
            "event": "recipes.updated",
            "recipe_id": str(receita.id),
            "campos": sorted(campos),
            "linhas_substituidas": linhas is not None,
        },
    )
    return receita


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
    - Quantidade é a de produto acabado desejada, na unidade base.
    - Interno: `quantity / yield_factor / batch_size` dá quantas **fornadas** são,
      e cada linha multiplica-se por esse número (a linha é por fornada desde a
      ADR 0035, decisão 8).
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

    # Quantas fornadas é que isto é, já com o rendimento. **A divisão pelo
    # `batch_size` entrou com a ADR 0035, decisão 8**, e não é um extra: a
    # linha passou a guardar a quantidade **por fornada**, logo sem este
    # divisor uma ficha de 400 pastéis consumia 400 vezes os ingredientes ao
    # produzir um. Com `batch_size = 1` — o caso particular que todas as fichas
    # de ontem são — o número é exactamente o de antes.
    fornadas = quantity / receita.yield_factor / receita.batch_size

    # Estrutura para os movimentos: output e input
    movements = []
    total_custo_entrada = Decimal("0")

    # Passo 1: Production_out (saída de ingredientes FEFO)
    for linha in linhas:
        ingrediente = linha.ingredient_product  # tipo: ignore[assignment]
        qty_a_consumir = linha.quantity_per_base_unit * fornadas

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
