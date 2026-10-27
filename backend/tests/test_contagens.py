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

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

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


def _movimento(
    casa: SimpleNamespace,
    produto: Product,
    localizacao: Location,
    lote: Lot,
    *,
    quantidade: Decimal,
    tipo: str,
    quando: datetime,
    custo: Decimal = Decimal("0.001"),
    transferencia: UUID | None = None,
) -> None:
    """Um movimento com **hora própria**: é o `occurred_at` que o cut-off lê.

    O `_receber` e o `_saida` acima escrevem sempre "agora", que é o que serve a
    quase todos os testes. O cut-off da ADR 0033 vive da diferença entre quando
    um movimento **aconteceu** e quando foi **inserido**, e essa diferença só se
    escreve com este parâmetro.
    """
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
                movement_type=tipo,
                occurred_at=quando,
                created_by_id=None,
                created_by_name="semeador",
                transfer_id=transferencia,
            )
        ],
    )


def _transferir(
    casa: SimpleNamespace,
    produto: Product,
    lote: Lot,
    *,
    de: Location,
    para: Location,
    quantidade: Decimal,
    quando: datetime,
) -> None:
    """As duas pernas de uma transferência, à mesma hora e com o mesmo `transfer_id`."""
    transferencia = uuid4()
    _movimento(casa, produto, de, lote, quantidade=-quantidade, tipo="transfer_out",
               quando=quando, transferencia=transferencia)
    _movimento(casa, produto, para, lote, quantidade=quantidade, tipo="transfer_in",
               quando=quando, transferencia=transferencia)


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

    def test_a_segunda_contagem_da_mesma_localizacao_e_recusada_com_o_id_da_primeira(self):
        """Regra 13, primeira metade, agora **por localização** (ADR 0033, decisão 1).

        O que não pode acontecer duas vezes ao mesmo tempo são **duas correcções
        dos mesmos factos**, e dois instantâneos de localizações diferentes não
        têm uma linha de nível em comum.
        """
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            primeira = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            with pytest.raises(ContagemJaAberta) as erro:
                abrir_contagem(tenant_id=casa.tenant.id, location_id=casa.armazem.id)
            assert erro.value.contagem_id == primeira.pk
            assert erro.value.location_name == "Armazém"
            assert StockCount.objects.filter(status="open").count() == 1

    def test_duas_localizacoes_contam_se_ao_mesmo_tempo(self):
        """A escassez acabou: quem chega às 6h não espera pela contagem de ontem."""
        casa = _casa()
        with tenant_scope(casa.tenant.id):
            arca = abrir_contagem(tenant_id=casa.tenant.id, location_id=casa.armazem.id)
            despensa = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.cozinha.id
            )
            assert arca.pk != despensa.pk
            assert StockCount.objects.filter(status="open").count() == 2
            # E a que fecha não leva a outra atrás.
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=arca, reason="Arca contada."
            )
            assert StockCount.objects.get(pk=despensa.pk).status == "open"

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
# O cut-off (ADR 0033, adenda): a base do ajuste é o que os livros diziam **no
# instante em que se contou**, e não na abertura nem agora.
#
#   ajuste = contado − Σ(movimentos da localização com occurred_at ≤ counted_at)
#
# Os dois primeiros testes são os dois modos de falhar do cálculo antigo, e o
# segundo é o que ninguém via: o antigo produzia **silêncio**, e silêncio não se
# audita.
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOCorteNaHoraEmQueSeContou:
    """A observação é datada, e a base de comparação tem a mesma data que ela."""

    def _armazem_com_cem(self, casa: SimpleNamespace, produto: Product, *, agora: datetime) -> Lot:
        """100 na arca, recebidos há seis horas. O ponto de partida dos dois casos."""
        lote = _lote(casa, produto, codigo="F", dias=10)
        _movimento(casa, produto, casa.armazem, lote, quantidade=Decimal("100"),
                   tipo="receipt", quando=agora - timedelta(hours=6))
        return lote

    def test_o_movimento_entre_abrir_e_contar_nao_e_contado_duas_vezes(self):
        """Cenário (A): o ajuste certo é **zero**, e o esperado congelado dava −10.

        Esperado 100 na abertura, transferência de −10 às 7h, contam-se 90 às
        8h. O cálculo antigo escrevia `90 − 100 = −10` **sobre um nível que já
        era 90**, e deixava a arca a 80: a transferência era contada duas vezes.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            assert _linha(contagem, farinha).quantity_expected == Decimal("100")

            _transferir(casa, farinha, lote, de=casa.armazem, para=casa.cozinha,
                        quantidade=Decimal("10"), quando=agora - timedelta(hours=3))
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("90"), user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="A arca bate certo com os livros.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )

            assert _ajustes(casa, contagem) == [], (
                "o que já estava registado não se corrige outra vez"
            )
            assert StockLevel.objects.get(
                lot=lote, location=casa.armazem
            ).quantity == Decimal("90.000")

    def test_a_sobra_real_que_um_movimento_registado_mascarava(self):
        """Cenário (B), o perigoso: o certo é **+10** e o cálculo antigo dava zero.

        Esperado 100, transferência de −10 às 7h, e às 8h contam-se **100** —
        há uma sobra real de dez face aos livros. `100 − 100 = 0` fechava a
        contagem com "tudo certo", sem movimento nenhum e sem ninguém a
        investigar, porque uma variância zero nunca é investigada.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            _transferir(casa, farinha, lote, de=casa.armazem, para=casa.cozinha,
                        quantidade=Decimal("10"), quando=agora - timedelta(hours=3))
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("100"), user_name="Ana Dona",
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Estavam lá cem, e os livros diziam noventa.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )

            ajustes = _ajustes(casa, contagem)
            assert [m.quantity for m in ajustes] == [Decimal("10.000")], (
                "um movimento registado não pode mascarar uma discrepância real"
            )
            assert StockLevel.objects.get(
                lot=lote, location=casa.armazem
            ).quantity == Decimal("100.000")

    def test_o_empate_no_instante_da_contagem_entra_na_base(self):
        """`occurred_at == counted_at` entra (`≤`): a base é tudo até à observação."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            linha = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("100"), user_name="Ana Dona",
            )
            # Um movimento ao segundo exacto da observação: entra na base, logo
            # os livros passam a dizer 90 e os 100 contados são uma sobra.
            _movimento(casa, farinha, casa.armazem, lote, quantidade=Decimal("-10"),
                       tipo="consumption", quando=linha.counted_at)
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Empate ao segundo.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )

            assert [m.quantity for m in _ajustes(casa, contagem)] == [Decimal("10.000")]

    def test_a_base_le_se_por_occurred_at_e_nunca_pela_ordem_de_insercao(self):
        """A fatura que entra às 9h com data de 7h30 muda a base de uma contagem das 8h.

        É o caso que obriga a recalcular a base **no fecho**: gravá-la na
        abertura ou no `POST` da linha deixava de fora um documento que ainda
        não existia. O `created_at` é posterior ao `counted_at` e o
        `occurred_at` é anterior — é o segundo que manda.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            linha = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("100"), user_name="Ana Dona",
            )
            assert linha.quantity_expected == Decimal("100"), "à hora de contar, 100"

            _movimento(casa, farinha, casa.armazem, lote, quantidade=Decimal("20"),
                       tipo="receipt", quando=linha.counted_at - timedelta(minutes=30))
            previsto = planear_fecho(tenant_id=casa.tenant.id, contagem=contagem)
            assert previsto.loss_eur == Decimal("0.02"), "20 × 0,001 € em falta"

            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="A fatura das 7h30 entrou depois de contarmos.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            assert [m.quantity for m in _ajustes(casa, contagem)] == [Decimal("-20.000")]

    @pytest.mark.parametrize("fechar_primeiro", ["armazem", "cozinha"])
    def test_as_duas_pernas_da_transferencia_dao_zero_em_qualquer_ordem(
        self, fechar_primeiro: str
    ):
        """Contadas as duas localizações depois da transferência, nenhuma a corrige.

        É o erro que esta ADR tornaria alcançável ao permitir duas contagens ao
        mesmo tempo: −10 de um lado e +10 do outro, com o total do
        estabelecimento certo e **nenhum relatório agregado a apanhá-lo**.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = _lote(casa, farinha, codigo="F", dias=10)
            _movimento(casa, farinha, casa.armazem, lote, quantidade=Decimal("100"),
                       tipo="receipt", quando=agora - timedelta(hours=6))
            _movimento(casa, farinha, casa.cozinha, lote, quantidade=Decimal("50"),
                       tipo="receipt", quando=agora - timedelta(hours=6))

            arca = abrir_contagem(tenant_id=casa.tenant.id, location_id=casa.armazem.id)
            despensa = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.cozinha.id
            )
            _transferir(casa, farinha, lote, de=casa.armazem, para=casa.cozinha,
                        quantidade=Decimal("10"), quando=agora - timedelta(hours=3))

            for contagem, contado in ((arca, Decimal("90")), (despensa, Decimal("60"))):
                registar_linha_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem,
                    product_id=farinha.id, quantity=contado, user_name="Ana Dona",
                )

            ordem = (arca, despensa) if fechar_primeiro == "armazem" else (despensa, arca)
            for contagem in ordem:
                fechar_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem,
                    reason="As duas batem certo.",
                    user_id=casa.dono.id, user_name="Ana Dona",
                )

            assert _ajustes(casa, arca) == []
            assert _ajustes(casa, despensa) == []
            niveis = {
                nivel.location_id: nivel.quantity
                for nivel in StockLevel.objects.filter(
                    tenant_id=casa.tenant.id, product=farinha
                )
            }
            assert niveis == {
                casa.armazem.id: Decimal("90.000"),
                casa.cozinha.id: Decimal("60.000"),
            }

    def test_a_recontagem_reescreve_o_esperado_com_o_contado_e_a_hora(self):
        """A tripla é atómica: `expected`, `counted` e `counted_at` movem-se juntos.

        O esperado deixou de ser congelado uma vez: é re-instantâneo em **cada**
        observação, e uma recontagem que não o reescrevesse comparava o número
        novo com os livros de uma hora que já passou.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            primeira = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("100"), user_name="Ana Dona",
            )
            assert (primeira.quantity_expected, primeira.quantity_counted) == (
                Decimal("100"),
                Decimal("100"),
            )

            _transferir(casa, farinha, lote, de=casa.armazem, para=casa.cozinha,
                        quantidade=Decimal("10"), quando=agora - timedelta(hours=3))
            segunda = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("90"),
                user_name="João Colaborador",
            )

            assert segunda.pk == primeira.pk, "continua a ser uma linha só"
            assert segunda.quantity_expected == Decimal("90"), "o esperado é re-instantâneo"
            assert segunda.quantity_counted == Decimal("90")
            assert segunda.counted_at > primeira.counted_at
            # E o invariante da tripla, lido da base e não do objeto em memória.
            for linha in StockCountLine.objects.filter(stock_count=contagem):
                assert (linha.quantity_counted is None) == (linha.counted_at is None)

            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Recontámos depois da transferência.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            assert _ajustes(casa, contagem) == []

    def test_a_linha_por_contar_nao_tem_corte_e_por_isso_nao_afirma_nada(self):
        """Sem `counted_at` não há base, logo não há afirmação — nem com stock a mexer.

        A contagem parcial fica mais coerente e não menos: "ausência de
        observação não é zero" passa a ser consequência da aritmética.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            lote = self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            _transferir(casa, farinha, lote, de=casa.armazem, para=casa.cozinha,
                        quantidade=Decimal("10"), quando=agora - timedelta(hours=3))
            fechada = fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Afinal não contámos nada.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )

            assert _ajustes(casa, contagem) == []
            assert fechada.status == "closed"

    def test_uma_contagem_sem_nada_contado_nao_carimba_a_ultima_contagem(self):
        """Decisão do dono (2026-10-21): o painel não diz que a arca foi contada.

        Esta ADR tornou o fecho a forma de limpar uma contagem aberta por
        engano. Carimbar o `last_count_at` com ela era o painel a dizer que
        alguém lá foi — e é esse o número que serve para saber o que falta
        contar.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            self._armazem_com_cem(casa, farinha, agora=agora)
            vazia = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            fechar_contagem(
                tenant_id=casa.tenant.id, contagem=vazia,
                reason="Aberta por engano.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            assert ultima_contagem_fechada_em(tenant_id=casa.tenant.id) is None

            a_serio = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=a_serio,
                product_id=farinha.id, quantity=Decimal("100"), user_name="Ana Dona",
            )
            fechada = fechar_contagem(
                tenant_id=casa.tenant.id, contagem=a_serio,
                reason="Esta contou-se.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            assert ultima_contagem_fechada_em(
                tenant_id=casa.tenant.id
            ) == fechada.closed_at

    def test_o_ajuste_acontece_na_hora_do_fecho_e_nao_na_da_contagem(self):
        """Decisão do dono: o `occurred_at` do ajuste é o fecho — o ajuste é uma decisão.

        O instante da observação não se perde: vive no `counted_at` da linha.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            self._armazem_com_cem(casa, farinha, agora=agora)
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            linha = registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=farinha.id, quantity=Decimal("95"), user_name="Ana Dona",
            )
            fechada = fechar_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                reason="Faltaram cinco.",
                user_id=casa.dono.id, user_name="Ana Dona",
            )
            ajuste = _ajustes(casa, contagem)[0]
            assert ajuste.occurred_at == fechada.closed_at
            assert ajuste.occurred_at > linha.counted_at

    def test_nenhuma_linha_desta_fatia_tem_lote_e_o_corte_depende_disso(self):
        """Invariante presa: `lot IS NULL` em toda a `StockCountLine` desta fatia.

        O corte é chaveado **por artigo** — o `_bases_do_corte` monta
        `{linha.product_id: linha.counted_at}` — e a base **permite** duas
        linhas do mesmo artigo com lotes diferentes: o `lot` é nullable e a
        restrição única é `(tenant, contagem, artigo, lote)` com
        `nulls_distinct=False`, logo o par `(A, lote1)` e `(A, lote2)` passa
        sem reclamação nenhuma. Nesse dia uma das duas recebe **em silêncio** o
        corte da outra — base errada, ajuste errado gravado num ledger
        append-only, e nenhuma exceção em lado nenhum para alguém reparar.

        O que impede o caso hoje não é a base: é **nenhum caminho desta fatia
        escrever `lot`**, nem o da abertura (a linha é por artigo, com os lotes
        somados) nem o do `POST /lines` (os dois ramos do upsert criam e
        procuram com `lot=None`). É isso que este teste prende, e é por isso
        que ele falha no commit que introduzir contar por lote, em vez de o
        erro sair como um ajuste errado em produção.

        **Onde se corrige quando cair** (contar por lote é fatia própria, ADR
        0030): no `count_services._bases_do_corte`, chaveando o corte por
        `linha.id` em vez de `linha.product_id` — ou agrupando as linhas do
        mesmo artigo e pedindo um corte por grupo, porque o
        `selectors.saldos_por_artigo_ate` também soma por artigo. **A chave não
        se muda agora**: hoje não há caso que a exercite, e mudá-la sem caso
        era correcção sem teste.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha", track_lots=True)
        canela = _artigo(casa, nome="Canela")
        agora = timezone.now()
        with tenant_scope(casa.tenant.id):
            # A base deixa: a coluna existe e aceita um lote. Quem a mantém a
            # `NULL` é o código, e é o código que este teste mede.
            assert StockCountLine._meta.get_field("lot").null is True

            lote_a = _lote(casa, farinha, codigo="A", dias=10)
            lote_b = _lote(casa, farinha, codigo="B", dias=30)
            _movimento(casa, farinha, casa.armazem, lote_a, quantidade=Decimal("40"),
                       tipo="receipt", quando=agora - timedelta(hours=6))
            _movimento(casa, farinha, casa.armazem, lote_b, quantidade=Decimal("60"),
                       tipo="receipt", quando=agora - timedelta(hours=5))

            # (1) Abertura: dois lotes do mesmo artigo dão **uma** linha.
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id, location_id=casa.armazem.id
            )
            assert _linha(contagem, farinha).quantity_expected == Decimal("100")

            # (2) Contar essa linha e (3) recontá-la: o upsert não cria a segunda.
            for quantidade in (Decimal("95"), Decimal("97")):
                registar_linha_contagem(
                    tenant_id=casa.tenant.id, contagem=contagem,
                    product_id=farinha.id, quantity=quantidade, user_name="Ana Dona",
                )
            # (4) Um artigo que não estava na lista: a linha nasce no `POST /lines`.
            registar_linha_contagem(
                tenant_id=casa.tenant.id, contagem=contagem,
                product_id=canela.id, quantity=Decimal("3"), user_name="Ana Dona",
            )

            linhas = list(StockCountLine.objects.filter(stock_count=contagem))
            assert len(linhas) == 2, "um artigo com dois lotes continua a ser uma linha"
            assert all(linha.lot_id is None for linha in linhas)
            # E a mesma pergunta sem passar pela contagem, para apanhar um
            # caminho de escrita novo que não seja nenhum dos quatro acima.
            assert not StockCountLine.objects.filter(lot__isnull=False).exists()

            # O corte não colide porque as chaves são distintas — é a leitura
            # que o `_bases_do_corte` faz, aqui à vista.
            cortes = {
                linha.product_id: linha.counted_at
                for linha in linhas
                if linha.counted_at is not None
            }
            assert len(cortes) == len([lin for lin in linhas if lin.counted_at])

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

        # 4,250 **kg** — o corpo fala na unidade de contagem da linha
        # (`count_unit`), que é a de apresentação do artigo. Quem conta escreve o
        # que o rótulo do campo diz; a conversão para gramas é do servidor.
        contou = dono.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(casa.farinha.id), "quantity": "4.250"},
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

    def test_a_segunda_contagem_da_mesma_localizacao_da_409_com_o_id_da_primeira(self):
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        primeira = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        )
        assert primeira.status_code == 201

        segunda = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        )
        assert segunda.status_code == 409
        assert segunda.json()["code"] == CODIGO_CONTAGEM_JA_ABERTA
        assert segunda.json()["id"] == primeira.json()["id"]
        # A frase nomeia a localização: o código é o mesmo, o significado é "já
        # há uma aberta **nesta** localização" (ADR 0033, decisão 1).
        assert "Armazém" in segunda.json()["detail"]

        # E a localização ao lado abre na mesma, ao mesmo tempo.
        outra = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.cozinha.id)}, format="json"
        )
        assert outra.status_code == 201, outra.content

    def test_a_lista_filtra_por_estado(self):
        """`?status=open|closed` — o cliente deixa de adivinhar qual é "a" aberta."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        aberta = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]
        a_fechar = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.cozinha.id)}, format="json"
        ).json()["id"]
        dono.post(
            f"/api/v1/stock/counts/{a_fechar}/closing",
            {"reason": "Contada e fechada."},
            format="json",
        )

        abertas = dono.get("/api/v1/stock/counts?status=open").json()
        assert [c["id"] for c in abertas["results"]] == [aberta]
        fechadas = dono.get("/api/v1/stock/counts?status=closed").json()
        assert [c["id"] for c in fechadas["results"]] == [a_fechar]
        assert dono.get("/api/v1/stock/counts").json()["count"] == 2
        # Um estado que não existe é recusa e não uma lista a fingir que filtrou.
        recusa = dono.get("/api/v1/stock/counts?status=aberta")
        assert recusa.status_code == 400
        assert "status" in recusa.json()

    def test_quem_conta_tambem_abre_mas_continua_a_nao_fechar(self):
        """ADR 0033, decisão 2: desaparecida a escassez, desaparece a razão de restringir.

        O custo está nomeado: alguém abre a contagem errada, e limpá-la é um
        fecho de `owner|manager` — **sem nada contado não escreve movimento
        nenhum**, logo a limpeza é inerte no ledger.
        """
        casa = self._casa_com_stock()
        staff = _sessao(casa.colaborador.email)

        aberta = staff.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        )
        assert aberta.status_code == 201, aberta.content
        contagem_id = aberta.json()["id"]
        assert aberta.json()["closing_role"] == "Dono ou gerente"
        # Abrir não revela euro nenhum: o 201 passa pelo mesmo mixin.
        assert aberta.json()["closing_reason"] is None

        assert staff.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "Eu abri, eu fecho."},
            format="json",
        ).status_code == 403
        with tenant_scope(casa.tenant.id):
            assert StockCount.objects.filter(pk=contagem_id, status="open").exists()

    def test_o_counted_at_e_sempre_do_servidor_e_nunca_do_corpo(self):
        """É carga aritmética: move a base do ajuste, logo não se aceita de quem conta."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        antes = timezone.now()
        contou = dono.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {
                "product": str(casa.farinha.id),
                "quantity": "4.250",
                "counted_at": "2020-01-01T00:00:00Z",
            },
            format="json",
        )
        assert contou.status_code == 200, contou.content
        with tenant_scope(casa.tenant.id):
            linha = _linha(StockCount.objects.get(pk=contagem_id), casa.farinha)
        assert linha.counted_at >= antes, "a hora é a do servidor, não a do corpo"

    def test_os_papeis_do_contrato(self):
        """Abrir e contar são de toda a gente; pré-ver e fechar não são (ADR 0033)."""
        casa = self._casa_com_stock()
        dono = _sessao(casa.dono.email)
        staff = _sessao(casa.colaborador.email)

        contagem_id = dono.post(
            "/api/v1/stock/counts", {"location": str(casa.armazem.id)}, format="json"
        ).json()["id"]

        # Contar: o `staff` pode, e é esse o ponto da fatia.
        contou = staff.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(casa.farinha.id), "quantity": "4.250"},
            format="json",
        )
        assert contou.status_code == 200, contou.content
        # **Ausente** e não `null`: a ADR 0032, decisão 5, trocou a forma. O
        # `null` da ADR 0030 dizia ao mesmo tempo "ainda não contado" e "não te
        # é mostrado"; a chave ausente diz a segunda e deixa o `null` com um
        # significado só.
        assert "difference_eur" not in contou.json(), "euros não, lista sim"
        assert contou.json()["counted_by"] == "João Colaborador"

        # Regra 14: a lista é dele, os euros não.
        linhas = staff.get(f"/api/v1/stock/counts/{contagem_id}/lines")
        assert linhas.status_code == 200
        assert "difference_eur" not in linhas.json()["results"][0]
        assert linhas.json()["results"][0]["counted"]["base"] == "4250.000"

        assert dono.get(
            f"/api/v1/stock/counts/{contagem_id}/lines"
        ).json()["results"][0]["difference_eur"] == "-0.90"

        assert staff.get(
            f"/api/v1/stock/counts/{contagem_id}/closing"
        ).status_code == 403

        # A justificação do fecho cita o valor ("faltaram 750 g, 0,90 €"), logo
        # segue a mesma fronteira dos euros: esconder a diferença e deixar
        # passar a frase que a descreve era fingir (decisão do dono, 2026-10-19).
        dono.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "Faltaram 750 g de farinha, 0,90 €."},
            format="json",
        )
        do_staff = staff.get("/api/v1/stock/counts").json()["results"][0]
        assert do_staff["closing_reason"] is None
        assert do_staff["status"] == "closed", "fechada vê-se; o porquê em euros não"
        assert dono.get("/api/v1/stock/counts").json()["results"][0][
            "closing_reason"
        ] == "Faltaram 750 g de farinha, 0,90 €."
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
        # O fecho é a única rota que **escreve no ledger**: faltava aqui, e um
        # refactor que contornasse o `get_object()` passava em silêncio
        # (revisão de segurança de 2026-10-19).
        assert dono.post(
            f"/api/v1/stock/counts/{alheia.pk}/closing",
            {"reason": "Fechar a do vizinho."},
            format="json",
        ).status_code == 404
        with tenant_scope(vizinha.tenant.id):
            alheia.refresh_from_db()
        assert alheia.status == "open"
        assert dono.get("/api/v1/stock/counts").json()["count"] == 0

    def test_abrir_na_localizacao_do_vizinho_e_400_igual_ao_de_um_uuid_inventado(self):
        """A rota que a ADR 0033 abriu a **todos os papéis**, vista do outro estabelecimento.

        `POST /stock/counts` deixou de ser de `owner|manager` (decisão 2), e o
        `location` é o único argumento que o cliente escolhe: é por aí que uma
        fronteira de tenant se atravessa, se alguém a esquecer. O
        `abrir_contagem` resolve a localização com
        `Location.objects.filter(tenant_id=..., pk=..., is_active=True)`
        **antes** de qualquer insert, logo a localização do vizinho não existe
        para este pedido e a recusa chega sem nada escrito.

        **O que este teste prende é o comportamento, e não aquele filtro** — e
        isso foi medido, não assumido: tirando o `tenant_id=tenant_id` da linha
        acima, este teste **continua a passar**. Quem recusa é a **RLS**, que
        filtra a `locations` dentro do `tenant_scope` antes de o ORM ver fosse o
        que fosse (ADR 0007). O filtro do ORM é a segunda camada e não a
        primeira, e é por isso que o `tests/test_rls_isolation.py` existe: é lá
        que a ausência de uma política dói. Aqui mede-se o que a rota responde,
        que é o que um cliente consegue observar.

        O que este teste prende não é só o 400: é a **igualdade das duas
        respostas**. Uma localização real de outro estabelecimento e um UUID
        que nunca existiu têm de dar a mesma frase — se a do vizinho dissesse
        "inativa" e a inventada "não encontrada", a rota passava a ser um
        oráculo de existência: um `staff` percorria UUIDs e sabia quais são
        localizações reais lá fora. É um 400 e não um 404 porque o recurso do
        pedido é a contagem (que não chegou a existir), e o `location` é um
        campo do corpo que não validou — a forma do DRF, por campo.
        """
        casa = self._casa_com_stock()
        vizinha = _casa(nome="Café do Lado")
        staff = _sessao(casa.colaborador.email)

        do_vizinho = staff.post(
            "/api/v1/stock/counts",
            {"location": str(vizinha.armazem.id)},
            format="json",
        )
        inventada = staff.post(
            "/api/v1/stock/counts",
            {"location": str(uuid4())},
            format="json",
        )

        assert do_vizinho.status_code == 400, do_vizinho.content
        assert inventada.status_code == 400, inventada.content
        assert do_vizinho.json() == inventada.json(), (
            "a frase de uma localização real do vizinho tem de ser a mesma de "
            "um UUID que nunca existiu — a diferença seria um oráculo de existência"
        )
        assert set(do_vizinho.json()) == {"location"}
        # E a frase não deixa escapar o que negou conhecer.
        frase = " ".join(do_vizinho.json()["location"])
        assert vizinha.armazem.name not in frase
        assert str(vizinha.armazem.id) not in frase

        # Nada escrito, de nenhum dos dois lados: a resolução da localização
        # acontece antes do primeiro insert.
        with tenant_scope(casa.tenant.id):
            assert not StockCount.objects.exists()
        with tenant_scope(vizinha.tenant.id):
            assert not StockCount.objects.exists()
        # E a lista de cada um continua vazia, vista por HTTP.
        assert staff.get("/api/v1/stock/counts").json()["count"] == 0
        assert _sessao(vizinha.dono.email).get(
            "/api/v1/stock/counts"
        ).json()["count"] == 0

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


