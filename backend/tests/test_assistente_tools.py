"""As regras de domínio das tools do assistente (ADR 0027, validadas pelo `domain-expert`).

Cada teste chama o despachante `tools.executar` directamente, dentro de
`tenant_scope`, com um contexto cujo dia de negócio é escolhido à mão — é o que
permite medir a janela das validades sem congelar o relógio. O que se afirma é o
JSON que o modelo recebe, porque é esse o contrato: o `texto` das quantidades, o
`iva_incluido: false`, o `nunca_entrou`, os estados `vencido`/`vence_hoje`, o
`sem_stock`, as transferências fora das perdas, o `truncado`.

As regras, uma a uma, estão no briefing da feature e no topo de
`apps/agents/tools.py`.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import conceder_pertenca, criar_tenant, revogar_pertenca
from apps.agents import navegacao, tools
from apps.catalog.models import (
    Product,
    ProductPackaging,
    Supplier,
    SupplierProductCode,
    UnidadeBase,
)
from apps.inventory.models import (
    Location,
    Lot,
    ProductCost,
    StockCount,
    StockCountLine,
    StockLevel,
    StockMovement,
)
from apps.purchasing.models import Receipt, ReceiptLine
from apps.recipes.models import Recipe, RecipeLineItem
from apps.shared.db import tenant_scope
from tests.factories import InvitationFactory

LISBOA = ZoneInfo("Europe/Lisbon")
INICIO_DO_DIA = time(4, 0)
#: Longa e sem palavra de dicionário: o `User.objects.create_user` valida-a.
CREDENCIAL_DE_TESTE = "farinha-fina-ao-amanhecer-9"


@dataclass(frozen=True, kw_only=True, slots=True)
class Loja:
    tenant: Tenant
    loja: Location
    armazem: Location
    cozinha: Location


@pytest.fixture
def loja(transactional_db: None) -> Loja:
    tenant = criar_tenant(name="Padaria Gama")
    with tenant_scope(tenant.id):
        loja = Location.objects.create(tenant=tenant, name="Loja", position=1)
        armazem = Location.objects.create(tenant=tenant, name="Armazém", position=2)
        cozinha = Location.objects.create(tenant=tenant, name="Cozinha", position=3)
    return Loja(tenant=tenant, loja=loja, armazem=armazem, cozinha=cozinha)


def _produto(
    tenant: Tenant,
    nome: str,
    *,
    sku: str = "",
    base_unit: str = UnidadeBase.GRAMA,
    display_unit: str = "kg",
    factor: str = "1000",
    minimo: str = "0",
    expiry_kind: str = "",
    track_lots: bool = True,
    ativo: bool = True,
) -> Product:
    with tenant_scope(tenant.id):
        return Product.objects.create(
            tenant=tenant,
            short_name=nome,
            sku=sku,
            base_unit=base_unit,
            display_unit=display_unit,
            display_factor=Decimal(factor),
            min_quantity=Decimal(minimo),
            expiry_kind=expiry_kind,
            track_lots=track_lots,
            is_active=ativo,
        )


def _lote(tenant: Tenant, produto: Product, codigo: str, *, validade: date | None) -> Lot:
    with tenant_scope(tenant.id):
        return Lot.objects.create(
            tenant=tenant,
            product=produto,
            code=codigo,
            expires_at=(
                datetime.combine(validade, time(12, 0), tzinfo=LISBOA) if validade else None
            ),
            received_at=timezone.now(),
        )


def _nivel(
    tenant: Tenant,
    produto: Product,
    local: Location,
    quantidade: str,
    *,
    lote: Lot | None = None,
    custo: str = "0",
) -> StockLevel:
    with tenant_scope(tenant.id):
        return StockLevel.objects.create(
            tenant=tenant,
            product=produto,
            location=local,
            lot=lote,
            quantity=Decimal(quantidade),
            unit_cost=Decimal(custo),
        )


def _movimento(
    tenant: Tenant,
    produto: Product,
    local: Location,
    tipo: str,
    quantidade: str,
    *,
    quando: datetime | None = None,
    custo: str = "0",
    estimado: bool = False,
    transfer_id: UUID | None = None,
    lote: Lot | None = None,
    por: str = "Teste",
) -> StockMovement:
    with tenant_scope(tenant.id):
        return StockMovement.objects.create(
            tenant=tenant,
            product=produto,
            location=local,
            lot=lote,
            movement_type=tipo,
            quantity=Decimal(quantidade),
            unit_cost=Decimal(custo),
            cost_is_estimate=estimado,
            transfer_id=transfer_id,
            occurred_at=quando or timezone.now(),
            created_by_name=por,
        )


def _rececao(
    tenant: Tenant,
    local: Location,
    *,
    doc_type: str,
    received_at: datetime,
    doc_date: date | None = None,
    confirmada: bool = True,
    fornecedor: Supplier | None = None,
    linhas: tuple[tuple[Product | None, str | None, str, str], ...] = (),
) -> Receipt:
    """Uma receção com linhas `(produto, line_total, status, kind)`."""
    with tenant_scope(tenant.id):
        rececao = Receipt.objects.create(
            tenant=tenant,
            supplier=fornecedor,
            doc_type=doc_type,
            doc_date=doc_date,
            received_at=received_at,
            location=local,
            confirmed_at=received_at if confirmada else None,
        )
        for posicao, (produto, total, estado, tipo) in enumerate(linhas, start=1):
            ReceiptLine.objects.create(
                tenant=tenant,
                receipt=rececao,
                position=posicao,
                quantity_received=Decimal("1"),
                location=local,
                kind=tipo,
                status=estado,
                product=produto,
                line_total=Decimal(total) if total is not None else None,
            )
    return rececao


def _contexto(
    tenant: Tenant,
    *,
    hoje: date | None = None,
    hoje_civil: date | None = None,
    papel: str = "owner",
    lingua: str = "pt-pt",
    user_id: UUID | None = None,
    agora: datetime | None = None,
) -> tools.ContextoDaTool:
    """O contexto de um turno, com os **dois** dias à mão.

    `hoje` é o dia de negócio (às 02:00 ainda é ontem) e decide movimentos,
    totais, receções e desperdício; `hoje_civil` é a data do calendário e decide
    **só** validades (ADR 0028). Separá-los aqui é o que permite medir a
    fronteira das 00:00–04:00, onde até 2026-10-16 os dois divergiam em
    silêncio.
    """
    agora = agora or timezone.now()
    return tools.ContextoDaTool(
        tenant_id=tenant.id,
        papel=papel,
        agora=agora,
        hoje=hoje or tools.dia_de_negocio(agora, INICIO_DO_DIA),
        inicio_do_dia=INICIO_DO_DIA,
        hoje_civil=hoje_civil or hoje or timezone.localdate(agora),
        lingua=lingua,
        user_id=user_id,
    )


def _executar(contexto: tools.ContextoDaTool, nome: str, **args: Any) -> tuple[dict[str, Any], tools.ResultadoDaTool]:
    """O `dados` do envelope e o resultado inteiro, dentro do âmbito."""
    with tenant_scope(contexto.tenant_id):
        resultado = tools.executar(
            nome=nome, argumentos=json.dumps(args, default=str), contexto=contexto
        )
    envelope = json.loads(resultado.conteudo)
    assert set(envelope) == {"dados", "truncado", "aviso"}
    return envelope["dados"], resultado


def _em_lisboa(dia: date, hora: time) -> datetime:
    return datetime.combine(dia, hora, tzinfo=LISBOA)


# ---------------------------------------------------------------------------
# Unidades e texto
# ---------------------------------------------------------------------------
def test_a_quantidade_sai_em_tres_formas_e_o_texto_tem_virgula(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha T65", track_lots=False)
    _nivel(loja.tenant, farinha, loja.loja, "12500", custo="0.003296")

    dados, resultado = _executar(_contexto(loja.tenant), "saldo_de_artigo", product_id=farinha.id)

    assert resultado.ok and resultado.linhas == 1
    linha = dados["linhas"][0]
    assert linha["texto"] == "12,5 kg"
    assert linha["quantidade"] == "12,5"
    assert linha["display_unit"] == "kg"
    chaves = list(linha)
    assert chaves.index("texto") < chaves.index("quantidade") < chaves.index("quantidade_base"), (
        "a base vem depois da apresentação, só para auditoria"
    )
    assert chaves.index("base_unit") == chaves.index("quantidade_base") + 1
    assert linha["quantidade_base"] == "12500" and linha["base_unit"] == "g"
    assert linha["valor_texto"] == "€ 41,20" and linha["custo"] == "conhecido"
    assert dados["total"]["texto"] == "12,5 kg"
    assert dados["valor_total_texto"] == "€ 41,20"
    assert dados["nunca_entrou"] is False


@pytest.mark.parametrize(
    ("base", "factor", "unidade", "esperado"),
    [
        ("12500", "1000", "kg", "12,5 kg"),
        ("100000", "1000", "kg", "100 kg"),
        ("1", "1", "un", "1 un"),
        ("12.3456", "1", "un", "12,346 un"),
        ("250", "1000", "L", "0,25 L"),
        ("0", "1000", "kg", "0 kg"),
    ],
)
def test_texto_de_quantidade(base: str, factor: str, unidade: str, esperado: str) -> None:
    assert (
        tools.texto_de_quantidade(
            Decimal(base), display_factor=Decimal(factor), display_unit=unidade
        )
        == esperado
    )


def test_texto_de_dinheiro() -> None:
    assert tools.texto_de_dinheiro(Decimal("41.2")) == "€ 41,20"
    assert tools.texto_de_dinheiro(Decimal("0.005")) == "€ 0,01"
    assert tools.texto_de_dinheiro(Decimal("-3")) == "€ -3,00"


# ---------------------------------------------------------------------------
# Validades: janela sobre o dia de negócio, por data, rótulo e saldo
# ---------------------------------------------------------------------------
def test_o_dia_de_negocio_as_duas_da_manha_ainda_e_ontem() -> None:
    assert tools.dia_de_negocio(_em_lisboa(date(2026, 10, 15), time(2, 0)), INICIO_DO_DIA) == date(
        2026, 10, 14
    )
    assert tools.dia_de_negocio(_em_lisboa(date(2026, 10, 15), time(4, 0)), INICIO_DO_DIA) == date(
        2026, 10, 15
    )
    assert tools.dia_de_negocio(_em_lisboa(date(2026, 10, 15), time(23, 59)), INICIO_DO_DIA) == date(
        2026, 10, 15
    )


def test_lotes_a_vencer_janela_rolante_por_data_sobre_o_dia_de_negocio(loja: Loja) -> None:
    hoje = date(2026, 10, 14)
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by", display_unit="L")
    ontem = _lote(loja.tenant, leite, "ONTEM", validade=hoje - timedelta(days=1))
    de_hoje = _lote(loja.tenant, leite, "HOJE", validade=hoje)
    em_sete = _lote(loja.tenant, leite, "SETE", validade=hoje + timedelta(days=7))
    em_oito = _lote(loja.tenant, leite, "OITO", validade=hoje + timedelta(days=8))
    for lote in (ontem, de_hoje, em_sete, em_oito):
        _nivel(loja.tenant, leite, loja.loja, "1000", lote=lote)

    dados, _ = _executar(_contexto(loja.tenant, hoje=hoje), "lotes_a_vencer")

    assert dados["hoje"] == "2026-10-14" and dados["ate"] == "2026-10-21" and dados["dias"] == 7
    por_lote = {linha["lote"]: linha for linha in dados["linhas"]}
    assert list(por_lote) == ["ONTEM", "HOJE", "SETE"], "por validade; o de oito dias fica fora"
    assert por_lote["ONTEM"]["estado"] == "vencido" and por_lote["ONTEM"]["dias"] == -1
    assert por_lote["HOJE"]["estado"] == "vence_hoje" and por_lote["HOJE"]["dias"] == 0
    assert por_lote["SETE"]["estado"] == "a_vencer" and por_lote["SETE"]["dias"] == 7
    assert por_lote["ONTEM"]["saldo"] == "1 L"


def test_use_by_vencido_e_critico_best_before_e_aviso_e_sem_rotulo_e_best_before(
    loja: Loja,
) -> None:
    hoje = date(2026, 10, 14)
    ontem = hoje - timedelta(days=1)
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by")
    farinha = _produto(loja.tenant, "Farinha", expiry_kind="best_before")
    sal = _produto(loja.tenant, "Sal", expiry_kind="")
    for produto, codigo in ((leite, "L"), (farinha, "F"), (sal, "S")):
        _nivel(loja.tenant, produto, loja.loja, "500", lote=_lote(loja.tenant, produto, codigo, validade=ontem))

    dados, _ = _executar(_contexto(loja.tenant, hoje=hoje), "lotes_a_vencer")

    por_nome = {linha["nome"]: linha for linha in dados["linhas"]}
    assert por_nome["Leite"]["gravidade"] == "critico"
    assert por_nome["Leite"]["rotulo"] == "consumir até"
    assert por_nome["Farinha"]["gravidade"] == "aviso"
    assert por_nome["Farinha"]["rotulo"] == "consumir de preferência antes de"
    assert por_nome["Sal"]["gravidade"] == "aviso"
    assert por_nome["Sal"]["rotulo"] == "sem rótulo"
    assert {linha["estado"] for linha in dados["linhas"]} == {"vencido"}


def test_um_lote_sem_saldo_nao_vence_em_lado_nenhum(loja: Loja) -> None:
    hoje = date(2026, 10, 14)
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by")
    vazio = _lote(loja.tenant, leite, "VAZIO", validade=hoje)
    negativo = _lote(loja.tenant, leite, "NEG", validade=hoje)
    cheio = _lote(loja.tenant, leite, "CHEIO", validade=hoje)
    sem_nivel = _lote(loja.tenant, leite, "SEMNIVEL", validade=hoje)
    _nivel(loja.tenant, leite, loja.loja, "0", lote=vazio)
    _nivel(loja.tenant, leite, loja.loja, "-5", lote=negativo)
    _nivel(loja.tenant, leite, loja.loja, "300", lote=cheio)
    _nivel(loja.tenant, leite, loja.armazem, "-300", lote=cheio)
    _nivel(loja.tenant, leite, loja.loja, "100", lote=sem_nivel)
    _nivel(loja.tenant, leite, loja.armazem, "100", lote=sem_nivel)

    dados, _ = _executar(_contexto(loja.tenant, hoje=hoje), "lotes_a_vencer")

    assert [linha["lote"] for linha in dados["linhas"]] == ["SEMNIVEL"], (
        "saldo somado ≤ 0 fica fora: o CHEIO soma zero entre as duas localizações"
    )
    # E `conservation` é dado na linha, não filtro.
    assert dados["linhas"][0]["conservacao"] == "ambient"


def test_lotes_a_vencer_com_localizacao_e_limite_e_truncado(loja: Loja) -> None:
    hoje = date(2026, 10, 14)
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by")
    for i in range(3):
        lote = _lote(loja.tenant, leite, f"L{i}", validade=hoje + timedelta(days=i))
        _nivel(loja.tenant, leite, loja.loja, "100", lote=lote)
    noutra = _lote(loja.tenant, leite, "ARM", validade=hoje)
    _nivel(loja.tenant, leite, loja.armazem, "100", lote=noutra)

    dados, resultado = _executar(
        _contexto(loja.tenant, hoje=hoje), "lotes_a_vencer", location_id=loja.loja.id, limite=2
    )

    assert [linha["lote"] for linha in dados["linhas"]] == ["L0", "L1"]
    assert resultado.truncado is True
    assert dados["localizacao_filtrada"] == str(loja.loja.id)


# ---------------------------------------------------------------------------
# Compras: received_at, NC/ND/GR, IVA, sem receções
# ---------------------------------------------------------------------------
def test_compras_agregam_por_received_at_e_nao_por_doc_date(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    periodo = date(2026, 9, 1), date(2026, 9, 30)
    # Documento datado de setembro, recebido em outubro: fora.
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        doc_date=date(2026, 9, 29),
        received_at=_em_lisboa(date(2026, 10, 2), time(10, 0)),
        linhas=((farinha, "100.00", "confirmed", "goods"),),
    )
    # Documento datado de agosto, recebido em setembro: dentro.
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        doc_date=date(2026, 8, 30),
        received_at=_em_lisboa(date(2026, 9, 1), time(10, 0)),
        linhas=((farinha, "41.20", "confirmed", "goods"),),
    )
    # Recebido no dia 1 de outubro às 02:00: ainda é o dia de negócio 30 de setembro.
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        received_at=_em_lisboa(date(2026, 10, 1), time(2, 0)),
        linhas=((farinha, "10.00", "confirmed", "goods"),),
    )
    # Recebido no dia 1 de setembro às 02:00: dia de negócio 31 de agosto, fora.
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        received_at=_em_lisboa(date(2026, 9, 1), time(2, 0)),
        linhas=((farinha, "999.00", "confirmed", "goods"),),
    )

    dados, _ = _executar(
        _contexto(loja.tenant), "compras_por_periodo", desde=periodo[0], ate=periodo[1]
    )

    assert dados["total_texto"] == "€ 51,20"
    assert dados["documentos"] == 2
    assert dados["iva_incluido"] is False
    assert dados["recebido_entre"]["desde"].startswith("2026-09-01T04:00")
    assert dados["recebido_entre"]["ate"].startswith("2026-10-01T04:00")


def test_nc_subtrai_nd_soma_gr_conta_zero_e_so_linhas_confirmadas_de_mercadoria(
    loja: Loja,
) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    with tenant_scope(loja.tenant.id):
        moagem = Supplier.objects.create(tenant=loja.tenant, name="Moagem", nif="500000001")
    dia = _em_lisboa(date(2026, 9, 10), time(10, 0))
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        received_at=dia,
        fornecedor=moagem,
        linhas=(
            (farinha, "100.00", "confirmed", "goods"),
            (farinha, "50.00", "skipped", "goods"),
            (farinha, "7.00", "confirmed", "deposit"),
            (farinha, "3.00", "confirmed", "charge"),
            (farinha, None, "confirmed", "goods"),
        ),
    )
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="NC",
        received_at=dia,
        fornecedor=moagem,
        linhas=((farinha, "30.00", "confirmed", "goods"),),
    )
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="ND",
        received_at=dia,
        fornecedor=moagem,
        linhas=((farinha, "5.00", "confirmed", "goods"),),
    )
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="GR",
        received_at=dia,
        fornecedor=moagem,
        linhas=((farinha, None, "confirmed", "goods"),),
    )
    # Não confirmada: fora, mesmo com linhas confirmadas.
    _rececao(
        loja.tenant,
        loja.loja,
        doc_type="FT",
        received_at=dia,
        confirmada=False,
        linhas=((farinha, "1000.00", "confirmed", "goods"),),
    )

    dados, _ = _executar(
        _contexto(loja.tenant),
        "compras_por_periodo",
        desde=date(2026, 9, 1),
        ate=date(2026, 9, 30),
    )

    assert dados["total_texto"] == "€ 75,00", "100 − 30 + 5, GR a 0"
    assert dados["documentos"] == 4
    assert dados["documentos_sem_preco"] == 1
    assert dados["linhas_sem_custo"] == 1
    assert dados["por_fornecedor"] == [
        {"supplier_id": str(moagem.id), "nome": "Moagem", "total": "€ 75,00"}
    ]
    assert dados["linhas"][0]["nome"] == "Farinha" and dados["linhas"][0]["total"] == "€ 75,00"
    assert "guias de remessa" in dados["nota"]


def test_um_periodo_sem_rececoes_diz_documentos_zero_e_nunca_gastou_zero(loja: Loja) -> None:
    dados, _ = _executar(
        _contexto(loja.tenant),
        "compras_por_periodo",
        desde=date(2026, 1, 1),
        ate=date(2026, 1, 31),
    )

    assert dados["documentos"] == 0
    assert dados["nota"] == "não há receções confirmadas neste período"
    assert dados["total_texto"] == "€ 0,00"


def test_compras_por_periodo_recusa_periodo_invalido_e_demasiado_longo(loja: Loja) -> None:
    dados, resultado = _executar(
        _contexto(loja.tenant), "compras_por_periodo", desde=date(2026, 2, 1), ate=date(2026, 1, 1)
    )
    assert resultado.ok is False and dados == {"erro": "periodo_invalido"}
    dados, resultado = _executar(
        _contexto(loja.tenant), "compras_por_periodo", desde=date(2024, 1, 1), ate=date(2026, 1, 1)
    )
    assert resultado.ok is False and dados == {"erro": "periodo_demasiado_longo"}


# ---------------------------------------------------------------------------
# Custo
# ---------------------------------------------------------------------------
def test_custo_zero_e_desconhecido_e_estimado_e_estimado(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    _nivel(loja.tenant, farinha, loja.loja, "1000", custo="0")
    _nivel(loja.tenant, farinha, loja.armazem, "2000", custo="0.002")
    _movimento(loja.tenant, farinha, loja.loja, "receipt", "1000", custo="0.002", estimado=True)
    _movimento(loja.tenant, farinha, loja.loja, "receipt", "500", custo="0")

    saldo, _ = _executar(_contexto(loja.tenant), "saldo_de_artigo", product_id=farinha.id)
    movimentos, _ = _executar(_contexto(loja.tenant), "movimentos_de_artigo", product_id=farinha.id)

    sem_custo = next(linha for linha in saldo["linhas"] if linha["localizacao"] == "Loja")
    assert sem_custo["valor_eur"] is None and sem_custo["custo"] == "desconhecido"
    assert saldo["linhas_sem_custo"] == 1
    assert saldo["valor_total_texto"] == "€ 4,00", "só as linhas com custo somam"
    por_custo = {linha["custo"] for linha in movimentos["linhas"]}
    assert por_custo == {"estimado", "desconhecido"}


# ---------------------------------------------------------------------------
# Abaixo do mínimo: SUM por artigo
# ---------------------------------------------------------------------------
def test_o_minimo_compara_com_o_sum_em_todas_as_localizacoes(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", minimo="1000", track_lots=False)
    for local in (loja.loja, loja.armazem, loja.cozinha):
        _nivel(loja.tenant, farinha, local, "400")
    acucar = _produto(loja.tenant, "Açúcar", minimo="1000", track_lots=False)
    _nivel(loja.tenant, acucar, loja.loja, "400")
    _nivel(loja.tenant, acucar, loja.armazem, "400")

    dados, _ = _executar(_contexto(loja.tenant), "artigos_abaixo_do_minimo")

    assert [linha["nome"] for linha in dados["linhas"]] == ["Açúcar"], (
        "3 × 400 g contra 1000 g não alarma; 2 × 400 g alarma"
    )
    linha = dados["linhas"][0]
    assert linha["estado"] == "abaixo_do_minimo" and linha["gravidade"] == "aviso"
    assert linha["saldo"] == "0,8 kg" and linha["minimo"] == "1 kg"

    so_loja, _ = _executar(
        _contexto(loja.tenant), "artigos_abaixo_do_minimo", location_id=loja.loja.id
    )
    assert [linha["nome"] for linha in so_loja["linhas"]] == ["Açúcar", "Farinha"]
    assert "mínimo é do artigo e não da loja" in so_loja["nota"]


def test_sem_stock_e_critico_e_quem_nunca_entrou_fica_fora(loja: Loja) -> None:
    esgotado = _produto(loja.tenant, "Esgotado", minimo="100", track_lots=False)
    _nivel(loja.tenant, esgotado, loja.loja, "0")
    nunca = _produto(loja.tenant, "Nunca entrou", minimo="100", track_lots=False)
    sem_minimo = _produto(loja.tenant, "Sem mínimo", minimo="0", track_lots=False)
    _nivel(loja.tenant, sem_minimo, loja.loja, "0")
    inativo = _produto(loja.tenant, "Inativo", minimo="100", track_lots=False, ativo=False)
    _nivel(loja.tenant, inativo, loja.loja, "0")

    dados, _ = _executar(_contexto(loja.tenant), "artigos_abaixo_do_minimo")

    assert [linha["nome"] for linha in dados["linhas"]] == ["Esgotado"]
    assert dados["linhas"][0]["estado"] == "sem_stock"
    assert dados["linhas"][0]["gravidade"] == "critico"
    assert nunca.id and sem_minimo.id


# ---------------------------------------------------------------------------
# Movimentos: resumo, transferências, truncado, vocabulário
# ---------------------------------------------------------------------------
def test_movimentos_resumo_por_tipo_transferencias_pareadas_e_fora_das_perdas(
    loja: Loja,
) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    agora = timezone.now()
    par = uuid4()
    _movimento(loja.tenant, farinha, loja.loja, "receipt", "10000", quando=agora - timedelta(days=5))
    _movimento(loja.tenant, farinha, loja.loja, "waste", "-500", quando=agora - timedelta(days=4))
    _movimento(loja.tenant, farinha, loja.loja, "waste", "-250", quando=agora - timedelta(days=3))
    _movimento(
        loja.tenant,
        farinha,
        loja.loja,
        "transfer_out",
        "-2000",
        quando=agora - timedelta(days=2),
        transfer_id=par,
    )
    _movimento(
        loja.tenant,
        farinha,
        loja.armazem,
        "transfer_in",
        "2000",
        quando=agora - timedelta(days=2),
        transfer_id=par,
    )
    _movimento(loja.tenant, farinha, loja.loja, "adjustment", "-100", quando=agora - timedelta(days=1))
    _movimento(loja.tenant, farinha, loja.loja, "consumption", "-300", quando=agora - timedelta(days=40))

    dados, resultado = _executar(
        _contexto(loja.tenant), "movimentos_de_artigo", product_id=farinha.id, limite=3
    )

    resumo = dados["resumo"]
    assert resumo["perda"] == {"tipo": "waste", "rotulo": "perda", "n": 2, "quantidade": "-0,75 kg"}
    assert resumo["transferido_saida"]["quantidade"] == "-2 kg"
    assert resumo["transferido_entrada"]["quantidade"] == "2 kg"
    assert resumo["diferenca_de_contagem"]["n"] == 1
    assert "uso" not in resumo, "o consumo de há 40 dias está fora da janela de 30"
    assert resultado.truncado is True, "o `truncado` da fonte sobe para o envelope"
    assert len(dados["linhas"]) == 3 and resultado.linhas == 3
    assert [linha["rotulo"] for linha in dados["linhas"]] == [
        "diferença de contagem",
        "transferido (entrada)",
        "transferido (saída)",
    ]
    assert dados["linhas"][1]["contraparte"] == "Loja"
    assert dados["linhas"][2]["contraparte"] == "Armazém"


def test_movimentos_com_tipos_e_periodo_e_sem_produto(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    _movimento(loja.tenant, farinha, loja.loja, "waste", "-500")
    _movimento(loja.tenant, farinha, loja.loja, "receipt", "5000")

    dados, _ = _executar(
        _contexto(loja.tenant), "movimentos_de_artigo", product_id=farinha.id, tipos=["waste"]
    )
    assert list(dados["resumo"]) == ["perda"]

    dados, resultado = _executar(
        _contexto(loja.tenant), "movimentos_de_artigo", product_id=uuid4()
    )
    assert resultado.ok is False and dados == {"erro": "artigo_nao_encontrado"}


# ---------------------------------------------------------------------------
# Procura
# ---------------------------------------------------------------------------
def test_procura_por_sku_tokens_em_and_inativos_marcados_e_limite(loja: Loja) -> None:
    _produto(loja.tenant, "Farinha T65", sku="FAR65", track_lots=False)
    _produto(loja.tenant, "Farinha T55", sku="FAR55", track_lots=False)
    _produto(loja.tenant, "Farinha antiga", sku="FARX", track_lots=False, ativo=False)
    _produto(loja.tenant, "Açúcar", sku="ACU", track_lots=False)
    contexto = _contexto(loja.tenant)

    por_sku, _ = _executar(contexto, "procurar_artigos", q="far65")
    assert [linha["nome"] for linha in por_sku["linhas"]] == ["Farinha T65"]

    por_tokens, _ = _executar(contexto, "procurar_artigos", q="farinha t55")
    assert [linha["nome"] for linha in por_tokens["linhas"]] == ["Farinha T55"]

    todas, _ = _executar(contexto, "procurar_artigos", q="farinha")
    assert [(linha["nome"], linha["ativo"]) for linha in todas["linhas"]] == [
        ("Farinha T55", True),
        ("Farinha T65", True),
        ("Farinha antiga", False),
    ], "activos primeiro, inactivos marcados"

    nada, _ = _executar(contexto, "procurar_artigos", q="manteiga")
    assert nada["linhas"] == [] and "nenhum artigo" in nada["nota"]

    _, invalido = _executar(contexto, "procurar_artigos", q="farinha", limite=21)
    assert invalido.ok is False
    assert "argumentos_invalidos" in invalido.conteudo

    _, a_mais = _executar(contexto, "procurar_artigos", q="farinha", limite=5, extra="x")
    assert a_mais.ok is False, "um campo a mais é uma recusa (extra=forbid)"


def test_procura_de_fornecedores_por_nome_e_por_nif_exacto(loja: Loja) -> None:
    with tenant_scope(loja.tenant.id):
        Supplier.objects.create(tenant=loja.tenant, name="Moagem do Norte", nif="500000001")
        Supplier.objects.create(tenant=loja.tenant, name="Moagem do Sul", nif="500000002")
    contexto = _contexto(loja.tenant)

    por_nome, _ = _executar(contexto, "procurar_fornecedores", q="moagem norte")
    assert [linha["nome"] for linha in por_nome["linhas"]] == ["Moagem do Norte"]

    por_nif, _ = _executar(contexto, "procurar_fornecedores", q="500000002")
    assert [linha["nome"] for linha in por_nif["linhas"]] == ["Moagem do Sul"]

    meio_nif, _ = _executar(contexto, "procurar_fornecedores", q="50000")
    assert meio_nif["linhas"] == [], "o NIF é exacto, não um prefixo"


# ---------------------------------------------------------------------------
# Não sei: product_id obrigatório, nunca entrou, papel
# ---------------------------------------------------------------------------
def test_saldo_exige_product_id_e_distingue_nunca_entrou(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    contexto = _contexto(loja.tenant)

    _, sem_id = _executar(contexto, "saldo_de_artigo")
    assert sem_id.ok is False and "argumentos_invalidos" in sem_id.conteudo

    nunca, _ = _executar(contexto, "saldo_de_artigo", product_id=farinha.id)
    assert nunca["nunca_entrou"] is True and nunca["linhas"] == []
    assert nunca["total"]["texto"] == "0 kg"

    _nivel(loja.tenant, farinha, loja.loja, "0")
    entrou, _ = _executar(contexto, "saldo_de_artigo", product_id=farinha.id)
    assert entrou["nunca_entrou"] is False and entrou["linhas"] == []
    assert entrou["total"]["texto"] == "0 kg"


SO_EUROS = ("compras_por_periodo", "historico_de_precos")


def test_o_staff_nao_tem_compras_e_o_despachante_recusa(loja: Loja) -> None:
    assert [t.nome for t in tools.tools_para("staff")] == [
        n for n in tools.nomes_das_tools() if n not in SO_EUROS
    ]
    assert [t.nome for t in tools.tools_para("manager")] == list(tools.nomes_das_tools())
    assert [t["function"]["name"] for t in tools.definicoes_para("owner")] == list(
        tools.nomes_das_tools()
    )

    dados, resultado = _executar(
        _contexto(loja.tenant, papel="staff"),
        "compras_por_periodo",
        desde=date(2026, 1, 1),
        ate=date(2026, 1, 2),
    )
    assert resultado.ok is False and dados == {"erro": "tool_nao_disponivel"}

    dados, resultado = _executar(_contexto(loja.tenant), "escrever_movimento", q="x")
    assert resultado.ok is False and dados == {"erro": "tool_nao_disponivel"}


# ---------------------------------------------------------------------------
# O envelope: 8 KB, strings a 120, marcado como dados
# ---------------------------------------------------------------------------
def test_um_resultado_grande_encolhe_ate_8_kb_e_as_strings_cortam_a_120(loja: Loja) -> None:
    hoje = date(2026, 10, 14)
    leite = _produto(loja.tenant, "Leite " + "x" * 70, expiry_kind="use_by")
    for i in range(50):
        lote = _lote(loja.tenant, leite, f"LOTE-{i:02d}-" + "y" * 140, validade=hoje)
        _nivel(loja.tenant, leite, loja.loja, "100", lote=lote)

    dados, resultado = _executar(_contexto(loja.tenant, hoje=hoje), "lotes_a_vencer", limite=50)

    assert len(resultado.conteudo.encode("utf-8")) <= tools.TAMANHO_MAXIMO_DO_RESULTADO
    assert resultado.truncado is True
    assert resultado.linhas == 50, "o rasto conta as linhas lidas, não as que couberam"
    assert 0 < len(dados["linhas"]) < 50
    assert all(len(linha["lote"]) == tools.TEXTO_MAXIMO for linha in dados["linhas"])


def test_os_schemas_das_tools_sao_json_schema_fechado() -> None:
    for tool in tools.REGISTO.values():
        definicao = tool.definicao()
        assert definicao["type"] == "function"
        parametros = definicao["function"]["parameters"]
        assert parametros["type"] == "object"
        assert parametros["additionalProperties"] is False, tool.nome
        assert definicao["function"]["description"]


# ===========================================================================
# ADR 0028 — as doze leituras novas e a ajuda, regra a regra
# ===========================================================================
def _rececao_rica(
    tenant: Tenant,
    local: Location,
    *,
    doc_type: str = "FT",
    received_at: datetime | None = None,
    confirmada: bool = False,
    fornecedor: Supplier | None = None,
    doc_number: str = "",
    total_do_documento: str | None = None,
    chilled: str | None = None,
    frozen: str | None = None,
    confirmada_por: str = "",
    linhas: tuple[dict[str, Any], ...] = (),
) -> Receipt:
    """Uma receção com linhas campo a campo, para medir pendências e preços."""
    quando = received_at or timezone.now()
    with tenant_scope(tenant.id):
        rececao = Receipt.objects.create(
            tenant=tenant,
            supplier=fornecedor,
            doc_type=doc_type,
            doc_number=doc_number,
            received_at=quando,
            location=local,
            confirmed_at=quando if confirmada else None,
            confirmed_by_name=confirmada_por,
            document_total_eur=(
                Decimal(total_do_documento) if total_do_documento is not None else None
            ),
            chilled_temperature_c=Decimal(chilled) if chilled is not None else None,
            frozen_temperature_c=Decimal(frozen) if frozen is not None else None,
        )
        for posicao, linha in enumerate(linhas, start=1):
            campos: dict[str, Any] = {
                "position": posicao,
                "description": linha.get("descricao", ""),
                "kind": linha.get("kind", "goods"),
                "status": linha.get("status", "confirmed"),
                "product": linha.get("produto"),
                "location": local,
                "invoice_unit": linha.get("invoice_unit", ""),
                "lot_code": linha.get("lote", ""),
                "expires_at": linha.get("validade"),
            }
            for nome in (
                "quantity_invoiced",
                "base_per_invoice_unit",
                "unit_price",
                "line_total",
            ):
                if linha.get(nome) is not None:
                    campos[nome] = Decimal(linha[nome])
            campos["quantity_received"] = Decimal(linha.get("quantity_received", "1"))
            ReceiptLine.objects.create(tenant=tenant, receipt=rececao, **campos)
    return rececao


# ---------------------------------------------------------------------------
# Receções: o que é "por rever", o dia de negócio, as pendências, os euros
# ---------------------------------------------------------------------------
def test_por_rever_e_confirmed_at_nulo_e_nao_tem_linhas_por_rever(loja: Loja) -> None:
    """A pendência de uma linha e a de um documento são coisas diferentes.

    Um documento confirmado com uma linha `needs_review` já entrou no stock; um
    documento por confirmar com todas as linhas revistas **não** entrou. "Por
    rever" é a segunda coisa, e é `confirmed_at IS NULL`.
    """
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    confirmada = _rececao_rica(
        loja.tenant,
        loja.loja,
        confirmada=True,
        linhas=({"produto": farinha, "status": "needs_review", "line_total": "10.00"},),
    )
    aberta = _rececao_rica(
        loja.tenant,
        loja.loja,
        confirmada=False,
        linhas=({"produto": farinha, "status": "confirmed", "line_total": "10.00"},),
    )

    dados, _ = _executar(_contexto(loja.tenant), "rececoes", estado="por_rever")

    assert [linha["rececao_id"] for linha in dados["linhas"]] == [str(aberta.id)]
    assert dados["linhas"][0]["estado"] == "por_rever"
    assert "nada destas linhas entrou no stock" in dados["nota"]
    assert confirmada.id


def test_rececoes_de_hoje_sao_o_dia_de_negocio_e_nao_a_meia_noite(loja: Loja) -> None:
    """A mesma fronteira que o `RececaoViewSet.list(estado=hoje)` passou a usar.

    O que se afirma não é um número escolhido aqui: é que a tool devolve
    exactamente as receções confirmadas a partir do `inicio_do_dia_de_negocio`
    do módulo — o selector partilhado. Até 2026-10-16 a view filtrava desde a
    meia-noite e o rótulo prometia o dia de negócio.
    """
    from apps.purchasing.selectors import inicio_do_dia_de_negocio

    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    agora = _em_lisboa(date(2026, 10, 15), time(10, 0))
    de_madrugada = _rececao_rica(
        loja.tenant,
        loja.loja,
        confirmada=True,
        received_at=_em_lisboa(date(2026, 10, 15), time(1, 0)),
        linhas=({"produto": farinha, "line_total": "10.00"},),
    )
    depois_de_abrir = _rececao_rica(
        loja.tenant,
        loja.loja,
        confirmada=True,
        received_at=_em_lisboa(date(2026, 10, 15), time(5, 0)),
        linhas=({"produto": farinha, "line_total": "20.00"},),
    )

    contexto = _contexto(loja.tenant, agora=agora)
    dados, _ = _executar(contexto, "rececoes", estado="hoje")

    with tenant_scope(loja.tenant.id):
        fronteira = inicio_do_dia_de_negocio(tenant_id=loja.tenant.id, agora=agora)
        esperadas = {
            str(r.id)
            for r in Receipt.objects.filter(confirmed_at__gte=fronteira)
        }
    assert {linha["rececao_id"] for linha in dados["linhas"]} == esperadas
    assert [linha["rececao_id"] for linha in dados["linhas"]] == [str(depois_de_abrir.id)]
    assert de_madrugada.id


def test_as_pendencias_de_uma_rececao_sao_derivadas_e_a_skipped_nao_conta(
    loja: Loja,
) -> None:
    sem_nada = _produto(loja.tenant, "Desconhecido", track_lots=False)
    com_lote = _produto(loja.tenant, "Leite", expiry_kind="use_by", track_lots=True)
    with tenant_scope(loja.tenant.id):
        com_lote.conservation = "chilled"
        com_lote.save(update_fields=["conservation"])
    rececao = _rececao_rica(
        loja.tenant,
        loja.loja,
        linhas=(
            {"produto": None, "descricao": "ARTIGO NOVO", "status": "needs_review"},
            {"produto": com_lote, "status": "needs_review"},
            {"produto": sem_nada, "status": "skipped"},
        ),
    )

    dados, _ = _executar(_contexto(loja.tenant), "rececao", id=rececao.id)

    pendencias = dados["pendencias"]
    assert pendencias["sem_artigo"] == 1
    assert pendencias["sem_lote"] == 1
    assert pendencias["sem_validade"] == 1
    assert pendencias["temperaturas_em_falta"] == ["refrigerado"]
    assert pendencias["total"] == 4
    assert dados["linhas_por_estado"] == {"por rever": 2, "de fora": 1}
    assert [linha["estado"] for linha in dados["linhas"]] == [
        "por rever",
        "por rever",
        "de fora",
    ]
    assert dados["linhas"][0]["ligada_a_artigo"] is False


def test_uma_rececao_so_de_ambiente_nunca_pede_temperatura(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    rececao = _rececao_rica(
        loja.tenant, loja.loja, linhas=({"produto": farinha, "line_total": "10.00"},)
    )

    dados, _ = _executar(_contexto(loja.tenant), "rececao", id=rececao.id)

    assert dados["pendencias"]["temperaturas_em_falta"] == []
    assert dados["pendencias"]["total"] == 0


def test_o_staff_nao_ve_euros_no_saldo_nem_nos_movimentos(loja: Loja) -> None:
    """As duas tools da ADR 0027 estavam fora da regra dos euros (2026-10-16).

    `saldo_de_artigo` devolvia `valor_total_eur` e o valor de cada lote, e
    `movimentos_de_artigo` o custo de cada linha, a quem o prompt promete que
    não os vê. O total continua certo para quem os vê: soma-se por inteiro e
    filtra-se à saída.
    """
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    _nivel(loja.tenant, farinha, loja.armazem, "10000", custo="0.0015")
    _movimento(loja.tenant, farinha, loja.armazem, "receipt", "10000", custo="0.0015")

    para_staff, _ = _executar(
        _contexto(loja.tenant, papel="staff"), "saldo_de_artigo", product_id=farinha.id
    )
    assert "valor_total_texto" not in para_staff
    assert para_staff["euros_visiveis"] is False
    for linha in para_staff["linhas"]:
        assert "valor_eur" not in linha and "valor_texto" not in linha

    para_dono, _ = _executar(
        _contexto(loja.tenant, papel="owner"), "saldo_de_artigo", product_id=farinha.id
    )
    assert para_dono["valor_total_texto"] == "€ 15,00"

    movimentos_staff, _ = _executar(
        _contexto(loja.tenant, papel="staff"), "movimentos_de_artigo", product_id=farinha.id
    )
    for linha in movimentos_staff["linhas"]:
        assert "valor_eur" not in linha and "valor_texto" not in linha
        assert linha["custo"] == "conhecido"

    movimentos_dono, _ = _executar(
        _contexto(loja.tenant, papel="owner"), "movimentos_de_artigo", product_id=farinha.id
    )
    assert movimentos_dono["linhas"][0]["valor_texto"] == "€ 15,00"


def test_o_email_de_quem_assinou_um_movimento_nao_sai_a_quem_nao_e_dono(loja: Loja) -> None:
    """`created_by_name` antigo é um email: o `movimentos_de_artigo` mostrava-o."""
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    # Gravado com o email, como o `inventory/services.py` fazia até 2026-10-16;
    # a tabela é append-only, logo escreve-se assim e não por `update`.
    _movimento(
        loja.tenant, farinha, loja.armazem, "receipt", "1000", custo="0.001", por="ana@exemplo.pt"
    )

    for papel in ("staff", "manager"):
        resultado, _ = _executar(
            _contexto(loja.tenant, papel=papel), "movimentos_de_artigo", product_id=farinha.id
        )
        assert "@" not in (resultado["linhas"][0]["por"] or "")

    do_dono, _ = _executar(
        _contexto(loja.tenant, papel="owner"), "movimentos_de_artigo", product_id=farinha.id
    )
    assert do_dono["linhas"][0]["por"] == "ana@exemplo.pt"


def test_o_staff_nao_ve_precos_de_uma_rececao_e_o_nif_nunca_sai(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    with tenant_scope(loja.tenant.id):
        makro = Supplier.objects.create(tenant=loja.tenant, name="Makro", nif="500123456")
    rececao = _rececao_rica(
        loja.tenant,
        loja.loja,
        fornecedor=makro,
        confirmada=True,
        total_do_documento="123.45",
        linhas=(
            {
                "produto": farinha,
                "unit_price": "0.0008",
                "line_total": "41.20",
                "quantity_received": "25000",
            },
        ),
    )

    do_dono, dono_bruto = _executar(_contexto(loja.tenant), "rececao", id=rececao.id)
    do_staff, staff_bruto = _executar(
        _contexto(loja.tenant, papel="staff"), "rececao", id=rececao.id
    )

    assert do_dono["total_do_documento"] == "€ 123,45"
    assert do_dono["linhas"][0]["preco_unitario"] == "€ 0,00"
    assert do_dono["linhas"][0]["total_da_linha"] == "€ 41,20"
    assert do_dono["euros_visiveis"] is True

    assert "total_do_documento" not in do_staff
    assert "preco_unitario" not in do_staff["linhas"][0]
    assert "total_da_linha" not in do_staff["linhas"][0]
    assert do_staff["euros_visiveis"] is False
    assert do_staff["linhas"][0]["recebido"] == "25 kg", "a quantidade continua lá"

    for conteudo in (dono_bruto.conteudo, staff_bruto.conteudo):
        assert "500123456" not in conteudo, "um NIF não é resposta de assistente"
        assert "nif" not in conteudo.lower()


def test_uma_rececao_de_outro_estabelecimento_nao_existe(loja: Loja) -> None:
    dados, resultado = _executar(_contexto(loja.tenant), "rececao", id=uuid4())
    assert resultado.ok is False and dados == {"erro": "rececao_nao_encontrada"}


# ---------------------------------------------------------------------------
# Histórico de preços: quantidade faturada, GR fora, notas contadas, ponderada
# ---------------------------------------------------------------------------
def test_o_preco_e_pela_quantidade_faturada_e_nao_pela_recebida(loja: Loja) -> None:
    """Numa receção parcial o que se pagou foi o que veio na fatura.

    Dez sacos faturados a 8,00 € dão 0,80 €/kg. Com a quantidade **recebida**
    (cinco sacos) davam 1,60 €/kg — o quilo a dobrar por causa de uma falta.
    """
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    with tenant_scope(loja.tenant.id):
        makro = Supplier.objects.create(tenant=loja.tenant, name="Makro", nif="500123456")
    _rececao_rica(
        loja.tenant,
        loja.loja,
        fornecedor=makro,
        confirmada=True,
        received_at=_em_lisboa(date(2026, 10, 10), time(9, 0)),
        linhas=(
            {
                "produto": farinha,
                "invoice_unit": "saco",
                "quantity_invoiced": "10",
                "base_per_invoice_unit": "1000",
                "line_total": "8.00",
                "quantity_received": "5000",
            },
        ),
    )

    dados, _ = _executar(
        _contexto(loja.tenant, agora=_em_lisboa(date(2026, 10, 15), time(10, 0))),
        "historico_de_precos",
        product_id=farinha.id,
    )

    assert dados["ultimo"] == "€ 0,80 / kg"
    assert dados["preco_por"] == "kg" and dados["iva_incluido"] is False
    assert dados["linhas"][0]["media"] == "€ 0,80 / kg"


def test_a_media_do_mes_e_ponderada_pela_quantidade_e_nao_a_media_dos_precos(
    loja: Loja,
) -> None:
    """Três sacos a 0,80 e um a 1,20 custaram 0,90 — não 1,00."""
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    with tenant_scope(loja.tenant.id):
        makro = Supplier.objects.create(tenant=loja.tenant, name="Makro", nif="500123456")
    for quantidade, total, dia in (("3", "2.40", 5), ("1", "1.20", 6)):
        _rececao_rica(
            loja.tenant,
            loja.loja,
            fornecedor=makro,
            confirmada=True,
            received_at=_em_lisboa(date(2026, 10, dia), time(9, 0)),
            linhas=(
                {
                    "produto": farinha,
                    "invoice_unit": "saco",
                    "quantity_invoiced": quantidade,
                    "base_per_invoice_unit": "1000",
                    "line_total": total,
                    "quantity_received": Decimal(quantidade) * 1000,
                },
            ),
        )

    dados, _ = _executar(
        _contexto(loja.tenant, agora=_em_lisboa(date(2026, 10, 15), time(10, 0))),
        "historico_de_precos",
        product_id=farinha.id,
    )

    assert len(dados["linhas"]) == 1, "mesmo fornecedor, mesmo mês de negócio"
    linha = dados["linhas"][0]
    assert linha["media"] == "€ 0,90 / kg", "ponderada; a média dos preços dava 1,00"
    assert linha["minimo"] == "€ 0,80 / kg" and linha["maximo"] == "€ 1,20 / kg"
    assert linha["compras"] == 2
    assert dados["ultimo"] == "€ 1,20 / kg" and dados["anterior"] == "€ 0,80 / kg"
    assert dados["variacao"] == "+50,0 %"
    assert "ponderada pela quantidade" in dados["nota"]


def test_a_guia_de_remessa_fica_fora_e_as_notas_ficam_contadas(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    with tenant_scope(loja.tenant.id):
        makro = Supplier.objects.create(tenant=loja.tenant, name="Makro", nif="500123456")
    comum = {
        "produto": farinha,
        "invoice_unit": "saco",
        "quantity_invoiced": "1",
        "base_per_invoice_unit": "1000",
        "quantity_received": "1000",
    }
    for doc_type, total in (("FT", "0.80"), ("GR", "99.00"), ("NC", "5.00"), ("ND", "3.00")):
        _rececao_rica(
            loja.tenant,
            loja.loja,
            doc_type=doc_type,
            fornecedor=makro,
            confirmada=True,
            received_at=_em_lisboa(date(2026, 10, 10), time(9, 0)),
            linhas=({**comum, "line_total": total},),
        )

    dados, _ = _executar(
        _contexto(loja.tenant, agora=_em_lisboa(date(2026, 10, 15), time(10, 0))),
        "historico_de_precos",
        product_id=farinha.id,
    )

    assert dados["linhas"][0]["compras"] == 1, "só a fatura"
    assert dados["ultimo"] == "€ 0,80 / kg"
    assert dados["notas_ignoradas"] == 2, "a NC e a ND contam-se, não se escondem"
    assert "crédito ou débito" in dados["nota_das_notas"]


def test_o_historico_de_precos_nao_e_oferecido_a_um_colaborador(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    dados, resultado = _executar(
        _contexto(loja.tenant, papel="staff"), "historico_de_precos", product_id=farinha.id
    )
    assert resultado.ok is False and dados == {"erro": "tool_nao_disponivel"}
    assert "historico_de_precos" not in [t.nome for t in tools.tools_para("staff")]


# ---------------------------------------------------------------------------
# Contagens: a diferença com sinal, o custo do lote certo, o fecho pelo ledger
# ---------------------------------------------------------------------------
def _contagem_de_stock(
    tenant: Tenant,
    local: Location,
    *,
    estado: str = "open",
    linhas: tuple[dict[str, Any], ...] = (),
) -> StockCount:
    with tenant_scope(tenant.id):
        contagem = StockCount.objects.create(tenant=tenant, location=local, status=estado)
        if estado == "closed":
            StockCount.objects.filter(pk=contagem.id).update(closed_at=timezone.now())
            contagem.refresh_from_db()
        for linha in linhas:
            StockCountLine.objects.create(
                tenant=tenant,
                stock_count=contagem,
                product=linha["produto"],
                lot=linha.get("lote"),
                zone=linha.get("zona"),
                quantity_expected=Decimal(linha["esperado"]),
                quantity_counted=(
                    Decimal(linha["contado"]) if linha.get("contado") is not None else None
                ),
            )
    return contagem


def test_a_diferenca_de_contagem_tem_sinal_e_o_euro_e_o_do_lote_contado(
    loja: Loja,
) -> None:
    """O custo é o do `(artigo, localização, **lote**)`, e é a correcção da 0028.

    Com dois lotes do mesmo artigo na mesma localização, a valorização sem o
    lote apanhava o custo do outro — em silêncio, e sempre pelo lote que a base
    devolvesse primeiro.
    """
    farinha = _produto(loja.tenant, "Farinha", track_lots=True)
    barato = _lote(loja.tenant, farinha, "BARATO", validade=None)
    caro = _lote(loja.tenant, farinha, "CARO", validade=None)
    _nivel(loja.tenant, farinha, loja.loja, "1000", lote=barato, custo="0.001")
    _nivel(loja.tenant, farinha, loja.loja, "1000", lote=caro, custo="0.005")
    contagem = _contagem_de_stock(
        loja.tenant,
        loja.loja,
        linhas=(
            {"produto": farinha, "lote": caro, "esperado": "1000", "contado": "800"},
            {"produto": farinha, "lote": barato, "esperado": "1000", "contado": "1000"},
        ),
    )

    dados, _ = _executar(_contexto(loja.tenant), "contagem", id=contagem.id)

    por_lote = {linha["lote"]: linha for linha in dados["linhas"]}
    assert por_lote["CARO"]["diferenca"] == {"texto": "−0,2 kg, falta", "sentido": "falta"}
    assert por_lote["CARO"]["valor_da_diferenca"] == "€ 1,00", (
        "200 g × 0,005 €/g do lote CARO; com o do BARATO dava € 0,20"
    )
    assert por_lote["BARATO"]["diferenca"]["sentido"] == "confere"
    assert por_lote["BARATO"]["valor_da_diferenca"] == "€ 0,00", (
        "uma linha que confere vale zero euros, e isso é um facto, não um número parcial"
    )
    assert dados["ajustes"]["n"] == 0
    assert "ainda não mexeu no stock" in dados["nota"]


def test_uma_contagem_fechada_vale_o_que_o_ajuste_gravou(loja: Loja) -> None:
    """O número que a resposta dá é o do ledger, não o custo de hoje (ADR 0014)."""
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    _nivel(loja.tenant, farinha, loja.loja, "800", custo="0.009")
    contagem = _contagem_de_stock(
        loja.tenant,
        loja.loja,
        estado="closed",
        linhas=({"produto": farinha, "esperado": "1000", "contado": "800"},),
    )
    with tenant_scope(loja.tenant.id):
        StockMovement.objects.create(
            tenant=loja.tenant,
            product=farinha,
            location=loja.loja,
            movement_type="adjustment",
            quantity=Decimal("-200"),
            unit_cost=Decimal("0.004"),
            occurred_at=timezone.now(),
            reference=str(contagem.id),
            created_by_name="Ana",
        )

    dados, _ = _executar(_contexto(loja.tenant), "contagem", id=contagem.id)

    assert dados["estado"] == "fechada"
    assert dados["ajustes"]["n"] == 1
    assert dados["ajustes"]["valor"] == "€ 0,80", "200 g × 0,004 €/g do movimento"
    assert dados["linhas"][0]["valor_da_diferenca"] == "€ 1,80", (
        "a linha mostra o custo actual do nível; o fecho é o do ledger"
    )
    assert "ajustes gravados no ledger" in dados["nota"]


def test_um_colaborador_ve_a_diferenca_e_nao_o_valor(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    _nivel(loja.tenant, farinha, loja.loja, "800", custo="0.005")
    contagem = _contagem_de_stock(
        loja.tenant,
        loja.loja,
        linhas=({"produto": farinha, "esperado": "1000", "contado": "800"},),
    )

    dados, _ = _executar(
        _contexto(loja.tenant, papel="staff"), "contagem", id=contagem.id
    )

    assert dados["linhas"][0]["diferenca"]["texto"] == "−0,2 kg, falta"
    assert "valor_da_diferenca" not in dados["linhas"][0]
    assert "valor" not in dados["ajustes"]
    assert dados["euros_visiveis"] is False


def test_por_contar_nao_e_zero_e_as_contagens_listam_se_por_estado(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    aberta = _contagem_de_stock(
        loja.tenant,
        loja.loja,
        linhas=(
            {"produto": farinha, "esperado": "1000", "contado": None, "zona": "frio"},
            {"produto": farinha, "esperado": "500", "contado": "0"},
        ),
    )
    fechada = _contagem_de_stock(
        loja.tenant,
        loja.armazem,
        estado="closed",
        linhas=({"produto": farinha, "esperado": "100", "contado": "100"},),
    )

    abertas, _ = _executar(_contexto(loja.tenant), "contagens", estado="abertas")
    fechadas, _ = _executar(_contexto(loja.tenant), "contagens", estado="fechadas")
    detalhe, _ = _executar(_contexto(loja.tenant), "contagem", id=aberta.id)

    assert [linha["contagem_id"] for linha in abertas["linhas"]] == [str(aberta.id)]
    assert abertas["linhas"][0]["n_por_contar"] == 1
    assert abertas["linhas"][0]["n_contadas"] == 1
    assert [linha["contagem_id"] for linha in fechadas["linhas"]] == [str(fechada.id)]
    por_estado = {linha["estado"] for linha in detalhe["linhas"]}
    assert por_estado == {"por_contar", "contada"}
    por_contar = next(
        linha for linha in detalhe["linhas"] if linha["estado"] == "por_contar"
    )
    assert por_contar["contado"] is None and por_contar["zona"] == "frio"
    contada = next(linha for linha in detalhe["linhas"] if linha["estado"] == "contada")
    assert contada["contado"] == "0 kg" and contada["diferenca"]["sentido"] == "falta"


def test_uma_contagem_de_outro_estabelecimento_nao_existe(loja: Loja) -> None:
    dados, resultado = _executar(_contexto(loja.tenant), "contagem", id=uuid4())
    assert resultado.ok is False and dados == {"erro": "contagem_nao_encontrada"}


# ---------------------------------------------------------------------------
# Alertas: validade em calendário civil, lote sem saldo fora, desperdício do dia
# ---------------------------------------------------------------------------
def test_a_uma_da_manha_do_dia_seguinte_o_lote_ja_esta_vencido(loja: Loja) -> None:
    """A validade é a data da embalagem e não se desloca pelo relógio do negócio.

    À 01:00 do dia 15 o dia de **negócio** ainda é 14 — e até 2026-10-16 era
    por ele que as validades se mediam, logo um lote com validade a 14 lia-se
    "vence hoje" quando a ASAE já o considerava expirado.
    """
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by", display_unit="L")
    lote = _lote(loja.tenant, leite, "L1", validade=date(2026, 10, 14))
    _nivel(loja.tenant, leite, loja.loja, "1000", lote=lote)
    contexto = _contexto(loja.tenant, agora=_em_lisboa(date(2026, 10, 15), time(1, 0)))

    assert contexto.hoje == date(2026, 10, 14), "o dia de negócio ainda é ontem"
    assert contexto.hoje_civil == date(2026, 10, 15)

    validades, _ = _executar(contexto, "lotes_a_vencer")
    alertas, _ = _executar(contexto, "alertas", tipo="validade")

    assert validades["linhas"][0]["estado"] == "vencido"
    assert validades["linhas"][0]["dias"] == -1
    assert alertas["hoje"] == "2026-10-15"
    assert alertas["linhas"][0]["estado"] == "vencido"
    assert alertas["linhas"][0]["gravidade"] == "critico"


def test_um_lote_sem_saldo_nao_entra_nos_alertas(loja: Loja) -> None:
    hoje = date(2026, 10, 14)
    leite = _produto(loja.tenant, "Leite", expiry_kind="use_by")
    vazio = _lote(loja.tenant, leite, "VAZIO", validade=hoje)
    cheio = _lote(loja.tenant, leite, "CHEIO", validade=hoje)
    _nivel(loja.tenant, leite, loja.loja, "0", lote=vazio)
    _nivel(loja.tenant, leite, loja.loja, "500", lote=cheio)

    dados, _ = _executar(
        _contexto(loja.tenant, hoje=hoje, hoje_civil=hoje), "alertas", tipo="validade"
    )

    assert [linha["lote"] for linha in dados["linhas"]] == ["CHEIO"]


def test_o_desperdicio_dos_alertas_e_so_waste_e_so_do_dia_de_negocio(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    hoje = date(2026, 10, 14)
    # Dentro: o dia de negócio 14 vai das 04:00 do dia 14 às 04:00 do dia 15.
    _movimento(
        loja.tenant,
        farinha,
        loja.loja,
        "waste",
        "-500",
        quando=_em_lisboa(hoje, time(5, 0)),
        custo="0.002",
    )
    _movimento(
        loja.tenant,
        farinha,
        loja.loja,
        "waste",
        "-250",
        quando=_em_lisboa(hoje + timedelta(days=1), time(1, 0)),
        custo="0.002",
    )
    # Fora: ontem, e um consumo de hoje que não é perda.
    _movimento(
        loja.tenant,
        farinha,
        loja.loja,
        "waste",
        "-9000",
        quando=_em_lisboa(hoje - timedelta(days=1), time(10, 0)),
        custo="0.002",
    )
    _movimento(
        loja.tenant,
        farinha,
        loja.loja,
        "consumption",
        "-9000",
        quando=_em_lisboa(hoje, time(10, 0)),
        custo="0.002",
    )

    dados, _ = _executar(
        _contexto(loja.tenant, hoje=hoje, hoje_civil=hoje), "alertas", tipo="desperdicio"
    )

    desperdicio = dados["desperdicio"]
    assert desperdicio["dia_de_negocio"] == "2026-10-14"
    assert desperdicio["desde"].startswith("2026-10-14T04:00")
    assert desperdicio["ate"].startswith("2026-10-15T04:00")
    assert len(desperdicio["itens"]) == 1
    assert desperdicio["itens"][0]["quantidade"] == "0,75 kg", "positiva: perdeu-se"
    assert desperdicio["itens"][0]["valor"] == "€ 1,50"
    assert desperdicio["total"] == "€ 1,50"

    do_staff, _ = _executar(
        _contexto(loja.tenant, hoje=hoje, hoje_civil=hoje, papel="staff"),
        "alertas",
        tipo="desperdicio",
    )
    assert "valor" not in do_staff["desperdicio"]["itens"][0]
    assert do_staff["desperdicio"]["itens"][0]["quantidade"] == "0,75 kg"


def test_os_alertas_sem_nada_dizem_que_nao_ha_e_nunca_um_numero(loja: Loja) -> None:
    dados, _ = _executar(_contexto(loja.tenant), "alertas")
    assert dados["linhas"] == [] and dados["nota"] == "não há alertas abertos"


# ---------------------------------------------------------------------------
# Artigo, receitas e produções
# ---------------------------------------------------------------------------
def _ficha(
    tenant: Tenant,
    acabado: Product,
    *,
    yield_factor: str = "1",
    ativa: bool = True,
    ingredientes: tuple[tuple[Product, str], ...] = (),
) -> Recipe:
    with tenant_scope(tenant.id):
        receita = Recipe.objects.create(
            tenant=tenant,
            product=acabado,
            is_active=ativa,
            yield_factor=Decimal(yield_factor),
        )
        for ingrediente, quantidade in ingredientes:
            RecipeLineItem.objects.create(
                tenant=tenant,
                recipe=receita,
                ingredient_product=ingrediente,
                quantity_per_base_unit=Decimal(quantidade),
            )
    return receita


def _producao(
    tenant: Tenant,
    local: Location,
    *,
    acabado: Product,
    quantidade: str,
    custo: str,
    por: str,
    ingredientes: tuple[tuple[Product, str], ...] = (),
    quando: datetime | None = None,
) -> UUID:
    producao_id = uuid4()
    instante = quando or timezone.now()
    with tenant_scope(tenant.id):
        for ingrediente, saiu in ingredientes:
            StockMovement.objects.create(
                tenant=tenant,
                product=ingrediente,
                location=local,
                movement_type="production_out",
                quantity=Decimal(saiu),
                unit_cost=Decimal("0"),
                occurred_at=instante,
                production_id=producao_id,
                created_by_name=por,
            )
        StockMovement.objects.create(
            tenant=tenant,
            product=acabado,
            location=local,
            movement_type="production_in",
            quantity=Decimal(quantidade),
            unit_cost=Decimal(custo),
            occurred_at=instante,
            production_id=producao_id,
            created_by_name=por,
        )
    return producao_id


def test_a_ficha_e_por_apresentacao_do_acabado_e_o_consumo_real_divide_pelo_rendimento(
    loja: Loja,
) -> None:
    """Dois números diferentes, e a confusão entre eles é o erro clássico.

    A lista escreve 0,9 kg de farinha por quilo de massa; com 80 % de
    rendimento, o que sai do stock para um quilo de massa sair é 1,125 kg.
    """
    massa = _produto(loja.tenant, "Massa", track_lots=False)
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    receita = _ficha(
        loja.tenant, massa, yield_factor="0.8", ingredientes=((farinha, "0.9"),)
    )

    dados, _ = _executar(_contexto(loja.tenant), "receita", id=receita.id)

    assert dados["por"] == "1 kg de Massa"
    assert dados["rendimento"] == "80 %"
    assert dados["linhas"][0]["na_lista"] == "0,9 kg"
    assert dados["linhas"][0]["consumo_real"] == "1,125 kg"
    assert "a dividir pelo rendimento" in dados["nota"]


def test_o_custo_da_receita_e_so_de_quem_ve_euros(loja: Loja) -> None:
    massa = _produto(loja.tenant, "Massa", track_lots=False)
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    receita = _ficha(loja.tenant, massa, ingredientes=((farinha, "0.5"),))
    with tenant_scope(loja.tenant.id):
        ProductCost.objects.create(
            tenant=loja.tenant,
            product=farinha,
            location=loja.loja,
            unit_cost=Decimal("0.002"),
        )

    do_dono, _ = _executar(_contexto(loja.tenant), "receita", id=receita.id)
    do_staff, _ = _executar(
        _contexto(loja.tenant, papel="staff"), "receita", id=receita.id
    )

    assert do_dono["custos"][0]["custo_teorico"] == "€ 1,00", "0,5 g/g × 0,002 €/g × 1000"
    assert do_dono["euros_visiveis"] is True
    assert do_staff["custos"] == [] and do_staff["euros_visiveis"] is False
    assert do_staff["linhas"][0]["na_lista"] == "0,5 kg", "a ficha técnica é de todos"


def test_que_receitas_usam_farinha_responde_se_pelo_ingrediente(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    acucar = _produto(loja.tenant, "Açúcar", track_lots=False)
    pao = _produto(loja.tenant, "Pão", track_lots=False)
    bolo = _produto(loja.tenant, "Bolo", track_lots=False)
    gelado = _produto(loja.tenant, "Gelado", track_lots=False)
    _ficha(loja.tenant, pao, ingredientes=((farinha, "0.6"),))
    _ficha(loja.tenant, bolo, ingredientes=((farinha, "0.3"), (acucar, "0.2")))
    _ficha(loja.tenant, gelado, ingredientes=((acucar, "0.4"),))
    antiga = _ficha(
        loja.tenant, _produto(loja.tenant, "Broa", track_lots=False),
        ativa=False,
        ingredientes=((farinha, "0.9"),),
    )
    contexto = _contexto(loja.tenant)

    com_farinha, _ = _executar(contexto, "receitas", ingrediente_id=farinha.id)
    com_inativas, _ = _executar(
        contexto, "receitas", ingrediente_id=farinha.id, incluir_inativas=True
    )
    por_nome, _ = _executar(contexto, "receitas", q="bolo")

    assert sorted(linha["artigo"] for linha in com_farinha["linhas"]) == ["Bolo", "Pão"]
    assert sorted(linha["artigo"] for linha in com_inativas["linhas"]) == [
        "Bolo",
        "Broa",
        "Pão",
    ]
    assert {linha["artigo"]: linha["ativa"] for linha in com_inativas["linhas"]}["Broa"] is False
    assert [linha["artigo"] for linha in por_nome["linhas"]] == ["Bolo"]
    assert antiga.id


def test_a_ficha_do_artigo_junta_embalagens_codigos_e_receitas(loja: Loja) -> None:
    farinha = _produto(loja.tenant, "Farinha T65", sku="FAR65", minimo="20000")
    pao = _produto(loja.tenant, "Pão", track_lots=False)
    _ficha(loja.tenant, pao, ingredientes=((farinha, "0.6"),))
    with tenant_scope(loja.tenant.id):
        makro = Supplier.objects.create(tenant=loja.tenant, name="Makro", nif="500123456")
        ProductPackaging.objects.create(
            tenant=loja.tenant,
            product=farinha,
            label="Saco de 25 kg",
            base_quantity=Decimal("25000"),
        )
        SupplierProductCode.objects.create(
            tenant=loja.tenant,
            supplier=makro,
            product=farinha,
            code="7734",
            description_raw="FARINHA T65 SACO 25KG",
            learned_at=timezone.now(),
        )
        ProductCost.objects.create(
            tenant=loja.tenant,
            product=farinha,
            location=loja.loja,
            unit_cost=Decimal("0.0008"),
        )
    _nivel(loja.tenant, farinha, loja.loja, "12500", custo="0.0008")

    dados, bruto = _executar(_contexto(loja.tenant), "artigo", id=farinha.id)

    assert dados["artigo"]["nome"] == "Farinha T65"
    assert dados["unidades"] == "conta-se em g, mostra-se em kg; 1 kg = 1000 g"
    assert dados["minimo"] == "20 kg" and dados["saldo_total"] == "12,5 kg"
    assert dados["embalagens"] == [
        {"rotulo": "Saco de 25 kg", "contem": "25 kg", "ean": None}
    ]
    assert dados["codigos_de_fornecedor"] == [
        {
            "fornecedor": "Makro",
            "codigo": "7734",
            "descricao_na_fatura": "FARINHA T65 SACO 25KG",
        }
    ]
    assert dados["usado_em_receitas"] == 1
    assert dados["e_produzido_por_receita"] is None
    assert dados["custo_medio_por_localizacao"][0]["custo_medio"] == "€ 0,00"
    assert "500123456" not in bruto.conteudo

    do_staff, _ = _executar(_contexto(loja.tenant, papel="staff"), "artigo", id=farinha.id)
    assert "custo_medio" not in do_staff["custo_medio_por_localizacao"][0]
    assert do_staff["saldo_total"] == "12,5 kg"


def test_producoes_recentes_nao_mostram_o_email_de_quem_produziu_a_um_colaborador(
    loja: Loja,
) -> None:
    """`created_by_name` de linhas antigas é o email: só o dono o vê (ADR 0028)."""
    massa = _produto(loja.tenant, "Massa", track_lots=False)
    farinha = _produto(loja.tenant, "Farinha", track_lots=False)
    hoje = date(2026, 10, 14)
    _producao(
        loja.tenant,
        loja.loja,
        acabado=massa,
        quantidade="2000",
        custo="0.003",
        por="ana@alfa.pt",
        ingredientes=((farinha, "-1800"),),
        quando=_em_lisboa(hoje, time(9, 0)),
    )
    # Fora da janela: há oito dias de negócio.
    _producao(
        loja.tenant,
        loja.loja,
        acabado=massa,
        quantidade="99000",
        custo="0.003",
        por="ana@alfa.pt",
        quando=_em_lisboa(hoje - timedelta(days=8), time(9, 0)),
    )

    do_dono, _ = _executar(
        _contexto(loja.tenant, hoje=hoje), "producoes_recentes", dias=7
    )
    do_staff, _ = _executar(
        _contexto(loja.tenant, hoje=hoje, papel="staff"), "producoes_recentes", dias=7
    )

    assert len(do_dono["linhas"]) == 1
    assert do_dono["linhas"][0]["por"] == "ana@alfa.pt"
    assert do_dono["linhas"][0]["produzido"] == "2 kg"
    assert do_dono["linhas"][0]["custo_total"] == "€ 6,00"
    assert do_dono["linhas"][0]["ingredientes"] == [
        {"artigo": "Farinha", "consumido": "1,8 kg"}
    ]
    assert do_staff["linhas"][0]["por"] == "", "um email não é o nome de ninguém aqui"
    assert "custo_total" not in do_staff["linhas"][0]
    assert do_staff["linhas"][0]["produzido"] == "2 kg"


# ---------------------------------------------------------------------------
# Equipa e estabelecimento: o que nunca sai
# ---------------------------------------------------------------------------
def test_a_equipa_tem_nomes_e_papeis_para_todos_e_emails_so_para_o_dono(
    loja: Loja,
) -> None:
    """Resposta do dono a 2026-10-16: o colaborador vê a equipa, sem emails."""
    ana = User.objects.create_user("ana@gama.pt", CREDENCIAL_DE_TESTE)
    bruno = User.objects.create_user("bruno@gama.pt", CREDENCIAL_DE_TESTE)
    antiga = User.objects.create_user("antiga@gama.pt", CREDENCIAL_DE_TESTE)
    with tenant_scope(loja.tenant.id):
        conceder_pertenca(
            user=ana, tenant_id=loja.tenant.id, role=Papel.OWNER, display_name="Ana"
        )
        conceder_pertenca(
            user=bruno, tenant_id=loja.tenant.id, role=Papel.MANAGER, display_name="Bruno"
        )
        conceder_pertenca(
            user=antiga, tenant_id=loja.tenant.id, role=Papel.STAFF, display_name="Antiga"
        )
        revogar_pertenca(user=antiga, tenant_id=loja.tenant.id)
        InvitationFactory(
            tenant=loja.tenant, email="novo@gama.pt", role=Papel.STAFF, display_name="Novo"
        )

    do_dono, dono_bruto = _executar(
        _contexto(loja.tenant, papel="owner", user_id=ana.id), "equipa"
    )
    do_staff, staff_bruto = _executar(
        _contexto(loja.tenant, papel="staff", user_id=bruno.id), "equipa"
    )

    assert {linha["nome"]: linha["papel"] for linha in do_dono["linhas"]} == {
        "Ana": "dono",
        "Bruno": "gerente",
    }
    assert do_dono["n"] == 2 and do_dono["n_inativos"] == 1
    assert next(linha for linha in do_dono["linhas"] if linha["nome"] == "Ana")["es_tu"]
    assert sorted(linha["email"] for linha in do_dono["linhas"]) == [
        "ana@gama.pt",
        "bruno@gama.pt",
    ]
    assert do_dono["convites"][0]["email"] == "novo@gama.pt"

    assert [linha["nome"] for linha in do_staff["linhas"]] == ["Ana", "Bruno"]
    assert all("email" not in linha for linha in do_staff["linhas"])
    assert do_staff["emails_visiveis"] is False
    assert do_staff["convites_pendentes"] == 1
    assert "convites" not in do_staff, "o número sim, os endereços não"
    assert "os emails da equipa só o dono" in do_staff["nota"]

    assert "ana@gama.pt" in dono_bruto.conteudo
    assert "@gama.pt" not in staff_bruto.conteudo
    for conteudo in (dono_bruto.conteudo, staff_bruto.conteudo):
        assert str(ana.id) not in conteudo, "um id de conta é uma chave para fora daqui"


def test_o_estabelecimento_diz_o_relogio_e_o_iva_e_nunca_um_nif_ou_um_user_id(
    loja: Loja,
) -> None:
    ana = User.objects.create_user("ana2@gama.pt", CREDENCIAL_DE_TESTE)
    with tenant_scope(loja.tenant.id):
        conceder_pertenca(
            user=ana, tenant_id=loja.tenant.id, role=Papel.OWNER, display_name="Ana"
        )

    dados, bruto = _executar(
        _contexto(loja.tenant, hoje=date(2026, 10, 14), user_id=ana.id), "estabelecimento"
    )

    assert dados["nome"] == "Padaria Gama"
    assert dados["dia_de_negocio_comeca_as"] == "04:00"
    assert dados["dia_de_negocio_de_hoje"] == "2026-10-14"
    assert "IVA das compras é dedutível" in dados["regime_de_iva"]
    assert dados["n_localizacoes"] == 3
    assert [linha["nome"] for linha in dados["linhas"]] == ["Loja", "Armazém", "Cozinha"]
    assert "nif" not in bruto.conteudo.lower()
    assert "user_id" not in bruto.conteudo
    assert str(ana.id) not in bruto.conteudo


# ---------------------------------------------------------------------------
# A ajuda e o mapa de navegação
# ---------------------------------------------------------------------------
def test_cada_tema_de_ajuda_existe_nas_duas_linguas_e_e_o_que_a_tool_devolve(
    loja: Loja,
) -> None:
    assert len(navegacao.indice_de_temas()) == 12
    for tema in navegacao.indice_de_temas():
        for lingua in navegacao.LINGUAS_DA_AJUDA:
            texto = navegacao.texto_de_ajuda(tema=tema, lingua=lingua)
            assert texto, f"falta o tema {tema} em {lingua}"
            assert texto.startswith("# "), tema

    em_portugues, _ = _executar(_contexto(loja.tenant), "ajuda_sobre", tema="contar")
    em_ingles, _ = _executar(
        _contexto(loja.tenant, lingua="en"), "ajuda_sobre", tema="contar"
    )

    assert em_portugues["lingua"] == "pt-pt" and em_ingles["lingua"] == "en"
    assert em_portugues["manual"] != em_ingles["manual"]
    assert len(em_portugues["manual"]) > tools.TEXTO_MAXIMO, (
        "o manual é texto nosso: o corte a 120 caracteres defende-nos do texto do tenant"
    )
    assert em_portugues["manual"] == navegacao.texto_de_ajuda(tema="contar", lingua="pt-pt")
    assert "não registes nada" in em_portugues["nota"]

    _, invalido = _executar(_contexto(loja.tenant), "ajuda_sobre", tema="../../etc/passwd")
    assert invalido.ok is False and "argumentos_invalidos" in invalido.conteudo


def test_uma_lingua_desconhecida_cai_no_portugues(loja: Loja) -> None:
    dados, _ = _executar(
        _contexto(loja.tenant, lingua="de"), "ajuda_sobre", tema="receber"
    )
    assert dados["lingua"] == "pt-pt"
    assert dados["manual"] == navegacao.texto_de_ajuda(tema="receber", lingua="pt-pt")


#: As rotas que os temas de ajuda podem citar, com o id do registo de cada uma.
_ROTA_DO_CAMINHO = {
    "/": "inicio",
    "/painel": "painel",
    "/alertas": "alertas",
    "/assistente": "assistente",
    "/stock": "stock",
    "/stock/<artigo>": "artigo",
    "/contar": "contar",
    "/receber": "receber",
    "/receber/<id>": "rececao",
    "/definicoes": "definicoes",
}


def test_a_ajuda_so_cita_rotas_que_existem_no_registo() -> None:
    """Quem muda um ecrã muda o tema — e é este teste que o lembra."""
    raiz = pathlib.Path(tools.__file__).resolve().parent / "ajuda"
    citadas = 0
    for ficheiro in sorted(raiz.rglob("*.md")):
        for citacao in re.findall(r"`(/[^`]*)`", ficheiro.read_text(encoding="utf-8")):
            caminho, _, procura = citacao.partition("?")
            rota = _ROTA_DO_CAMINHO.get(caminho)
            assert rota is not None, f"{ficheiro.name} cita {citacao}, que não é uma rota"
            assert rota in navegacao.ROTAS
            citadas += 1
            for par in filter(None, procura.split("&")):
                nome, _, valor = par.partition("=")
                assert nome in navegacao.PARAMETROS_POR_ROTA[rota], (
                    f"{ficheiro.name} cita {citacao}: a rota {rota} não aceita {nome}"
                )
                valores = navegacao.VALORES_POR_PARAMETRO.get(nome)
                if valores is not None and valor != "...":
                    assert valor in valores, f"{ficheiro.name}: {nome}={valor} não existe"
    assert citadas > 20, "os temas citam ecrãs; um manual sem rotas não orienta ninguém"


#: Argumentos plausíveis por tool, para percorrer o mapa inteiro de uma vez.
_ARGS_DE_EXEMPLO: dict[str, dict[str, Any]] = {
    "procurar_artigos": {"q": "farinha", "limite": 10},
    "procurar_fornecedores": {"q": "makro", "limite": 10},
    "saldo_de_artigo": {"product_id": "0c5a2a2e-0000-4000-8000-000000000001"},
    "artigos_abaixo_do_minimo": {"limite": 50},
    "lotes_a_vencer": {"dias": 7, "limite": 50},
    "movimentos_de_artigo": {"product_id": "0c5a2a2e-0000-4000-8000-000000000001"},
    "compras_por_periodo": {"desde": "2026-10-01", "ate": "2026-10-14"},
    "rececoes": {"estado": "por_rever", "limite": 10},
    "rececao": {"id": "0c5a2a2e-0000-4000-8000-000000000002"},
    "historico_de_precos": {"product_id": "0c5a2a2e-0000-4000-8000-000000000001"},
    "contagens": {"estado": "abertas", "limite": 10},
    "contagem": {"id": "0c5a2a2e-0000-4000-8000-000000000003"},
    "alertas": {"tipo": "todos"},
    "artigo": {"id": "0c5a2a2e-0000-4000-8000-000000000001"},
    "receitas": {"q": "", "limite": 10},
    "receita": {"id": "0c5a2a2e-0000-4000-8000-000000000004"},
    "producoes_recentes": {"dias": 7, "limite": 10},
    "equipa": {},
    "estabelecimento": {},
    "ajuda_sobre": {"tema": "perdas-ajustes-transferencias"},
}


def _chamada(nome: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return {"name": nome, "args": args, "rows": 1, "truncated": False, "ok": ok, "ms": 1}


def test_o_mapa_de_navegacao_so_produz_rotas_e_parametros_que_existem() -> None:
    """Nenhuma acção nomeia um ecrã ou um parâmetro que a árvore não tenha.

    Não há URL vinda do modelo para injectar: o que o mapa recebe são os
    argumentos **já revalidados** e o que devolve é um id de rota de uma lista
    fechada. Este teste percorre o registo inteiro com argumentos plausíveis,
    para que uma tool nova sem entrada no mapa não passe despercebida.
    """
    assert set(_ARGS_DE_EXEMPLO) == set(tools.nomes_das_tools()), (
        "uma tool nova precisa de uma linha aqui — e de uma decisão sobre o botão dela"
    )
    vistas = 0
    for papel in ("owner", "manager", "staff"):
        for nome, args in _ARGS_DE_EXEMPLO.items():
            for acao in navegacao.acoes_do_turno(
                chamadas=[_chamada(nome, args)], papel=papel
            ):
                vistas += 1
                assert acao.rota in navegacao.ROTAS, nome
                assert acao.rotulo_id in navegacao.ROTULOS, nome
                assert set(acao.parametros) <= navegacao.PARAMETROS_POR_ROTA[acao.rota]
                for chave, valor in acao.parametros.items():
                    valores = navegacao.VALORES_POR_PARAMETRO.get(chave)
                    if valores is not None:
                        assert valor in valores, f"{nome}: {chave}={valor}"
                    else:
                        # Um parâmetro livre (o `artigo` de `/stock/<artigo>`,
                        # a `rececao` de `/receber/<id>`) só sai de um id que
                        # uma tool já validou — nunca de texto do modelo.
                        assert UUID(valor), f"{nome}: {chave} não é um uuid"
    assert vistas > 20


def test_uma_chamada_que_falhou_nao_da_botao_e_as_repeticoes_contam_uma_vez() -> None:
    artigo = "0c5a2a2e-0000-4000-8000-000000000001"
    acoes = navegacao.acoes_do_turno(
        chamadas=[
            _chamada("saldo_de_artigo", {"product_id": artigo}),
            _chamada("movimentos_de_artigo", {"product_id": artigo}),
            _chamada("rececoes", {"estado": "por_rever"}, ok=False),
            _chamada("procurar_artigos", {"q": "farinha"}),
        ],
        papel="owner",
    )
    assert [(a.rota, a.rotulo_id) for a in acoes] == [("artigo", "ver_artigo")]


def test_um_colaborador_nao_recebe_botoes_de_ecras_que_nao_ve() -> None:
    """O painel e as definições são do dono; o botão para lá não sai aos outros."""
    chamadas = [
        _chamada("equipa", {}),
        _chamada("estabelecimento", {}),
        _chamada("alertas", {"tipo": "falta"}),
    ]
    do_dono = navegacao.acoes_do_turno(chamadas=chamadas, papel="owner")
    do_staff = navegacao.acoes_do_turno(chamadas=chamadas, papel="staff")

    assert [(a.rota, a.rotulo_id) for a in do_dono] == [
        ("definicoes", "ver_equipa"),
        ("definicoes", "ver_estabelecimento"),
        ("alertas", "ver_falta"),
    ]
    assert [a.rota for a in do_staff] == ["alertas"]
    assert do_staff[0].parametros == {"ver": "falta"}
    assert navegacao.acoes_do_turno(
        chamadas=[_chamada("ajuda_sobre", {"tema": "painel"})], papel="staff"
    ) == (), "o Painel é do dono (ADR 0013)"


#: Onde vive o `z.enum` de cada search param do cliente: ficheiro e nome do
#: símbolo. Nem sempre é o nome do parâmetro — `period` é o `periodoSchema`,
#: que vive nos schemas do `reporting` e é a rota que o importa.
_ZOD: dict[str, tuple[str, str]] = {
    "ver": ("routes/busca-de-alertas.ts", "ver"),
    "periodo": ("routes/busca-de-alertas.ts", "periodo"),
    "filtro": ("routes/busca-de-stock.ts", "filtro"),
    "estado": ("routes/busca-de-rececoes.ts", "estado"),
    "secao": ("features/accounts/secoes.ts", "secaoSchema"),
    "period": ("features/reporting/schemas.ts", "periodoSchema"),
    "aba": ("features/reporting/abas.ts", "abaSchema"),
}


def test_os_valores_dos_search_params_sao_os_mesmos_dos_schemas_zod() -> None:
    """As duas pontas da decisão 3, amarradas — e falha nos **dois** sentidos.

    Um botão com `?ver=expirados` cai no `.catch(undefined)` do Zod e abre o
    ecrã sem filtro nenhum: a navegação não rebenta, mente. As duas metades
    vivem em repositórios de linguagens diferentes, que é a forma de divergência
    que ninguém vê.
    """
    raiz = pathlib.Path(__file__).resolve().parents[2] / "frontend/src"
    for parametro, (ficheiro, simbolo) in _ZOD.items():
        fonte = (raiz / ficheiro).read_text(encoding="utf-8")
        bloco = re.search(rf"{simbolo}\s*[:=]\s*z\.enum\(\[([^\]]*)\]\)", fonte)
        assert bloco is not None, f"não encontrei o z.enum de {parametro} em {ficheiro}"
        assert set(re.findall(r'"([^"]+)"', bloco.group(1))) == set(
            navegacao.VALORES_POR_PARAMETRO[parametro]
        ), parametro
    # O `explicar` é um `z.literal(1)` e não um enum: o único valor é "1".
    painel = (raiz / "routes/busca-do-painel.ts").read_text(encoding="utf-8")
    assert "explicar: z.literal(1)" in painel
    assert navegacao.VALORES_POR_PARAMETRO["explicar"] == frozenset({"1"})
