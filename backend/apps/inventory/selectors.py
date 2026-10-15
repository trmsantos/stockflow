"""Queries de leitura do `inventory`. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele — a segunda rede, ao lado da política
de RLS (SECURITY.md §1).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.utils import timezone

from apps.inventory.models import Location, Lot, StockLevel, StockMovement

__all__ = [
    "artigos_abaixo_do_minimo",
    "listar_localizacoes",
    "localizacoes_do_ambito",
    "lotes_a_vencer",
    "movimentos_resumidos",
    "saldos_do_artigo",
    "stock_alerts",
    "stock_summary",
    "stock_by_location",
    "stock_by_product",
]

#: Os estados de um artigo contra o seu mínimo (ADR 0027, regras de domínio):
#: `sem_stock` é saldo ≤ 0 **com** `StockLevel` — o artigo já entrou e acabou —
#: e `abaixo_do_minimo` é `0 < saldo < min`. Um artigo sem `StockLevel` nunca
#: entrou e não alarma: não se avisa de falta do que nunca houve.
SEM_STOCK = "sem_stock"
ABAIXO_DO_MINIMO = "abaixo_do_minimo"

#: A janela por omissão dos alertas de validade do painel: sete dias.
DIAS_DE_VALIDADE_DO_PAINEL = 7


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


def stock_summary(
    *, tenant_id: UUID, location_id: UUID | None = None
) -> QuerySet:
    """Saldo agregado por produto (com ou sem localização).

    Retorna: product_id, product_name, quantity (SUM), unit_cost, total_value.
    Filtra por: quantity != 0.
    """
    qs = (
        StockLevel.objects.filter(tenant_id=tenant_id)
        .exclude(quantity=Decimal("0"))
        .select_related("product", "lot")
        .values("product_id", "product__short_name")
        .annotate(
            product_name=F("product__short_name"),
            total_quantity=Sum("quantity"),
            avg_unit_cost=Case(
                When(quantity__gt=0, then=F("unit_cost")),
                default=Value(Decimal("0")),
                output_field=DecimalField(),
            ),
        )
    )

    if location_id:
        qs = qs.filter(location_id=location_id)

    return qs.order_by("product__short_name")


def stock_by_location(
    *, tenant_id: UUID, location_id: UUID, search_text: str = ""
) -> QuerySet:
    """Saldo por (product, lot) nessa localização, ordenado por FEFO.

    Retorna: product_id, product_name, lot_code, expires_at, quantity, unit_cost, total_value.
    FEFO: expires_at ASC NULLS LAST, received_at ASC.
    """
    qs = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            location_id=location_id,
        )
        .exclude(quantity=Decimal("0"))
        .select_related("product", "lot")
        .values(
            "product_id",
            "product__short_name",
            "lot__code",
            "lot__expires_at",
            "lot__received_at",
            "unit_cost",
        )
        .annotate(
            product_name=F("product__short_name"),
            lot_code=F("lot__code"),
            expires_at=F("lot__expires_at"),
            received_at=F("lot__received_at"),
        )
    )

    if search_text:
        qs = qs.filter(
            Q(product__short_name__icontains=search_text)
            | Q(lot__code__icontains=search_text)
        )

    return qs.order_by("lot__expires_at", "lot__received_at")


def stock_by_product(
    *, tenant_id: UUID, product_id: UUID, search_text: str = ""
) -> QuerySet:
    """Saldo por (location, lot) desse produto, ordenado por FEFO.

    Retorna: product_id, product_name, location_id, location_name, lot_code, expires_at,
    quantity, unit_cost, total_value.
    """
    qs = (
        StockLevel.objects.filter(
            tenant_id=tenant_id,
            product_id=product_id,
        )
        .exclude(quantity=Decimal("0"))
        .select_related("product", "location", "lot")
        .values(
            "product_id",
            "product__short_name",
            "location_id",
            "location__name",
            "lot__code",
            "lot__expires_at",
            "lot__received_at",
            "unit_cost",
        )
        .annotate(
            product_name=F("product__short_name"),
            location_name=F("location__name"),
            lot_code=F("lot__code"),
            expires_at=F("lot__expires_at"),
            received_at=F("lot__received_at"),
        )
    )

    if search_text:
        qs = qs.filter(
            Q(location__name__icontains=search_text)
            | Q(lot__code__icontains=search_text)
        )

    return qs.order_by("lot__expires_at", "lot__received_at")


# ---------------------------------------------------------------------------
# As leituras do assistente (ADR 0027, decisão 6) e dos alertas do painel
# ---------------------------------------------------------------------------
_CAMPOS_DO_ARTIGO = (
    "product_id",
    "product__short_name",
    "product__sku",
    "product__base_unit",
    "product__display_unit",
    "product__display_factor",
)


def saldos_do_artigo(
    *, tenant_id: UUID, product_id: UUID, location_id: UUID | None = None
) -> QuerySet[StockLevel]:
    """Os níveis de um artigo, por localização e lote, em ordem FEFO.

    Sem o `exclude(quantity=0)` das vistas do painel: o chamador distingue
    "nunca entrou" (zero linhas) de "entrou e acabou" (linhas a zero), e é essa
    a diferença entre `nunca_entrou: true` e um saldo de 0 (ADR 0027).
    """
    niveis = StockLevel.objects.filter(tenant_id=tenant_id, product_id=product_id)
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    return niveis.select_related("product", "location", "lot").order_by(
        F("lot__expires_at").asc(nulls_last=True), "lot__received_at", "location__position", "id"
    )


def artigos_abaixo_do_minimo(
    *, tenant_id: UUID, location_id: UUID | None = None, limite: int = 50
) -> list[dict[str, Any]]:
    """Os artigos cujo **saldo somado** está abaixo do mínimo do artigo.

    `min_quantity` é por artigo e não por loja, logo compara-se contra o `SUM`
    em todas as localizações: 3 × 400 g em três lojas contra um mínimo de
    1000 g **não** alarma. O selector antigo comparava lote a lote e dava
    exactamente esse alarme falso. Com `location_id` soma-se só essa, e quem lê
    tem de dizer que o mínimo é do artigo e não da loja.

    Excluídos: mínimo a zero (não há mínimo), inactivos, e artigos sem
    `StockLevel` nenhum (nunca entraram). Saldo ≤ 0 com `StockLevel` é
    `sem_stock`; `0 < saldo < min` é `abaixo_do_minimo`.

    Devolve `limite + 1` linhas no máximo, para o chamador saber se cortou.
    """
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id,
        product__is_active=True,
        product__min_quantity__gt=Decimal("0"),
    )
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    linhas = (
        niveis.values(*_CAMPOS_DO_ARTIGO, "product__min_quantity")
        .annotate(saldo=Sum("quantity"))
        .filter(saldo__lt=F("product__min_quantity"))
        .order_by("product__short_name", "product_id")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "min_quantity": linha["product__min_quantity"],
            "saldo": linha["saldo"],
            "estado": SEM_STOCK if linha["saldo"] <= Decimal("0") else ABAIXO_DO_MINIMO,
        }
        for linha in linhas
    ]


def lotes_a_vencer(
    *,
    tenant_id: UUID,
    hoje: date,
    dias: int,
    location_id: UUID | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Os lotes **com saldo** que vencem até `hoje + dias`, vencidos incluídos.

    Comparação por **data** e não por instante: a validade é a data impressa na
    embalagem. `hoje` vem de quem chama — o assistente passa o dia de negócio
    (às 02:00 ainda é ontem), o painel passa o dia civil — e a janela é rolante
    sobre ele. Os lotes já vencidos entram **e são marcados** pelo chamador
    (`< hoje`), porque a pergunta "o que vence esta semana" tem como pior
    resposta um lote vencido que ficou de fora por já ter vencido.

    Só lotes com saldo somado > 0: um lote consumido até ao fim não vence em
    lado nenhum. O `join` ao `StockLevel` é o que o garante; a tabela `Lot`
    sozinha não sabe se ainda há mercadoria.

    `conservation` e `expiry_kind` são dados da linha, nunca filtro. Devolve
    `limite + 1` linhas no máximo.
    """
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id,
        lot__isnull=False,
        lot__expires_at__isnull=False,
        lot__expires_at__date__lte=hoje + timedelta(days=dias),
    )
    if location_id is not None:
        niveis = niveis.filter(location_id=location_id)
    linhas = (
        niveis.values(
            *_CAMPOS_DO_ARTIGO,
            "product__expiry_kind",
            "product__conservation",
            "lot_id",
            "lot__code",
            "lot__expires_at",
        )
        .annotate(saldo=Sum("quantity"))
        .filter(saldo__gt=Decimal("0"))
        .order_by("lot__expires_at", "product__short_name", "lot__code")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "expiry_kind": linha["product__expiry_kind"],
            "conservation": linha["product__conservation"],
            "lot_id": linha["lot_id"],
            "lot_code": linha["lot__code"],
            "expires_at": linha["lot__expires_at"],
            "expires_on": timezone.localdate(linha["lot__expires_at"]),
            "saldo": linha["saldo"],
        }
        for linha in linhas
    ]


