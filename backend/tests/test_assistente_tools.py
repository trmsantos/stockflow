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
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.accounts.services import criar_tenant
from apps.agents import tools
from apps.catalog.models import Product, Supplier, UnidadeBase
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.purchasing.models import Receipt, ReceiptLine
from apps.shared.db import tenant_scope

LISBOA = ZoneInfo("Europe/Lisbon")
INICIO_DO_DIA = time(4, 0)


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
            created_by_name="Teste",
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


def _contexto(tenant: Tenant, *, hoje: date | None = None, papel: str = "owner") -> tools.ContextoDaTool:
    agora = timezone.now()
    return tools.ContextoDaTool(
        tenant_id=tenant.id,
        papel=papel,
        agora=agora,
        hoje=hoje or tools.dia_de_negocio(agora, INICIO_DO_DIA),
        inicio_do_dia=INICIO_DO_DIA,
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


def test_o_staff_nao_tem_compras_e_o_despachante_recusa(loja: Loja) -> None:
    assert [t.nome for t in tools.tools_para("staff")] == [
        n for n in tools.nomes_das_tools() if n != "compras_por_periodo"
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
