"""O painel de gestão: os três endpoints e a aritmética que está por baixo.

Doze testes, e cada um existe por um modo de falha nomeado pelo `domain-expert`
antes de haver código (ADR 0029). O que eles afirmam, por ordem:

1. a identidade da ADR 0013 decisão 4 fecha **antes** do arredondamento
   (exactamente zero, o que é uma prova de classificação) e **depois**, nos
   números servidos;
2. os nove tipos de movimento: `production_*` e `transfer_*` não mexem em
   nenhum dos quatro termos — e a exclusão é por tipo, não por se assumir que
   as pernas se anulam;
3. o desperdício está **dentro** da mercadoria consumida, e a soma dos motivos
   é o total ao cêntimo;
4. o sinal da quebra desconhecida: negativo no ledger é positivo no ecrã, e um
   excedente de contagem sai negativo **sem clamp**;
5. um período sem ajustes dá quebra zero — e é por isso que o `last_count_at`
   viaja ao lado: zero sem contagem não é boa notícia;
6. o `last_count_at` ignora contagens abertas e é o máximo entre localizações;
7. uma nota de crédito de devolução reduz as compras **no período do
   movimento**, e compras negativas servem-se como são;
8. um custo estimado conta nas compras **e** aparece decomposto, sem a
   identidade deixar de fechar;
9. `Σ(points) == total_eur`, incluindo nos dois domingos em que o relógio muda;
10. a fronteira do mês de negócio, e `/summary?period=month` == `/month`;
11. o que não se sabe é `null` e o porquê viaja em `unavailable`;
12. as três views respondem 403 a quem não é dono.

## Duas formas de teste, de propósito

Os que afirmam **aritmética** chamam o `selectors.py` dentro de um
`tenant_scope` aberto pela fixture: é onde os números nascem e é onde um erro
de sinal se vê sem passar por HTTP. Os que afirmam **contrato** (10, 11, 12)
passam pelo cliente autenticado, porque o que eles medem é o payload e a
permissão — e isso inclui o serializer, que é onde um `null` se transforma num
`"0.00"` sem ninguém dar por ela.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product
from apps.inventory.models import (
    Location,
    StockCount,
    StockCountLine,
    StockLevel,
    StockMovement,
)
from apps.reporting import periodos, selectors
from apps.shared.db import tenant_scope

CREDENCIAL = "painel-teste-123456"
INICIO_DO_DIA = time(4, 0)

#: Os dois domingos de 2026 em que o relógio muda em Lisboa: o de março tem 23
#: horas e o de outubro 25. É neles que um balde calculado em UTC põe um dia
#: inteiro no sítio errado.
DOMINGO_DE_MARCO = datetime(2026, 3, 29)
DOMINGO_DE_OUTUBRO = datetime(2026, 10, 25)


# ---------------------------------------------------------------------------
# Andaimes
# ---------------------------------------------------------------------------
@pytest.fixture
def painel(db: None) -> Iterator[Ambiente]:
    """Um estabelecimento com dono, encarregado, operação, local e artigo.

    Cede com o âmbito **aberto**: os testes de aritmética chamam selectors que
    leem tabelas com política, e o guarda do `conftest.py` recusa qualquer DML
    fora de `tenant_scope`.
    """
    tenant = criar_tenant(name="Pastelaria do Painel")
    with tenant_scope(tenant.id):
        papeis = {}
        for papel, email in (
            (Papel.OWNER, "dona@painel.pt"),
            (Papel.MANAGER, "encarregado@painel.pt"),
            (Papel.STAFF, "balcao@painel.pt"),
        ):
            utilizador = User.objects.create_user(email, CREDENCIAL)
            conceder_pertenca(
                user=utilizador,
                tenant_id=tenant.id,
                role=papel,
                display_name=email.split("@")[0],
            )
            papeis[papel] = email
        local = Location.objects.create(tenant=tenant, name="Loja", position=1)
        artigo = Product.objects.create(
            tenant=tenant,
            short_name="Farinha",
            base_unit="kg",
            display_unit="kg",
            display_factor=Decimal("1"),
        )
        yield Ambiente(
            tenant_id=tenant.id, local=local, artigo=artigo, emails=papeis
        )


class Ambiente:
    """O que cada teste precisa de ter à mão. Não é um DTO de domínio."""

    def __init__(
        self, *, tenant_id: UUID, local: Location, artigo: Product, emails: dict
    ) -> None:
        self.tenant_id = tenant_id
        self.local = local
        self.artigo = artigo
        self.emails = emails

    def movimento(
        self,
        tipo: str,
        quantidade: str,
        *,
        custo: str = "1.00",
        quando: datetime | None = None,
        reason: str = "",
        estimado: bool = False,
    ) -> StockMovement:
        """Uma linha no ledger. `quando` é local e ingénuo; aqui torna-se ciente."""
        instante = timezone.now() if quando is None else timezone.make_aware(quando)
        return StockMovement.objects.create(
            tenant_id=self.tenant_id,
            product=self.artigo,
            location=self.local,
            movement_type=tipo,
            quantity=Decimal(quantidade),
            unit_cost=Decimal(custo),
            cost_is_estimate=estimado,
            reason=reason,
            occurred_at=instante,
            created_by_name="teste",
        )

    def janela(self, *, key: str = "30d", desde: datetime, ate: datetime) -> periodos.Janela:
        """Uma janela explícita, para os testes não dependerem do relógio."""
        return periodos.Janela(
            key=key,
            desde=timezone.make_aware(desde),
            ate=timezone.make_aware(ate),
            inicio_do_dia=INICIO_DO_DIA,
        )

    def resumo(self, janela: periodos.Janela) -> selectors.SummaryOut:
        return selectors.resumo_do_periodo(
            tenant_id=self.tenant_id, janela=janela, vat_regime="normal"
        )


def contagem_fechada(painel: Ambiente, *, local: Location, quando: datetime) -> StockCount:
    """Uma contagem fechada **com uma linha contada**, que é o que o painel conta.

    Uma contagem fechada sem nenhuma linha contada deixou de carimbar o
    `last_count_at` (ADR 0033, decisão do dono de 2026-10-21): o fecho passou a
    ser a forma de limpar uma contagem aberta por engano, e sem esta regra o
    painel dizia que a arca foi contada sem ninguém lá ter ido.
    """
    contagem = StockCount.objects.create(
        tenant_id=painel.tenant_id,
        location=local,
        status="closed",
        closed_at=timezone.make_aware(quando),
    )
    StockCountLine.objects.create(
        tenant_id=painel.tenant_id,
        stock_count=contagem,
        product=painel.artigo,
        quantity_expected=Decimal("1"),
        quantity_counted=Decimal("1"),
        counted_at=contagem.closed_at,
    )
    return contagem


def janela_larga() -> tuple[datetime, datetime]:
    """Uma janela que apanha tudo o que os testes escrevem em 2026."""
    return datetime(2026, 1, 1, 4, 0), datetime(2027, 1, 1, 4, 0)


def autenticar(email: str) -> APIClient:
    """Sessão por cookie, como o cliente a faz."""
    navegador = Client()
    resposta = navegador.post(
        "/api/v1/auth/login",
        {"email": email, "password": CREDENCIAL},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    cliente = APIClient()
    for chave, valor in resposta.cookies.items():
        cliente.cookies[chave] = valor.value
    return cliente


# ---------------------------------------------------------------------------
# 1 e 2 — a identidade e os nove tipos
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_identidade_fecha_antes_e_depois_do_arredondamento(painel: Ambiente) -> None:
    """`stock_change == purchases − goods_consumed − unknown_shrinkage`, duas vezes.

    O custo tem seis casas de propósito: é com ele que a soma exacta e a soma
    arredondada deixam de coincidir, e é aí que uma linha "diferença" nasceria
    se o arredondamento acontecesse por movimento.
    """
    painel.movimento("receipt", "7", custo="1.234567", quando=datetime(2026, 5, 2, 10))
    painel.movimento("consumption", "-3", custo="1.234567", quando=datetime(2026, 5, 3, 10))
    painel.movimento(
        "waste", "-1", custo="1.234567", quando=datetime(2026, 5, 4, 10), reason="expired"
    )
    painel.movimento("adjustment", "-2", custo="1.234567", quando=datetime(2026, 5, 5, 10))

    desde, ate = janela_larga()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    bruto = resumo.bruto

    # Antes: exactamente zero. Não é uma tolerância — é uma afirmação sobre a
    # classificação dos tipos.
    assert bruto.variacao - (
        bruto.purchases - bruto.goods_consumed - bruto.unknown_shrinkage
    ) == Decimal("0")
    # E os termos são os que a tabela da ADR 0014 manda.
    assert bruto.purchases == Decimal("8.641969")
    assert bruto.goods_consumed == Decimal("4.938268")
    assert bruto.unknown_shrinkage == Decimal("2.469134")

    # Depois: nos números servidos, com duas casas.
    assert resumo.stock_change_eur == (
        resumo.purchases_eur - resumo.goods_consumed_eur - resumo.unknown_shrinkage_eur
    )
    assert resumo.purchases_eur == Decimal("8.64")
    assert resumo.goods_consumed_eur == Decimal("4.94")
    assert resumo.unknown_shrinkage_eur == Decimal("2.47")
    assert resumo.stock_change_eur == Decimal("1.23")


@pytest.mark.django_db
def test_producao_e_transferencia_ficam_fora_dos_quatro_termos(painel: Ambiente) -> None:
    """Os nove tipos no ledger, e só cinco são evento económico (ADR 0014).

    As pernas de produção e de transferência anulam-se **ao nível do tenant**,
    o que torna este teste fraco se as quantidades forem simétricas: por isso
    são assimétricas em valor (a produção entra ao custo das pernas que a
    produziram, e a transferência move quantidades diferentes de propósito).
    Um termo que as apanhasse mudava de valor.
    """
    quando = datetime(2026, 5, 10, 10)
    painel.movimento("receipt", "10", custo="2.00", quando=quando)
    painel.movimento("consumption", "-4", custo="2.00", quando=quando)
    # Produção: saem 2 kg de farinha, entra 1 kg de massa ao dobro do custo.
    painel.movimento("production_out", "-2", custo="2.00", quando=quando)
    painel.movimento("production_in", "1", custo="4.00", quando=quando)
    # Transferência: as duas pernas com o mesmo valor, mas tipos distintos.
    painel.movimento("transfer_out", "-3", custo="2.00", quando=quando)
    painel.movimento("transfer_in", "3", custo="2.00", quando=quando)

    desde, ate = janela_larga()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))

    assert resumo.purchases_eur == Decimal("20.00")
    assert resumo.goods_consumed_eur == Decimal("8.00")
    assert resumo.unknown_shrinkage_eur == Decimal("0.00")
    assert resumo.stock_change_eur == Decimal("12.00")
    # E a identidade continua a fechar antes do arredondamento: o `variacao`
    # exclui os quatro tipos, logo não traz o custo da produção lá para dentro.
    assert resumo.bruto.variacao == Decimal("12.00")


# ---------------------------------------------------------------------------
# 3 — o desperdício está dentro da mercadoria consumida
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_desperdicio_dentro_do_consumo_e_motivos_somam_ao_total(painel: Ambiente) -> None:
    """`waste ≤ goods_consumed` e `Σ(waste_by_reason) == waste_eur`, ao cêntimo."""
    quando = datetime(2026, 5, 12, 10)
    painel.movimento("consumption", "-10", custo="1.11", quando=quando)
    painel.movimento("waste", "-3", custo="1.11", quando=quando, reason="expired")
    painel.movimento("waste", "-2", custo="1.11", quando=quando, reason="spoiled")
    painel.movimento("waste", "-1", custo="1.11", quando=quando, reason="breakage")

    desde, ate = janela_larga()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))

    assert resumo.goods_consumed_eur == Decimal("17.76")
    assert resumo.waste_eur == Decimal("6.66")
    assert resumo.waste_eur <= resumo.goods_consumed_eur
    assert sum(linha.amount_eur for linha in resumo.waste_by_reason) == resumo.waste_eur
    # Ordenada pelo servidor, a maior primeiro.
    assert [linha.reason for linha in resumo.waste_by_reason] == [
        "expired",
        "spoiled",
        "breakage",
    ]
    # O desperdício é decomposição e não parcela: não soma ao total.
    dentro = {linha.id: linha for linha in resumo.costs}
    assert dentro["waste"].part_of == "goods_consumed"
    assert dentro["waste"].is_part_of_total is False
    assert dentro["goods_consumed"].is_part_of_total is True


# ---------------------------------------------------------------------------
# 4 e 5 — o sinal da quebra desconhecida
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_ajuste_negativo_e_quebra_positiva_e_o_excedente_nao_leva_clamp(
    painel: Ambiente,
) -> None:
    """O ledger grava a falta a negativo; o ecrã lê "positivo = quebra".

    E quando o líquido dos ajustes é positivo — mais stock do que o sistema
    sabia — o campo fica **negativo**. Sem clamp e sem mudar de campo: é um
    excedente de contagem e o ecrã dá-lhe outra palavra, não outro número.
    """
    desde, ate = janela_larga()
    painel.movimento("adjustment", "-5", custo="2.00", quando=datetime(2026, 5, 14, 10))
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    assert resumo.unknown_shrinkage_eur == Decimal("10.00")

    # O ajuste manual da ADR 0025 entra pela mesma porta: o que conta é o tipo.
    painel.movimento("adjustment", "12", custo="2.00", quando=datetime(2026, 5, 15, 10))
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    assert resumo.unknown_shrinkage_eur == Decimal("-14.00")
    assert resumo.stock_change_eur == Decimal("14.00")

    excedente = {linha.id: linha for linha in resumo.costs}["unknown_shrinkage"]
    assert excedente.amount_eur == Decimal("-14.00")
    assert excedente.is_part_of_total is False
    assert excedente.share == Decimal("0.000")


@pytest.mark.django_db
def test_sem_ajustes_a_quebra_e_zero_e_a_contagem_diz_porque(painel: Ambiente) -> None:
    """Zero quebra não é boa notícia: é ausência de contagem, e o campo ao lado di-lo."""
    painel.movimento("consumption", "-2", quando=datetime(2026, 5, 16, 10))
    desde, ate = janela_larga()

    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    assert resumo.unknown_shrinkage_eur == Decimal("0.00")
    assert resumo.data_quality.last_count_at is None

    fechada = contagem_fechada(
        painel, local=painel.local, quando=datetime(2026, 5, 16, 20)
    )
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    assert resumo.unknown_shrinkage_eur == Decimal("0.00")
    assert resumo.data_quality.last_count_at == fechada.closed_at


# ---------------------------------------------------------------------------
# 6 — o last_count_at
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_ultima_contagem_ignora_abertas_e_devolve_o_maximo(painel: Ambiente) -> None:
    """Fechadas e não iniciadas: é o fecho que gera os ajustes.

    Com duas localizações o campo é o **máximo**, e não o da última
    localização a ser contada: a pergunta é "quando é que se contou pela última
    vez", não "quando é que esta prateleira foi contada".
    """
    armazem = Location.objects.create(
        tenant_id=painel.tenant_id, name="Armazém", position=2
    )
    contagem_fechada(painel, local=painel.local, quando=datetime(2026, 5, 10, 18))
    mais_recente = contagem_fechada(
        painel, local=armazem, quando=datetime(2026, 5, 18, 9)
    )
    # Uma contagem aberta a que alguém pôs data sem a fechar: não conta. O que o
    # teste precisa é de uma aberta com `closed_at` preenchido, que é o caso
    # perverso; a aberta sem data está coberta pelo filtro `status="closed"`.
    # Desde a ADR 0033 há uma aberta **por localização**
    # (`inventory_stockcount_uma_aberta_por_local`), e esta é a da Loja.
    StockCount.objects.create(
        tenant_id=painel.tenant_id,
        location=painel.local,
        status="open",
        closed_at=timezone.make_aware(datetime(2026, 6, 1, 9)),
    )

    desde, ate = janela_larga()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))
    assert resumo.data_quality.last_count_at == mais_recente.closed_at


# ---------------------------------------------------------------------------
# 7 — a nota de crédito de devolução
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_devolucao_reduz_as_compras_no_periodo_do_movimento(painel: Ambiente) -> None:
    """Uma devolução reduz as compras **no mês em que a mercadoria saiu**.

    Não no da fatura original: reabrir um mês já lido pelo dono é pior do que
    um mês com compras negativas — e compras negativas servem-se como são, sem
    clamp e sem linha de correcção.
    """
    painel.movimento("receipt", "10", custo="3.00", quando=datetime(2026, 4, 20, 9))
    painel.movimento("return", "-10", custo="3.00", quando=datetime(2026, 5, 3, 9))

    abril = painel.resumo(
        painel.janela(desde=datetime(2026, 4, 1, 4), ate=datetime(2026, 5, 1, 4))
    )
    maio = painel.resumo(
        painel.janela(desde=datetime(2026, 5, 1, 4), ate=datetime(2026, 6, 1, 4))
    )

    assert abril.purchases_eur == Decimal("30.00")
    assert maio.purchases_eur == Decimal("-30.00")
    # A devolução **não** é consumo: saiu do stock e não foi usada.
    assert maio.goods_consumed_eur == Decimal("0.00")
    assert maio.stock_change_eur == Decimal("-30.00")
    # E a componente de custo serve o negativo sem o esconder.
    compras = {linha.id: linha for linha in maio.costs}["purchases"]
    assert compras.amount_eur == Decimal("-30.00")


# ---------------------------------------------------------------------------
# 8 — o custo estimado
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_custo_estimado_conta_nas_compras_e_viaja_decomposto(painel: Ambiente) -> None:
    """A mercadoria entrou: o que falta é a fatura, não a mercadoria.

    `purchases_awaiting_invoice_eur` é **decomposição e nunca parcela** — está
    dentro de `purchases_eur`. Sem isso a identidade não fecharia, porque o
    stock subiu na mesma.
    """
    painel.movimento("receipt", "4", custo="2.50", quando=datetime(2026, 5, 20, 9))
    painel.movimento(
        "receipt", "2", custo="5.00", quando=datetime(2026, 5, 21, 9), estimado=True
    )

    desde, ate = janela_larga()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))

    assert resumo.purchases_eur == Decimal("20.00")
    assert resumo.data_quality.purchases_awaiting_invoice_eur == Decimal("10.00")
    assert resumo.stock_change_eur == resumo.purchases_eur
    assert resumo.bruto.variacao == resumo.bruto.purchases


# ---------------------------------------------------------------------------
# 9 — os baldes somam o total, inclusive nos domingos de mudança de hora
# ---------------------------------------------------------------------------
@pytest.mark.django_db
@pytest.mark.parametrize("domingo", [DOMINGO_DE_MARCO, DOMINGO_DE_OUTUBRO])
def test_os_pontos_somam_o_total_mesmo_na_mudanca_de_hora(
    painel: Ambiente, domingo: datetime
) -> None:
    """`Σ(points) == total_eur`, e o dia de negócio é o certo nos dois domingos.

    O movimento das 04:30 pertence ao dia do domingo (já passou das 04:00) e o
    das 02:30 ao sábado. Com o desconto da hora feito em UTC, o de março caía
    no sábado — e o total continuava certo, que é o que torna este erro difícil
    de ver sem comparar balde a balde.
    """
    sabado = domingo - timedelta(days=1)
    painel.movimento(
        "receipt", "1", custo="10.00", quando=domingo.replace(hour=4, minute=30)
    )
    painel.movimento(
        "receipt", "1", custo="20.00", quando=domingo.replace(hour=2, minute=30)
    )
    painel.movimento(
        "receipt", "1", custo="30.00", quando=(domingo + timedelta(days=1)).replace(hour=12)
    )

    janela = painel.janela(
        key="7d",
        desde=sabado.replace(hour=4),
        ate=(domingo + timedelta(days=2)).replace(hour=4),
    )
    series = selectors.series_do_periodo(tenant_id=painel.tenant_id, janela=janela)
    serie = series.series[0]

    assert series.granularity == "day"
    assert len(series.buckets) == len(serie.points) == 3
    assert sum(ponto.value_eur for ponto in serie.points) == serie.total_eur
    assert serie.total_eur == Decimal("60.00")
    # Sábado leva o das 02:30 de domingo; domingo leva o das 04:30.
    assert [ponto.value_eur for ponto in serie.points] == [
        Decimal("20.00"),
        Decimal("10.00"),
        Decimal("30.00"),
    ]
    # E o eixo é a maior barra, com o share a reconstruir o valor.
    assert series.scale_max_eur == Decimal("30.00")
    assert serie.points[2].share == Decimal("1.000")


@pytest.mark.django_db
def test_os_pontos_somam_o_total_tambem_com_baldes_de_semana(painel: Ambiente) -> None:
    """A granularidade é do servidor: `30d` e os meses agrupam de sete em sete dias."""
    for dia in range(1, 29):
        painel.movimento(
            "receipt", "1", custo="1.11", quando=datetime(2026, 5, dia, 10)
        )

    janela = painel.janela(
        key="30d", desde=datetime(2026, 5, 1, 4), ate=datetime(2026, 5, 29, 4)
    )
    series = selectors.series_do_periodo(tenant_id=painel.tenant_id, janela=janela)
    serie = series.series[0]

    assert series.granularity == "week"
    assert len(series.buckets) == 4
    assert sum(ponto.value_eur for ponto in serie.points) == serie.total_eur
    assert serie.total_eur == Decimal("31.08")
    assert series.buckets[0].since == timezone.make_aware(datetime(2026, 5, 1, 4))
    assert series.buckets[-1].until == janela.ate


# ---------------------------------------------------------------------------
# 10 — a fronteira do mês de negócio
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_movimento_das_duas_da_manha_do_dia_um_cai_no_mes_anterior(
    painel: Ambiente,
) -> None:
    """O mês de negócio é `[dia 1 às 04:00, dia 1 do mês seguinte às 04:00)`.

    Uma entrada das 02:00 do dia 1 de junho é de maio, porque o dia de negócio
    dela é 31 de maio. É a decisão 8 da ADR 0013, e é ela que faz
    `Σ(dias) == mês`.
    """
    painel.movimento("receipt", "1", custo="99.00", quando=datetime(2026, 6, 1, 2, 0))
    agora = timezone.make_aware(datetime(2026, 7, 15, 12))

    maio = periodos.janela_do_mes(mes="2026-05", inicio_do_dia=INICIO_DO_DIA, agora=agora)
    junho = periodos.janela_do_mes(mes="2026-06", inicio_do_dia=INICIO_DO_DIA, agora=agora)

    assert selectors.fecho_do_mes(
        tenant_id=painel.tenant_id, mes=maio, vat_regime="normal"
    ).purchases_eur == Decimal("99.00")
    assert selectors.fecho_do_mes(
        tenant_id=painel.tenant_id, mes=junho, vat_regime="normal"
    ).purchases_eur == Decimal("0.00")

    assert maio.closed is True
    assert maio.days_elapsed == maio.days_in_month == 31
    # Um mês a correr conta o dia a correr como um dia inteiro, sem fracção.
    a_correr = periodos.janela_do_mes(
        mes="2026-07", inicio_do_dia=INICIO_DO_DIA, agora=agora
    )
    assert a_correr.closed is False
    assert (a_correr.days_elapsed, a_correr.days_in_month) == (15, 31)


@pytest.mark.django_db(transaction=True)
def test_o_resumo_do_mes_e_o_fecho_dizem_o_mesmo_sobre_mercadoria() -> None:
    """`/summary?period=month` e `/month?month=<corrente>` sobre a mesma janela.

    Dois endpoints que respondessem números diferentes à mesma pergunta eram o
    primeiro bug reportado — e é precisamente por isso que a janela se resolve
    num sítio só (`periodos.py`).
    """
    tenant = criar_tenant(name="Mês Corrente")
    with tenant_scope(tenant.id):
        dona = User.objects.create_user("dona@mes.pt", CREDENCIAL)
        conceder_pertenca(
            user=dona, tenant_id=tenant.id, role=Papel.OWNER, display_name="Dona"
        )
        local = Location.objects.create(tenant=tenant, name="Loja", position=1)
        artigo = Product.objects.create(
            tenant=tenant,
            short_name="Açúcar",
            base_unit="kg",
            display_unit="kg",
            display_factor=Decimal("1"),
        )
        StockMovement.objects.create(
            tenant_id=tenant.id,
            product=artigo,
            location=local,
            movement_type="receipt",
            quantity=Decimal("5"),
            unit_cost=Decimal("3.00"),
            occurred_at=timezone.now(),
            created_by_name="teste",
        )

    cliente = autenticar("dona@mes.pt")
    mes = periodos.mes_de_negocio(instante=timezone.now(), inicio_do_dia=INICIO_DO_DIA)

    resumo = cliente.get("/api/v1/reporting/summary", {"period": "month"})
    fecho = cliente.get("/api/v1/reporting/month", {"month": mes})
    assert resumo.status_code == 200, resumo.content
    assert fecho.status_code == 200, fecho.content

    campos = (
        "purchases_eur",
        "goods_consumed_eur",
        "stock_change_eur",
        "waste_eur",
        "unknown_shrinkage_eur",
        "stock_value_eur",
    )
    assert {campo: resumo.json()[campo] for campo in campos} == {
        campo: fecho.json()[campo] for campo in campos
    }
    assert resumo.json()["purchases_eur"] == "15.00"
    assert fecho.json()["month"] == mes
    assert resumo.json()["period"]["since"] == fecho.json()["since"]
    # O `until` **não** é igual ao milissegundo, e é isso que se afirma: num
    # período a correr ele é `agora`, logo dois pedidos consecutivos diferem no
    # tempo que passou entre eles. O que tem de bater é a fronteira que o
    # negócio define — o `since` — e não o instante em que se perguntou.
    distancia = datetime.fromisoformat(resumo.json()["period"]["until"]) - (
        datetime.fromisoformat(fecho.json()["until"])
    )
    assert abs(distancia) < timedelta(seconds=5)


# ---------------------------------------------------------------------------
# 11 e 12 — o contrato e o gate
# ---------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_o_que_nao_se_sabe_viaja_a_null_e_com_a_razao_ao_lado() -> None:
    """`null` e nunca `"0.00"`: um zero em euros é um facto e o painel desenha-o.

    O porquê viaja uma vez, em `unavailable`, numa união fechada de três
    valores — e não campo a campo, que é como um `null` se lê como erro.
    """
    tenant = criar_tenant(name="Sem Vendas")
    with tenant_scope(tenant.id):
        dona = User.objects.create_user("dona@sem.pt", CREDENCIAL)
        conceder_pertenca(
            user=dona, tenant_id=tenant.id, role=Papel.OWNER, display_name="Dona"
        )
    cliente = autenticar("dona@sem.pt")
    mes = periodos.mes_de_negocio(instante=timezone.now(), inicio_do_dia=INICIO_DO_DIA)

    resumo = cliente.get("/api/v1/reporting/summary", {"period": "7d"}).json()
    fecho = cliente.get("/api/v1/reporting/month", {"month": mes}).json()

    for campo in ("revenue_net_eur", "revenue_gross_eur", "revenue_basis"):
        assert resumo[campo] is None, campo
        assert fecho[campo] is None, campo
    for campo in (
        "payroll_eur",
        "payroll_basis",
        "payroll_source",
        "cost_total_eur",
        "result_eur",
        "labour_cost_ratio_pct",
        "prime_cost_pct",
        "goods_cost_ratio_pct",
    ):
        assert fecho[campo] is None, campo
    for campo in ("payroll_breakdown", "roles", "other_costs", "result_excludes"):
        assert fecho[campo] == [], campo

    for resposta in (resumo, fecho):
        qualidade = resposta["data_quality"]
        assert qualidade["unavailable"] == ["revenue", "payroll", "other_costs"]
        assert qualidade["revenue_source"] == "none"
        assert qualidade["vat_regime"] == "normal"
        assert qualidade["last_count_at"] is None

    # O que é real continua a ser servido a sério, e em euros com duas casas.
    assert resumo["purchases_eur"] == "0.00"
    assert resumo["stock_value_eur"] == "0.00"
    assert resumo["period"]["business_day_starts_at"] == "04:00"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("papel", [Papel.MANAGER, Papel.STAFF])
def test_as_tres_vistas_recusam_quem_nao_e_dono(papel: str) -> None:
    """403 nas três, com o `detail` do DRF e **sem `code` novo** (ADR 0013, d6).

    Não é 200 com blocos ausentes: um 200 parcial torna "não podes ver"
    indistinguível de "não há nada", e os dois pedem ecrãs opostos. O cliente já
    sabe o papel antes de pedir — isto é a rede do deep link e da pertença
    revogada com a página aberta.
    """
    tenant = criar_tenant(name="Com Equipa")
    email = f"{papel}@equipa.pt"
    with tenant_scope(tenant.id):
        pessoa = User.objects.create_user(email, CREDENCIAL)
        conceder_pertenca(
            user=pessoa, tenant_id=tenant.id, role=papel, display_name=str(papel)
        )
    cliente = autenticar(email)
    mes = periodos.mes_de_negocio(instante=timezone.now(), inicio_do_dia=INICIO_DO_DIA)

    for caminho, parametros in (
        ("/api/v1/reporting/summary", {"period": "7d"}),
        ("/api/v1/reporting/series", {"period": "7d"}),
        ("/api/v1/reporting/month", {"month": mes}),
    ):
        resposta = cliente.get(caminho, parametros)
        assert resposta.status_code == 403, caminho
        corpo = resposta.json()
        assert set(corpo) == {"detail"}
        assert corpo["detail"]


@pytest.mark.django_db(transaction=True)
def test_um_periodo_desconhecido_e_400_e_nao_um_painel_de_outra_janela() -> None:
    """A união fechada é do servidor: um `period` inventado não cai num default."""
    tenant = criar_tenant(name="Parâmetro")
    with tenant_scope(tenant.id):
        dona = User.objects.create_user("dona@parametro.pt", CREDENCIAL)
        conceder_pertenca(
            user=dona, tenant_id=tenant.id, role=Papel.OWNER, display_name="Dona"
        )
    cliente = autenticar("dona@parametro.pt")

    recusa = cliente.get("/api/v1/reporting/summary", {"period": "ontem"})
    assert recusa.status_code == 400
    assert set(recusa.json()) == {"detail"}

    mes_mau = cliente.get("/api/v1/reporting/month", {"month": "2026-13"})
    assert mes_mau.status_code == 400
    assert set(mes_mau.json()) == {"detail"}


# ---------------------------------------------------------------------------
# As portas novas do `inventory`, pelo lado de quem as chama
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_o_valor_de_stock_e_instantaneo_e_diz_a_que_horas(painel: Ambiente) -> None:
    """`Σ(saldo × CMP)` lido **agora**, com a hora ao lado.

    Base diferente da do fluxo (que vale ao custo gravado em cada movimento),
    e é por isso que a variação de stock **não** se deriva da diferença de dois
    instantâneos: o `/month` de um mês passado mostra o valor de hoje, e o ecrã
    tem de o poder dizer.
    """
    StockLevel.objects.create(
        tenant_id=painel.tenant_id,
        product=painel.artigo,
        location=painel.local,
        quantity=Decimal("8"),
        unit_cost=Decimal("1.555"),
    )
    desde, ate = janela_larga()
    antes = timezone.now()
    resumo = painel.resumo(painel.janela(desde=desde, ate=ate))

    assert resumo.stock_value_eur == Decimal("12.44")
    assert antes <= resumo.stock_value_as_of <= timezone.now()
