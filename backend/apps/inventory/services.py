"""Os casos de uso do `inventory`: localizações (fatia 2) e ledger (fatia 3).

Uma função por caso de uso, `@transaction.atomic`, e nenhuma escrita fora daqui.

Fatia 2: criar e editar uma localização (sem outbox).
Fatia 3: `record_movements` escreve no ledger — movimentos, lotes, níveis e custos.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.api import produto_por_id
from apps.inventory.models import Location, Lot, ProductCost, StockLevel, StockMovement

__all__ = [
    "CAMPOS_DA_LOCALIZACAO",
    "MovementDTO",
    "actualizar_localizacao",
    "criar_localizacao",
    "get_or_create_lots",
    "record_movements",
    "registar_waste",
    "registar_adjustment",
    "registar_transfer",
    "get_fefo_lot",
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
    - reference, production_id, reason (opcionais; texto ausente é `""`, nunca None)
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
    reference: str = ""
    production_id: UUID | None = None
    reason: str = ""
    #: O texto livre que acompanha o motivo. Estava a ser **aceite pela API e
    #: deitado fora** — o `WasteSerializer` validava-o, o serviço recebia-o e o
    #: DTO não o tinha, logo a coluna ficava sempre a `""`. Um campo aceite e
    #: silenciosamente ignorado é pior do que um campo que não existe.
    reason_detail: str = ""
    #: O par `transfer_out`/`transfer_in` partilha este id, e ele entra **na
    #: criação**: a tabela é append-only (`REVOKE UPDATE`, ADR 0006), logo
    #: escrevê-lo depois, com um `update()`, é `permission denied`.
    transfer_id: UUID | None = None


class Autor(Protocol):
    """Quem assina um movimento manual: o que os serviços leem de `request.user`.

    Um `Protocol` e não o modelo `User`: este módulo não pode importar
    `apps.accounts.models` (só `api.py` atravessa a fronteira, ARCHITECTURE.md
    §3), e do utilizador guarda-se o `id` no FK.

    **Um campo só, e o `email` deixou de estar cá.** O nome que fica em
    `created_by_name` — a cópia que sobrevive à conta ser apagada — é o
    `display_name` da **pertença**, que vem por `user_name` de quem chama. Até
    2026-10-19 havia um `user_name or user.email` a servir de recurso para
    chamadores antigos, e o recurso era a fuga: um email no ledger é a
    credencial de login de um colega, lida depois por qualquer outro (é a mesma
    regra do `membros_do_ambito`, que só o mostra ao dono). Sem nome fica
    **vazio** — a ausência lê-se como ausência, e quem agiu continua gravado no
    FK ao lado. Tirar o campo do `Protocol` é o que impede o recurso de voltar:
    um `user.email` aqui dentro passa a ser erro de tipo.
    """

    id: UUID


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
            reason_detail=mvt_dto.reason_detail,
            reference=mvt_dto.reference,
            production_id=mvt_dto.production_id,
            transfer_id=mvt_dto.transfer_id,
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

    for product_id, location_id in by_product_location:
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


# === Fatia 5: Movimentos manuais ===


def get_fefo_lot(
    *,
    tenant_id: UUID,
    product_id: UUID,
    location_id: UUID,
    lot_id: UUID | None = None,
) -> Lot | None:
    """Encontra o lote mais antigo (FEFO) para uma saída.

    Se `lot_id` for fornecido, devolve esse lote (validação apenas).
    Senão, busca pelo critério FEFO: expires_at ASC NULLS LAST, received_at ASC.

    Retorna None se não houver lote com stock > 0.
    """
    if lot_id is not None:
        return Lot.objects.filter(tenant_id=tenant_id, pk=lot_id, product_id=product_id).first()

    # Buscar lotes do produto nesta localização com stock > 0, ordenado por FEFO
    qs = (
        Lot.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
        )
        .select_related("product")
        # NULLS LAST é o que o Postgres faz por omissão num ORDER BY ascendente.
        .order_by("expires_at", "received_at")
    )

    # Filtrar apenas lotes com stock > 0 nesta localização
    lotes_com_stock = []
    for lote in qs:
        nivel = StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lote.id,
            quantity__gt=Decimal("0"),
        ).exists()
        if nivel:
            lotes_com_stock.append(lote)

    return lotes_com_stock[0] if lotes_com_stock else None


#: O que uma saída tem à frente, por ordem FEFO: o nível, o lote e o custo.
#: Uma tupla e não um dict porque é consumida duas linhas abaixo de onde nasce.
_SaldoFEFO = tuple[UUID | None, Decimal, Decimal]


def _saldos_fefo(
    *, tenant_id: UUID, product_id: UUID, location_id: UUID
) -> list[_SaldoFEFO]:
    """Os lotes com saldo **naquela localização**, por FEFO: `(lot_id, saldo, custo)`.

    `expires_at ASC NULLS LAST`, depois `received_at ASC`, e **só** entre os
    que têm saldo positivo ali. É a mesma regra que o consumo de receitas já
    segue (ADR 0026) e a que a ADR 0034, decisão 8, escreve para a quebra.

    O lote sintético é encontrado por este caminho como qualquer outro, porque
    também é um lote com saldo. O ramo especial que o procurava pelo código
    (`__<product_id>__`) **sem olhar à localização** deixa de existir, e com
    ele a porta por onde se tirava stock de uma prateleira onde ele não está.
    """
    niveis = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            quantity__gt=Decimal("0"),
        )
        .select_related("lot")
        .order_by(
            F("lot__expires_at").asc(nulls_last=True),
            F("lot__received_at").asc(nulls_last=True),
            "lot_id",
        )
    )
    return [(nivel.lot_id, nivel.quantity, nivel.unit_cost) for nivel in niveis]


def _repartir_por_fefo(
    saldos: Sequence[_SaldoFEFO], *, quantidade: Decimal
) -> list[tuple[UUID | None, Decimal, Decimal]]:
    """Reparte `quantidade` pelos saldos, por ordem, até perfazer. `[]` se não chega.

    Lista vazia é "não há saldo que chegue" e **nunca** uma repartição parcial:
    escrever menos do que foi pedido, em silêncio, é a quebra a entrar errada
    num ledger sem desfazer (ADR 0034, decisão 8).
    """
    if sum((saldo for _, saldo, _ in saldos), Decimal("0")) < quantidade:
        return []
    restante = quantidade
    reparticao: list[tuple[UUID | None, Decimal, Decimal]] = []
    for lot_id, saldo, custo in saldos:
        if restante <= Decimal("0"):
            break
        leva = min(restante, saldo)
        reparticao.append((lot_id, leva, custo))
        restante -= leva
    return reparticao


@transaction.atomic
def registar_waste(
    *,
    tenant_id: UUID,
    product_id: UUID,
    location_id: UUID,
    quantity: Decimal,
    lot_id: UUID | None,
    reason: str,
    reason_detail: str,
    user: Autor,
    user_name: str = "",
) -> list[UUID]:
    """Registar uma quebra. Devolve os ids dos movimentos, **sempre uma lista**.

    Sem `lot_id`, o servidor escolhe por **FEFO na localização pedida** e
    reparte por quantos lotes forem precisos — uma quebra de 2 kg com o lote
    mais próximo de expirar a 0,4 kg gera duas linhas, na mesma transação e com
    a mesma `reference`. Com `lot_id`, sai tudo desse lote: é o caso do ecrã de
    Alertas, onde o alerta **é** sobre um lote e deitar fora outro seria deitar
    fora o lote errado.

    ## O que esta função fazia e deixou de fazer (ADR 0034, decisão 8)

    Até 2026-10-27 levantava `ValidationError({"lot_id": …})` sempre que o
    artigo tinha `track_lots=True` e o corpo não trazia lote — enquanto o
    docstring prometia FEFO e o `formulario-de-desperdicio.tsx` **nunca** envia
    lote. Resultado medido: **400 em todos os artigos com lotes**, no ecrã mais
    usado pelo `staff`. O `get_fefo_lot` só era chamado no ramo em que o lote
    já tinha vindo, onde fazia apenas validação.

    A frase do 400 também mudou, e isso é parte da decisão: sem saldo diz
    *"não há saldo deste artigo nesta localização"* e **nunca** "lote
    obrigatório". A segunda manda a pessoa procurar um campo que o ecrã não
    tem, e esconde a causa real.

    ## O custo, e o zero que deixou de mentir

    O custo de cada linha é o do **nível** de onde ela sai (ADR 0025, decisão
    5). Quando esse nível não tem preço, o movimento grava
    `cost_is_estimate=True` e a resposta diz `cost_status: "desconhecido"` — e
    não um zero com `cost_is_estimate=False`, que afirmava "esta quebra custou
    zero euros" num ledger append-only.

    **Nunca se bloqueia o registo por falta de preço**: quem está a deitar fora
    não anda à procura de uma fatura.

    Argumentos: `quantity` > 0 em unidade **base** (a conversão faz-se na
    camada do contrato, como nas linhas de contagem), `reason` num dos cinco,
    `lot_id` opcional.
    """
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": [_("Quantity must be positive.")]})

    if reason not in dict(StockMovement.REASON_CHOICES):
        raise ValidationError({"reason": [_("Invalid reason.")]})

    localizacao = Location.objects.filter(pk=location_id, tenant_id=tenant_id).first()
    if not localizacao:
        raise ValidationError({"location": [_("Location not found.")]})
    if not localizacao.is_active:
        raise ValidationError({"location": [_("Location is inactive.")]})

    produto = produto_por_id(tenant_id=tenant_id, product_id=product_id)
    if produto is None:
        raise ValidationError({"product": [_("Product not found.")]})

    if lot_id is not None:
        lote = Lot.objects.filter(
            tenant_id=tenant_id, pk=lot_id, product_id=product_id
        ).first()
        if lote is None:
            raise ValidationError({"lot": [_("Lot not found.")]})
        nivel = StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lote.id,
        ).first()
        # Um lote escolhido à mão sai inteiro daquele lote, mesmo que o saldo
        # não chegue: stock negativo continua a ser possível por outras portas
        # (ADR 0012) e esta é uma delas — o que a decisão 8 proíbe é a
        # repartição a escrever menos do que foi pedido sem o dizer.
        reparticao = [
            (lote.id, quantity, nivel.unit_cost if nivel else Decimal("0"))
        ]
    else:
        saldos = _saldos_fefo(
            tenant_id=tenant_id, product_id=product_id, location_id=location_id
        )
        reparticao = _repartir_por_fefo(saldos, quantidade=quantity)
        if not reparticao:
            disponivel = sum((saldo for _, saldo, _ in saldos), Decimal("0"))
            raise ValidationError(
                {
                    "quantity": [
                        _(
                            "There is no stock of this product at this location "
                            "(available: %(disponivel)s)."
                        )
                        % {"disponivel": disponivel}
                    ]
                }
            )

    # A `reference` comum só quando há mais do que uma linha: com uma linha não
    # há nada para agrupar, e o índice parcial `inv_stockmv_tenant_ref_idx`
    # existe na maior tabela do sistema — só se paga escrita nele quando compra
    # alguma coisa (ADR 0034, decisão 8).
    referencia = str(uuid.uuid4()) if len(reparticao) > 1 else ""
    agora = timezone.now()
    movimentos = [
        MovementDTO(
            product_id=product_id,
            location_id=location_id,
            lot_id=lote_da_linha,
            quantity=-quantidade_da_linha,
            unit_cost=custo,
            # A proveniência que falta não se disfarça de preço: ver o
            # docstring acima e o `ESTADOS_DO_CUSTO` do `selectors.py`.
            cost_is_estimate=custo == Decimal("0"),
            movement_type="waste",
            occurred_at=agora,
            created_by_id=user.id,
            created_by_name=user_name,
            reason=reason,
            reason_detail=reason_detail,
            reference=referencia,
        )
        for lote_da_linha, quantidade_da_linha, custo in reparticao
    ]
    return record_movements(tenant_id=tenant_id, movements=movimentos)


@transaction.atomic
def registar_adjustment(
    *,
    tenant_id: UUID,
    product_id: UUID,
    location_id: UUID,
    quantity: Decimal,
    lot_id: UUID | None,
    reason: str,
    reason_detail: str,
    user: Autor,
    user_name: str = "",
) -> UUID:
    """Registar um movimento de ajuste (adjustment).

    Cria um StockMovement com type=adjustment, quantidade com sinal conforme correção.
    Usa FEFO para saídas (quantity < 0).

    Argumentos:
    - quantity: Decimal ± (positivo = entrada, negativo = saída)
    - Resto igual a waste

    Retorna: movement_id
    """
    if quantity == Decimal("0"):
        raise ValidationError({"quantity": [_("Quantity cannot be zero.")]})

    if reason not in dict(StockMovement.REASON_CHOICES):
        raise ValidationError({"reason": [_("Invalid reason.")]})

    # Validar localização
    localizacao = Location.objects.filter(pk=location_id, tenant_id=tenant_id).first()
    if not localizacao:
        raise ValidationError({"location": [_("Location not found.")]})

    if not localizacao.is_active:
        raise ValidationError({"location": [_("Location is inactive.")]})

    produto = produto_por_id(tenant_id=tenant_id, product_id=product_id)
    if produto is None:
        raise ValidationError({"product": [_("Product not found.")]})

    # Buscar ou criar lote
    if lot_id is None:
        if produto.track_lots:
            raise ValidationError({"lot": [_("Lot is required for tracked products.")]})
        # Buscar ou criar lote sintético
        lote, _criado = Lot.objects.get_or_create(
            tenant_id=tenant_id,
            product_id=product_id,
            code=f"__{product_id}__",
            defaults={"received_at": timezone.now()},
        )
    else:
        lote = Lot.objects.filter(tenant_id=tenant_id, pk=lot_id, product_id=product_id).first()
        if not lote:
            raise ValidationError({"lot": [_("Lot not found.")]})

    # Para saídas (quantity < 0), usar FEFO; para entradas, usar o lote fornecido
    if quantity < Decimal("0"):
        fefo_lote = get_fefo_lot(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lote.id if lot_id else None,
        )
        if fefo_lote and lot_id is None:
            lote = fefo_lote

    # Buscar custo
    nivel = StockLevel.objects.filter(
        tenant_id=tenant_id,
        product_id=product_id,
        location_id=location_id,
        lot_id=lote.id,
    ).first()

    unit_cost = nivel.unit_cost if nivel else Decimal("0")

    # Criar movimento
    mvt_dto = MovementDTO(
        product_id=product_id,
        location_id=location_id,
        lot_id=lote.id,
        quantity=quantity,
        unit_cost=unit_cost,
        # Mesma regra da quebra (ADR 0034): um nível sem preço escreve-se
        # "desconhecido" e não "zero euros". Ver `registar_waste`.
        cost_is_estimate=unit_cost == Decimal("0"),
        movement_type="adjustment",
        occurred_at=timezone.now(),
        created_by_id=user.id,
        created_by_name=user_name,
        reason=reason,
        reason_detail=reason_detail,
    )

    movement_ids = record_movements(tenant_id=tenant_id, movements=[mvt_dto])
    return movement_ids[0] if movement_ids else None


@transaction.atomic
def registar_transfer(
    *,
    tenant_id: UUID,
    product_id: UUID,
    from_location_id: UUID,
    to_location_id: UUID,
    quantity: Decimal,
    lot_id: UUID | None,
    user: Autor,
    user_name: str = "",
) -> tuple[UUID, UUID]:
    """Registar uma transferência entre localizações (pair atómico).

    Cria dois StockMovements: transfer_out (negativo) e transfer_in (positivo),
    ambos com o mesmo transfer_id.

    Argumentos:
    - quantity: Decimal > 0
    - Resto igual a waste

    Retorna: (transfer_out_id, transfer_in_id)

    Validações:
    - Localizações devem ser diferentes
    - Ambas devem estar ativas
    - Lote obrigatório se product.track_lots=True
    """
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": [_("Quantity must be positive.")]})

    if from_location_id == to_location_id:
        raise ValidationError(
            {"to_location": [_("Cannot transfer to the same location.")]}
        )

    # Validar localizações
    from_loc = Location.objects.filter(pk=from_location_id, tenant_id=tenant_id).first()
    if not from_loc:
        raise ValidationError({"from_location": [_("Location not found.")]})

    to_loc = Location.objects.filter(pk=to_location_id, tenant_id=tenant_id).first()
    if not to_loc:
        raise ValidationError({"to_location": [_("Location not found.")]})

    if not from_loc.is_active or not to_loc.is_active:
        raise ValidationError(
            {"location": [_("One or both locations are inactive.")]}
        )

    produto = produto_por_id(tenant_id=tenant_id, product_id=product_id)
    if produto is None:
        raise ValidationError({"product": [_("Product not found.")]})

    # Buscar lote a sair (FEFO)
    if lot_id is None:
        if produto.track_lots:
            raise ValidationError({"lot": [_("Lot is required for tracked products.")]})
        # Buscar lote sintético
        lote = Lot.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
            code=f"__{product_id}__",
        ).first()
        if not lote:
            raise ValidationError(
                {"lot": [_("Synthetic lot not found. Create stock first.")]}
            )
    else:
        lote = get_fefo_lot(
            tenant_id=tenant_id,
            product_id=product_id,
            location_id=from_location_id,
            lot_id=lot_id,
        )
        if not lote:
            raise ValidationError(
                {"lot": [_("Lot not found or has no stock at source location.")]}
            )

    # Buscar custo
    nivel_origem = StockLevel.objects.filter(
        tenant_id=tenant_id,
        product_id=product_id,
        location_id=from_location_id,
        lot_id=lote.id,
    ).first()

    unit_cost = nivel_origem.unit_cost if nivel_origem else Decimal("0")

    # Gerar transfer_id compartilhado
    transfer_id = uuid.uuid4()

    # Criar dois movimentos atomicamente, com o mesmo instante e o mesmo
    # `transfer_id` já na criação: o ledger é append-only e não se corrige depois.
    agora = timezone.now()
    out_dto = MovementDTO(
        product_id=product_id,
        location_id=from_location_id,
        lot_id=lote.id,
        quantity=-quantity,  # Negativo para saída
        unit_cost=unit_cost,
        # Mesma regra da quebra (ADR 0034): zero não é um preço de zero euros.
        cost_is_estimate=unit_cost == Decimal("0"),
        movement_type="transfer_out",
        occurred_at=agora,
        created_by_id=user.id,
        created_by_name=user_name,
        reason="",
        transfer_id=transfer_id,
    )

    in_dto = MovementDTO(
        product_id=product_id,
        location_id=to_location_id,
        lot_id=lote.id,
        quantity=quantity,  # Positivo para entrada
        unit_cost=unit_cost,
        # Mesma regra da quebra (ADR 0034): zero não é um preço de zero euros.
        cost_is_estimate=unit_cost == Decimal("0"),
        movement_type="transfer_in",
        occurred_at=agora,
        created_by_id=user.id,
        created_by_name=user_name,
        reason="",
        transfer_id=transfer_id,
    )

    # Gravar ambos os movimentos
    out_id, in_id = record_movements(tenant_id=tenant_id, movements=[out_dto, in_dto])
    return out_id, in_id
