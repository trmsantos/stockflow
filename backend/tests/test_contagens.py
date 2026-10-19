"""Contagem física: as regras do domínio e as seis rotas (ADR 0030).

O que este ficheiro mede são as catorze regras que o `domain-expert` fixou antes
da implementação, mais a recusa que o dono acrescentou na segunda ronda. A ordem
é a delas, e cada classe diz a regra que prova.

## Porque é que o stock entra sempre pelo ledger

Nenhum teste escreve `StockLevel.objects.create(...)`. O nível é a **projeção**
da soma dos movimentos: o `record_movements` recalcula-o a partir deles, logo um
nível escrito à mão desaparece no primeiro movimento que lhe toca — e era isso
que fazia os testes de ajuste esperarem 110 e medirem 10
(`tests/test_manual_movements.py` tem a mesma nota, pela mesma razão).

## Os dois estilos de teste, e quando cada um

As regras de repartição (FEFO, cascata, lote recente, custo) medem-se nos
**serviços**, dentro de `tenant_scope`: é lá que elas vivem e o HTTP só as
repetiria mais devagar. As de contrato — estados, papéis, 404 e 409 — medem-se
por **HTTP**, com sessão a sério, porque é o único sítio onde as
`permission_classes` e o `get_queryset` filtrado existem.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.count_services import (
    CODIGO_CONTAGEM_FECHADA,
    CODIGO_CONTAGEM_JA_ABERTA,
    ContagemFechada,
    ContagemJaAberta,
    abrir_contagem,
    ao_centimo,
    fechar_contagem,
    planear_fecho,
    registar_linha_contagem,
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
from apps.inventory.selectors import ultima_contagem_fechada_em
from apps.inventory.services import MovementDTO, record_movements
from apps.shared.db import tenant_scope

CREDENCIAL = "contagens-teste-123"


# ---------------------------------------------------------------------------
# Andaimes
# ---------------------------------------------------------------------------
def _casa(*, nome: str = "Pastelaria das Contagens") -> SimpleNamespace:
    """Um estabelecimento com dono, colaborador e uma localização."""
    tenant = criar_tenant(name=nome)
    with tenant_scope(tenant.id):
        dono = User.objects.create_user(f"dono@{tenant.id}.pt", CREDENCIAL)
        conceder_pertenca(
            user=dono, tenant_id=tenant.id, role=Papel.OWNER, display_name="Ana Dona"
        )
        colaborador = User.objects.create_user(f"staff@{tenant.id}.pt", CREDENCIAL)
        conceder_pertenca(
            user=colaborador,
            tenant_id=tenant.id,
            role=Papel.STAFF,
            display_name="João Colaborador",
        )
        armazem = Location.objects.create(tenant=tenant, name="Armazém", position=0)
        cozinha = Location.objects.create(tenant=tenant, name="Cozinha", position=1)
    return SimpleNamespace(
        tenant=tenant,
        dono=dono,
        colaborador=colaborador,
        armazem=armazem,
        cozinha=cozinha,
    )


def _artigo(
    casa: SimpleNamespace,
    *,
    nome: str = "Farinha T65",
    base: str = UnidadeBase.GRAMA,
    apresentacao: str = "kg",
    factor: Decimal = Decimal("1000"),
    track_lots: bool = False,
) -> Product:
    with tenant_scope(casa.tenant.id):
        return Product.objects.create(
            tenant=casa.tenant,
            short_name=nome,
            sku=nome.replace(" ", "-").lower(),
            base_unit=base,
            display_unit=apresentacao,
            display_factor=factor,
            track_lots=track_lots,
        )


def _lote(
    casa: SimpleNamespace, produto: Product, *, codigo: str, dias: int | None, recebido: int = 0
) -> Lot:
    """Um lote com validade daqui a `dias` (ou sem validade) e recebido há `recebido` dias."""
    agora = timezone.now()
    return Lot.objects.create(
        tenant=casa.tenant,
        product=produto,
        code=codigo,
        expires_at=None if dias is None else agora + timedelta(days=dias),
        received_at=agora - timedelta(days=recebido),
    )


def _receber(
    casa: SimpleNamespace,
    produto: Product,
    localizacao: Location,
    lote: Lot,
    *,
    quantidade: Decimal,
    custo: Decimal,
) -> None:
    """Stock inicial **pelo ledger**. Nunca por `StockLevel.objects.create`."""
    record_movements(
        tenant_id=casa.tenant.id,
        movements=[
            MovementDTO(
                product_id=produto.id,
                location_id=localizacao.id,
                lot_id=lote.id,
                quantity=quantidade,
                unit_cost=custo,
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=timezone.now(),
                created_by_id=None,
                created_by_name="semeador",
            )
        ],
    )


def _saida(
    casa: SimpleNamespace,
    produto: Product,
    localizacao: Location,
    lote: Lot,
    *,
    quantidade: Decimal,
) -> None:
    """Uma saída que leva o nível abaixo de zero — o ledger permite-o (ADR 0012)."""
    record_movements(
        tenant_id=casa.tenant.id,
        movements=[
            MovementDTO(
                product_id=produto.id,
                location_id=localizacao.id,
                lot_id=lote.id,
                quantity=-quantidade,
                unit_cost=Decimal("0"),
                cost_is_estimate=False,
                movement_type="consumption",
                occurred_at=timezone.now(),
                created_by_id=None,
                created_by_name="semeador",
            )
        ],
    )


def _linha(contagem: StockCount, produto: Product) -> StockCountLine:
    return StockCountLine.objects.get(stock_count=contagem, product=produto)


def _ajustes(casa: SimpleNamespace, contagem: StockCount) -> list[StockMovement]:
    return list(
        StockMovement.objects.filter(
            tenant_id=casa.tenant.id,
            movement_type="adjustment",
            reference=str(contagem.pk),
        ).order_by("created_at", "id")
    )


def _sessao(email: str) -> APIClient:
    """Sessão a sério: o `TenantMiddleware` precisa dela para abrir o âmbito."""
    cliente = Client()
    resposta = cliente.post(
        "/api/v1/auth/login",
        {"email": email, "password": CREDENCIAL},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    api = APIClient()
    for chave, valor in resposta.cookies.items():
        api.cookies[chave] = valor.value
    return api


# ---------------------------------------------------------------------------
# 1. Abrir materializa a lista
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAbrir:
    """Regra 1: uma linha por artigo com nível não-zero; sem nível não entra."""

    def test_linha_por_artigo_com_nivel_e_nenhuma_para_quem_nunca_entrou(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Açúcar")
        nunca_entrou = _artigo(casa, nome="Canela")
        with tenant_scope(casa.tenant.id):
            lote_a = _lote(casa, farinha, codigo="A", dias=10)
            lote_b = _lote(casa, farinha, codigo="B", dias=30)
            lote_c = _lote(casa, acucar, codigo="C", dias=None)
            _receber(casa, farinha, casa.armazem, lote_a, quantidade=Decimal("2000"),
                     custo=Decimal("0.001"))
            _receber(casa, farinha, casa.armazem, lote_b, quantidade=Decimal("3000"),
                     custo=Decimal("0.002"))
            _receber(casa, acucar, casa.armazem, lote_c, quantidade=Decimal("500"),
                     custo=Decimal("0.003"))
            # Noutra localização: não entra nesta contagem.
            _receber(casa, acucar, casa.cozinha, lote_c, quantidade=Decimal("100"),
                     custo=Decimal("0.003"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id,
                location_id=casa.armazem.id,
                user_id=casa.dono.id,
            )
            linhas = list(StockCountLine.objects.filter(stock_count=contagem))

            assert {linha.product_id for linha in linhas} == {farinha.id, acucar.id}
            assert nunca_entrou.id not in {linha.product_id for linha in linhas}
            # O esperado é a **soma dos lotes** daquela localização, congelada.
            assert _linha(contagem, farinha).quantity_expected == Decimal("5000")
            assert _linha(contagem, acucar).quantity_expected == Decimal("500")
            # E nasce por contar: `None` não é zero.
            assert all(linha.quantity_counted is None for linha in linhas)

    def test_a_segunda_contagem_aberta_e_recusada_com_o_id_da_primeira(self):
        """Regra 13, primeira metade: 409 `contagem_ja_aberta`, com o `id`."""
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            primeira = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            with pytest.raises(ContagemJaAberta) as erro:
                abrir_contagem(tenant_id=casa.tenant.id, location_id=casa.cozinha.id)
            assert erro.value.contagem_id == primeira.pk
            assert StockCount.objects.filter(status="open").count() == 1

    def test_localizacao_inativa_ou_inexistente_e_recusada(self):
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            casa.cozinha.is_active = False
            casa.cozinha.save(update_fields=["is_active"])
            with pytest.raises(ValidationError) as erro:
                abrir_contagem(tenant_id=casa.tenant.id, location_id=casa.cozinha.id)
            assert "location" in erro.value.error_dict
            with pytest.raises(ValidationError):
                abrir_contagem(tenant_id=casa.tenant.id, location_id=uuid4())


# ---------------------------------------------------------------------------
# 2 a 5 e 11. A repartição de uma diferença pelos lotes, e o custo
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestReparticao:
    """Regras 2, 3, 4, 5 e 11: FEFO em cascata, lote recente, custo e negativos."""

    def test_falta_sai_por_fefo_e_cascata_para_o_lote_seguinte(self):
        """Regra 2: dois lotes, a falta excede o primeiro e transborda."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            perto = _lote(casa, farinha, codigo="PERTO", dias=5)
            longe = _lote(casa, farinha, codigo="LONGE", dias=90)
            _receber(casa, farinha, casa.armazem, perto, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))
            _receber(casa, farinha, casa.armazem, longe, quantidade=Decimal("4000"),
                     custo=Decimal("0.002"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                product_id=farinha.id,
                quantity=Decimal("3500"),  # faltam 1500 de 5000
                user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="Contagem de fim de mês.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )

            ajustes = _ajustes(casa, contagem)
            por_lote = {m.lot_id: m for m in ajustes}
            assert len(ajustes) == 2, "um movimento por lote, não um por linha"
            # O lote a expirar primeiro esvazia-se antes de o segundo ser tocado.
            assert por_lote[perto.id].quantity == Decimal("-1000")
            assert por_lote[longe.id].quantity == Decimal("-500")
            # E cada um leva o custo do **seu** nível.
            assert por_lote[perto.id].unit_cost == Decimal("0.001000")
            assert por_lote[longe.id].unit_cost == Decimal("0.002000")
            assert StockLevel.objects.get(lot=perto, location=casa.armazem).quantity == 0
            assert StockLevel.objects.get(lot=longe, location=casa.armazem).quantity == 3500

    def test_sobra_entra_no_lote_mais_recente_e_nunca_no_que_expira_primeiro(self):
        """Regra 3: inflacionar o lote a expirar criaria um alerta falso."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            antigo = _lote(casa, farinha, codigo="ANTIGO", dias=5, recebido=30)
            recente = _lote(casa, farinha, codigo="RECENTE", dias=90, recebido=1)
            _receber(casa, farinha, casa.armazem, antigo, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))
            _receber(casa, farinha, casa.armazem, recente, quantidade=Decimal("1000"),
                     custo=Decimal("0.002"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                product_id=farinha.id,
                quantity=Decimal("2300"),  # sobram 300
                user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="Apareceu um saco.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )

            ajustes = _ajustes(casa, contagem)
            assert len(ajustes) == 1
            assert ajustes[0].lot_id == recente.id, "a sobra nunca vai ao lote FEFO"
            assert ajustes[0].quantity == Decimal("300")
            assert ajustes[0].unit_cost == Decimal("0.002000")

    def test_custo_de_um_artigo_sem_rastreio_nao_e_zero(self):
        """Regra 4: a regressão do `lot_id = NULL` — valorizava a zero, em silêncio."""
        casa = _casa()
        agua = _artigo(casa, nome="Água", base=UnidadeBase.UNIDADE, apresentacao="un",
                       factor=Decimal("1"), track_lots=False)
        with tenant_scope(casa.tenant.id):
            sintetico = _lote(casa, agua, codigo=f"__{agua.id}__", dias=None)
            _receber(casa, agua, casa.armazem, sintetico, quantidade=Decimal("100"),
                     custo=Decimal("0.350000"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                product_id=agua.id,
                quantity=Decimal("90"),
                user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="Faltam dez garrafas.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )

            ajuste = _ajustes(casa, contagem)[0]
            assert ajuste.lot_id == sintetico.id
            assert ajuste.unit_cost == Decimal("0.350000"), (
                "o nível vive no lote sintético; procurar lot_id=NULL acerta "
                "sempre em nada e valoriza a zero"
            )
            assert ajuste.cost_is_estimate is False

    def test_sem_nivel_o_custo_desce_ao_productcost_e_depois_a_zero_estimado(self):
        """Regra 5: os dois degraus do custo, e a marca de estimativa no último."""
        casa = _casa()
        canela = _artigo(casa, nome="Canela")
        azeite = _artigo(casa, nome="Azeite")
        with tenant_scope(casa.tenant.id):
            ProductCost.objects.create(
                tenant=casa.tenant,
                product=canela,
                location=casa.armazem,
                unit_cost=Decimal("0.020000"),
            )
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            for artigo in (canela, azeite):
                registar_linha_contagem(
                    tenant_id=casa.tenant.id,
                    contagem=contagem,
                    product_id=artigo.id,
                    quantity=Decimal("50"),
                    user_name="Ana Dona",
                )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="Apareceram dois artigos que não estavam na lista.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )

            por_artigo = {m.product_id: m for m in _ajustes(casa, contagem)}
            assert por_artigo[canela.id].unit_cost == Decimal("0.020000")
            assert por_artigo[canela.id].cost_is_estimate is True
            assert por_artigo[azeite.id].unit_cost == Decimal("0")
            assert por_artigo[azeite.id].cost_is_estimate is True

    def test_artigo_que_nunca_entrou_da_ajuste_positivo_e_nunca_receipt(self):
        """Regra 7: `expected = 0`, e uma receção tem fornecedor, documento e preço."""
        casa = _casa()
        canela = _artigo(casa, nome="Canela")
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            linha = registar_linha_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                product_id=canela.id,
                quantity=Decimal("250"),
                user_name="Ana Dona",
            )
            assert linha.quantity_expected == Decimal("0")

            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="Estava no fundo da prateleira.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )
            ajuste = _ajustes(casa, contagem)[0]
            assert ajuste.movement_type == "adjustment"
            assert ajuste.quantity == Decimal("250")
            assert StockMovement.objects.filter(
                tenant_id=casa.tenant.id, movement_type="receipt", product=canela
            ).count() == 0

    def test_esperado_negativo_repoe_o_lote_negativo_primeiro(self):
        """Regra 11: nenhum nível fica com o sinal invertido por causa da contagem."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            devedor = _lote(casa, farinha, codigo="DEVEDOR", dias=5, recebido=30)
            recente = _lote(casa, farinha, codigo="RECENTE", dias=90, recebido=1)
            _receber(casa, farinha, casa.armazem, devedor, quantidade=Decimal("100"),
                     custo=Decimal("0.001"))
            _receber(casa, farinha, casa.armazem, recente, quantidade=Decimal("50"),
                     custo=Decimal("0.002"))
            _saida(casa, farinha, casa.armazem, devedor, quantidade=Decimal("300"))
            # O ledger ficou a dever: -200 no devedor, +50 no recente, soma -150.

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            assert _linha(contagem, farinha).quantity_expected == Decimal("-150")
            registar_linha_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                product_id=farinha.id,
                quantity=Decimal("100"),  # sobram 250
                user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="O ledger estava a dever.",
                user_id=casa.dono.id,
                user_name="Ana Dona",
            )

            por_lote = {m.lot_id: m for m in _ajustes(casa, contagem)}
            assert por_lote[devedor.id].quantity == Decimal("200"), "repõe até zerar"
            assert por_lote[recente.id].quantity == Decimal("50"), "e só o excedente"
            niveis = StockLevel.objects.filter(
                tenant_id=casa.tenant.id, product=farinha, location=casa.armazem
            )
            assert {n.lot_id: n.quantity for n in niveis} == {
                devedor.id: Decimal("0.000"),
                recente.id: Decimal("100.000"),
            }
            assert all(n.quantity >= 0 for n in niveis)


# ---------------------------------------------------------------------------
# 6. A pré-visualização e o ledger dizem o mesmo
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPreVisualizacao:
    """Regra 6: `difference_eur` previsto == soma dos movimentos gravados, ao cêntimo."""

    def test_o_previsto_e_o_gravado_batem_certo(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Açúcar")
        with tenant_scope(casa.tenant.id):
            lote_f = _lote(casa, farinha, codigo="F", dias=10)
            lote_a = _lote(casa, acucar, codigo="A", dias=20)
            _receber(casa, farinha, casa.armazem, lote_f, quantidade=Decimal("5000"),
                     custo=Decimal("0.001200"))
            _receber(casa, acucar, casa.armazem, lote_a, quantidade=Decimal("2000"),
                     custo=Decimal("0.000800"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("4250"), user_name="Ana Dona",
            )  # −750 × 0,0012 = −0,90 €
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=acucar.id, quantity=Decimal("2500"), user_name="Ana Dona",
            )  # +500 × 0,0008 = +0,40 €

            previsto = planear_fecho(tenant_id=casa.tenant.id, contagem=contagem)
            assert previsto.loss_eur == Decimal("0.90")
            assert previsto.gain_eur == Decimal("0.40")
            assert previsto.net_eur == Decimal("-0.50")

            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Fecho com as duas direcções.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            gravado = sum(
                (abs(m.quantity) * m.unit_cost for m in _ajustes(casa, contagem)),
                Decimal("0"),
            )
            assert ao_centimo(gravado) == previsto.loss_eur + previsto.gain_eur

            # E depois de fechar os números vêm do ledger, não de um recálculo.
            depois = planear_fecho(
                tenant_id=casa.tenant.id,
                contagem=StockCount.objects.get(pk=contagem.pk),
            )
            assert depois.loss_eur == Decimal("0.90")
            assert depois.gain_eur == Decimal("0.40")


# ---------------------------------------------------------------------------
# 8, 9 e 10. Contagem parcial, `last_count_at` e a justificação
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestFecho:
    """Regras 8, 9 e 10: fechar imperfeito é possível, e a frase é obrigatória."""

    def test_linha_por_contar_nao_gera_movimento_e_nao_impede_o_fecho(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Açúcar")
        with tenant_scope(casa.tenant.id):
            lote_f = _lote(casa, farinha, codigo="F", dias=10)
            lote_a = _lote(casa, acucar, codigo="A", dias=20)
            _receber(casa, farinha, casa.armazem, lote_f, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))
            _receber(casa, acucar, casa.armazem, lote_a, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))

            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("900"), user_name="Ana Dona",
            )

            previsto = planear_fecho(tenant_id=casa.tenant.id, contagem=contagem)
            assert previsto.total_lines == 2
            assert previsto.counted_lines == 1
            assert previsto.por_contar == ("Açúcar",)

            fechada = fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Fechámos com o açúcar por contar.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            ajustes = _ajustes(casa, contagem)
            assert [m.product_id for m in ajustes] == [farinha.id], (
                "ausência de observação não é diferença de zero"
            )
            assert fechada.status == "closed"
            assert fechada.closing_reason == "Fechámos com o açúcar por contar."
            # Regra 9: uma contagem parcial conta para o painel.
            assert ultima_contagem_fechada_em(tenant_id=casa.tenant.id) == fechada.closed_at

    def test_justificacao_vazia_e_recusada_sempre_e_sem_limiar(self):
        """Regra 10: sem limiar — até uma contagem sem diferença nenhuma."""
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            for vazia in ("", "   "):
                with pytest.raises(ValidationError) as erro:
                    fechar_contagem(
                        tenant_id=casa.tenant.id, contagem=contagem, reason=vazia
                    )
                assert "reason" in erro.value.error_dict
            assert StockCount.objects.get(pk=contagem.pk).status == "open"

    def test_fechar_duas_vezes_e_conflito(self):
        """Regra 13, segunda metade."""
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem, reason="Primeira vez."
            )
            with pytest.raises(ContagemFechada) as erro:
                fechar_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem, reason="Segunda vez."
                )
            assert erro.value.contagem_id == contagem.pk


