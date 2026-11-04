"""Fichas técnicas: as quatro rotas, a escada do custo e os euros por papel.

ADR 0035, fatia A. O que este ficheiro mede são as decisões da ADR, uma classe
por decisão, mais os casos-limite que ela deixou escritos.

## Porque é que o stock entra sempre pelo ledger

Nenhum teste escreve `StockLevel.objects.create(...)`. O nível é a **projecção**
da soma dos movimentos: o `record_movements` recalcula-o a partir deles, logo um
nível escrito à mão desaparece no primeiro movimento que lhe toca. É a mesma
nota que o `tests/test_contagens.py` tem, pela mesma razão.

## Os dois estilos de teste, e quando cada um

A escada do custo e a guarda de ciclos medem-se por **HTTP**, porque é no corpo
da resposta que elas são visíveis e porque é lá que os euros desaparecem por
papel. As regras que não têm forma HTTP — a terminação da cascata, a ordem da
aritmética — medem-se também por HTTP, mas com os números escolhidos para que a
resposta distinga as duas ordens possíveis.

## O throttle, e o balde que é de toda a gente

As escritas levam o balde `catalogo` (20/min) e o `ScopedRateThrottle` conta por
**utilizador**: cada teste cria o seu `_casa()`, logo o seu dono, logo o seu
balde.

O **login** não é assim, e isto custou uma corrida inteira da suite a descobrir:
`/api/v1/auth/login` é anónimo, logo quem o cobre é o `AnonRateThrottle` a
60/min, e a chave dele é o **endereço IP** — que numa suite é `127.0.0.1` para
todos os testes de todos os ficheiros. O balde não é deste ficheiro: é da suite
inteira, e sobrevive de teste para teste dentro do `LocMemCache`.

Este ficheiro faz cerca de sessenta `_sessao(...)`, ou seja **um minuto inteiro
de orçamento sozinho**. Corrido isolado passava; corrido depois dos outros
levava `429` no login, e o teste que o apanhasse parecia um bug de domínio
(`KeyError: 'batch_cost'` numa ficha que o servidor nunca chegou a servir).

A `_limpa_o_balde_do_throttle` abaixo resolve-o nos **dois** sentidos: este
ficheiro deixa de falhar pelo que correu antes dele, e deixa de empurrar para 429
o que correr a seguir.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import serializers as drf
from rest_framework.test import APIClient

from apps.accounts.api import PAPEIS_QUE_VEEM_EUROS
from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.models import Location
from apps.inventory.services import MovementDTO, record_movements
from apps.recipes import serializers as serializers_das_receitas
from apps.recipes.models import Recipe, RecipeLineItem
from apps.recipes.views import SO_OWNER_OU_MANAGER
from apps.shared.db import tenant_scope

URL = "/api/v1/recipes"
CREDENCIAL = "receitas-teste-123"


@pytest.fixture(autouse=True)
def _limpa_o_balde_do_throttle() -> None:
    """Zera o histórico do throttle antes de cada teste deste ficheiro.

    O `AnonRateThrottle` do login guarda o histórico no cache e indexa-o pelo
    **IP**, que é o mesmo para a suite toda. Sem isto, o resultado de um teste
    daqui depende de quantos logins os outros ficheiros já fizeram neste minuto
    — exactamente o tipo de teste que "afirma coisas diferentes em máquinas
    diferentes" que o CLAUDE.md proíbe, com o agravante de a diferença ser a
    **ordem** e não a máquina.

    Limpa o cache inteiro porque em testes ele só tem isto: o `CACHES` do
    `config/settings/test.py` é um `LocMemCache` local ao processo.
    """
    cache.clear()


# ---------------------------------------------------------------------------
# Andaimes
# ---------------------------------------------------------------------------
def _casa(*, nome: str = "Pastelaria das Fichas") -> SimpleNamespace:
    """Um estabelecimento com os três papéis e uma localização."""
    tenant = criar_tenant(name=nome)
    with tenant_scope(tenant.id):
        dono = User.objects.create_user(f"dono@{tenant.id}.pt", CREDENCIAL)
        conceder_pertenca(
            user=dono, tenant_id=tenant.id, role=Papel.OWNER, display_name="Ana Dona"
        )
        gerente = User.objects.create_user(f"gerente@{tenant.id}.pt", CREDENCIAL)
        conceder_pertenca(
            user=gerente,
            tenant_id=tenant.id,
            role=Papel.MANAGER,
            display_name="Bruno Gerente",
        )
        colaborador = User.objects.create_user(f"staff@{tenant.id}.pt", CREDENCIAL)
        conceder_pertenca(
            user=colaborador,
            tenant_id=tenant.id,
            role=Papel.STAFF,
            display_name="Carla Pasteleira",
        )
        loja = Location.objects.create(tenant=tenant, name="Loja", position=0)
        armazem = Location.objects.create(tenant=tenant, name="Armazem", position=1)
    return SimpleNamespace(
        tenant=tenant,
        dono=dono,
        gerente=gerente,
        colaborador=colaborador,
        loja=loja,
        armazem=armazem,
    )


def _artigo(
    casa: SimpleNamespace,
    *,
    nome: str,
    base: str = UnidadeBase.GRAMA,
    apresentacao: str = "kg",
    factor: str = "1000",
    ativo: bool = True,
) -> Product:
    with tenant_scope(casa.tenant.id):
        return Product.objects.create(
            tenant=casa.tenant,
            short_name=nome,
            sku=nome.replace(" ", "-").lower(),
            base_unit=base,
            display_unit=apresentacao,
            display_factor=Decimal(factor),
            track_lots=False,
            is_active=ativo,
        )


def _unidades(casa: SimpleNamespace, *, nome: str) -> Product:
    """Um artigo que se conta às unidades: base `un`, apresentação `un`."""
    return _artigo(
        casa,
        nome=nome,
        base=UnidadeBase.UNIDADE,
        apresentacao=UnidadeBase.UNIDADE,
        factor="1",
    )


def _receber(
    casa: SimpleNamespace,
    produto: Product,
    *,
    quantidade: str,
    custo: str,
    local: Location | None = None,
) -> None:
    """Stock inicial **pelo ledger**. Nunca por `StockLevel.objects.create`."""
    with tenant_scope(casa.tenant.id):
        record_movements(
            tenant_id=casa.tenant.id,
            movements=[
                MovementDTO(
                    product_id=produto.id,
                    location_id=(local or casa.loja).id,
                    lot_id=None,
                    quantity=Decimal(quantidade),
                    unit_cost=Decimal(custo),
                    cost_is_estimate=False,
                    movement_type="receipt",
                    occurred_at=timezone.now(),
                    created_by_id=None,
                    created_by_name="semeador",
                )
            ],
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


def _corpo(
    *,
    produto: Product,
    fornada: str = "1",
    unidade_da_fornada: str | None = None,
    linhas: tuple[tuple[Product, str, str], ...],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "product": str(produto.id),
        "batch_size": fornada,
        "batch_unit": unidade_da_fornada or produto.display_unit,
        "lines": [
            {"ingredient": str(artigo.id), "quantity": quantidade, "unit": unidade}
            for artigo, quantidade, unidade in linhas
        ],
        **extra,
    }


def _ficha(
    casa: SimpleNamespace,
    *,
    acabado: Product,
    fornada: str = "1000",
    rendimento: str = "1.000",
    ativa: bool = True,
    linhas: tuple[tuple[Product, str], ...] = (),
) -> Recipe:
    """Uma ficha escrita directamente, para os testes que não medem a escrita.

    Os números são em unidade **base** e por fornada, que é o que o serviço e a
    base de dados guardam.
    """
    with tenant_scope(casa.tenant.id):
        receita = Recipe.objects.create(
            tenant=casa.tenant,
            product=acabado,
            is_active=ativa,
            batch_size=Decimal(fornada),
            yield_factor=Decimal(rendimento),
        )
        for artigo, quantidade in linhas:
            RecipeLineItem.objects.create(
                tenant=casa.tenant,
                recipe=receita,
                ingredient_product=artigo,
                quantity_per_base_unit=Decimal(quantidade),
            )
    return receita


def _linha_de(ficha: dict[str, Any], nome: str) -> dict[str, Any]:
    """A linha de um ingrediente pelo nome curto.

    Pelo nome e não pelo índice: os testes do lote leem a mesma ficha de dois
    sítios e o que se compara é o **ingrediente**, não a posição dele.
    """
    for linha in ficha["lines"]:
        if linha["short_name"] == nome:
            return linha
    raise AssertionError(
        f"{nome!r} não está na ficha: {[linha['short_name'] for linha in ficha['lines']]}"
    )


# ---------------------------------------------------------------------------
# 1. O caminho feliz e a forma do contrato
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOCaminhoFeliz:
    """Decisões 4 e 8: a ficha é um documento, e é por fornada."""

    def test_grava_a_ficha_inteira_num_pedido_e_devolve_a_ficha(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa Folhada")
        farinha = _artigo(casa, nome="Farinha T65")
        ovos = _unidades(casa, nome="Ovos")

        criou = _sessao(casa.dono.email).post(
            URL,
            _corpo(
                produto=massa,
                fornada="2.4",
                linhas=((farinha, "1.5", "kg"), (ovos, "6", "un")),
            ),
            format="json",
        )

        assert criou.status_code == 201, criou.content
        corpo = criou.json()
        # A fornada veio em quilos e é guardada em gramas, com as duas formas.
        assert corpo["batch_size"] == {
            "base": "2400.000",
            "base_unit": "g",
            "display": "2.400",
            "display_unit": "kg",
        }
        assert corpo["yield_factor"] == "1.000", "o default nasce a 1, não a 0,9"
        assert corpo["is_active"] is True
        assert corpo["line_count"] == 2
        assert [linha["short_name"] for linha in corpo["lines"]] == [
            "Farinha T65",
            "Ovos",
        ]
        # 1,5 kg escritos, 1500 g guardados — a conversão é do servidor.
        assert corpo["lines"][0]["quantity"]["base"] == "1500.000"
        assert corpo["lines"][0]["quantity"]["display"] == "1.500"
        assert corpo["lines"][1]["quantity"]["base"] == "6.000"
        # Rendimento 1 → o consumo real é igual ao da lista.
        assert corpo["lines"][0]["quantity_real"]["base"] == "1500.000"

    def test_a_ficha_fica_na_base_de_dados_por_fornada_e_nao_por_unidade(self):
        """Decisão 8: dividir pela fornada ao gravar arrasava os pequenos."""
        casa = _casa()
        bolo = _artigo(casa, nome="Bolo")
        corante = _artigo(casa, nome="Corante")

        criou = _sessao(casa.dono.email).post(
            URL,
            _corpo(
                produto=bolo,
                fornada="400",
                unidade_da_fornada="g",
                linhas=((corante, "2", "g"),),
            ),
            format="json",
        )

        assert criou.status_code == 201, criou.content
        with tenant_scope(casa.tenant.id):
            linha = RecipeLineItem.objects.get(ingredient_product=corante)
        assert linha.quantity_per_base_unit == Decimal("2.000"), (
            "2 g na ficha são 2 g na coluna; a dividir por 400 seriam 0,005 — e "
            "uma essência numa fornada maior seria 0,000, que desaparece do "
            "custo e do consumo"
        )

    def test_a_lista_traz_a_ficha_e_o_detalhe_e_a_linha_mais_as_linhas(self):
        """A linha da lista **é** o cabeçalho da ficha, por construção."""
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))
        dono = _sessao(casa.dono.email)

        lista = dono.get(URL)
        detalhe = dono.get(f"{URL}/{receita.id}")

        assert lista.status_code == 200 and detalhe.status_code == 200
        da_lista = lista.json()["results"][0]
        da_ficha = detalhe.json()
        assert set(da_ficha) - set(da_lista) == {"lines"}, (
            "o detalhe é a linha da lista mais as linhas, e mais nada"
        )
        assert {
            chave: valor for chave, valor in da_ficha.items() if chave != "lines"
        } == da_lista

    def test_uma_receita_inactiva_responde_200_e_nunca_404(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, ativa=False, linhas=((farinha, "10"),))

        resposta = _sessao(casa.dono.email).get(f"{URL}/{receita.id}")

        assert resposta.status_code == 200, "mercadoria que existiu continua auditável"
        assert resposta.json()["is_active"] is False, "marcada, nunca escondida"

    def test_a_lista_esconde_as_inactivas_por_omissao_e_mostra_as_com_estado_todas(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        _ficha(casa, acabado=_artigo(casa, nome="Massa"), linhas=((farinha, "10"),))
        _ficha(
            casa,
            acabado=_artigo(casa, nome="Broa"),
            ativa=False,
            linhas=((farinha, "10"),),
        )
        dono = _sessao(casa.dono.email)

        assert dono.get(URL).json()["count"] == 1
        assert dono.get(f"{URL}?estado=todas").json()["count"] == 2
        assert dono.get(f"{URL}?estado=arquivadas").status_code == 400

    def test_o_filtro_por_ingrediente_responde_que_receitas_usam_farinha(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Acucar")
        _ficha(casa, acabado=_artigo(casa, nome="Pao"), linhas=((farinha, "600"),))
        _ficha(casa, acabado=_artigo(casa, nome="Gelado"), linhas=((acucar, "400"),))
        dono = _sessao(casa.dono.email)

        com_farinha = dono.get(f"{URL}?ingrediente={farinha.id}").json()

        assert [linha["short_name"] for linha in com_farinha["results"]] == ["Pao"]
        assert dono.get(f"{URL}?ingrediente=nao-e-um-uuid").status_code == 400


# ---------------------------------------------------------------------------
# 2. Os papéis, e a assimetria (decisão 5)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOsPapeis:
    """Ler é dos três; escrever é de `owner|manager`."""

    def test_o_colaborador_le_a_ficha_e_nao_a_escreve(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))
        staff = _sessao(casa.colaborador.email)

        assert staff.get(URL).status_code == 200
        assert staff.get(f"{URL}/{receita.id}").status_code == 200
        assert (
            staff.post(
                URL,
                _corpo(produto=_artigo(casa, nome="Pao"), linhas=((farinha, "1", "kg"),)),
                format="json",
            ).status_code
            == 403
        )
        assert (
            staff.patch(
                f"{URL}/{receita.id}", {"is_active": False}, format="json"
            ).status_code
            == 403
        )

    def test_o_gerente_escreve(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")

        criou = _sessao(casa.gerente.email).post(
            URL, _corpo(produto=massa, linhas=((farinha, "1", "kg"),)), format="json"
        )

        assert criou.status_code == 201, criou.content

    def test_quem_escreve_e_exactamente_quem_ve_euros(self):
        """A assimetria é uma só regra, e vive no `accounts.api`.

        Prende as duas listas uma à outra: no dia em que os euros passarem a ser
        de outro conjunto de papéis, ou a escrita da ficha acompanha ou esta
        asserção diz que divergiram.
        """
        assert SO_OWNER_OU_MANAGER.papeis == PAPEIS_QUE_VEEM_EUROS

    def test_sem_sessao_e_403(self):
        assert APIClient().get(URL).status_code == 403


# ---------------------------------------------------------------------------
# 3. O tenant errado é 404, e não 403
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOTenantErrado:
    """404 porque a política não devolve a linha, não porque alguém comparou."""

    def test_a_ficha_de_outro_estabelecimento_e_404(self):
        alfa = _casa(nome="Alfa")
        beta = _casa(nome="Beta")
        massa = _artigo(beta, nome="Massa")
        farinha = _artigo(beta, nome="Farinha")
        da_beta = _ficha(beta, acabado=massa, linhas=((farinha, "10"),))

        dono_da_alfa = _sessao(alfa.dono.email)

        assert dono_da_alfa.get(f"{URL}/{da_beta.id}").status_code == 404
        assert (
            dono_da_alfa.patch(
                f"{URL}/{da_beta.id}", {"is_active": False}, format="json"
            ).status_code
            == 404
        ), "404 e não 403: um 403 confirmava que a ficha existe"
        assert dono_da_alfa.get(URL).json()["count"] == 0

    def test_um_ingrediente_de_outro_estabelecimento_e_404(self):
        alfa = _casa(nome="Alfa")
        beta = _casa(nome="Beta")
        massa = _artigo(alfa, nome="Massa")
        farinha_da_beta = _artigo(beta, nome="Farinha")

        resposta = _sessao(alfa.dono.email).post(
            URL,
            _corpo(produto=massa, linhas=((farinha_da_beta, "1", "kg"),)),
            format="json",
        )

        assert resposta.status_code == 404

    def test_um_acabado_que_nao_existe_e_404(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        corpo = _corpo(produto=farinha, linhas=((farinha, "1", "kg"),))
        corpo["product"] = str(uuid4())

        assert _sessao(casa.dono.email).post(URL, corpo, format="json").status_code == 404


# ---------------------------------------------------------------------------
# 4. As recusas do contrato
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAsRecusas:
    """Os 400 e o 409 que a ADR escreve por extenso."""

    def test_os_quatro_numeros(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        dono = _sessao(casa.dono.email)
        linha = (farinha, "1", "kg")

        sem_linhas = dono.post(URL, _corpo(produto=massa, linhas=()), format="json")
        fornada_zero = dono.post(
            URL, _corpo(produto=massa, fornada="0", linhas=(linha,)), format="json"
        )
        rendimento_zero = dono.post(
            URL,
            _corpo(produto=massa, linhas=(linha,), yield_factor="0"),
            format="json",
        )
        quantidade_zero = dono.post(
            URL, _corpo(produto=massa, linhas=((farinha, "0", "kg"),)), format="json"
        )

        assert sem_linhas.status_code == 400 and "lines" in sem_linhas.json()
        assert fornada_zero.status_code == 400 and "batch_size" in fornada_zero.json()
        assert rendimento_zero.status_code == 400
        assert "yield_factor" in rendimento_zero.json()
        assert quantidade_zero.status_code == 400 and "lines" in quantidade_zero.json()

    def test_o_rendimento_nao_tem_tecto_de_um(self):
        """Arroz 1 kg cru → 2,7 kg cozido é caso real, e o ganho é água."""
        casa = _casa()
        arroz_cozido = _artigo(casa, nome="Arroz Cozido")
        arroz = _artigo(casa, nome="Arroz")

        criou = _sessao(casa.dono.email).post(
            URL,
            _corpo(
                produto=arroz_cozido, linhas=((arroz, "1", "kg"),), yield_factor="2.700"
            ),
            format="json",
        )

        assert criou.status_code == 201, criou.content
        assert criou.json()["yield_factor"] == "2.700"

    def test_ingrediente_repetido_e_400_e_nunca_duas_linhas_somadas(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")

        resposta = _sessao(casa.dono.email).post(
            URL,
            _corpo(produto=massa, linhas=((farinha, "1", "kg"), (farinha, "2", "kg"))),
            format="json",
        )

        assert resposta.status_code == 400
        assert "lines" in resposta.json()

    def test_a_unidade_tem_de_ser_a_base_ou_a_de_apresentacao_daquele_artigo(self):
        """Não há motor genérico de conversão (ADR 0011), e o 400 diz **qual**."""
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        ovos = _unidades(casa, nome="Ovos")
        dono = _sessao(casa.dono.email)

        resposta = dono.post(
            URL,
            _corpo(
                produto=massa,
                linhas=((farinha, "1", "kg"), (ovos, "60", "g")),
            ),
            format="json",
        )

        assert resposta.status_code == 400
        erros = resposta.json()["lines"]
        assert erros[0] == {}, "a primeira linha passou"
        assert "unit" in erros[1], "ovos contam-se às unidades, e o erro diz em qual"

    def test_a_unidade_da_fornada_segue_a_mesma_regra_contra_o_acabado(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")

        resposta = _sessao(casa.dono.email).post(
            URL,
            _corpo(
                produto=massa,
                fornada="2.4",
                unidade_da_fornada="l",
                linhas=((farinha, "1", "kg"),),
            ),
            format="json",
        )

        assert resposta.status_code == 400
        assert "batch_unit" in resposta.json(), (
            "o erro aponta para o campo que o corpo tem, e não para o `unit` de "
            "uma linha que aqui não existe"
        )

    def test_o_segundo_post_sobre_o_mesmo_artigo_e_409_com_o_id_do_primeiro(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        dono = _sessao(casa.dono.email)
        corpo = _corpo(produto=massa, linhas=((farinha, "1", "kg"),))

        primeiro = dono.post(URL, corpo, format="json")
        segundo = dono.post(URL, corpo, format="json")

        assert primeiro.status_code == 201
        assert segundo.status_code == 409, segundo.content
        assert segundo.json()["code"] == "receita_ja_existe"
        assert segundo.json()["id"] == primeiro.json()["id"], (
            "o id leva o ecrã à ficha que existe, em vez de dizer 'erro'"
        )

    def test_nao_ha_put_nem_delete(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "10"),))
        dono = _sessao(casa.dono.email)

        assert dono.delete(f"{URL}/{receita.id}").status_code == 405
        assert dono.put(f"{URL}/{receita.id}", {}, format="json").status_code == 405


# ---------------------------------------------------------------------------
# 5. Os ciclos (decisão 10)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOsCiclos:
    """Um ciclo no grafo é sempre erro de dados; a escrita recusa-o."""

    def test_um_artigo_ingrediente_de_si_proprio_e_400(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")

        resposta = _sessao(casa.dono.email).post(
            URL, _corpo(produto=massa, linhas=((massa, "1", "kg"),)), format="json"
        )

        assert resposta.status_code == 400
        assert "lines" in resposta.json()

    def test_o_ciclo_transitivo_tambem_e_400(self):
        """Folhada → aparas → folhada. Ninguém vê este a olho."""
        casa = _casa()
        folhada = _artigo(casa, nome="Folhada")
        aparas = _artigo(casa, nome="Aparas")
        # A ficha das aparas já usa folhada.
        _ficha(casa, acabado=aparas, linhas=((folhada, "100"),))

        resposta = _sessao(casa.dono.email).post(
            URL, _corpo(produto=folhada, linhas=((aparas, "1", "kg"),)), format="json"
        )

        assert resposta.status_code == 400
        assert "lines" in resposta.json()

    def test_o_patch_tambem_recusa_o_ciclo(self):
        casa = _casa()
        folhada = _artigo(casa, nome="Folhada")
        aparas = _artigo(casa, nome="Aparas")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=folhada, linhas=((farinha, "500"),))
        _ficha(casa, acabado=aparas, linhas=((folhada, "100"),))

        resposta = _sessao(casa.dono.email).patch(
            f"{URL}/{receita.id}",
            {"lines": [{"ingredient": str(aparas.id), "quantity": "1", "unit": "kg"}]},
            format="json",
        )

        assert resposta.status_code == 400

    def test_a_reembalagem_nao_e_ciclo_e_o_custo_nao_conta_em_dobro(self):
        """"Caixa de 6 pastéis" = 6 × "pastel". São dois artigos, não um ciclo."""
        casa = _casa()
        pastel = _unidades(casa, nome="Pastel")
        caixa = _unidades(casa, nome="Caixa de 6")
        _receber(casa, pastel, quantidade="100", custo="0.30")

        criou = _sessao(casa.dono.email).post(
            URL,
            _corpo(
                produto=caixa,
                fornada="1",
                unidade_da_fornada="un",
                linhas=((pastel, "6", "un"),),
            ),
            format="json",
        )

        assert criou.status_code == 201, criou.content
        corpo = criou.json()
        assert corpo["batch_cost"] == "1.80", "6 × 0,30 €, e não 12 × 0,30 €"
        assert corpo["unit_cost"] == "1.800000"


# ---------------------------------------------------------------------------
# 6. A escada dos cinco degraus (decisão 10)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAEscadaDoCusto:
    """Um teste por degrau, e o 3 e o 4 são os que ninguém adivinha."""

    def _ficha_de_um_ingrediente(
        self, casa: SimpleNamespace, ingrediente: Product, *, nome: str = "Massa"
    ) -> dict[str, Any]:
        massa = _artigo(casa, nome=nome)
        receita = _ficha(
            casa, acabado=massa, fornada="1000", linhas=((ingrediente, "500"),)
        )
        resposta = _sessao(casa.dono.email).get(f"{URL}/{receita.id}")
        assert resposta.status_code == 200, resposta.content
        return resposta.json()

    def test_degrau_1_stock_todo_com_preco_e_conhecido(self):
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="10000", custo="0.002")

        ficha = self._ficha_de_um_ingrediente(casa, farinha)

        assert ficha["lines"][0]["cost_status"] == "conhecido"
        assert ficha["lines"][0]["unit_cost"] == "0.002000"
        assert ficha["lines"][0]["line_cost"] == "1.00"
        assert ficha["cost_status"] == "conhecido"
        assert ficha["ingredients_without_cost"] == 0
        assert ficha["batch_cost"] == "1.00"

    def test_degrau_2_parte_do_stock_sem_preco_e_estimado(self):
        """`conhecido` só com cobertura completa: o CMP está **por baixo**."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        # Duas prateleiras porque a cobertura soma **níveis**: o mesmo artigo no
        # mesmo sítio é um nível só, e o segundo movimento mudava o preço desse
        # em vez de criar quantidade sem preço.
        _receber(casa, farinha, quantidade="10000", custo="0.002")
        _receber(casa, farinha, quantidade="10000", custo="0", local=casa.armazem)

        ficha = self._ficha_de_um_ingrediente(casa, farinha)

        assert ficha["lines"][0]["cost_status"] == "estimado"
        assert ficha["lines"][0]["unit_cost"] == "0.002000", (
            "o número é o mesmo CMP do ecrã de Stock; o que muda é a palavra"
        )
        assert ficha["cost_status"] == "estimado"
        assert ficha["ingredients_without_cost"] == 0, (
            "o ingrediente **tem** custo; o que não tem é precisão"
        )

    def test_degrau_3_o_stock_acabou_e_o_custo_vem_do_ledger(self):
        """O creme acaba ao domingo e o custo do pastel não pode desaparecer."""
        casa = _casa()
        creme = _artigo(casa, nome="Creme")
        _receber(casa, creme, quantidade="10000", custo="0.004")
        _receber(casa, creme, quantidade="-10000", custo="0.004")

        ficha = self._ficha_de_um_ingrediente(casa, creme)

        assert ficha["lines"][0]["cost_status"] == "estimado"
        assert ficha["lines"][0]["unit_cost"] == "0.004000", (
            "um custo que desaparece porque o frigorífico esvaziou é um custo "
            "em que o dono deixa de acreditar"
        )
        assert ficha["cost_status"] == "estimado"

    def test_degrau_4_um_semi_acabado_sem_stock_custa_o_da_sua_ficha(self):
        """No dia 1 não há produções, logo nenhum semi-acabado tem CMP."""
        casa = _casa()
        folhada = _artigo(casa, nome="Folhada")
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        # 1 kg de folhada sai de 800 g de farinha → 0,0016 €/g de folhada.
        _ficha(casa, acabado=folhada, fornada="1000", linhas=((farinha, "800"),))

        ficha = self._ficha_de_um_ingrediente(casa, folhada)

        assert ficha["lines"][0]["cost_status"] == "estimado"
        assert ficha["lines"][0]["unit_cost"] == "0.001600"
        assert ficha["lines"][0]["line_cost"] == "0.80", "500 g × 0,0016 €/g"
        assert ficha["cost_status"] == "estimado", "nunca `conhecido` por cascata"

    def test_a_cascata_para_na_profundidade_tres(self):
        """`inventory-domain` §4: três níveis, e o quarto fica desconhecido."""
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        anterior = farinha
        fichas = []
        for numero in range(4):
            artigo = _artigo(casa, nome=f"Semi {numero}")
            fichas.append(artigo)
            _ficha(casa, acabado=artigo, fornada="1000", linhas=((anterior, "1000"),))
            anterior = artigo

        ao_terceiro = self._ficha_de_um_ingrediente(casa, fichas[2], nome="Ao Terceiro")
        ao_quarto = self._ficha_de_um_ingrediente(casa, fichas[3], nome="Ao Quarto")

        assert ao_terceiro["lines"][0]["cost_status"] == "estimado"
        assert ao_quarto["lines"][0]["cost_status"] == "desconhecido"

    def test_degrau_5_sem_nada_o_custo_e_null_e_nunca_zero(self):
        casa = _casa()
        agua = _artigo(casa, nome="Agua das Pedras")

        ficha = self._ficha_de_um_ingrediente(casa, agua)

        assert ficha["lines"][0]["cost_status"] == "desconhecido"
        assert ficha["lines"][0]["unit_cost"] is None
        assert ficha["lines"][0]["line_cost"] is None
        assert ficha["cost_status"] == "desconhecido"
        assert ficha["ingredients_without_cost"] == 1
        assert ficha["batch_cost"] is None, "zero seria uma afirmação falsa"
        assert ficha["unit_cost"] is None
        assert ficha["display_cost"] is None

    def test_uma_linha_sem_custo_entre_duas_com_custo_da_estimado(self):
        """O agregado nunca é `conhecido` se alguma linha não o for."""
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        agua = _artigo(casa, nome="Agua")
        _receber(casa, farinha, quantidade="10000", custo="0.002")
        receita = _ficha(
            casa,
            acabado=massa,
            fornada="1000",
            linhas=((farinha, "500"), (agua, "100")),
        )

        ficha = _sessao(casa.dono.email).get(f"{URL}/{receita.id}").json()

        assert ficha["cost_status"] == "estimado"
        assert ficha["ingredients_without_cost"] == 1
        assert ficha["batch_cost"] == "1.00", "soma o que sabe, e diz que falta uma"

    def test_a_leitura_termina_mesmo_com_um_ciclo_ja_gravado(self):
        """A guarda de escrita só vale até à última escrita.

        O ciclo entra pela porta das traseiras — duas fichas escritas
        directamente, como ficariam dados de uma versão anterior — e a leitura
        tem de responder em vez de recursar para sempre.
        """
        casa = _casa()
        folhada = _artigo(casa, nome="Folhada")
        aparas = _artigo(casa, nome="Aparas")
        _ficha(casa, acabado=folhada, fornada="1000", linhas=((aparas, "100"),))
        receita = _ficha(casa, acabado=aparas, fornada="1000", linhas=((folhada, "100"),))

        resposta = _sessao(casa.dono.email).get(f"{URL}/{receita.id}")

        assert resposta.status_code == 200
        assert resposta.json()["cost_status"] == "desconhecido"


