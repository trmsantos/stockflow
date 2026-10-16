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

from apps.inventory.models import (
    Location,
    ProductCost,
    StockCount,
    StockCountLine,
    StockLevel,
    StockMovement,
)

__all__ = [
    "ajustes_da_contagem",
    "artigos_abaixo_do_minimo",
    "contagens_do_ambito",
    "custos_dos_niveis",
    "custos_medios_do_artigo",
    "desperdicio_por_artigo_e_motivo",
    "e_lote_sintetico",
    "linhas_da_contagem",
    "listar_contagens",
    "listar_localizacoes",
    "localizacoes_do_ambito",
    "lotes_a_vencer",
    "movimentos_resumidos",
    "producoes_por_periodo",
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
#: Quantos lotes a vencer o painel lista no máximo. Um alerta é para agir, e
#: uma lista de duzentos não é accionável — o ecrã Alertas tem o resto.
LIMITE_DE_LOTES_DO_PAINEL = 200


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
    embalagem. `hoje` é o dia **civil** nos dois chamadores — painel e
    assistente —, e a razão está no `business_day_starts_at` do `Tenant`: o
    relógio do negócio decide a que dia pertence um movimento, um total, uma
    receção ou um desperdício, e **não** decide validades. Entre as 00:00 e as
    04:00 o "hoje" do negócio ainda é ontem, e com ele a app diria "expira
    amanhã" de um lote que a ASAE já considera expirado. Até 2026-10-16 o
    assistente passava aqui o dia de negócio e o painel o civil — duas regras
    para a mesma data (ADR 0028). A janela é rolante sobre `hoje`.

    Os lotes já vencidos entram **e são marcados** pelo chamador
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

    As validades estão no calendário civil (`timezone.localdate()`): são a data
    impressa na embalagem e não se deslocam pelo relógio do negócio. É a **mesma
    regra e o mesmo selector** que o assistente usa desde a ADR 0028.
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

    # **O mesmo selector do assistente**, e não uma segunda varredura do `Lot`
    # (ADR 0028): a tabela `Lot` sozinha não sabe se ainda há mercadoria, e o
    # painel listava lotes já consumidos até ao fim como se estivessem a vencer.
    # A janela é a mesma e a comparação é por data civil nos dois sítios.
    for lote in lotes_a_vencer(
        tenant_id=tenant_id,
        hoje=hoje,
        dias=DIAS_DE_VALIDADE_DO_PAINEL,
        location_id=location_id,
        limite=LIMITE_DE_LOTES_DO_PAINEL,
    ):
        if product_id is not None and lote["product_id"] != product_id:
            continue
        vencido = lote["expires_on"] < hoje
        gravidade = "critical" if vencido else "warning"
        if severity and severity != gravidade:
            continue
        alertas.append(
            {
                "alert_type": "expired" if vencido else "expiring_soon",
                "severity": gravidade,
                "product_id": lote["product_id"],
                "product_name": lote["product_name"],
                "location_id": None,
                "location_name": None,
                "lot_code": lote["lot_code"],
                "expires_at": lote["expires_at"],
            }
        )
    return alertas


# ---------------------------------------------------------------------------
# As leituras da ADR 0028: contagens, desperdício, produções e custo médio.
# Nenhuma escreve, e nenhuma devolve ORM a quem chama pela porta — o `api.py`
# congela tudo em DTOs.
# ---------------------------------------------------------------------------
def e_lote_sintetico(codigo: str | None) -> bool:
    """O `code` deste lote é um sintético (`__…__`) e não um lote de verdade?

    Um lote sintético nasce em dois sítios — a confirmação de uma receção de um
    artigo sem lote impresso e a produção de uma receita (ADR 0023 e 0026) — e
    existe para o ledger ter uma chave, não para alguém o ler. Quem o mostra diz
    "sem lote".
    """
    return bool(codigo) and codigo.startswith("__") and codigo.endswith("__")


def contagens_do_ambito(*, tenant_id: UUID) -> QuerySet[StockCount]:
    """Todas as contagens do estabelecimento, com a localização carregada."""
    return StockCount.objects.filter(tenant_id=tenant_id).select_related("location")


def listar_contagens(
    *, tenant_id: UUID, estado: str = "", limite: int = 20
) -> list[StockCount]:
    """As contagens por estado: `open` primeiro pelo início, `closed` pelo fecho.

    Devolve `limite + 1` linhas no máximo, para quem chama saber se cortou. Uma
    contagem aberta ordena-se pela data em que começou (a mais antiga é a que
    está esquecida) e uma fechada pela data em que fechou, mais recente
    primeiro — são duas perguntas diferentes.
    """
    contagens = contagens_do_ambito(tenant_id=tenant_id)
    if estado:
        contagens = contagens.filter(status=estado)
    if estado == "open":
        contagens = contagens.order_by("started_at", "id")
    else:
        contagens = contagens.order_by(F("closed_at").desc(nulls_last=True), "-started_at", "id")
    return list(contagens[: limite + 1])


def linhas_da_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> list[StockCountLine]:
    """As linhas de uma contagem, com artigo e lote carregados, por zona e nome."""
    return list(
        StockCountLine.objects.filter(tenant_id=tenant_id, stock_count_id=stock_count_id)
        .select_related("product", "lot")
        .order_by("zone", "product__short_name", "id")
    )


def custos_dos_niveis(
    *, tenant_id: UUID, location_id: UUID, chaves: Sequence[tuple[UUID, UUID | None]]
) -> dict[tuple[UUID, UUID | None], Decimal]:
    """O `unit_cost` de cada `(artigo, lote)` nesta localização, numa query.

    A chave inclui o **lote**, e é essa a correcção da ADR 0028: o
    `resumo_contagem` lia `.first()` de `(artigo, localização)` sem lote, e numa
    localização com dois lotes do mesmo artigo valorizava a diferença de um pelo
    custo do outro — em silêncio, e sempre pelo lote que a base devolvesse
    primeiro.
    """
    if not chaves:
        return {}
    produtos = {produto_id for produto_id, _ in chaves}
    niveis = StockLevel.objects.filter(
        tenant_id=tenant_id, location_id=location_id, product_id__in=produtos
    ).values("product_id", "lot_id", "unit_cost")
    return {(nivel["product_id"], nivel["lot_id"]): nivel["unit_cost"] for nivel in niveis}


def ajustes_da_contagem(*, tenant_id: UUID, stock_count_id: UUID) -> dict[str, Any]:
    """Os `adjustment` que o fecho de uma contagem gravou: quantos, quando e quanto.

    A ligação é o `reference` do movimento, que o `fechar_contagem` grava com o
    id da contagem (ADR 0025). Uma contagem aberta não tem nenhum — e é isso
    que permite dizer "esta contagem ainda não mexeu no stock".
    """
    linhas = StockMovement.objects.filter(
        tenant_id=tenant_id, movement_type="adjustment", reference=str(stock_count_id)
    ).values("quantity", "unit_cost", "occurred_at")
    n = 0
    valor = Decimal("0")
    quando: datetime | None = None
    for linha in linhas:
        n += 1
        valor += abs(linha["quantity"]) * linha["unit_cost"]
        if quando is None or linha["occurred_at"] > quando:
            quando = linha["occurred_at"]
    return {"n": n, "valor_eur": valor, "ultimo_em": quando}


def desperdicio_por_artigo_e_motivo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 50
) -> list[dict[str, Any]]:
    """Σ dos `waste` de `[desde, ate)`, por artigo e motivo, com o valor em euros.

    Resumo e não lista de movimentos, e **sem limiar**: um desperdício de 200 g
    de salsa conta na mesma linha que o de 20 kg de farinha, e quem lê decide o
    que destaca. O valor é `|quantidade| × unit_cost` **do movimento** (ADR
    0014: qualquer agregado se valoriza pelo custo gravado na linha, nunca pelo
    custo de hoje), e um `unit_cost` a zero sai como zero com a contagem de
    linhas sem custo ao lado.
    """
    linhas = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            movement_type="waste",
            occurred_at__gte=desde,
            occurred_at__lt=ate,
        )
        .values(*_CAMPOS_DO_ARTIGO, "reason")
        .annotate(
            n=Count("id"),
            quantidade=Sum("quantity"),
            valor=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField()),
            sem_custo=Count("id", filter=Q(unit_cost=Decimal("0"))),
        )
        .order_by("product__short_name", "reason")[: limite + 1]
    )
    return [
        {
            "product_id": linha["product_id"],
            "product_name": linha["product__short_name"],
            "sku": linha["product__sku"],
            "base_unit": linha["product__base_unit"],
            "display_unit": linha["product__display_unit"],
            "display_factor": linha["product__display_factor"],
            "reason": linha["reason"] or "",
            "n": linha["n"],
            # **Positiva**: um `waste` está no ledger com a quantidade a
            # negativo, porque é uma saída, e "perdeu-se −2 kg" não é uma
            # frase. O sinal lê-se aqui, uma vez, como já se lia no valor — o
            # DTO `DesperdicioPorArtigo` promete-o e até 2026-10-16 só o valor
            # o cumpria.
            "quantidade": abs(linha["quantidade"] or Decimal("0")),
            "valor_eur": abs(linha["valor"] or Decimal("0")),
            "linhas_sem_custo": linha["sem_custo"],
        }
        for linha in linhas
    ]