# ---------------------------------------------------------------------------
# O nome de quem age é o da pertença, nunca o email (2026-10-19)
#
# A mesma classe de fuga que se corrigiu nas receções, do outro lado: o
# `inventory` gravava (nos movimentos manuais) e derivava (no resumo de uma
# contagem) o **email** de quem agiu. Esse resumo é servido pelo assistente a
# qualquer dos três papéis, logo era o endereço de um colega a sair numa
# resposta sobre uma contagem. Um email é a credencial de login de alguém e não
# o nome dela neste estabelecimento.
#
# Os valores já gravados ficam como estão — é uma coluna de histórico, e
# reescrevê-la era mentir sobre o passado (a mesma regra do ledger). Por isso
# não há migração de dados, e o que estes testes medem é a escrita nova.
# ---------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
class TestONomeDeQuemAgeNaoEUmEmail:
    """O `display_name` da pertença, e nada quando ele não existe."""

    def test_o_resumo_de_uma_contagem_traz_o_nome_da_pertenca(self):
        from apps.inventory.api import contagem_por_id, listar_contagens

        casa = _casa(nome="Contagem com nome")
        with tenant_scope(casa.tenant.id):
            contagem = abrir_contagem(
                tenant_id=casa.tenant.id,
                location_id=casa.armazem.id,
                user_id=casa.dono.id,
            )
            fechar_contagem(
                tenant_id=casa.tenant.id,
                contagem=contagem,
                reason="conferido ao cêntimo",
                user_id=casa.colaborador.id,
                user_name="João Colaborador",
            )
            resumos, _ = listar_contagens(tenant_id=casa.tenant.id)
            detalhe = contagem_por_id(
                tenant_id=casa.tenant.id, stock_count_id=contagem.id
            )

        assert resumos[0].created_by_name == "Ana Dona"
        assert resumos[0].closed_by_name == "João Colaborador"
        assert detalhe.resumo.created_by_name == "Ana Dona"
        for nome in (resumos[0].created_by_name, resumos[0].closed_by_name):
            assert "@" not in nome, "o email de quem agiu não sai no resumo"

    def test_um_movimento_manual_sem_nome_fica_sem_nome_e_nunca_com_o_email(self):
        """Sem `user_name` fica vazio: o email não é um nome e não serve de recurso."""
        from apps.inventory.services import registar_waste

        casa = _casa(nome="Movimento sem nome")
        produto = _artigo(casa)

        with tenant_scope(casa.tenant.id):
            lote = _lote(casa, produto, codigo=f"__{produto.id}__", dias=30)
            _receber(
                casa, produto, casa.armazem, lote, quantidade=Decimal("1000"), custo=Decimal("2")
            )
            # Uma lista desde a ADR 0034, decisão 8: a quebra reparte-se por
            # lotes e o 201 é sempre `{movements: [...]}`, mesmo com um só.
            [movimento_id] = registar_waste(
                tenant_id=casa.tenant.id,
                product_id=produto.id,
                location_id=casa.armazem.id,
                quantity=Decimal("100"),
                lot_id=None,
                reason="spoiled",
                reason_detail="",
                user=casa.colaborador,
            )
            movimento = StockMovement.objects.get(pk=movimento_id)

        assert movimento.created_by_name == ""
        assert casa.colaborador.email not in movimento.created_by_name
