"""Quem vê os custos de stock (ADR 0032), e o que **não** é uma chave de dinheiro.

A ADR 0032 revogou a 0024 d4 e a 0025 d3: o custo de stock passou a ser de
`owner|manager`, com a **chave ausente** do JSON — nunca zero, nunca `null`.
Nenhuma rota passou a 403 e nenhuma quantidade desapareceu.

## Os três testes que não são sobre chaves de dinheiro, e são os que interessam

Um ficheiro que só enumerasse `unit_cost` e `total_value` dava verde com as três
fugas que o `domain-expert` encontrou abertas, porque nenhuma delas tem um euro
no payload:

1. **A contagem de linhas era um oráculo.** Com o `Case` fora do agregado, um
   artigo saía em N linhas — uma por custo distinto —, logo contar as linhas
   dizia quantos preços diferentes aquele artigo tem. Ver
   `TestContarLinhasNaoDizQuantosCustosExistem`.
2. **Uma lista ordenada por euros *são* os euros.** Ordenar por valor conta o
   preço relativo de tudo sem mostrar um número. Ver `TestAOrdemNaoDizOPreco`.
3. **O limiar do fecho limita um custo por linha.** Ver
   `TestOLimiarDoFechoNaoChegaAQuemNaoVeEuros`.

## E um defeito que não é fuga nenhuma: o custo diluído

`TestOCustoUnitarioNaoEDiluido` (secção 8) prende a correcção de 2026-10-21: o
`unit_cost` dividia o valor da parte **com** preço pela quantidade **toda**, e
30 unidades a 2,00 € mais 70 sem preço davam 0,60 €/un. Ninguém via um euro a
mais do que devia — via um euro **errado**, que é outra maneira de uma política
de euros falhar. A invariante da ADR sobrevive com o divisor certo, e é ela que
tem um teste próprio.

## E um que prova o outro lado

`TestOTrabalhoDeCampoNaoPerdeNada`: contar, receber, perder e transferir
continuam a funcionar para o colaborador. A decisão 3 da ADR é metade da
decisão 1 — se o trabalho de campo partisse, a política estava errada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework import serializers as drf
from rest_framework.test import APIClient

from apps.accounts.api import PAPEIS_QUE_VEEM_EUROS
from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.agents.tools import _custo
from apps.catalog.models import Product, UnidadeBase
from apps.inventory import serializers as serializers_do_inventory
from apps.inventory.models import Location, Lot
from apps.inventory.selectors import (
    CUSTO_CONHECIDO,
    CUSTO_DESCONHECIDO,
    CUSTO_ESTIMADO,
    ESTADOS_DO_CUSTO,
)
from apps.inventory.services import MovementDTO, record_movements
from apps.inventory.views import SO_OWNER_OU_MANAGER
from apps.shared.db import tenant_scope

CREDENCIAL = "custos-de-stock-teste-123"


@pytest.fixture(autouse=True)
def _cache_limpa():
    """O throttle do DRF conta em cache, e a cache é local ao processo.

    Sem isto, o balde `user` de 600/min acumula entre testes do mesmo processo
    — e estes ficheiros fazem centenas de pedidos autenticados — e um teste
    começa a falhar com 429 por causa dos que correram antes. É a mesma
    fixture do `test_autenticacao.py`, pela mesma razão.
    """
    cache.clear()
    yield
    cache.clear()

pytestmark = pytest.mark.django_db(transaction=True)

#: As duas chaves que saem das três rotas do painel, e a única que sai dos 201.
EUROS_DO_PAINEL = ("unit_cost", "total_value")
EUROS_DO_MOVIMENTO = ("unit_cost",)


# ---------------------------------------------------------------------------
# Andaimes. O stock entra **sempre pelo ledger** — um `StockLevel` escrito à
# mão desaparece no primeiro movimento que lhe toca (ver `test_contagens.py`).
# ---------------------------------------------------------------------------
def _casa(nome: str) -> SimpleNamespace:
    """Um estabelecimento com dono, gerente, colaborador e duas localizações."""
    tenant = criar_tenant(name=f"Casa dos Custos {nome}")
    with tenant_scope(tenant.id):
        dono = User.objects.create_user(f"dono-{nome}@custos.pt", CREDENCIAL)
        conceder_pertenca(
            user=dono, tenant_id=tenant.id, role=Papel.OWNER, display_name="Ana Dona"
        )
        gerente = User.objects.create_user(f"gerente-{nome}@custos.pt", CREDENCIAL)
        conceder_pertenca(
            user=gerente,
            tenant_id=tenant.id,
            role=Papel.MANAGER,
            display_name="Rui Gerente",
        )
        staff = User.objects.create_user(f"staff-{nome}@custos.pt", CREDENCIAL)
        conceder_pertenca(
            user=staff,
            tenant_id=tenant.id,
            role=Papel.STAFF,
            display_name="João Colaborador",
        )
        loja = Location.objects.create(tenant=tenant, name="Loja", position=0)
        armazem = Location.objects.create(tenant=tenant, name="Armazém", position=1)
    return SimpleNamespace(
        tenant=tenant,
        dono=dono,
        gerente=gerente,
        staff=staff,
        loja=loja,
        armazem=armazem,
    )


def _artigo(
    casa: SimpleNamespace,
    *,
    nome: str,
    minimo: Decimal = Decimal("0"),
    track_lots: bool = True,
) -> Product:
    with tenant_scope(casa.tenant.id):
        return Product.objects.create(
            tenant=casa.tenant,
            short_name=nome,
            sku=nome.replace(" ", "-").lower(),
            base_unit=UnidadeBase.UNIDADE,
            display_unit="un",
            display_factor=Decimal("1"),
            min_quantity=minimo,
            track_lots=track_lots,
        )


def _lote(
    casa: SimpleNamespace, produto: Product, *, codigo: str, dias: int | None = 30
) -> Lot:
    agora = timezone.now()
    with tenant_scope(casa.tenant.id):
        return Lot.objects.create(
            tenant=casa.tenant,
            product=produto,
            code=codigo,
            expires_at=None if dias is None else agora + timedelta(days=dias),
            received_at=agora,
        )


def _receber(
    casa: SimpleNamespace,
    produto: Product,
    localizacao: Location,
    lote: Lot,
    *,
    quantidade: Decimal,
    custo: Decimal,
    estimado: bool = False,
) -> None:
    with tenant_scope(casa.tenant.id):
        record_movements(
            tenant_id=casa.tenant.id,
            movements=[
                MovementDTO(
                    product_id=produto.id,
                    location_id=localizacao.id,
                    lot_id=lote.id,
                    quantity=quantidade,
                    unit_cost=custo,
                    cost_is_estimate=estimado,
                    movement_type="receipt",
                    occurred_at=timezone.now(),
                    created_by_id=None,
                    created_by_name="semeador",
                )
            ],
        )


def _quebrar(
    casa: SimpleNamespace, *, quantidade: str, lote: Lot | None = None
) -> Any:
    """Uma quebra pela porta da frente, com o corpo da ADR 0034 (sem `_id`)."""
    corpo: dict[str, Any] = {
        "product": str(casa.farinha.id),
        "location": str(casa.loja.id),
        "quantity": quantidade,
        "unit": "un",
        "reason": "spoiled",
    }
    if lote is not None:
        corpo["lot"] = str(lote.id)
    resposta = _sessao(casa.staff.email).post(
        "/api/v1/stock/movements/waste", corpo, format="json"
    )
    assert resposta.status_code == 201, resposta.content
    return resposta


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


def _itens(resposta: Any) -> list[dict[str, Any]]:
    """As linhas de uma página do DRF.

    Era `["items"]`: as quatro rotas do painel devolviam
    `{items, total, page, page_size}` com `page: 1` fixo — um envelope que não
    paginava e que mentia sobre o fazer. A ADR 0034, decisão 3, trocou-o pelo
    do DRF, que é o que o `paginated()` do cliente valida.
    """
    assert resposta.status_code == 200, resposta.content
    return resposta.json()["results"]


def _corpo(resposta: Any) -> dict[str, Any]:
    """O corpo de uma resposta que não é lista (os dois resumos)."""
    assert resposta.status_code == 200, resposta.content
    return resposta.json()


def _loja_com_dois_artigos(nome: str) -> SimpleNamespace:
    """Farinha (2 lotes, 2 custos) e Açúcar (1 lote), tudo na Loja."""
    casa = _casa(nome)
    casa.farinha = _artigo(casa, nome="Farinha T65")
    casa.acucar = _artigo(casa, nome="Açúcar")
    casa.lote_a = _lote(casa, casa.farinha, codigo="FA-1", dias=10)
    casa.lote_b = _lote(casa, casa.farinha, codigo="FA-2", dias=40)
    casa.lote_c = _lote(casa, casa.acucar, codigo="AC-1", dias=60)
    _receber(
        casa, casa.farinha, casa.loja, casa.lote_a,
        quantidade=Decimal("100"), custo=Decimal("0.5"),
    )
    _receber(
        casa, casa.farinha, casa.loja, casa.lote_b,
        quantidade=Decimal("20"), custo=Decimal("0.75"),
    )
    _receber(
        casa, casa.acucar, casa.loja, casa.lote_c,
        quantidade=Decimal("30"), custo=Decimal("1.20"),
    )
    return casa


# ---------------------------------------------------------------------------
# 1. O painel: as três rotas, nos dois sentidos
# ---------------------------------------------------------------------------
class TestOPainelDeStock:
    """Decisão 2: as chaves de dinheiro saem do payload de quem não vê euros.

    Os caminhos mudaram com a ADR 0034 — o `/stock/summary` do servidor passou
    a `/stock/levels` e o `by-location`/`by-product` morreram inteiros —, mas a
    política é a mesma e é ela que estes testes prendem.
    """

    def test_os_niveis_nao_trazem_euros_ao_colaborador(self):
        casa = _loja_com_dois_artigos("resumo")
        itens = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))

        assert len(itens) == 2
        for item in itens:
            for chave in EUROS_DO_PAINEL:
                assert chave not in item, f"{chave} chegou a quem não vê euros"

    def test_o_gerente_recebe_os_euros_dos_niveis(self):
        casa = _loja_com_dois_artigos("resumo-gerente")
        itens = _itens(_sessao(casa.gerente.email).get("/api/v1/stock/levels"))

        por_nome = {item["short_name"]: item for item in itens}
        # 100 × 0,50 + 20 × 0,75 = 65,00; o custo é a média **ponderada**.
        assert por_nome["Farinha T65"]["total_value"] == "65.00"
        assert por_nome["Farinha T65"]["unit_cost"] == "0.541667"
        assert por_nome["Açúcar"]["total_value"] == "36.00"

    def test_o_valor_do_stock_nao_chega_ao_colaborador(self):
        """A chave nova da ADR 0034: o `stock_value_eur` dos quatro números."""
        casa = _loja_com_dois_artigos("valor-do-stock")

        do_staff = _corpo(_sessao(casa.staff.email).get("/api/v1/stock/summary"))
        assert "stock_value_eur" not in do_staff
        # E o que ele precisa para trabalhar continua lá, inteiro.
        assert do_staff["below_min_count"] == 0
        assert do_staff["expiring_within_days"] == 7

        do_gerente = _corpo(_sessao(casa.gerente.email).get("/api/v1/stock/summary"))
        assert do_gerente["stock_value_eur"] == "101.00"

    def test_os_alertas_escondem_o_valor_e_mais_nada(self):
        """O `value_eur` sai; a linha — que é accionável — fica igual."""
        casa = _loja_com_dois_artigos("alertas")
        # Um lote dentro do limiar de sete dias e um artigo em falta: a lista
        # tem de ter as duas famílias para a comparação dizer alguma coisa.
        a_vencer = _lote(casa, casa.farinha, codigo="FA-3", dias=2)
        _receber(casa, casa.farinha, casa.loja, a_vencer,
                 quantidade=Decimal("5"), custo=Decimal("0.60"))
        falta = _artigo(casa, nome="Sal", minimo=Decimal("10"))
        _receber(casa, falta, casa.loja, _lote(casa, falta, codigo="SA-1"),
                 quantidade=Decimal("1"), custo=Decimal("0.30"))

        do_staff = _itens(_sessao(casa.staff.email).get("/api/v1/stock/alerts"))
        do_dono = _itens(_sessao(casa.dono.email).get("/api/v1/stock/alerts"))

        assert len(do_staff) == len(do_dono) == 2
        for linha_do_staff, linha_do_dono in zip(do_staff, do_dono, strict=True):
            assert "value_eur" not in linha_do_staff
            assert "value_eur" in linha_do_dono
            assert linha_do_staff == {
                chave: valor
                for chave, valor in linha_do_dono.items()
                if chave != "value_eur"
            }

    def test_o_desperdicio_esconde_o_valor_e_a_lista_chega_aos_tres_papeis(self):
        """A decisão 4: esta lista é do `inventory` e **tem** de chegar ao `staff`."""
        casa = self_casa = _loja_com_dois_artigos("desperdicio")
        _quebrar(self_casa, quantidade="2.000")

        do_staff = _itens(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts/waste")
        )
        do_dono = _itens(_sessao(casa.dono.email).get("/api/v1/stock/alerts/waste"))

        assert len(do_staff) == len(do_dono) == 1
        assert "value_eur" not in do_staff[0]
        assert do_dono[0]["value_eur"] == "1.00"
        # O que ele precisa para reconhecer a linha fica todo.
        assert do_staff[0]["short_name"] == "Farinha T65"
        assert do_staff[0]["quantity"]["base"] == "2.000"
        assert do_staff[0]["created_by"] == "João Colaborador"


# ---------------------------------------------------------------------------
# 1b. A ficha de um artigo: `GET /stock/levels/<product_id>`
#
# A porta nova da adenda de 2026-10-29 à ADR 0034 (decisão 15). O que ela
# proíbe é o reflexo contrário ao que parece prudente: **redeclarar o
# `CAMPOS_DE_DINHEIRO` numa subclasse de detalhe**. É literalmente a porta irmã
# por onde o dinheiro sai, e é o padrão que esta casa já apanhou duas vezes —
# a ADR 0031 fechou os euros da receção e deixou o `ExtracaoOut` do documento
# aberto **sobre a mesma fatura**.
#
# Por isso o `assert` que interessa não é "o `staff` não tem `unit_cost`": é
# **o conjunto de chaves do detalhe contra o da linha da lista, por papel**.
# Uma subclasse que redeclarasse a lista a menos passava no primeiro e caía
# neste. Afirma presença e ausência de chave, e nunca valores: um
# `assert resposta["unit_cost"] is None` passaria com a fuga meio tapada.
#
# Os testes de forma desta rota (os três estados, o `?loja=`, o uuid mal
# formado) vivem no `test_stock_e_alertas.py`, que é o ficheiro dela.
# ---------------------------------------------------------------------------
class TestAFichaDeUmArtigoSegueAMesmaPolitica:
    """Decisão 15: os euros herdam-se, e o detalhe não é uma quarta porta."""

    def _ficha(self, email: str, produto: Product) -> dict[str, Any]:
        return _corpo(_sessao(email).get(f"/api/v1/stock/levels/{produto.id}"))

    def _linha(self, email: str, produto: Product) -> dict[str, Any]:
        linhas = [
            item
            for item in _itens(_sessao(email).get("/api/v1/stock/levels"))
            if item["product"] == str(produto.id)
        ]
        assert len(linhas) == 1
        return linhas[0]

    def test_as_chaves_de_dinheiro_da_ficha_sao_as_da_linha_da_lista(self):
        """Os três papéis, nas duas metades, e por **conjunto de chaves**."""
        casa = _loja_com_dois_artigos("ficha-por-papel")

        for membro, ve_euros in (
            (casa.dono, True),
            (casa.gerente, True),
            (casa.staff, False),
        ):
            ficha = self._ficha(membro.email, casa.farinha)
            linha = self._linha(membro.email, casa.farinha)

            for chave in EUROS_DO_PAINEL:
                assert (chave in ficha) is ve_euros, (membro.email, chave)
                assert (chave in linha) is ve_euros, (membro.email, chave)

            assert set(ficha) - set(linha) == {"never_stocked"}, (
                f"a ficha de {membro.email} tem chaves que a linha não tem: "
                "é a segunda porta do mesmo dinheiro a abrir-se"
            )
            assert set(linha) - set(ficha) == set(), (
                f"a ficha de {membro.email} perdeu chaves da linha"
            )

    def test_a_cobertura_do_custo_continua_a_chegar_aos_tres_papeis(self):
        """`quantity_without_cost` é **quantidade** e não euro, também aqui."""
        casa = _loja_com_dois_artigos("ficha-cobertura")

        for membro in (casa.dono, casa.gerente, casa.staff):
            ficha = self._ficha(membro.email, casa.farinha)
            assert "quantity_without_cost" in ficha, membro.email
            assert "never_stocked" in ficha, membro.email

    def test_o_artigo_que_nunca_entrou_nao_serve_um_zero_a_quem_nao_ve_euros(self):
        """Em (b) o `total_value` seria `0` — e um zero é uma afirmação sobre o preço.

        É o caso em que a herança tem de valer: o artigo não tem linha nenhuma
        no `inventory`, o corpo é construído a partir do `ProdutoResumo`, e as
        duas chaves têm de ficar **ausentes** para o colaborador na mesma.
        """
        casa = _loja_com_dois_artigos("ficha-sem-entradas")
        nunca = _artigo(casa, nome="Fermento")

        do_staff = self._ficha(casa.staff.email, nunca)
        do_gerente = self._ficha(casa.gerente.email, nunca)

        assert do_staff["never_stocked"] is True
        for chave in EUROS_DO_PAINEL:
            assert chave not in do_staff, chave
            assert chave in do_gerente, chave
        assert set(do_gerente) - set(do_staff) == set(EUROS_DO_PAINEL)


# ---------------------------------------------------------------------------
# 2. As quantidades. A outra metade da política: **nada** desaparece.
# ---------------------------------------------------------------------------
class TestAsQuantidadesNaoDesaparecem:
    """Os dois defeitos de query que a ADR 0032 nomeou nas consequências."""

    def test_os_niveis_devolvem_a_quantidade(self):
        """O defeito (a): a rota entregava o valor em euros e **não** o saldo.

        O selector anotava `total_quantity`, o serializer declarava `quantity`,
        e um campo `read_only` que não encontra a sua chave sai por `SkipField`
        — sem erro, sem log, sem campo. Este teste falha por **ausência da
        quantidade**, que é o sintoma que ninguém via.
        """
        casa = _loja_com_dois_artigos("quantidade")
        itens = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))
        por_nome = {item["short_name"]: item for item in itens}

        assert "quantity" in por_nome["Farinha T65"], "a rota não devolveu a quantidade"
        assert por_nome["Farinha T65"]["quantity"]["base"] == "120.000"
        assert por_nome["Açúcar"]["quantity"]["base"] == "30.000"

    def test_a_reparticao_por_localizacao_e_do_colaborador(self):
        """O `by_location` é o que responde a "onde está?", e não tem euros.

        Substitui o que o `by-location`/`by-product` mediam: a quantidade por
        prateleira. O grão de lote morreu com essas rotas (ADR 0034, decisão
        1), o de localização mudou-se para dentro da linha do artigo.
        """
        casa = _casa("reparticao")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="F-1")
        _receber(casa, farinha, casa.loja, lote,
                 quantidade=Decimal("40"), custo=Decimal("1"))
        _receber(casa, farinha, casa.armazem, lote,
                 quantidade=Decimal("60"), custo=Decimal("1"))

        linha = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))[0]
        por_loja = {
            parcela["location"]["name"]: parcela["quantity"]["base"]
            for parcela in linha["by_location"]
        }
        assert por_loja == {"Loja": "40.000", "Armazém": "60.000"}
        for parcela in linha["by_location"]:
            assert not [c for c in parcela if "eur" in c or "cost" in c]

    def test_os_niveis_somam_as_localizacoes_e_o_filtro_restringe(self):
        """A agregação é por artigo: dois sítios, uma linha, a soma dos dois."""
        casa = _casa("duas-localizacoes")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="F-1")
        _receber(casa, farinha, casa.loja, lote,
                 quantidade=Decimal("40"), custo=Decimal("1"))
        _receber(casa, farinha, casa.armazem, lote,
                 quantidade=Decimal("60"), custo=Decimal("1"))

        api = _sessao(casa.staff.email)
        todos = _itens(api.get("/api/v1/stock/levels"))
        assert len(todos) == 1
        assert todos[0]["quantity"]["base"] == "100.000"

        so_na_loja = _itens(api.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))
        assert len(so_na_loja) == 1
        assert so_na_loja[0]["quantity"]["base"] == "40.000"


# ---------------------------------------------------------------------------
# 3. Fuga (a): contar as linhas dizia quantos custos existem
# ---------------------------------------------------------------------------
class TestContarLinhasNaoDizQuantosCustosExistem:
    """O defeito (b) das consequências da ADR 0032, lido como **fuga de informação**.

    O `Case` sobre `quantity` vivia **fora** de um agregado dentro de um
    `values().annotate()`, logo o Django punha `quantity` e `unit_cost` no
    `GROUP BY`: um artigo com três lotes a três preços saía em **três** linhas.
    O colaborador não via nenhum euro e ficava a saber exactamente quantos
    preços distintos aquele artigo tem no armazém — e via-o mudar quando
    chegava uma entrada mais cara.

    Nenhum teste de "chaves de dinheiro" apanha isto, porque não há aqui chave
    nenhuma de dinheiro: a fuga está na **cardinalidade**.
    """

    def test_um_artigo_com_tres_custos_sai_numa_linha_so(self):
        casa = _casa("tres-custos")
        farinha = _artigo(casa, nome="Farinha")
        for indice, custo in enumerate(("0.5", "0.75", "1.10")):
            lote = _lote(casa, farinha, codigo=f"F-{indice}", dias=10 + indice)
            _receber(
                casa, farinha, casa.loja, lote,
                quantidade=Decimal("10"), custo=Decimal(custo),
            )

        itens = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))

        assert len(itens) == 1, (
            "três lotes a três preços deram três linhas: contar as linhas "
            "dizia quantos custos distintos o artigo tem"
        )
        assert itens[0]["quantity"]["base"] == "30.000"

    def test_o_colaborador_e_o_gerente_veem_o_mesmo_numero_de_linhas(self):
        """A cardinalidade não pode depender do papel — nem ao contrário."""
        casa = _casa("cardinalidade")
        farinha = _artigo(casa, nome="Farinha")
        for indice, custo in enumerate(("0.5", "0.9")):
            lote = _lote(casa, farinha, codigo=f"C-{indice}", dias=5 + indice)
            _receber(
                casa, farinha, casa.loja, lote,
                quantidade=Decimal("7"), custo=Decimal(custo),
            )

        do_staff = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))
        do_dono = _itens(_sessao(casa.dono.email).get("/api/v1/stock/levels"))

        assert len(do_staff) == len(do_dono) == 1
        # E a repartição também não conta custos: dois lotes na mesma
        # prateleira são **uma** parcela, não duas.
        assert len(do_staff[0]["by_location"]) == 1

    def test_os_alertas_sao_por_lote_e_localizacao_e_nao_por_custo(self):
        """O alerta é de grão lote × localização — dois lotes, dois alertas.

        A cardinalidade aqui **é** o número de lotes a vencer, e isso é o
        produto: o alerta tem de ser accionável sobre um lote concreto. O que
        não pode é variar com o número de **custos**, e é isso que o segundo
        lote com o mesmo preço prende.
        """
        casa = _casa("alertas-cardinalidade")
        farinha = _artigo(casa, nome="Farinha")
        for indice in range(2):
            lote = _lote(casa, farinha, codigo=f"A-{indice}", dias=2 + indice)
            # **O mesmo custo nos dois**: se a linha fosse por custo, dava uma.
            _receber(
                casa, farinha, casa.loja, lote,
                quantidade=Decimal("5"), custo=Decimal("1.25"),
            )

        alertas = _itens(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts?risco=expira")
        )
        assert len(alertas) == 2
        assert len({a["id"] for a in alertas}) == 2


# ---------------------------------------------------------------------------
# 4. Fuga (b): uma lista ordenada por euros *são* os euros
# ---------------------------------------------------------------------------
class TestAOrdemNaoDizOPreco:
    """Nenhuma rota servida ao colaborador ordena por valor, custo ou derivado.

    Uma ordenação é invisível a qualquer teste de campos: o payload pode não
    ter um único euro e a **sequência** contar o preço relativo de tudo o que
    lá está — "o mais caro primeiro" é a informação quase inteira. Por isso os
    dados destes testes são construídos de propósito com a ordem dos euros
    **ao contrário** da ordem servida: se alguém trocar o `order_by`, a
    asserção parte.

    O desempate por `value_eur` que o `ordenar()` do fixture fazia **não**
    atravessa (ADR 0034, decisão 6).
    """

    def test_os_niveis_vem_por_estado_e_validade_e_nunca_por_valor(self):
        """Estado, depois `days_away` (NULLS LAST), depois o nome."""
        casa = _casa("ordem-niveis")
        # O que está pior é o mais barato; por valor a ordem inverte-se.
        for nome, dias, quantidade, custo in (
            ("Tarde", 60, "90", "10"),
            ("Cedo", 2, "10", "0.10"),
            ("Sem data", None, "50", "5"),
        ):
            artigo = _artigo(casa, nome=nome)
            lote = _lote(casa, artigo, codigo=f"{nome}-1", dias=dias)
            _receber(casa, artigo, casa.loja, lote,
                     quantidade=Decimal(quantidade), custo=Decimal(custo))

        nomes = [
            item["short_name"]
            for item in _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))
        ]
        assert nomes == ["Cedo", "Tarde", "Sem data"], (
            "a ordem é estado → days_away (NULLS LAST) → nome, e nunca valor"
        )

    def test_um_artigo_em_falta_vem_antes_de_um_artigo_caro(self):
        """O estado ganha ao relógio, e o relógio ganha ao nome. Valor, nunca."""
        casa = _casa("ordem-estado")
        caro = _artigo(casa, nome="Caro")
        vazio = _artigo(casa, nome="Vazio", minimo=Decimal("10"))
        _receber(casa, caro, casa.loja, _lote(casa, caro, codigo="C-1", dias=1),
                 quantidade=Decimal("100"), custo=Decimal("50"))
        _receber(casa, vazio, casa.loja, _lote(casa, vazio, codigo="V-1", dias=90),
                 quantidade=Decimal("1"), custo=Decimal("0.01"))

        nomes = [
            item["short_name"]
            for item in _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))
        ]
        assert nomes == ["Vazio", "Caro"]

    def test_os_alertas_vem_por_gravidade_e_validade_e_nunca_por_valor(self):
        casa = _casa("ordem-alertas")
        farinha = _artigo(casa, nome="Farinha")
        # "JA" vence amanhã (danger pela tabela da d9) e é o mais barato.
        for codigo, dias, custo in (("JA", 1, "0.10"), ("DEPOIS", 5, "9.00")):
            lote = _lote(casa, farinha, codigo=codigo, dias=dias)
            _receber(casa, farinha, casa.loja, lote,
                     quantidade=Decimal("10"), custo=Decimal(custo))

        validades = [
            item["lot"]["lot_code"]
            for item in _itens(_sessao(casa.staff.email).get("/api/v1/stock/alerts"))
            if item["lot"]
        ]
        assert validades == ["JA", "DEPOIS"]

    def test_o_desperdicio_vem_do_mais_recente_e_nunca_por_valor(self):
        """A última coisa que se deitou fora é a que se reconhece."""
        casa = _loja_com_dois_artigos("ordem-desperdicio")
        # O primeiro é o maior em euros; se a ordem fosse por valor vinha à frente.
        _quebrar(casa, quantidade="10.000", lote=casa.lote_b)
        _quebrar(casa, quantidade="1.000", lote=casa.lote_a)

        linhas = _itens(_sessao(casa.dono.email).get("/api/v1/stock/alerts/waste"))
        assert [linha["value_eur"] for linha in linhas] == ["0.50", "7.50"]


# ---------------------------------------------------------------------------
# 5. Fuga (c): o oráculo morto que tem de continuar morto
# ---------------------------------------------------------------------------
class TestOLimiarDoFechoNaoChegaAQuemNaoVeEuros:
    """`reason_required_above_eur` é `0` hoje. Com um limiar ≠ 0 e a bandeira à
    vista de quem conta, **cada fecho limita um custo**: "esta diferença vale
    mais de X €", repetido artigo a artigo, é uma busca binária sobre o preço.

    Hoje não chega lá porque as duas rotas de `/closing` são de `owner|manager`.
    O que este teste prende é essa coincidência: os papéis da rota **são** os
    `PAPEIS_QUE_VEEM_EUROS`, e o dia em que alguém alargar a rota sem tirar o
    limiar parte aqui.
    """

    def test_os_papeis_da_rota_de_fecho_sao_os_que_veem_euros(self):
        assert SO_OWNER_OU_MANAGER.papeis == PAPEIS_QUE_VEEM_EUROS

    def test_o_porto_do_assistente_usa_os_mesmos_papeis(self):
        """A **segunda** escrita literal da mesma política, prendida aqui.

        O `agents/tools.py` tem o seu `OWNER_E_MANAGER`, independente do
        `PAPEIS_QUE_VEEM_EUROS`. Hoje os dois conjuntos são iguais e nada o
        obrigava — a revisão da ADR 0032 apanhou-o, e a decisão 4 dessa ADR
        existe precisamente porque **duas definições da mesma política** foram a
        origem desta família de defeitos.

        Não se unificam os dois símbolos aqui: o `agents` está fora do âmbito da
        ADR, e a aresta entre os módulos é matéria do import-linter. O que se
        prende é a **igualdade**, para a divergência doer no dia em que alguém
        alargar um dos lados sem olhar para o outro.
        """
        from apps.agents.tools import OWNER_E_MANAGER

        assert OWNER_E_MANAGER == PAPEIS_QUE_VEEM_EUROS

    def test_o_colaborador_leva_403_nas_duas_rotas_do_fecho(self):
        casa = _loja_com_dois_artigos("limiar")
        contagem = _sessao(casa.dono.email).post(
            "/api/v1/stock/counts", {"location": str(casa.loja.id)}, format="json"
        )
        assert contagem.status_code == 201, contagem.content
        contagem_id = contagem.json()["id"]

        staff = _sessao(casa.staff.email)
        assert staff.get(f"/api/v1/stock/counts/{contagem_id}/closing").status_code == 403
        assert staff.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "tentativa"},
            format="json",
        ).status_code == 403

    def test_o_limiar_nao_aparece_em_nenhum_payload_servido_ao_colaborador(self):
        """Nem no cabeçalho da contagem, nem na lista, nem numa linha contada."""
        casa = _loja_com_dois_artigos("limiar-payload")
        contagem_id = _sessao(casa.dono.email).post(
            "/api/v1/stock/counts", {"location": str(casa.loja.id)}, format="json"
        ).json()["id"]
        staff = _sessao(casa.staff.email)

        linha = staff.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(casa.farinha.id), "quantity": "99.000"},
            format="json",
        )
        assert linha.status_code == 200, linha.content

        corpos = [
            linha.json(),
            staff.get("/api/v1/stock/counts").json(),
            staff.get(f"/api/v1/stock/counts/{contagem_id}/lines").json(),
        ]
        for corpo in corpos:
            texto = str(corpo)
            assert "reason_required" not in texto
            assert "reason_required_above_eur" not in texto


# ---------------------------------------------------------------------------
# 6. Os três 201 de `stock/movements/*`
# ---------------------------------------------------------------------------
class TestOs201DosMovimentos:
    """Decisão 4 da ADR 0032: os três passaram a ser serializados.

    E a ADR 0034 mudou-lhes os corpos: **sem sufixos `_id`** nos três, `unit`
    obrigatório na quebra, e o 201 da quebra passou a `{movements: [...]}`.
    """

    def _casa_com_stock(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")
        casa.lote = _lote(casa, casa.farinha, codigo="L-1")
        _receber(casa, casa.farinha, casa.loja, casa.lote,
                 quantidade=Decimal("100"), custo=Decimal("0.5"))
        return casa

    def _corpo_da_quebra(self, casa: SimpleNamespace) -> dict[str, Any]:
        return {
            "product": str(casa.farinha.id),
            "location": str(casa.loja.id),
            "lot": str(casa.lote.id),
            "quantity": "2.000",
            "unit": "un",
            "reason": "spoiled",
        }

    def test_o_desperdicio_nao_devolve_o_custo_ao_colaborador(self):
        casa = self._casa_com_stock("waste")
        resposta = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste", self._corpo_da_quebra(casa), format="json"
        )

        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        for chave in EUROS_DO_MOVIMENTO:
            assert chave not in linha, chave
        # O trabalho de campo fica inteiro.
        assert linha["quantity"]["base"] == "-2.000"
        assert linha["location"]["name"] == "Loja"
        assert linha["lot_code"] == "L-1"
        assert linha["cost_status"] == CUSTO_CONHECIDO

    def test_o_desperdicio_devolve_o_custo_ao_gerente(self):
        casa = self._casa_com_stock("waste-gerente")
        resposta = _sessao(casa.gerente.email).post(
            "/api/v1/stock/movements/waste", self._corpo_da_quebra(casa), format="json"
        )

        assert resposta.status_code == 201, resposta.content
        assert resposta.json()["movements"][0]["unit_cost"] == "0.500000"

    def test_o_ajuste_segue_a_mesma_regra(self):
        casa = self._casa_com_stock("ajuste")
        corpo = {
            "product": str(casa.farinha.id),
            "location": str(casa.loja.id),
            "lot": str(casa.lote.id),
            "quantity": "-3.000",
            "reason": "spoiled",
        }

        do_staff = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/adjustment", corpo, format="json"
        )
        assert do_staff.status_code == 201, do_staff.content
        assert "unit_cost" not in do_staff.json()
        assert do_staff.json()["quantity"] == "3.000"

        do_gerente = _sessao(casa.gerente.email).post(
            "/api/v1/stock/movements/adjustment", corpo, format="json"
        )
        assert do_gerente.status_code == 201
        assert do_gerente.json()["unit_cost"] == "0.500000"

    def test_a_transferencia_esconde_o_custo_nas_duas_pernas(self):
        """Esconder numa só dava o mesmo número pelo outro lado."""
        casa = self._casa_com_stock("transferencia")
        corpo = {
            "product": str(casa.farinha.id),
            "from_location": str(casa.loja.id),
            "to_location": str(casa.armazem.id),
            "lot": str(casa.lote.id),
            "quantity": "5.000",
        }

        do_staff = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/transfer", corpo, format="json"
        )
        assert do_staff.status_code == 201, do_staff.content
        corpo_do_staff = do_staff.json()
        assert set(corpo_do_staff) == {"transfer_id", "movements", "created_at"}
        assert corpo_do_staff["transfer_id"] is not None
        assert len(corpo_do_staff["movements"]) == 2
        for perna in corpo_do_staff["movements"]:
            assert "unit_cost" not in perna, perna["type"]
            assert perna["quantity"] == "5.000"
        assert [p["type"] for p in corpo_do_staff["movements"]] == [
            "transfer_out",
            "transfer_in",
        ]

        do_gerente = _sessao(casa.gerente.email).post(
            "/api/v1/stock/movements/transfer", corpo, format="json"
        )
        assert do_gerente.status_code == 201
        for perna in do_gerente.json()["movements"]:
            assert perna["unit_cost"] == "0.500000"

    def test_o_ledger_de_um_artigo_esconde_o_custo_e_mostra_o_resto(self):
        """`GET /stock/movements?artigo=` — a rota nova, com a mesma política."""
        casa = self._casa_com_stock("ledger")
        _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste", self._corpo_da_quebra(casa), format="json"
        )

        caminho = f"/api/v1/stock/movements?artigo={casa.farinha.id}"
        do_staff = _itens(_sessao(casa.staff.email).get(caminho))
        do_dono = _itens(_sessao(casa.dono.email).get(caminho))

        assert [linha["movement_type"] for linha in do_staff] == ["waste", "receipt"]
        for linha in do_staff:
            assert "unit_cost" not in linha
        assert do_dono[0]["unit_cost"] == "0.500000"


# ---------------------------------------------------------------------------
# 7. O marcador qualitativo do custo
# ---------------------------------------------------------------------------
class TestOMarcadorDeCusto:
    """Decisão 2: o marcador de "preço desconhecido" fica visível para todos.

    É qualidade de dados e não um euro — o reflexo da `vat_rate` da ADR 0031 e
    do `custo: "conhecido"` que o porto do `agents` já dá ao `staff`.
    """

    def test_as_tres_palavras_sao_as_do_porto_do_assistente(self):
        """Uma quarta palavra aqui recriava a divergência que a ADR fechou."""
        desconhecido = _custo(Decimal("1"), Decimal("0"))["custo"]
        conhecido = _custo(Decimal("1"), Decimal("2"))["custo"]
        estimado = _custo(Decimal("1"), Decimal("2"), estimado=True)["custo"]

        assert (conhecido, estimado, desconhecido) == ESTADOS_DO_CUSTO
        assert (CUSTO_CONHECIDO, CUSTO_ESTIMADO, CUSTO_DESCONHECIDO) == ESTADOS_DO_CUSTO

    def test_um_lote_sem_preco_e_desconhecido_para_os_dois_papeis(self):
        """O facto é **por lote**: é o defeito de uma receção concreta.

        Mudou de rota com a ADR 0034 — o `by-product` morreu —, e o sítio onde
        o grão de lote continua a existir é o alerta de validade. A palavra é a
        mesma e chega aos dois papéis: é qualidade de dados, não um euro.
        """
        casa = _casa("sem-preco")
        farinha = _artigo(casa, nome="Farinha")
        com_preco = _lote(casa, farinha, codigo="COM", dias=3)
        sem_preco = _lote(casa, farinha, codigo="SEM", dias=5)
        _receber(casa, farinha, casa.loja, com_preco,
                 quantidade=Decimal("30"), custo=Decimal("2"))
        _receber(casa, farinha, casa.loja, sem_preco,
                 quantidade=Decimal("70"), custo=Decimal("0"))

        caminho = "/api/v1/stock/alerts?risco=expira"
        for email in (casa.staff.email, casa.gerente.email):
            por_lote = {
                item["lot"]["lot_code"]: item
                for item in _itens(_sessao(email).get(caminho))
            }
            assert por_lote["COM"]["cost_status"] == CUSTO_CONHECIDO
            assert por_lote["SEM"]["cost_status"] == CUSTO_DESCONHECIDO
            # A quantidade do lote sem preço **não** desaparece.
            assert por_lote["SEM"]["quantity"]["base"] == "70.000"

    def test_o_agregado_mostra_a_cobertura_e_nao_uma_quarta_palavra(self):
        """Com lotes mistos o que se mostra é **quanta** quantidade não tem preço.

        É quantidade e não euro, e diz se a subestimação do valor é de 5 % ou de
        95 %. O padrão já existia no `linhas_sem_custo` do desperdício e no
        `ingredientes_sem_custo` de uma receita; "parcialmente desconhecido" não
        é palavra deste sistema.
        """
        casa = _casa("cobertura")
        farinha = _artigo(casa, nome="Farinha")
        com_preco = _lote(casa, farinha, codigo="COM", dias=10)
        sem_preco = _lote(casa, farinha, codigo="SEM", dias=20)
        _receber(casa, farinha, casa.loja, com_preco,
                 quantidade=Decimal("30"), custo=Decimal("2"))
        _receber(casa, farinha, casa.loja, sem_preco,
                 quantidade=Decimal("70"), custo=Decimal("0"))

        resumo = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))
        assert len(resumo) == 1
        assert resumo[0]["quantity"]["base"] == "100.000"
        assert resumo[0]["quantity_without_cost"]["base"] == "70.000"
        # E **nenhuma palavra** na linha agregada: não há uma que descreva "um
        # lote com preço e outro sem" sem inventar a quarta.
        assert "cost_status" not in resumo[0]

        # E o gerente vê que o valor está subestimado: 30 × 2 e mais nada.
        do_gerente = _itens(_sessao(casa.gerente.email).get("/api/v1/stock/levels"))
        assert do_gerente[0]["total_value"] == "60.00"
        assert do_gerente[0]["quantity_without_cost"]["base"] == "70.000"

    def test_estimado_e_divida_nomeada_e_nao_uma_quarta_palavra(self):
        """A terceira palavra existe, a função sabe produzi-la, e hoje ninguém a serve.

        O `cost_is_estimate` vive no `StockMovement` e **não** no `StockLevel`:
        os três serviços manuais lêem o custo do nível (ADR 0025, decisão 5) e
        gravam `cost_is_estimate=False`, porque uma saída não sabe se a entrada
        que a pagou veio de uma guia ou de uma fatura. O painel lê a projeção e
        tem o mesmo buraco.

        Isto afirma as duas coisas: que a composição **sabe** dizer `estimado`
        (logo o dia da correcção é uma linha no serviço, não uma palavra nova no
        contrato), e que hoje o 201 de um artigo recebido como estimado diz
        `conhecido` — que é a dívida, nomeada aqui para quem a for pagar a
        encontrar com um `grep`.
        """
        assert serializers_do_inventory.estado_do_custo(
            unit_cost=Decimal("2"), estimado=True
        ) == CUSTO_ESTIMADO

        casa = _casa("estimado")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="E-1")
        _receber(casa, farinha, casa.loja, lote,
                 quantidade=Decimal("50"), custo=Decimal("1.25"), estimado=True)

        resposta = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(farinha.id),
                "location": str(casa.loja.id),
                "lot": str(lote.id),
                "quantity": "1.000",
                "unit": "un",
                "reason": "breakage",
            },
            format="json",
        )
        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        assert linha["cost_status"] == CUSTO_CONHECIDO, (
            "a dívida foi paga: a proveniência do custo chegou ao movimento "
            "manual — actualiza esta asserção para `estimado`"
        )
        assert "unit_cost" not in linha


# ---------------------------------------------------------------------------
# 8. O custo unitário não é diluído pela quantidade sem preço
# ---------------------------------------------------------------------------
class TestOCustoUnitarioNaoEDiluido:
    """O divisor é a quantidade que **pagou** o valor, e não o saldo todo.

    O defeito, medido: o numerador era a soma só da parte **com** preço e o
    denominador somava **tudo**, logo 30 unidades a 2,00 € mais 70 sem preço
    davam `unit_cost = 0,60 €/un` num artigo cujo custo conhecido é 2,00 €/un.
    Não é uma escolha de produto: o diluído não é uma grandeza de gestão —
    dividem-se euros por unidades que não contribuíram com um cêntimo — e por
    isso não tem nome honesto possível.

    **A invariante da ADR 0032 sobrevive**, que é o que não podia partir:
    `unit_cost × (quantity − quantity_without_cost) == total_value`. As duas
    pontas do divisor são quantidades, as duas estão no payload do colaborador,
    e esconder as duas chaves de euro continua a não deixar reconstruir nada.
    """

    def _farinha_com_lote_com_preco_e_outro_sem(self, nome: str) -> SimpleNamespace:
        """O caso exacto do `domain-expert`: 30 un a 2,00 € e 70 un sem preço."""
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")
        # Dentro do limiar de sete dias, para a mesma casa servir o teste do
        # alerta de grão lote sem repetir os andaimes.
        com_preco = _lote(casa, casa.farinha, codigo="COM", dias=3)
        sem_preco = _lote(casa, casa.farinha, codigo="SEM", dias=5)
        _receber(casa, casa.farinha, casa.loja, com_preco,
                 quantidade=Decimal("30"), custo=Decimal("2"))
        _receber(casa, casa.farinha, casa.loja, sem_preco,
                 quantidade=Decimal("70"), custo=Decimal("0"))
        return casa

    def test_trinta_a_dois_euros_e_setenta_sem_preco_dao_dois_euros(self):
        """0,60 €/un era o número que alguém lia para decidir uma compra."""
        casa = self._farinha_com_lote_com_preco_e_outro_sem("diluicao")
        linha = _itens(_sessao(casa.gerente.email).get("/api/v1/stock/levels"))[0]

        assert linha["unit_cost"] == "2.000000", (
            "o custo unitário voltou a ser diluído pela quantidade sem preço"
        )
        assert linha["total_value"] == "60.00"
        assert linha["quantity"]["base"] == "100.000"
        assert linha["quantity_without_cost"]["base"] == "70.000"

    def test_a_invariante_fecha_ao_centimo(self):
        """`unit_cost × (quantity − quantity_without_cost) == total_value`.

        Ao cêntimo e não ao milionésimo: o `unit_cost` sai com seis casas e o
        `total_value` com duas, logo a igualdade é a do dinheiro que se imprime.
        Três formas diferentes do mesmo artigo — cobertura parcial, cobertura
        total com dois preços, e um artigo só — para a invariante não passar por
        acidente num caso.
        """
        casa = self._farinha_com_lote_com_preco_e_outro_sem("invariante")
        acucar = _artigo(casa, nome="Açúcar")
        for indice, (quantidade, custo) in enumerate((("100", "0.5"), ("20", "0.75"))):
            lote = _lote(casa, acucar, codigo=f"AC-{indice}", dias=30 + indice)
            _receber(casa, acucar, casa.loja, lote,
                     quantidade=Decimal(quantidade), custo=Decimal(custo))

        linhas = _itens(_sessao(casa.dono.email).get("/api/v1/stock/levels"))
        assert len(linhas) == 2
        for linha in linhas:
            com_preco = Decimal(linha["quantity"]["base"]) - Decimal(
                linha["quantity_without_cost"]["base"]
            )
            reconstruido = (Decimal(linha["unit_cost"]) * com_preco).quantize(
                Decimal("0.01")
            )
            assert reconstruido == Decimal(linha["total_value"]), linha

    def test_o_artigo_sem_preco_nenhum_nao_tem_custo_unitario(self):
        """Divisor a zero: `unit_cost` é `null` e `total_value` é `0,00`.

        São **factos diferentes** e por isso têm formas diferentes. O
        `total_value` é a soma de nada e zero é verdade — "deste artigo não se
        conhece um cêntimo de valor" —, e é somável com o resto do painel. O
        `unit_cost` seria uma afirmação falsa sobre o preço, logo não existe:
        `null` é "não se conhece custo", que é o que a ADR 0032 separou da
        **chave ausente**, que é "não te compete". Quem lê distingue o zero de
        mercadoria oferecida pela cobertura, que é igual ao saldo todo.
        """
        casa = _casa("sem-preco-nenhum")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="S-1")
        _receber(casa, farinha, casa.loja, lote,
                 quantidade=Decimal("40"), custo=Decimal("0"))

        linha = _itens(_sessao(casa.gerente.email).get("/api/v1/stock/levels"))[0]
        assert linha["unit_cost"] is None
        assert linha["total_value"] == "0.00"
        assert linha["quantity"]["base"] == "40.000"
        assert linha["quantity_without_cost"]["base"] == "40.000"

        # E ao colaborador continuam a faltar as duas chaves de euro, com a
        # quantidade toda lá: a política não muda com o divisor.
        do_staff = _itens(_sessao(casa.staff.email).get("/api/v1/stock/levels"))[0]
        for chave in EUROS_DO_PAINEL:
            assert chave not in do_staff
        assert do_staff["quantity"]["base"] == "40.000"

    def test_o_lote_sem_preco_do_alerta_diz_o_mesmo(self):
        """Num alerta a linha é **um lote**, logo o divisor é tudo ou nada.

        Tem preço (e o valor em risco é o do lote) ou não tem (e não há valor
        nenhum). É por isso que a linha de grão lote nunca pôde diluir e é
        nela que o marcador é uma palavra em vez de uma cobertura. Era o
        `by-product` que a servia; morreu com a ADR 0034 e o grão de lote
        ficou onde é accionável.
        """
        casa = self._farinha_com_lote_com_preco_e_outro_sem("detalhe-sem-preco")
        por_lote = {
            item["lot"]["lot_code"]: item
            for item in _itens(
                _sessao(casa.gerente.email).get("/api/v1/stock/alerts?risco=expira")
            )
        }

        assert por_lote["COM"]["value_eur"] == "60.00"
        assert por_lote["COM"]["cost_status"] == CUSTO_CONHECIDO
        assert por_lote["SEM"]["value_eur"] == "0.00"
        assert por_lote["SEM"]["cost_status"] == CUSTO_DESCONHECIDO


# ---------------------------------------------------------------------------
# 9. O trabalho de campo não perde nada (decisão 3)
# ---------------------------------------------------------------------------
class TestOTrabalhoDeCampoNaoPerdeNada:
    """Contar, receber, perder e transferir continuam todos abertos ao `staff`.

    É a outra metade da decisão 1: onde um custo é preciso para a operação
    funcionar, quem o calcula é o **servidor** — o `waste`, o `adjustment` e o
    `transfer` escolhem o lote por FEFO e lêem o custo do nível por dentro, e o
    corpo de entrada nunca traz dinheiro.
    """

    def test_contar_receber_perder_e_transferir_continuam_a_funcionar(self):
        casa = _casa("trabalho")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="T-1")
        _receber(casa, farinha, casa.loja, lote,
                 quantidade=Decimal("100"), custo=Decimal("0.5"))
        staff = _sessao(casa.staff.email)

        # Receber mercadoria: a receção é de quem está lá (ADR 0021, d9).
        rececao = staff.post(
            "/api/v1/receipts",
            {
                "location": str(casa.loja.id),
                "supplier_name": "Makro",
                "doc_type": "FT",
            },
            format="json",
        )
        assert rececao.status_code == 201, rececao.content

        # Contar: a contagem é aberta por quem pode, e contada por quem conta.
        contagem_id = _sessao(casa.dono.email).post(
            "/api/v1/stock/counts", {"location": str(casa.loja.id)}, format="json"
        ).json()["id"]
        contou = staff.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(farinha.id), "quantity": "97.000"},
            format="json",
        )
        assert contou.status_code == 200, contou.content
        assert contou.json()["counted"]["base"] == "97.000"
        assert contou.json()["difference"]["base"] == "-3.000"

        # Perder — e **sem lote no corpo**, que é como o ecrã o envia: o FEFO
        # é do servidor desde a ADR 0034, decisão 8.
        perdeu = staff.post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(farinha.id),
                "location": str(casa.loja.id),
                "quantity": "1.500",
                "unit": "un",
                "reason": "expired",
            },
            format="json",
        )
        assert perdeu.status_code == 201, perdeu.content

        # Transferir.
        transferiu = staff.post(
            "/api/v1/stock/movements/transfer",
            {
                "product": str(farinha.id),
                "from_location": str(casa.loja.id),
                "to_location": str(casa.armazem.id),
                "lot": str(lote.id),
                "quantity": "10.000",
            },
            format="json",
        )
        assert transferiu.status_code == 201, transferiu.content

        # E o saldo que ele vê reflecte tudo o que fez: 100 − 1,5 − 10 na loja.
        linha = _itens(staff.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))[0]
        assert linha["quantity"]["base"] == "88.500"


# ---------------------------------------------------------------------------
# 10. A lista fechada das chaves de dinheiro do módulo
# ---------------------------------------------------------------------------
#: Cada campo do `inventory/serializers.py` cujo **nome** parece dinheiro, e o
#: que o protege. Três valores possíveis:
#:
#: - `"mixin"` — o `SemEurosParaQuemNaoVe` tira-o do payload (ADR 0032);
#: - `"rota"`  — a rota inteira é de `owner|manager`, logo não há o que filtrar;
#: - `"não é dinheiro"` — o nome engana: é quantidade ou qualidade de dados.
#:
#: O teste falha nos **dois** sentidos: uma chave nova sem entrada aqui, ou uma
#: entrada aqui sem campo lá. É a oitava chave que a ADR 0032 quer apanhar.
CHAVES_QUE_PARECEM_DINHEIRO: dict[tuple[str, str], str] = {
    # --- Os sete recursos de `/stock` (ADR 0034) ---
    ("NivelDeStockOutSerializer", "unit_cost"): "mixin",
    ("NivelDeStockOutSerializer", "total_value"): "mixin",
    # A cobertura do agregado: é **quantidade**, e é o que substitui a palavra
    # numa linha que soma lotes com preço e lotes sem.
    ("NivelDeStockOutSerializer", "quantity_without_cost"): "não é dinheiro",
    # A ficha de um artigo (ADR 0034, adenda de 29, decisão 15). As três
    # entradas são **herdadas** e é esse o ponto: o `NivelDoArtigoOut` declara
    # um campo só (`never_stocked`) e **não** redeclara o `CAMPOS_DE_DINHEIRO`
    # — redeclará-lo é a porta irmã por onde o dinheiro sai. O
    # `test_o_que_a_tabela_diz_que_o_mixin_esconde_esta_mesmo_no_mixin` lê o
    # atributo **na subclasse**, logo uma redeclaração a menos cai aqui.
    ("NivelDoArtigoOutSerializer", "unit_cost"): "mixin",
    ("NivelDoArtigoOutSerializer", "total_value"): "mixin",
    ("NivelDoArtigoOutSerializer", "quantity_without_cost"): "não é dinheiro",
    ("ResumoDeStockOutSerializer", "stock_value_eur"): "mixin",
    ("MovimentoOutSerializer", "unit_cost"): "mixin",
    ("MovimentoOutSerializer", "cost_status"): "não é dinheiro",
    ("AlertaOutSerializer", "value_eur"): "mixin",
    ("AlertaOutSerializer", "cost_status"): "não é dinheiro",
    ("DesperdicioOutSerializer", "value_eur"): "mixin",
    ("DesperdicioOutSerializer", "cost_status"): "não é dinheiro",
    ("ResumoDeAlertasOutSerializer", "wasted_today_eur"): "mixin",
    ("ResumoDeAlertasOutSerializer", "wasted_week_eur"): "mixin",
    # As duas da cobertura (decisão 10): **contagens de linhas**, presentes
    # para os três papéis. Um `COUNT(id)` não tem euros em ponta nenhuma — não
    # há numerador nem denominador —, logo nenhuma sequência de observações
    # reconstrói o custo unitário a partir delas. A condição está no
    # `aggregate()` do `contadores_de_desperdicio` e tem teste próprio que lê
    # o SQL (`test_stock_e_alertas.py`). Os dois `wasted_*_count` não aparecem
    # nesta tabela porque o filtro de nomes não lhes toca — e é isso que o
    # `test_os_quatro_contadores_novos_chegam_aos_tres_papeis` cobre.
    (
        "ResumoDeAlertasOutSerializer",
        "wasted_today_lines_without_cost",
    ): "não é dinheiro",
    (
        "ResumoDeAlertasOutSerializer",
        "wasted_week_lines_without_cost",
    ): "não é dinheiro",
    # --- Os 201 dos movimentos manuais (ADR 0025, ADR 0032) ---
    ("MovimentoDeStockOutSerializer", "unit_cost"): "mixin",
    ("MovimentoDeStockOutSerializer", "cost_status"): "não é dinheiro",
    ("StockMovementResponseSerializer", "unit_cost"): "mixin",
    ("StockMovementResponseSerializer", "cost_status"): "não é dinheiro",
    ("PernaDeTransferenciaOutSerializer", "unit_cost"): "mixin",
    ("PernaDeTransferenciaOutSerializer", "cost_status"): "não é dinheiro",
    # --- A contagem física (ADR 0030) ---
    ("LinhaDeContagemOutSerializer", "difference_eur"): "mixin",
    # As quatro do fecho: a rota é de `owner|manager` (ADR 0030) e esses são
    # exactamente os `PAPEIS_QUE_VEEM_EUROS` — ver
    # `TestOLimiarDoFechoNaoChegaAQuemNaoVeEuros`. O
    # `reason_required_above_eur` é o oráculo adormecido: a zero não diz nada,
    # com limiar ≠ 0 cada linha limita um custo.
    ("FechoDeContagemOutSerializer", "loss_eur"): "rota",
    ("FechoDeContagemOutSerializer", "gain_eur"): "rota",
    ("FechoDeContagemOutSerializer", "net_eur"): "rota",
    ("FechoDeContagemOutSerializer", "reason_required_above_eur"): "rota",
    # `total_lines` é a contagem de **linhas** da contagem física. Está aqui
    # porque o filtro apanha o pedaço "total" de propósito: um campo chamado
    # `total` sem mais nada é quase sempre dinheiro, e preferiu-se três linhas
    # de ruído a um buraco no alarme.
    ("ContagemOutSerializer", "total_lines"): "não é dinheiro",
    ("ProgressoDeZonaOutSerializer", "total_lines"): "não é dinheiro",
    ("FechoDeContagemOutSerializer", "total_lines"): "não é dinheiro",
}

#: O que faz um nome "parecer dinheiro". Grosseiro de propósito: apanha
#: `quantity_without_cost` e `cost_status`, que não são dinheiro — e é por isso
#: que a tabela acima diz, campo a campo, qual é qual.
PEDACOS_DE_DINHEIRO = ("eur", "cost", "value", "price", "total")


def _campos_que_parecem_dinheiro() -> dict[tuple[str, str], list[str]]:
    encontrados: dict[tuple[str, str], list[str]] = {}
    for nome, objeto in vars(serializers_do_inventory).items():
        if not isinstance(objeto, type) or not issubclass(objeto, drf.Serializer):
            continue
        for campo in objeto().fields:
            if any(pedaco in campo for pedaco in PEDACOS_DE_DINHEIRO):
                chave = (nome, campo)
                encontrados[chave] = list(
                    getattr(objeto, "CAMPOS_DE_DINHEIRO", ())
                )
    return encontrados


class TestAsChavesDeDinheiroDoModulo:
    """A lista fechada, e um teste que falha nos dois sentidos."""

    def test_a_lista_de_chaves_e_exactamente_esta(self):
        encontrados = _campos_que_parecem_dinheiro()
        assert set(encontrados) == set(CHAVES_QUE_PARECEM_DINHEIRO), (
            "um campo com nome de dinheiro apareceu ou desapareceu no "
            "`inventory/serializers.py`: decide se se esconde pelo mixin, se a "
            "rota já o protege, ou se o nome engana — e escreve-o na tabela"
        )

    def test_o_que_a_tabela_diz_que_o_mixin_esconde_esta_mesmo_no_mixin(self):
        for (classe, campo), quem_protege in CHAVES_QUE_PARECEM_DINHEIRO.items():
            campos_do_mixin = _campos_que_parecem_dinheiro()[(classe, campo)]
            if quem_protege == "mixin":
                assert campo in campos_do_mixin, f"{classe}.{campo}"
            else:
                assert campo not in campos_do_mixin, f"{classe}.{campo}"

    def test_a_reparticao_por_localizacao_nao_tem_chave_de_dinheiro_nenhuma(self):
        """O `by_location` é quantidade pura, e é o que o `staff` mais lê.

        Substitui a asserção sobre o `AlertSerializer`, que a ADR 0032 deixara
        intacto por não ter euros: com a ADR 0034 o alerta **ganhou** um
        `value_eur`, protegido pelo mixin e inscrito na tabela acima. O campo
        que continua a não poder ter euro nenhum é este.
        """
        campos = set(serializers_do_inventory.NivelPorLocalizacaoOutSerializer().fields)
        assert not [
            campo
            for campo in campos
            if any(pedaco in campo for pedaco in PEDACOS_DE_DINHEIRO)
        ]