# ---------------------------------------------------------------------------
# 12 e a recusa da segunda ronda
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestContar:
    """Regra 12 (upsert e idempotência) e a recusa de um artigo sem lote."""

    def test_duas_pessoas_a_contar_deixam_uma_linha_com_o_ultimo_valor(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            lote = _lote(casa, farinha, codigo="F", dias=10)
            _receber(casa, farinha, casa.armazem, lote, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("800"), user_name="Ana Dona",
            )
            segunda = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("950"),
                user_name="João Colaborador",
            )

            linhas = StockCountLine.objects.filter(stock_count=contagem, product=farinha)
            assert linhas.count() == 1, "nunca se somam os dois números"
            assert segunda.quantity_counted == Decimal("950")
            assert segunda.counted_by_name == "João Colaborador"
            assert "@" not in segunda.counted_by_name, "o nome da pertença, nunca o email"
            assert segunda.counted_at is not None

            # Repetir o mesmo POST depois de um timeout não conta duas vezes.
            terceira = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("950"),
                user_name="João Colaborador",
            )
            assert terceira.pk == segunda.pk
            assert terceira.quantity_counted == Decimal("950")
            assert linhas.count() == 1

    def test_artigo_com_lotes_e_sem_lote_registado_recusa_se(self):
        """Segunda ronda, resposta 4: a rastreabilidade não nasce partida."""
        casa = _casa()
        bacalhau = _artigo(casa, nome="Bacalhau", track_lots=True)
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            with pytest.raises(ValidationError) as erro:
                registar_linha_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem,
                    product_id=bacalhau.id, quantity=Decimal("5"),
                    user_name="Ana Dona",
                )
            mensagem = " ".join(erro.value.message_dict["product"])
            assert "receção" in mensagem, mensagem
            assert not StockCountLine.objects.filter(
                stock_count=contagem, product=bacalhau
            ).exists()

            # Com lote registado, já conta.
            _lote(casa, bacalhau, codigo="BAC-2026-01", dias=200)
            linha = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=bacalhau.id, quantity=Decimal("5"), user_name="Ana Dona",
            )
            assert linha.quantity_counted == Decimal("5")

    def test_artigo_noutra_localizacao_nao_e_transferido_implicitamente(self):
        """Gera-se um ajuste positivo aqui, e a outra localização fica como está."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            lote = _lote(casa, farinha, codigo="F", dias=10)
            _receber(casa, farinha, casa.cozinha, lote, quantidade=Decimal("1000"),
                     custo=Decimal("0.001"))
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            assert StockCountLine.objects.filter(stock_count=contagem).count() == 0
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("300"), user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Apareceu farinha no armazém.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )

            ajuste = _ajustes(casa, contagem)[0]
            assert ajuste.location_id == casa.armazem.id
            assert ajuste.quantity == Decimal("300")
            assert StockLevel.objects.get(
                product=farinha, location=casa.cozinha, lot=lote
            ).quantity == Decimal("1000.000"), "a outra localização fica como está"

    def test_contar_numa_contagem_fechada_e_conflito(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem, reason="Fechada."
            )
            with pytest.raises(ContagemFechada):
                registar_linha_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem,
                    product_id=farinha.id, quantity=Decimal("1"), user_name="Ana Dona",
                )


# ---------------------------------------------------------------------------
# As seis rotas, os papéis e os conflitos — por HTTP
# ---------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
class TestRotas:
    """Regra 14 e o contrato: papéis, formas, 404 do tenant errado e 409."""

    def _casa_com_stock(self) -> SimpleNamespace:
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        with tenant_scope(casa.tenant.id):
            lote = _lote(casa, farinha, codigo="F", dias=10)
            _receber(casa, farinha, casa.armazem, lote, quantidade=Decimal("5000"),
                     custo=Decimal("0.001200"))
        casa.farinha = farinha
        casa.lote = lote
        return casa

    def test_o_percurso_inteiro_do_ecra(self):
        """Abrir, listar, contar, pré-ver e fechar — nas formas do cliente."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)

        aberta = dono.post(
            "/api/v1/stock/counts",
            {"location": str(casa.armazem.id)},
            format="json",
        )
        assert aberta.status_code == 201, aberta.content
        corpo = aberta.json()
        assert corpo["location"] == {"id": str(casa.armazem.id), "name": "Armazém"}
        assert corpo["status"] == "open"
        assert corpo["total_lines"] == 1
        assert corpo["counted_lines"] == 0
        assert corpo["closing_role"] == "Dono ou gerente"
        assert corpo["closing_reason"] is None
        assert corpo["current_zone"]["slug"] == "armazem"
        assert corpo["current_zone"]["blind"] is False
        assert corpo["zones"] == [corpo["current_zone"]]
        contagem_id = corpo["id"]

        lista = dono.get("/api/v1/stock/counts")
        assert lista.status_code == 200
        assert [c["id"] for c in lista.json()["results"]] == [contagem_id]

        linhas = dono.get(f"/api/v1/stock/counts/{contagem_id}/lines")
        assert linhas.status_code == 200
        linha = linhas.json()["results"][0]
        assert linha["product"] == str(casa.farinha.id)
        assert linha["short_name"] == "Farinha"
        assert linha["position"] == 0
        assert linha["count_unit"] == "kg"
        assert linha["expected"] == {
            "base": "5000.000",
            "base_unit": "g",
            "display": "5.000",
            "display_unit": "kg",
        }
        assert linha["counted"] is None
        assert linha["difference"] is None
        assert linha["counted_by"] is None

        contou = dono.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(casa.farinha.id), "quantity": "4250.000"},
            format="json",
        )
        assert contou.status_code == 200, contou.content
        corpo_da_linha = contou.json()
        assert corpo_da_linha["counted"]["display"] == "4.250"
        assert corpo_da_linha["difference"]["base"] == "-750.000"
        assert corpo_da_linha["difference_eur"] == "-0.90"
        assert corpo_da_linha["counted_by"] == "Ana Dona"
        assert corpo_da_linha["counted_at"] is not None

        previsto = dono.get(f"/api/v1/stock/counts/{contagem_id}/closing")
        assert previsto.status_code == 200
        fecho = previsto.json()
        assert fecho["count"] == contagem_id
        assert fecho["status"] == "open"
        assert fecho["loss_eur"] == "0.90"
        assert fecho["gain_eur"] == "0.00"
        assert fecho["net_eur"] == "-0.90"
        assert fecho["reason_required"] is True
        assert fecho["reason_required_above_eur"] == "0.00"
        assert fecho["uncounted_lines"] == {"count": 0, "names": []}
        assert len(fecho["differences"]) == 1

        fechou = dono.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "Faltaram 750 g de farinha."},
            format="json",
        )
        assert fechou.status_code == 200, fechou.content
        assert fechou.json()["status"] == "closed"
        assert fechou.json()["closing_reason"] == "Faltaram 750 g de farinha."
        assert fechou.json()["loss_eur"] == "0.90"

        outra_vez = dono.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "Outra vez."},
            format="json",
        )
        assert outra_vez.status_code == 409
        assert outra_vez.json()["code"] == CODIGO_CONTAGEM_FECHADA

    def test_a_segunda_contagem_aberta_da_409_com_o_id_da_primeira(self):
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        primeira = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        )
        assert primeira.status_code == 201

        segunda = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.cozinha.id)}, format="json"
        )
        assert segunda.status_code == 409
        assert segunda.json()["code"] == CODIGO_CONTAGEM_JA_ABERTA
        assert segunda.json()["id"] == primeira.json()["id"]

    def test_os_papeis_do_contrato(self):
        """Contar é de toda a gente; abrir, pré-ver e fechar não são."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        staff = _sessao(casa.colaborador.email)

        assert staff.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).status_code == 403

        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        # Contar: o `staff` pode, e é esse o ponto da fatia.
        contou = staff.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(casa.farinha.id), "quantity": "4250"},
            format="json",
        )
        assert contou.status_code == 200, contou.content
        assert contou.json()["difference_eur"] is None, "euros não, lista sim"
        assert contou.json()["counted_by"] == "João Colaborador"

        # Regra 14: a lista é dele, os euros não.
        linhas = staff.get(f"/api/v1/stock/counts/{contagem_id}/lines")
        assert linhas.status_code == 200
        assert linhas.json()["results"][0]["difference_eur"] is None
        assert linhas.json()["results"][0]["counted"]["base"] == "4250.000"

        assert dono.get(
            f"/api/v1/stock/counts/{contagem_id}/lines"
        ).json()["results"][0]["difference_eur"] == "-0.90"

        assert staff.get(
            f"/api/v1/stock/counts/{contagem_id}/closing"
        ).status_code == 403
        assert staff.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "Eu fecho."},
            format="json",
        ).status_code == 403

    def test_a_contagem_de_outro_estabelecimento_e_404_e_nunca_403(self):
        """403 confirmaria que o objeto existe a quem o não pode ver."""
        casa = self._casa_com_stock()
        vizinha = _casa(nome="Café do Lado")
        with tenant_scope(vizinha.tenant.id):
            alheia = abrir_contagem(
                tenant_id=vizinha.tenant.id, location_id=vizinha.armazem.id
            )

        dono = _sessao(casa.dono.email)
        assert dono.get(f"/api/v1/stock/counts/{alheia.pk}/lines").status_code == 404
        assert dono.get(f"/api/v1/stock/counts/{alheia.pk}/closing").status_code == 404
        assert dono.post(
            f"/api/v1/stock/counts/{alheia.pk}/lines",
            {"product": str(casa.farinha.id), "quantity": "1"},
            format="json",
        ).status_code == 404
        assert dono.get("/api/v1/stock/counts").json()["count"] == 0

    def test_o_corpo_do_fecho_e_validado(self):
        """Sem `reason` é 400, e sem sessão é 403."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        for corpo in ({}, {"reason": ""}, {"reason": "   "}):
            recusa = dono.post(
                f"/api/v1/stock/counts/{contagem_id}/closing", corpo, format="json"
            )
            assert recusa.status_code == 400, corpo
            assert "reason" in recusa.json()

        assert APIClient().get("/api/v1/stock/counts").status_code == 403

    def test_a_pagina_das_linhas_cobre_uma_contagem_maior_que_o_default(self):
        """Decisão 6a: o ecrã não tem paginador, e 50 linhas truncavam a contagem.

        60 artigos é mais do que o `PAGE_SIZE` do `base.py` e menos do que as
        200 desta rota: é o intervalo onde uma lista truncada seria uma contagem
        errada que ninguém vê.
        """
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            for numero in range(60):
                artigo = _artigo(casa, nome=f"Artigo {numero:02d}")
                lote = _lote(casa, artigo, codigo=f"L{numero:02d}", dias=30)
                _receber(casa, artigo, casa.armazem, lote, quantidade=Decimal("10"),
                         custo=Decimal("1"))

        dono = _sessao(casa.dono.email)
        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        pagina = dono.get(f"/api/v1/stock/counts/{contagem_id}/lines").json()
        assert pagina["count"] == 60
        assert len(pagina["results"]) == 60, "a página tem de cobrir a contagem inteira"
        assert pagina["next"] is None
        # O `position` é o índice na ordenação do servidor, e é único e contíguo.
        assert [linha["position"] for linha in pagina["results"]] == list(range(60))

    def test_a_zona_filtra_e_um_slug_desconhecido_da_pagina_vazia(self):
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        certa = dono.get(f"/api/v1/stock/counts/{contagem_id}/lines?zona=armazem")
        assert certa.json()["count"] == 1
        vazia = dono.get(f"/api/v1/stock/counts/{contagem_id}/lines?zona=camara-fria")
        assert vazia.json()["count"] == 0
        assert vazia.json()["results"] == []