# ---------------------------------------------------------------------------
# 6b. O lote de um nível não contamina os irmãos
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOsIrmaosNoMesmoLote:
    """O defeito medido contra o servidor a 2026-11-04, e o leque dele.

    A escada expande em **lote por nível** — é o que mata o N+1 da decisão 3 —,
    e o conjunto que impedia ciclos levava o lote **inteiro do nível** antes de
    descer. Dois semi-acabados **irmãos** no mesmo lote, com um a depender do
    outro, davam o dependente por `desconhecido`: a mesma ficha valia 0,03 €
    dentro da Tarte e **nada** dentro do Bolo, e a contribuição dela desaparecia
    da soma em silêncio — a família do *zero mentiroso* que a ADR 0034 fechou no
    ledger, num número com que o dono decide preços.

    Irmãos não formam ciclo entre si; o que forma ciclo é um **caminho**. O que
    estes testes fixam é a propriedade que a correcção compra: **o custo de uma
    ficha não depende de com quem ela calha no mesmo lote** — nem dentro de
    outra receita, nem na mesma página da lista.
    """

    def _a_escada_medida(self, casa: SimpleNamespace) -> tuple[Recipe, Recipe]:
        """O grafo exacto da reprodução: `Creme` ← açúcar, `Massa` ← `Creme`.

        A `Tarte` leva só `Massa`; o `Bolo` leva `Massa` **e** `Creme`, logo os
        dois entram no mesmo lote do primeiro nível e um depende do outro.
        """
        acucar = _artigo(casa, nome="Acucar")
        _receber(casa, acucar, quantidade="100000", custo="0.0015")
        creme = _artigo(casa, nome="Creme")
        massa = _artigo(casa, nome="Massa")
        _ficha(casa, acabado=creme, fornada="10", linhas=((acucar, "1000"),))
        _ficha(casa, acabado=massa, fornada="10", linhas=((creme, "2"),))
        tarte = _ficha(
            casa, acabado=_artigo(casa, nome="Tarte"), fornada="10", linhas=((massa, "1"),)
        )
        bolo = _ficha(
            casa,
            acabado=_artigo(casa, nome="Bolo"),
            fornada="10",
            linhas=((massa, "1"), (creme, "1")),
        )
        return tarte, bolo

    def test_a_mesma_ficha_custa_o_mesmo_dentro_de_duas_receitas(self):
        """O caso medido: 0,03 € na Tarte e `None` no Bolo era a mesma Massa."""
        casa = _casa()
        tarte, bolo = self._a_escada_medida(casa)
        dono = _sessao(casa.dono.email)

        na_tarte = _linha_de(dono.get(f"{URL}/{tarte.id}").json(), "Massa")
        no_bolo = _linha_de(dono.get(f"{URL}/{bolo.id}").json(), "Massa")

        assert na_tarte["unit_cost"] == no_bolo["unit_cost"] == "0.030000", (
            "a Massa é a mesma ficha nas duas receitas: no Bolo ela vem no "
            "mesmo lote que o Creme de que depende, e isso não pode saltá-la"
        )
        assert na_tarte["cost_status"] == no_bolo["cost_status"] == "estimado"

    def test_a_contribuicao_do_irmao_nao_desaparece_da_soma(self):
        casa = _casa()
        _, bolo = self._a_escada_medida(casa)

        ficha = _sessao(casa.dono.email).get(f"{URL}/{bolo.id}").json()

        assert ficha["batch_cost"] == "0.18", (
            "0,03 € da Massa mais 0,15 € do Creme — e não só o Creme"
        )
        assert ficha["ingredients_without_cost"] == 0

    def test_a_lista_diz_o_mesmo_que_o_detalhe(self):
        """Na lista o lote cobre a página toda, logo era aqui que era pior.

        O custo de uma ficha não pode depender de quem calhou na mesma página,
        nem mudar entre a linha da lista e o cabeçalho da ficha.
        """
        casa = _casa()
        tarte, bolo = self._a_escada_medida(casa)
        dono = _sessao(casa.dono.email)

        lista = {linha["id"]: linha for linha in dono.get(URL).json()["results"]}
        detalhe_do_bolo = dono.get(f"{URL}/{bolo.id}").json()
        detalhe_da_tarte = dono.get(f"{URL}/{tarte.id}").json()

        assert lista[str(bolo.id)]["batch_cost"] == detalhe_do_bolo["batch_cost"] == "0.18"
        assert lista[str(tarte.id)]["batch_cost"] == detalhe_da_tarte["batch_cost"] == "0.03"

    def test_o_leque_de_oito_irmaos_com_dependencias_cruzadas(self):
        """Oito semi-acabados no mesmo lote, metade a depender de um irmão.

        Os pares levam a `Base`; os ímpares levam o irmão anterior; e o acabado
        leva os oito, logo entram todos no mesmo lote do primeiro nível. Cada um
        leva uma quantidade diferente, para que oito números iguais não possam
        passar por acaso.

        O que se compara não são números escritos à mão: é o `unit_cost` de cada
        irmão **dentro** do acabado contra o `unit_cost` da **ficha dele**, que
        sai de um lote onde ele está sozinho. São dois caminhos para o mesmo
        número, e o defeito era exactamente os dois discordarem.
        """
        casa = _casa()
        acucar = _artigo(casa, nome="Acucar")
        _receber(casa, acucar, quantidade="1000000", custo="0.002")
        base = _artigo(casa, nome="Base")
        _ficha(casa, acabado=base, fornada="1000", linhas=((acucar, "1000"),))
        irmaos: list[Product] = []
        fichas: list[Recipe] = []
        for numero in range(8):
            irmao = _artigo(casa, nome=f"Semi {numero}")
            ingrediente = base if numero % 2 == 0 else irmaos[numero - 1]
            fichas.append(
                _ficha(
                    casa,
                    acabado=irmao,
                    fornada="1000",
                    linhas=((ingrediente, str(100 * (numero + 1))),),
                )
            )
            irmaos.append(irmao)
        acabado = _ficha(
            casa,
            acabado=_artigo(casa, nome="Acabado"),
            fornada="1000",
            linhas=tuple((irmao, "100") for irmao in irmaos),
        )
        dono = _sessao(casa.dono.email)

        no_acabado = dono.get(f"{URL}/{acabado.id}").json()
        sozinhos = [dono.get(f"{URL}/{ficha.id}").json() for ficha in fichas]

        for numero, sozinho in enumerate(sozinhos):
            dentro = _linha_de(no_acabado, f"Semi {numero}")
            assert dentro["unit_cost"] is not None, (
                f"Semi {numero} ficou sem custo dentro do acabado — e tem ficha"
            )
            assert dentro["unit_cost"] == sozinho["unit_cost"], (
                f"Semi {numero} vale uma coisa dentro do acabado e outra na sua "
                "própria ficha: o custo não pode depender do lote"
            )
            assert dentro["cost_status"] == "estimado"
        assert no_acabado["ingredients_without_cost"] == 0

    def test_um_ciclo_de_tres_responde_e_nao_apaga_os_vizinhos(self):
        """A guarda de escrita só vale até à última escrita.

        Três fichas escritas directamente fecham um ciclo — A leva B, B leva C,
        C leva A —, como ficariam dados de uma versão anterior à guarda. A
        leitura tem de responder em vez de recursar para sempre, **e** o
        ingrediente que não está no ciclo tem de manter o seu custo: um ciclo é
        erro de dados num sítio, não na página inteira.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        a = _artigo(casa, nome="Aparas")
        b = _artigo(casa, nome="Bolacha")
        c = _artigo(casa, nome="Crosta")
        _ficha(casa, acabado=a, fornada="1000", linhas=((b, "1000"),))
        _ficha(casa, acabado=b, fornada="1000", linhas=((c, "1000"),))
        _ficha(casa, acabado=c, fornada="1000", linhas=((a, "1000"),))
        bolo = _ficha(
            casa,
            acabado=_artigo(casa, nome="Bolo"),
            fornada="1000",
            linhas=((a, "500"), (farinha, "500")),
        )

        resposta = _sessao(casa.dono.email).get(f"{URL}/{bolo.id}")

        assert resposta.status_code == 200, resposta.content
        ficha = resposta.json()
        assert _linha_de(ficha, "Aparas")["cost_status"] == "desconhecido"
        assert _linha_de(ficha, "Aparas")["unit_cost"] is None
        assert _linha_de(ficha, "Farinha")["cost_status"] == "conhecido", (
            "o vizinho do ciclo continua a ter o custo que sempre teve"
        )
        assert ficha["batch_cost"] == "1.00"
        assert ficha["ingredients_without_cost"] == 1

    def test_o_ciclo_entre_irmaos_do_mesmo_lote_tambem_termina(self):
        """O ciclo no sítio onde o conjunto de visitados deixou de existir.

        Os três do ciclo entram **no mesmo lote**, como linhas da mesma ficha.
        Era o conjunto de visitados que garantia a terminação aqui; passou a ser
        o orçamento de profundidade, e o que não muda é que a resposta sai.
        """
        casa = _casa()
        a = _artigo(casa, nome="Aparas")
        b = _artigo(casa, nome="Bolacha")
        c = _artigo(casa, nome="Crosta")
        _ficha(casa, acabado=a, fornada="1000", linhas=((b, "1000"),))
        _ficha(casa, acabado=b, fornada="1000", linhas=((c, "1000"),))
        _ficha(casa, acabado=c, fornada="1000", linhas=((a, "1000"),))
        receita = _ficha(
            casa,
            acabado=_artigo(casa, nome="Tudo"),
            fornada="1000",
            linhas=((a, "100"), (b, "100"), (c, "100")),
        )

        resposta = _sessao(casa.dono.email).get(f"{URL}/{receita.id}")

        assert resposta.status_code == 200, resposta.content
        ficha = resposta.json()
        assert ficha["cost_status"] == "desconhecido"
        assert ficha["ingredients_without_cost"] == 3
        assert ficha["batch_cost"] is None, "zero seria uma afirmação falsa"


# ---------------------------------------------------------------------------
# 7. A aritmética e a ordem dela (decisão 8)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAAritmetica:
    """`Σ(linhas) ÷ batch_size`, divisão no fim, arredondamento só na saída."""

    def test_a_divisao_e_no_fim_e_nada_arredonda_pelo_caminho(self):
        """Dividir por linha e somar dava zero; somar e dividir dá um cêntimo.

        Uma fornada de 3 g com um ingrediente que custa um cêntimo: se o
        servidor dividisse cada linha pela fornada **e** arredondasse ao
        cêntimo, a soma saía `0,00` — o custo que desaparece.
        """
        casa = _casa()
        doce = _artigo(casa, nome="Doce", base=UnidadeBase.GRAMA, apresentacao="g", factor="1")
        especiaria = _artigo(
            casa, nome="Especiaria", base=UnidadeBase.GRAMA, apresentacao="g", factor="1"
        )
        _receber(casa, especiaria, quantidade="1000", custo="0.01")
        receita = _ficha(casa, acabado=doce, fornada="3", linhas=((especiaria, "1"),))

        ficha = _sessao(casa.dono.email).get(f"{URL}/{receita.id}").json()

        assert ficha["batch_cost"] == "0.01"
        assert ficha["unit_cost"] == "0.003333", "0,01 ÷ 3, e não 0,00"
        assert ficha["display_cost"] == "0.003333"

    def test_o_consumo_real_divide_pelo_rendimento_e_o_custo_segue(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        receita = _ficha(
            casa,
            acabado=massa,
            fornada="1000",
            rendimento="0.800",
            linhas=((farinha, "800"),),
        )

        ficha = _sessao(casa.dono.email).get(f"{URL}/{receita.id}").json()

        assert ficha["lines"][0]["quantity"]["base"] == "800.000"
        assert ficha["lines"][0]["quantity_real"]["base"] == "1000.000", "800 ÷ 0,8"
        assert ficha["lines"][0]["line_cost"] == "2.00", "1000 g × 0,002 €/g"
        assert ficha["batch_cost"] == "2.00"
        assert ficha["unit_cost"] == "0.002000", "2,00 € ÷ 1000 g"

    def test_os_tres_euros_reconstroem_se_uns_aos_outros(self):
        """Regra da reconstrução por aritmética (ADR 0032, decisão 2)."""
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        ovos = _unidades(casa, nome="Ovos")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        _receber(casa, ovos, quantidade="100", custo="0.25")
        receita = _ficha(
            casa, acabado=massa, fornada="2400", linhas=((farinha, "1500"), (ovos, "6"))
        )

        ficha = _sessao(casa.dono.email).get(f"{URL}/{receita.id}").json()

        linhas = Decimal(ficha["lines"][0]["line_cost"]) + Decimal(
            ficha["lines"][1]["line_cost"]
        )
        assert linhas == Decimal(ficha["batch_cost"]) == Decimal("4.50")
        fornada = Decimal(ficha["batch_size"]["base"])
        assert Decimal(ficha["unit_cost"]) == Decimal("0.001875") == Decimal(
            "4.50"
        ) / fornada
        assert Decimal(ficha["display_cost"]) == Decimal(ficha["unit_cost"]) * Decimal(
            ficha["display_factor"]
        )


# ---------------------------------------------------------------------------
# 8. O PATCH e a substituição total (decisão 4)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOPatch:
    """`lines` ausente não toca nas linhas; presente substitui-as todas."""

    def test_lines_ausente_nao_toca_nas_linhas(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))

        resposta = _sessao(casa.dono.email).patch(
            f"{URL}/{receita.id}", {"yield_factor": "0.900"}, format="json"
        )

        assert resposta.status_code == 200, resposta.content
        assert resposta.json()["yield_factor"] == "0.900"
        assert resposta.json()["line_count"] == 1
        assert resposta.json()["lines"][0]["quantity"]["base"] == "500.000"

    def test_lines_presente_substitui_as_linhas_todas(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Acucar")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))

        resposta = _sessao(casa.dono.email).patch(
            f"{URL}/{receita.id}",
            {"lines": [{"ingredient": str(acucar.id), "quantity": "0.2", "unit": "kg"}]},
            format="json",
        )

        assert resposta.status_code == 200, resposta.content
        assert [linha["short_name"] for linha in resposta.json()["lines"]] == ["Acucar"]
        with tenant_scope(casa.tenant.id):
            assert RecipeLineItem.objects.filter(recipe=receita).count() == 1

    def test_arquivar_e_um_patch_e_desarquivar_tambem(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))
        dono = _sessao(casa.dono.email)

        arquivou = dono.patch(f"{URL}/{receita.id}", {"is_active": False}, format="json")
        voltou = dono.patch(f"{URL}/{receita.id}", {"is_active": True}, format="json")

        assert arquivou.status_code == 200 and arquivou.json()["is_active"] is False
        assert voltou.status_code == 200, (
            "o `get_queryset` não filtra pelo estado: filtrá-lo fazia 404 "
            "exactamente na operação que desarquiva"
        )

    def test_a_fornada_e_a_unidade_dela_viajam_juntas(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))
        dono = _sessao(casa.dono.email)

        so_o_numero = dono.patch(
            f"{URL}/{receita.id}", {"batch_size": "2.4"}, format="json"
        )
        as_duas = dono.patch(
            f"{URL}/{receita.id}",
            {"batch_size": "2.4", "batch_unit": "kg"},
            format="json",
        )

        assert so_o_numero.status_code == 400, "2,4 é quilos ou gramas?"
        assert as_duas.status_code == 200
        assert as_duas.json()["batch_size"]["base"] == "2400.000"

    def test_o_product_nao_e_alteravel(self):
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        outro = _artigo(casa, nome="Outro")
        farinha = _artigo(casa, nome="Farinha")
        receita = _ficha(casa, acabado=massa, linhas=((farinha, "500"),))

        resposta = _sessao(casa.dono.email).patch(
            f"{URL}/{receita.id}", {"product": str(outro.id)}, format="json"
        )

        assert resposta.status_code == 200
        assert resposta.json()["product"] == str(massa.id), (
            "o acabado é a identidade da ficha; mudá-lo fazia o custo de ontem "
            "passar a ser de outro produto sem ninguém ver"
        )


# ---------------------------------------------------------------------------
# 9. Os euros por papel (decisão 6)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOsEurosPorPapel:
    """Cinco chaves, e a **ausência** é a forma — nunca zero, nunca null."""

    def _ficha_com_custo(self, casa: SimpleNamespace) -> Recipe:
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="10000", custo="0.002")
        return _ficha(casa, acabado=massa, fornada="1000", linhas=((farinha, "500"),))

    def test_ao_colaborador_as_cinco_chaves_faltam_na_lista_e_na_ficha(self):
        casa = _casa()
        receita = self._ficha_com_custo(casa)
        staff = _sessao(casa.colaborador.email)

        da_lista = staff.get(URL).json()["results"][0]
        da_ficha = staff.get(f"{URL}/{receita.id}").json()

        for chave in ("batch_cost", "unit_cost", "display_cost"):
            assert chave not in da_lista, f"{chave} na lista"
            assert chave not in da_ficha, f"{chave} na ficha"
        for chave in ("unit_cost", "line_cost"):
            assert chave not in da_ficha["lines"][0], f"{chave} na linha"

    def test_ao_colaborador_as_quantidades_e_a_certeza_ficam(self):
        """As quantidades são o produto, e a palavra é o que resta do custo."""
        casa = _casa()
        receita = self._ficha_com_custo(casa)

        da_ficha = _sessao(casa.colaborador.email).get(f"{URL}/{receita.id}").json()

        assert da_ficha["batch_size"]["display"] == "1.000"
        assert da_ficha["yield_factor"] == "1.000"
        assert da_ficha["cost_status"] == "conhecido"
        assert da_ficha["ingredients_without_cost"] == 0
        assert da_ficha["lines"][0]["cost_status"] == "conhecido"
        assert da_ficha["lines"][0]["quantity_real"]["base"] == "500.000"

    def test_ao_dono_e_ao_gerente_as_cinco_chaves_vem(self):
        casa = _casa()
        receita = self._ficha_com_custo(casa)

        for email in (casa.dono.email, casa.gerente.email):
            ficha = _sessao(email).get(f"{URL}/{receita.id}").json()
            assert ficha["batch_cost"] == "1.00", email
            assert ficha["unit_cost"] == "0.001000", email
            assert ficha["display_cost"] == "1.000000", email
            assert ficha["lines"][0]["unit_cost"] == "0.002000", email
            assert ficha["lines"][0]["line_cost"] == "1.00", email

    def test_o_201_tambem_passa_pelo_filtro(self):
        """O `get_serializer_context()` cobre as quatro rotas, não só as leituras."""
        casa = _casa()
        massa = _artigo(casa, nome="Massa")
        farinha = _artigo(casa, nome="Farinha")
        _receber(casa, farinha, quantidade="10000", custo="0.002")

        criou = _sessao(casa.gerente.email).post(
            URL, _corpo(produto=massa, linhas=((farinha, "0.5", "kg"),)), format="json"
        )

        assert criou.status_code == 201
        assert criou.json()["batch_cost"] == "1.00"


# ---------------------------------------------------------------------------
# 10. A lista fechada das chaves de dinheiro do módulo
# ---------------------------------------------------------------------------
#: Cada campo do `recipes/serializers.py` cujo **nome** parece dinheiro, e o que
#: o protege. Três valores possíveis:
#:
#: - `"mixin"` — o `SemEurosParaQuemNaoVe` tira-o do payload (ADR 0032);
#: - `"rota"`  — a rota inteira é de `owner|manager`, logo não há o que filtrar;
#: - `"não é dinheiro"` — o nome engana: é quantidade ou qualidade de dados.
#:
#: Existe aqui e não no `tests/test_custos_de_stock.py` porque o gate de lá está
#: preso ao `vars(inventory.serializers)` e **não alcança este módulo**: as cinco
#: chaves de dinheiro desta fatia nasciam sem guarda nenhum (ADR 0035, Impacto,
#: gate 2). O teste falha nos **dois** sentidos: uma chave nova sem entrada aqui,
#: ou uma entrada aqui sem campo lá.
CHAVES_QUE_PARECEM_DINHEIRO: dict[tuple[str, str], str] = {
    ("ReceitaResumoOutSerializer", "batch_cost"): "mixin",
    ("ReceitaResumoOutSerializer", "unit_cost"): "mixin",
    ("ReceitaResumoOutSerializer", "display_cost"): "mixin",
    # A palavra da certeza: vai para os três papéis, porque é o que resta do
    # custo a quem não vê o número. Não é euro e não tem euro em ponta nenhuma.
    ("ReceitaResumoOutSerializer", "cost_status"): "não é dinheiro",
    # A cobertura: uma **contagem de linhas**. Um `COUNT` não tem numerador nem
    # denominador, logo nenhuma sequência de observações reconstrói um custo.
    ("ReceitaResumoOutSerializer", "ingredients_without_cost"): "não é dinheiro",
    # As cinco entradas do detalhe são **herdadas**, e é esse o ponto: o
    # `ReceitaDetalheOut` declara um campo só (`lines`) e **não** redeclara o
    # `CAMPOS_DE_DINHEIRO`. O segundo teste lê o atributo na subclasse, logo uma
    # redeclaração a menos cai aqui.
    ("ReceitaDetalheOutSerializer", "batch_cost"): "mixin",
    ("ReceitaDetalheOutSerializer", "unit_cost"): "mixin",
    ("ReceitaDetalheOutSerializer", "display_cost"): "mixin",
    ("ReceitaDetalheOutSerializer", "cost_status"): "não é dinheiro",
    ("ReceitaDetalheOutSerializer", "ingredients_without_cost"): "não é dinheiro",
    ("LinhaDaReceitaOutSerializer", "unit_cost"): "mixin",
    ("LinhaDaReceitaOutSerializer", "line_cost"): "mixin",
    ("LinhaDaReceitaOutSerializer", "cost_status"): "não é dinheiro",
}

#: O que faz um nome "parecer dinheiro". O mesmo filtro grosseiro do
#: `tests/test_custos_de_stock.py`, e de propósito: duas definições de "parece
#: dinheiro" é o começo de um módulo onde o alarme não toca.
PEDACOS_DE_DINHEIRO = ("eur", "cost", "value", "price", "total")


def _campos_que_parecem_dinheiro() -> dict[tuple[str, str], list[str]]:
    encontrados: dict[tuple[str, str], list[str]] = {}
    for nome, objeto in vars(serializers_das_receitas).items():
        if not isinstance(objeto, type) or not issubclass(objeto, drf.Serializer):
            continue
        for campo in objeto().fields:
            if any(pedaco in campo for pedaco in PEDACOS_DE_DINHEIRO):
                encontrados[(nome, campo)] = list(
                    getattr(objeto, "CAMPOS_DE_DINHEIRO", ())
                )
    return encontrados


class TestAsChavesDeDinheiroDoModulo:
    """A lista fechada, e um teste que falha nos dois sentidos."""

    def test_a_lista_de_chaves_e_exactamente_esta(self):
        encontrados = _campos_que_parecem_dinheiro()
        assert set(encontrados) == set(CHAVES_QUE_PARECEM_DINHEIRO), (
            "um campo com nome de dinheiro apareceu ou desapareceu no "
            "`recipes/serializers.py`: decide se se esconde pelo mixin, se a "
            "rota já o protege, ou se o nome engana — e escreve-o na tabela"
        )

    def test_o_que_a_tabela_diz_que_o_mixin_esconde_esta_mesmo_no_mixin(self):
        encontrados = _campos_que_parecem_dinheiro()
        for (classe, campo), quem_protege in CHAVES_QUE_PARECEM_DINHEIRO.items():
            campos_do_mixin = encontrados[(classe, campo)]
            if quem_protege == "mixin":
                assert campo in campos_do_mixin, f"{classe}.{campo}"
            else:
                assert campo not in campos_do_mixin, f"{classe}.{campo}"

    def test_o_detalhe_nao_redeclara_a_lista_do_mixin(self):
        """A porta irmã, medida directamente e não por consequência.

        É a ADR 0035, decisão 6: redeclarar o `CAMPOS_DE_DINHEIRO` numa
        subclasse é como esta casa deixou escapar os euros duas vezes.
        """
        assert (
            "CAMPOS_DE_DINHEIRO"
            not in vars(serializers_das_receitas.ReceitaDetalheOutSerializer)
        )
        assert (
            serializers_das_receitas.ReceitaDetalheOutSerializer.CAMPOS_DE_DINHEIRO
            is serializers_das_receitas.ReceitaResumoOutSerializer.CAMPOS_DE_DINHEIRO
        )


# ---------------------------------------------------------------------------
# 11. A escada corre em lote (decisão 10) — e a 3 matou um N+1
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestOLoteNaoVoltaASerNMaisUm:
    """Uma leitura por página, não um degrau por ingrediente."""

    def test_a_lista_de_dez_receitas_nao_custa_mais_queries_do_que_a_de_uma(self):
        """A **diferença** entre uma página de 1 e uma de 10 é zero queries.

        Medido por diferença e não por um tecto absoluto de propósito: o custo
        fixo de um pedido autenticado (sessão, pertença, contagem da página)
        muda quando o `accounts` muda, e um número redondo neste teste
        transformava isso numa falha que não é sobre receitas. O que a decisão
        10 promete é que a escada corre **em lote**, e isso é exactamente uma
        diferença de zero.
        """
        casa = _casa()
        farinha = _artigo(casa, nome="Farinha")
        acucar = _artigo(casa, nome="Acucar")
        _receber(casa, farinha, quantidade="100000", custo="0.002")
        _receber(casa, acucar, quantidade="100000", custo="0.003")
        for numero in range(10):
            _ficha(
                casa,
                acabado=_artigo(casa, nome=f"Bolo {numero:02d}"),
                fornada="1000",
                linhas=((farinha, "500"), (acucar, "200")),
            )
        dono = _sessao(casa.dono.email)
        dono.get(URL)  # aquece o que houver a aquecer no pedido autenticado

        with CaptureQueriesContext(connection) as de_uma:
            uma = dono.get(f"{URL}?q=Bolo 00")
        with CaptureQueriesContext(connection) as de_dez:
            dez = dono.get(URL)

        assert uma.json()["count"] == 1
        assert dez.json()["count"] == 10
        assert len(de_dez.captured_queries) == len(de_uma.captured_queries), (
            "dez receitas custam as mesmas queries que uma: a escada do custo "
            "corre sobre o conjunto todo dos ingredientes da página, e não um "
            "degrau por ingrediente"
        )
        assert all(linha["batch_cost"] == "1.60" for linha in dez.json()["results"])

    def test_com_a_cascata_a_diferenca_tambem_e_zero(self):
        """O mesmo, mas com o custo a vir do **degrau 4** — onde mora a correcção.

        A avaliação da escada passou a ser por artigo, sobre um grafo já em
        memória; a **leitura** continua a ser por níveis e em lote. Avaliar por
        artigo não pode ter voltado a ler por artigo, e é isso que esta
        diferença mede.

        As duas páginas têm o mesmo filtro (`Bolo`) de propósito: assim as duas
        partem exactamente do mesmo conjunto de ingredientes de raiz — Massa e
        Creme — e o que sobra entre elas é só o número de fichas.
        """
        casa = _casa()
        acucar = _artigo(casa, nome="Acucar")
        _receber(casa, acucar, quantidade="1000000", custo="0.002")
        creme = _artigo(casa, nome="Creme")
        _ficha(casa, acabado=creme, fornada="1000", linhas=((acucar, "500"),))
        massa = _artigo(casa, nome="Massa")
        _ficha(casa, acabado=massa, fornada="1000", linhas=((creme, "500"),))
        for numero in range(10):
            _ficha(
                casa,
                acabado=_artigo(casa, nome=f"Bolo {numero:02d}"),
                fornada="1000",
                linhas=((massa, "200"), (creme, "100")),
            )
        dono = _sessao(casa.dono.email)
        dono.get(URL)  # aquece o que houver a aquecer no pedido autenticado

        with CaptureQueriesContext(connection) as de_uma:
            uma = dono.get(f"{URL}?q=Bolo 00")
        with CaptureQueriesContext(connection) as de_dez:
            dez = dono.get(f"{URL}?q=Bolo")

        assert uma.json()["count"] == 1
        assert dez.json()["count"] == 10
        assert len(de_dez.captured_queries) == len(de_uma.captured_queries), (
            "dez fichas que cascateiam custam as mesmas queries que uma: a "
            "leitura do grafo é por níveis e em lote, e a avaliação não lê nada"
        )
        assert all(linha["batch_cost"] == "0.20" for linha in dez.json()["results"]), (
            "200 g de Massa a 0,0005 €/g mais 100 g de Creme a 0,001 €/g"
        )