def producoes_por_periodo(
    *, tenant_id: UUID, desde: datetime, ate: datetime, limite: int = 20
) -> list[dict[str, Any]]:
    """As produções de `[desde, ate)`, uma por `production_id`, mais recente primeiro.

    Uma produção é o par que a ADR 0026 grava: N `production_out` (os
    ingredientes que saíram, em FEFO) e **um** `production_in` (o acabado que
    entrou), todos com o mesmo `production_id`. É por ele que se agrupa, porque
    é o único laço que o ledger tem entre as duas pontas.

    O `unit_cost` do `production_in` é o custo real daquela produção, gravado no
    momento (ADR 0026, decisão 2): é o número que se compara com o teórico da
    ficha, e não se recalcula a partir dos custos de hoje.
    """
    movimentos = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            production_id__isnull=False,
            occurred_at__gte=desde,
            occurred_at__lt=ate,
        )
        .select_related("product", "location")
        .order_by("-occurred_at", "id")
    )
    producoes: dict[UUID, dict[str, Any]] = {}
    for movimento in movimentos:
        producao = producoes.setdefault(
            movimento.production_id,
            {
                "production_id": movimento.production_id,
                "occurred_at": movimento.occurred_at,
                "location_name": movimento.location.name,
                "created_by_name": movimento.created_by_name,
                "product_id": None,
                "product_name": "",
                "base_unit": "",
                "display_unit": "",
                "display_factor": Decimal("1"),
                "quantidade": Decimal("0"),
                "unit_cost": Decimal("0"),
                "ingredientes": [],
            },
        )
        if movimento.movement_type == "production_in":
            producao["product_id"] = movimento.product_id
            producao["product_name"] = movimento.product.short_name
            producao["base_unit"] = movimento.product.base_unit
            producao["display_unit"] = movimento.product.display_unit
            producao["display_factor"] = movimento.product.display_factor
            producao["quantidade"] = movimento.quantity
            producao["unit_cost"] = movimento.unit_cost
            producao["occurred_at"] = movimento.occurred_at
        elif movimento.movement_type == "production_out":
            producao["ingredientes"].append(
                {
                    "product_id": movimento.product_id,
                    "product_name": movimento.product.short_name,
                    "base_unit": movimento.product.base_unit,
                    "display_unit": movimento.product.display_unit,
                    "display_factor": movimento.product.display_factor,
                    "quantidade": abs(movimento.quantity),
                    "unit_cost": movimento.unit_cost,
                }
            )
    ordenadas = sorted(producoes.values(), key=lambda p: p["occurred_at"], reverse=True)
    return ordenadas[: limite + 1]


def custos_medios_do_artigo(*, tenant_id: UUID, product_id: UUID) -> list[dict[str, Any]]:
    """O CMP de um artigo por localização (`inventory_productcost`), por posição.

    Zero é "preço desconhecido" e não "de graça" (ADR 0024): o artigo entrou
    sem preço — uma guia de remessa — ou nunca entrou. Quem lê diz a palavra.
    """
    return [
        {
            "product_id": custo.product_id,
            "location_id": custo.location_id,
            "location_name": custo.location.name,
            "unit_cost": custo.unit_cost,
        }
        for custo in ProductCost.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related("location")
        .order_by("location__position", "location__name")
    ]