def movimentos_resumidos(
    *,
    tenant_id: UUID,
    product_id: UUID,
    desde: datetime,
    ate: datetime,
    tipos: Sequence[str] | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    """O resumo por tipo e as últimas `limite` linhas de um artigo em `[desde, ate)`.

    O resumo é um `GROUP BY movement_type` com `n` e a quantidade **com sinal**,
    e cobre o período inteiro; as linhas são as `limite` mais recentes e vêm
    com `truncado` quando há mais. As transferências vêm com a contraparte — a
    localização do outro movimento do mesmo `transfer_id` — para a resposta
    poder dizer "da Loja para o Armazém" em vez de duas linhas soltas.
    """
    movimentos = StockMovement.objects.filter(
        tenant_id=tenant_id, product_id=product_id, occurred_at__gte=desde, occurred_at__lt=ate
    )
    if tipos:
        movimentos = movimentos.filter(movement_type__in=list(tipos))
    resumo = {
        linha["movement_type"]: {"n": linha["n"], "quantidade": linha["quantidade"]}
        for linha in movimentos.values("movement_type")
        .annotate(n=Count("id"), quantidade=Sum("quantity"))
        .order_by("movement_type")
    }
    ultimos = list(
        movimentos.select_related("location", "lot").order_by("-occurred_at", "-created_at", "-id")[
            : limite + 1
        ]
    )
    truncado = len(ultimos) > limite
    ultimos = ultimos[:limite]

    transfer_ids = {m.transfer_id for m in ultimos if m.transfer_id is not None}
    contrapartes: dict[tuple[UUID, str], str] = {}
    if transfer_ids:
        pares = StockMovement.objects.filter(
            tenant_id=tenant_id, transfer_id__in=transfer_ids
        ).select_related("location")
        for par in pares:
            contrapartes[(par.transfer_id, par.movement_type)] = par.location.name

    linhas = []
    for m in ultimos:
        contraparte = None
        if m.transfer_id is not None:
            outro = "transfer_in" if m.movement_type == "transfer_out" else "transfer_out"
            contraparte = contrapartes.get((m.transfer_id, outro))
        linhas.append(
            {
                "id": m.id,
                "movement_type": m.movement_type,
                "quantity": m.quantity,
                "unit_cost": m.unit_cost,
                "cost_is_estimate": m.cost_is_estimate,
                "occurred_at": m.occurred_at,
                "location_name": m.location.name,
                "lot_code": m.lot.code if m.lot is not None else None,
                "reason": m.reason,
                "reference": m.reference,
                "transfer_id": m.transfer_id,
                "contraparte": contraparte,
                "created_by_name": m.created_by_name,
            }
        )
    return {"resumo": resumo, "linhas": linhas, "truncado": truncado}


def stock_alerts(
    *,
    tenant_id: UUID,
    severity: str = "",
    product_id: UUID | None = None,
    location_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Os alertas do painel: falta, validade a vencer e validade vencida (ADR 0024).

    Vivia em `views.py`, e uma view não é chamável pela porta do módulo (ADR
    0027, decisão 6). A mudança que não é só de sítio é a **falta**: compara o
    saldo somado do artigo contra o mínimo do artigo (`artigos_abaixo_do_minimo`),
    em vez de lote a lote — um artigo com 3 × 400 g contra um mínimo de 1000 g
    deixou de alarmar. Sem `location_id` o alerta de falta não tem localização,
    porque o saldo é de todas; com ele, é a dessa loja contra o mínimo do artigo.

    As validades continuam no calendário civil (`timezone.localdate()`): são a
    data impressa na embalagem e não se deslocam pelo relógio do negócio.
    """
    alertas: list[dict[str, Any]] = []
    hoje = timezone.localdate()

    if not severity or severity == "critical":
        nome_da_localizacao = None
        if location_id is not None:
            localizacao = Location.objects.filter(tenant_id=tenant_id, pk=location_id).first()
            nome_da_localizacao = localizacao.name if localizacao is not None else None
        for artigo in artigos_abaixo_do_minimo(tenant_id=tenant_id, location_id=location_id):
            if product_id is not None and artigo["product_id"] != product_id:
                continue
            alertas.append(
                {
                    "alert_type": "shortage",
                    "severity": "critical",
                    "product_id": artigo["product_id"],
                    "product_name": artigo["product_name"],
                    "location_id": location_id,
                    "location_name": nome_da_localizacao,
                    "lot_code": None,
                    "expires_at": None,
                }
            )

    lotes = Lot.objects.filter(
        tenant_id=tenant_id,
        expires_at__isnull=False,
        expires_at__date__lte=hoje + timedelta(days=DIAS_DE_VALIDADE_DO_PAINEL),
    ).select_related("product")
    if product_id is not None:
        lotes = lotes.filter(product_id=product_id)
    for lote in lotes.order_by("expires_at", "code"):
        vencido = timezone.localdate(lote.expires_at) < hoje
        gravidade = "critical" if vencido else "warning"
        if severity and severity != gravidade:
            continue
        alertas.append(
            {
                "alert_type": "expired" if vencido else "expiring_soon",
                "severity": gravidade,
                "product_id": lote.product_id,
                "product_name": lote.product.short_name,
                "location_id": None,
                "location_name": None,
                "lot_code": lote.code,
                "expires_at": lote.expires_at,
            }
        )
    return alertas
