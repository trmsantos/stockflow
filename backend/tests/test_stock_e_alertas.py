"""Os sete recursos de `/stock` (ADR 0034), e as armadilhas que a ADR nomeou.

Substitui o `test_stock_panel.py`, que media as duas rotas que morreram
(`by-location`, `by-product`) e o envelope `{items, total, page, page_size}`
que mentia sobre paginar. O que aqui está é o que a ADR 0034 mandou provar:

1. **A invariante dos contadores** (`TestCadaContadorEIgualASuaLista`): cada
   número do topo é o `count` da lista que ele filtra, no mesmo âmbito. É ela
   que impede a divergência entre os dois ecrãs de voltar, e por isso é o
   primeiro teste do ficheiro.
2. **A tabela da gravidade, célula a célula** (`TestATabelaDaGravidade`):
   `use_by`/`best_before`/vazio × vencido/hoje/1–3/4–7, mais a prova de que as
   **duas** portas do servidor a lêem da mesma função.
3. **O FEFO reparado** (`TestOFefoDaQuebra`): sem lote no corpo, na
   localização pedida, repartido por vários lotes com `reference` comum, e com
   400 — nunca uma escrita parcial — quando o saldo não chega.
4. **O zero que deixou de mentir** (`TestOCustoDesconhecidoNaoSeDisfarcaDeZero`).
5. **A unidade no corpo** (`TestAUnidadeDaQuebra`): decisão 11.
6. **A fuga por aritmética** (`TestOContadorNaoReconstroiOCusto`): um teste que
   lê o **SQL** e não só o JSON, porque o defeito é um `GROUP BY`.
7. **Os dois relógios** (`TestOsDoisRelogios`): a validade é dia civil, o
   desperdício é dia de negócio, e a semana é aritmética de **calendário** —
   com o teste que corre no domingo da mudança da hora e compara as duas
   implementações (o `inventory` não pode importar o `reporting`, ADR 0029 d6).

As asserções sobre **chaves de dinheiro por papel** vivem no
`test_custos_de_stock.py`, que é o ficheiro dessa política: duplicá-las aqui
era a segunda lista a divergir da primeira.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product, UnidadeBase
from apps.inventory import api as inventory_api
from apps.inventory import selectors
from apps.inventory.models import Location, Lot, StockMovement
from apps.inventory.services import MovementDTO, record_movements
from apps.shared.db import tenant_scope

CREDENCIAL = "stock-e-alertas-teste-123"


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

#: O fuso em que o projecto corre. Fixado nos testes de relógio com
#: `override_settings` porque o Django lê o `backend/.env` da máquina de quem
#: desenvolve: sem isto, "a suite passou" dizia coisas diferentes em máquinas
#: diferentes (CLAUDE.md).
FUSO = "Europe/Lisbon"


# ---------------------------------------------------------------------------
# Andaimes. O stock entra **sempre pelo ledger** — um `StockLevel` escrito à
# mão desaparece no primeiro movimento que lhe toca.
# ---------------------------------------------------------------------------
def _casa(nome: str, *, inicio_do_dia: time | None = None) -> SimpleNamespace:
    """Um estabelecimento com os três papéis e duas localizações."""
    tenant = criar_tenant(name=f"Casa do Stock {nome}")
    with tenant_scope(tenant.id):
        # Dentro do âmbito: o `accounts_tenant` tem política de RLS e o
        # predicado compara a coluna `id` (ADR 0007). Fora dele, o `UPDATE`
        # não encontra a linha e o guarda do `conftest` levanta.
        if inicio_do_dia is not None:
            tenant.business_day_starts_at = inicio_do_dia
            tenant.save(update_fields=["business_day_starts_at"])
        dono = User.objects.create_user(f"dono-{nome}@stock.pt", CREDENCIAL)
        conceder_pertenca(
            user=dono, tenant_id=tenant.id, role=Papel.OWNER, display_name="Ana Dona"
        )
        staff = User.objects.create_user(f"staff-{nome}@stock.pt", CREDENCIAL)
        conceder_pertenca(
            user=staff,
            tenant_id=tenant.id,
            role=Papel.STAFF,
            display_name="João Colaborador",
        )
        loja = Location.objects.create(tenant=tenant, name="Loja", position=0)
        armazem = Location.objects.create(tenant=tenant, name="Armazém", position=1)
    return SimpleNamespace(
        tenant=tenant, dono=dono, staff=staff, loja=loja, armazem=armazem
    )


def _artigo(
    casa: SimpleNamespace,
    *,
    nome: str,
    minimo: Decimal = Decimal("0"),
    track_lots: bool = True,
    expiry_kind: str = "use_by",
    base_unit: str = UnidadeBase.GRAMA,
    display_unit: str = "kg",
    display_factor: Decimal = Decimal("1000"),
) -> Product:
    with tenant_scope(casa.tenant.id):
        return Product.objects.create(
            tenant=casa.tenant,
            short_name=nome,
            sku=nome.replace(" ", "-").lower(),
            base_unit=base_unit,
            display_unit=display_unit,
            display_factor=display_factor,
            min_quantity=minimo,
            track_lots=track_lots,
            expiry_kind=expiry_kind,
        )


def _lote(
    casa: SimpleNamespace,
    produto: Product,
    *,
    codigo: str,
    dias: int | None = 30,
    recebido_ha: int = 0,
) -> Lot:
    agora = timezone.now()
    with tenant_scope(casa.tenant.id):
        return Lot.objects.create(
            tenant=casa.tenant,
            product=produto,
            code=codigo,
            expires_at=None if dias is None else agora + timedelta(days=dias),
            received_at=agora - timedelta(days=recebido_ha),
        )


def _receber(
    casa: SimpleNamespace,
    produto: Product,
    localizacao: Location,
    lote: Lot | None,
    *,
    quantidade: Decimal,
    custo: Decimal = Decimal("1"),
) -> None:
    with tenant_scope(casa.tenant.id):
        record_movements(
            tenant_id=casa.tenant.id,
            movements=[
                MovementDTO(
                    product_id=produto.id,
                    location_id=localizacao.id,
                    lot_id=None if lote is None else lote.id,
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


def _pagina(resposta: Any) -> dict[str, Any]:
    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert set(corpo) == {"count", "next", "previous", "results"}, (
        "o envelope é o do DRF desde a ADR 0034, decisão 3"
    )
    return corpo


def _corpo(resposta: Any) -> dict[str, Any]:
    assert resposta.status_code == 200, resposta.content
    return resposta.json()


# ===========================================================================
# 1. A invariante: cada contador é igual ao `count` da lista que filtra
# ===========================================================================
class TestCadaContadorEIgualASuaLista:
    """*Cada contador é igual ao `count` da lista que filtra, no mesmo âmbito.*

    É a frase da ADR 0034 e é testável: sem ela, o topo do ecrã diz "3 a
    expirar" e a lista mostra duas, e quem o nota é o dono. Está garantida por
    **construção** — o `resumo_de_stock` chama o mesmo `niveis_filtrados` que
    a rota — e este teste é o que impede alguém de a desfazer.
    """

    def _casa_com_as_tres_familias(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        # Dois lotes a vencer do mesmo artigo, em duas prateleiras: dois
        # alertas (lote × localização) mas **um** artigo a expirar.
        farinha = _artigo(casa, nome="Farinha")
        cedo = _lote(casa, farinha, codigo="F-CEDO", dias=2)
        _receber(casa, farinha, casa.loja, cedo, quantidade=Decimal("1000"))
        _receber(casa, farinha, casa.armazem, cedo, quantidade=Decimal("500"))
        # Um artigo abaixo do mínimo, sem validade.
        sal = _artigo(casa, nome="Sal", minimo=Decimal("5000"))
        _receber(
            casa, sal, casa.loja, _lote(casa, sal, codigo="S-1", dias=None),
            quantidade=Decimal("100"),
        )
        # E um artigo tranquilo, para a lista não ser só alarme.
        acucar = _artigo(casa, nome="Açúcar")
        _receber(
            casa, acucar, casa.loja, _lote(casa, acucar, codigo="A-1", dias=90),
            quantidade=Decimal("5000"),
        )
        casa.farinha = farinha
        return casa

    def test_o_resumo_do_stock_bate_certo_com_as_duas_listas(self):
        casa = self._casa_com_as_tres_familias("invariante-stock")
        api = _sessao(casa.dono.email)
        resumo = _corpo(api.get("/api/v1/stock/summary"))

        falta = _pagina(api.get("/api/v1/stock/levels?filtro=falta"))
        validade = _pagina(api.get("/api/v1/stock/levels?filtro=validade"))

        assert resumo["below_min_count"] == falta["count"] == 1
        assert resumo["expiring_count"] == validade["count"] == 1, (
            "o `expiring_count` do Stock conta **artigos**, não lotes"
        )

    def test_a_invariante_vale_tambem_com_loja_posta(self):
        """No mesmo âmbito: o contador e a lista lêem o mesmo `?loja=`."""
        casa = self._casa_com_as_tres_familias("invariante-loja")
        api = _sessao(casa.dono.email)
        for loja in (casa.loja, casa.armazem):
            resumo = _corpo(api.get(f"/api/v1/stock/summary?loja={loja.id}"))
            falta = _pagina(api.get(f"/api/v1/stock/levels?loja={loja.id}&filtro=falta"))
            validade = _pagina(
                api.get(f"/api/v1/stock/levels?loja={loja.id}&filtro=validade")
            )
            assert resumo["below_min_count"] == falta["count"], loja.name
            assert resumo["expiring_count"] == validade["count"], loja.name

    def test_o_resumo_dos_alertas_bate_certo_com_as_duas_listas(self):
        casa = self._casa_com_as_tres_familias("invariante-alertas")
        api = _sessao(casa.dono.email)
        resumo = _corpo(api.get("/api/v1/stock/alerts/summary"))

        expira = _pagina(api.get("/api/v1/stock/alerts?risco=expira"))
        falta = _pagina(api.get("/api/v1/stock/alerts?risco=falta"))

        assert resumo["expiring_count"] == expira["count"] == 2, (
            "o alerta é por lote **× localização**: o mesmo lote em duas "
            "prateleiras são duas linhas accionáveis"
        )
        assert resumo["missing_count"] == falta["count"] == 1

    def test_os_dois_expiring_count_sao_dois_factos_e_nao_um_defeito(self):
        """Um conta artigos, o outro conta linhas da lista de alertas.

        A consulta (c) da ADR 0034 fica respondida aqui: são dois números
        porque contam **duas listas**, cada um igual à sua. O mesmo lote em
        duas prateleiras é um artigo a expirar e dois alertas a tratar.
        """
        casa = self._casa_com_as_tres_familias("dois-contadores")
        api = _sessao(casa.dono.email)
        do_stock = _corpo(api.get("/api/v1/stock/summary"))["expiring_count"]
        dos_alertas = _corpo(api.get("/api/v1/stock/alerts/summary"))["expiring_count"]
        assert (do_stock, dos_alertas) == (1, 2)

    def test_os_contadores_de_desperdicio_batem_certo_com_as_duas_janelas(self):
        casa = _casa("invariante-desperdicio")
        casa.farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, casa.farinha, codigo="F-1")
        _receber(casa, casa.farinha, casa.loja, lote, quantidade=Decimal("10000"))
        api = _sessao(casa.dono.email)
        for _ in range(3):
            assert api.post(
                "/api/v1/stock/movements/waste",
                {
                    "product": str(casa.farinha.id),
                    "location": str(casa.loja.id),
                    "quantity": "0.100",
                    "unit": "kg",
                    "reason": "spoiled",
                },
                format="json",
            ).status_code == 201

        resumo = _corpo(api.get("/api/v1/stock/alerts/summary"))
        hoje = _pagina(api.get("/api/v1/stock/alerts/waste?periodo=hoje"))
        semana = _pagina(api.get("/api/v1/stock/alerts/waste?periodo=semana"))

        assert resumo["wasted_today_count"] == hoje["count"] == 3
        assert resumo["wasted_week_count"] == semana["count"] == 3


# ===========================================================================
# 2. A tabela da gravidade (decisão 9), célula a célula
# ===========================================================================
#: A tabela da ADR 0034, decisão 9, escrita como dados. Cada célula é um teste.
#:
#: | dias | `use_by` | `best_before` | `kind` vazio |
#: |---|---|---|---|
#: | `< 0` | danger | warning | danger |
#: | `0` | danger | info | danger |
#: | `1–3` | warning | info | warning |
#: | `4–limiar(7)` | info | info | info |
CELULAS_DA_GRAVIDADE: tuple[tuple[int, str, str], ...] = (
    (-30, "use_by", "danger"),
    (-1, "use_by", "danger"),
    (0, "use_by", "danger"),
    (1, "use_by", "warning"),
    (3, "use_by", "warning"),
    (4, "use_by", "info"),
    (7, "use_by", "info"),
    (-30, "best_before", "warning"),
    (-1, "best_before", "warning"),
    (0, "best_before", "info"),
    (1, "best_before", "info"),
    (3, "best_before", "info"),
    (4, "best_before", "info"),
    (7, "best_before", "info"),
    (-1, "", "danger"),
    (0, "", "danger"),
    (1, "", "warning"),
    (3, "", "warning"),
    (4, "", "info"),
    (7, "", "info"),
)


class TestATabelaDaGravidade:
    """Uma gravidade, uma função, e um teste por célula.

    Havia **quatro** definições: duas no servidor que discordavam uma da outra
    (`selectors.stock_alerts` dava `critical` a tudo o que tinha vencido; o
    `api._gravidade_da_validade` dava aviso a um `use_by` que vence hoje), a do
    fixture, e a do cliente — a única que o utilizador via.
    """

    @pytest.mark.parametrize(("dias", "kind", "esperada"), CELULAS_DA_GRAVIDADE)
    def test_cada_celula_da_tabela(self, dias: int, kind: str, esperada: str):
        assert selectors.gravidade_da_validade(dias=dias, kind=kind or None) == esperada

    def test_um_best_before_nunca_chega_a_danger(self):
        """O tecto é **legal** e não é uma preferência de paleta.

        `best_before` é DDM (DL 26/2016): passada a data ainda se vende se
        estiver íntegro. Quem lhe mexer está a dizer "deita fora" sobre
        mercadoria vendável — por isso o teste varre um ano inteiro e não três
        casos escolhidos.
        """
        for dias in range(-365, 366):
            gravidade = selectors.gravidade_da_validade(dias=dias, kind="best_before")
            assert gravidade != "danger", dias

    def test_as_duas_portas_do_servidor_leem_a_mesma_funcao(self):
        """A porta do assistente traduz as palavras; não decide a gravidade.

        O `AlertaResumo.gravidade` fala `critico|aviso|info` e o contrato HTTP
        fala `danger|warning|info`: são as mesmas três com dois nomes, e a
        tradução vive numa linha do `api.py`. Se alguém lhe puser uma segunda
        regra, este teste parte.
        """
        hoje = date(2026, 6, 15)
        for dias, kind, esperada in CELULAS_DA_GRAVIDADE:
            do_porto = inventory_api._gravidade_da_validade(
                expires_on=hoje + timedelta(days=dias), expiry_kind=kind, hoje=hoje
            )
            assert do_porto == inventory_api._PALAVRA_DA_GRAVIDADE[esperada], (
                dias,
                kind,
            )

    def test_a_gravidade_viaja_no_alerta_e_no_nivel(self):
        """Sem o campo, o cliente é **obrigado** a recalcular para pintar."""
        casa = _casa("gravidade-no-payload")
        iogurte = _artigo(casa, nome="Iogurte", expiry_kind="best_before")
        vencido = _lote(casa, iogurte, codigo="I-1", dias=-1)
        _receber(casa, iogurte, casa.loja, vencido, quantidade=Decimal("1000"))

        api = _sessao(casa.staff.email)
        nivel = _pagina(api.get("/api/v1/stock/levels"))["results"][0]
        alerta = _pagina(api.get("/api/v1/stock/alerts?risco=expira"))["results"][0]

        assert nivel["nearest_expiry"]["severity"] == "warning"
        assert alerta["severity"] == alerta["lot"]["severity"] == "warning", (
            "num alerta de validade os dois são o mesmo número pela mesma função"
        )

    def test_um_lote_a_cinco_dias_entra_na_lista_a_info(self):
        """Janela ≠ corte: é isto que devolve significado ao âmbar.

        Com o limiar a fazer também de corte de gravidade, **tudo** o que
        entrava na lista era pelo menos âmbar e âmbar deixava de querer dizer
        nada. O limiar decide o que aparece; a tabela decide como aparece.
        """
        casa = _casa("janela-nao-e-corte")
        farinha = _artigo(casa, nome="Farinha")
        _receber(
            casa, farinha, casa.loja, _lote(casa, farinha, codigo="F-5", dias=5),
            quantidade=Decimal("1000"),
        )
        alertas = _pagina(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts?risco=expira")
        )
        assert alertas["count"] == 1
        assert alertas["results"][0]["severity"] == "info"


# ===========================================================================
# 3. O FEFO da quebra (decisão 8)
# ===========================================================================
class TestOFefoDaQuebra:
    """O caminho de escrita que esta fatia liga, e que estava partido.

    Medido antes: `registar_waste` levantava `ValidationError({"lot_id": …})`
    sempre que o artigo tinha `track_lots=True` e o corpo não trazia lote —
    enquanto o docstring prometia FEFO e o `formulario-de-desperdicio.tsx`
    **nunca** envia lote. Era **400 em todos os artigos com lotes**, no ecrã
    mais usado pelo `staff`.
    """

    def _casa_com_dois_lotes(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")
        # O que vence primeiro tem pouco; o segundo tem o resto.
        casa.cedo = _lote(casa, casa.farinha, codigo="CEDO", dias=2)
        casa.tarde = _lote(casa, casa.farinha, codigo="TARDE", dias=40)
        _receber(
            casa, casa.farinha, casa.loja, casa.cedo,
            quantidade=Decimal("400"), custo=Decimal("0.002"),
        )
        _receber(
            casa, casa.farinha, casa.loja, casa.tarde,
            quantidade=Decimal("5000"), custo=Decimal("0.003"),
        )
        return casa

    def _quebrar(self, casa: SimpleNamespace, *, kg: str, **extra: Any) -> Any:
        return _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.loja.id),
                "quantity": kg,
                "unit": "kg",
                "reason": "spoiled",
                **extra,
            },
            format="json",
        )

    def test_sem_lote_no_corpo_o_servidor_escolhe_o_que_expira_primeiro(self):
        casa = self._casa_com_dois_lotes("fefo")
        resposta = self._quebrar(casa, kg="0.300")

        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        assert linha["lot_code"] == "CEDO"
        assert linha["quantity"]["base"] == "-300.000"

    def test_a_resposta_e_sempre_uma_lista_mesmo_com_um_lote_so(self):
        """Objecto no caso normal e lista no caso raro é um cliente que parte.

        É a forma que o 201 da transferência já tem (ADR 0032, decisão 4).
        """
        casa = self._casa_com_dois_lotes("lista-sempre")
        corpo = self._quebrar(casa, kg="0.100").json()
        assert set(corpo) == {"movements"}
        assert isinstance(corpo["movements"], list)
        assert len(corpo["movements"]) == 1

    def test_dois_quilos_com_o_lote_fefo_a_quatrocentos_gramas_repartem_se(self):
        """O caso limite decidido pelo dono: reparte-se, não se recusa.

        Tem precedente escrito na casa — é o que o consumo de receitas faz
        (ADR 0026, FEFO até esgotar).
        """
        casa = self._casa_com_dois_lotes("reparticao")
        resposta = self._quebrar(casa, kg="2.000")

        assert resposta.status_code == 201, resposta.content
        linhas = resposta.json()["movements"]
        assert [linha["lot_code"] for linha in linhas] == ["CEDO", "TARDE"]
        assert [linha["quantity"]["base"] for linha in linhas] == [
            "-400.000",
            "-1600.000",
        ]

    def test_a_reparticao_partilha_uma_reference_e_uma_linha_so_nao_tem(self):
        """A `reference` comum é um `uuid4` do gesto, **só** com N > 1.

        Com uma linha não há nada para agrupar, e o índice parcial
        `inv_stockmv_tenant_ref_idx` existe na maior tabela do sistema: só se
        paga escrita nele quando compra alguma coisa.
        """
        casa = self._casa_com_dois_lotes("reference")
        self._quebrar(casa, kg="2.000")
        with tenant_scope(casa.tenant.id):
            referencias = list(
                StockMovement.objects.filter(
                    tenant_id=casa.tenant.id, movement_type="waste"
                ).values_list("reference", flat=True)
            )
        assert len(referencias) == 2
        assert referencias[0] == referencias[1] != ""

        self._quebrar(casa, kg="0.050")
        with tenant_scope(casa.tenant.id):
            sozinha = (
                StockMovement.objects.filter(
                    tenant_id=casa.tenant.id, movement_type="waste"
                )
                .order_by("-created_at")
                .first()
            )
        assert sozinha.reference == ""

    def test_a_reference_da_reparticao_nao_colide_com_o_lookup_das_contagens(self):
        """Os dois lookups da contagem filtram também `movement_type`.

        `selectors.ajustes_da_contagem` e `valor_dos_ajustes_por_artigo`
        procuram por `reference=<id>` **e** `movement_type="adjustment"`, logo
        uma quebra com `reference` nunca entra na conta de uma contagem.
        """
        casa = self._casa_com_dois_lotes("colisao")
        self._quebrar(casa, kg="2.000")
        with tenant_scope(casa.tenant.id):
            referencia = (
                StockMovement.objects.filter(tenant_id=casa.tenant.id)
                .exclude(reference="")
                .values_list("reference", flat=True)
                .first()
            )
            ajustes = selectors.ajustes_da_contagem(
                tenant_id=casa.tenant.id, stock_count_id=referencia
            )
        assert ajustes["n"] == 0

    def test_saldo_que_nao_chega_e_quatrocentos_e_nunca_uma_escrita_parcial(self):
        """Escrever menos do que foi pedido, em silêncio, é a quebra errada.

        E num ledger append-only não se desfaz. Stock negativo continua a ser
        possível por outras portas (ADR 0012), mas não como efeito secundário
        de uma repartição.
        """
        casa = self._casa_com_dois_lotes("saldo-curto")
        resposta = self._quebrar(casa, kg="99.000")

        assert resposta.status_code == 400, resposta.content
        with tenant_scope(casa.tenant.id):
            assert not StockMovement.objects.filter(
                tenant_id=casa.tenant.id, movement_type="waste"
            ).exists()

    def test_sem_saldo_a_frase_nomeia_a_localizacao_e_nunca_o_lote(self):
        """*"lote obrigatório"* manda a pessoa procurar um campo que não existe.

        E esconde a causa real, que é a prateleira estar vazia.
        """
        casa = self._casa_com_dois_lotes("frase")
        # O armazém está vazio: o artigo existe, o saldo está noutro sítio.
        resposta = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.armazem.id),
                "quantity": "0.100",
                "unit": "kg",
                "reason": "spoiled",
            },
            format="json",
        )
        assert resposta.status_code == 400
        texto = str(resposta.json()).lower()
        # Em pt-PT e em inglês: o que não pode aparecer é a palavra "lote".
        assert "lote" not in texto and "lot " not in texto, (
            "a frase mandava procurar um campo que o ecrã não tem"
        )
        assert "localização" in texto or "location" in texto, (
            "a causa real é a prateleira estar vazia, e a frase tem de a nomear"
        )
        # E o campo que a recusa nomeia é a quantidade, não um lote ausente.
        assert set(resposta.json()) == {"quantity"}

    def test_o_fefo_e_na_localizacao_pedida_e_nao_na_casa_toda(self):
        """O ramo especial do lote sintético tirava stock de onde ele não está.

        Procurava o lote por `code=f"__{product_id}__"` **sem olhar à
        localização**; agora o lote sintético é encontrado pelo mesmo caminho
        que os outros, porque também é um lote com saldo *ali*.
        """
        casa = _casa("fefo-por-local")
        casa.farinha = _artigo(casa, nome="Farinha", track_lots=False)
        sintetico = _lote(
            casa, casa.farinha, codigo=f"__{casa.farinha.id}__", dias=None
        )
        _receber(casa, casa.farinha, casa.armazem, sintetico, quantidade=Decimal("900"))

        # Na loja não há nada: 400, e o armazém fica intacto.
        na_loja = self._quebrar(casa, kg="0.100")
        assert na_loja.status_code == 400, na_loja.content

        # No armazém sai, e o lote sintético não aparece no payload.
        no_armazem = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.armazem.id),
                "quantity": "0.100",
                "unit": "kg",
                "reason": "spoiled",
            },
            format="json",
        )
        assert no_armazem.status_code == 201, no_armazem.content
        assert no_armazem.json()["movements"][0]["lot_code"] is None

    def test_com_lote_no_corpo_sai_desse_lote_e_de_mais_nenhum(self):
        """É o caso do ecrã de Alertas: o alerta **é** sobre um lote."""
        casa = self._casa_com_dois_lotes("lote-escolhido")
        resposta = self._quebrar(casa, kg="0.100", lot=str(casa.tarde.id))

        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        assert linha["lot_code"] == "TARDE"


# ===========================================================================
# 4. O zero mentiroso
# ===========================================================================
class TestOCustoDesconhecidoNaoSeDisfarcaDeZero:
    """`unit_cost = 0` com `cost_is_estimate=False` num ledger append-only.

    Escrevia "esta quebra custou zero euros" sobre mercadoria cujo preço
    ninguém sabe — e sem `UPDATE` nem `DELETE` para o corrigir depois.
    """

    def _casa_sem_preco(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, casa.farinha, codigo="SEM-PRECO")
        _receber(
            casa, casa.farinha, casa.loja, lote,
            quantidade=Decimal("1000"), custo=Decimal("0"),
        )
        return casa

    def _quebrar(self, casa: SimpleNamespace) -> Any:
        return _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.loja.id),
                "quantity": "0.100",
                "unit": "kg",
                "reason": "spoiled",
            },
            format="json",
        )

    def test_a_falta_de_preco_nunca_bloqueia_o_registo(self):
        """Quem está a deitar fora não anda à procura de uma fatura."""
        casa = self._casa_sem_preco("sem-preco-regista")
        assert self._quebrar(casa).status_code == 201

    def test_o_201_diz_desconhecido_e_nao_um_custo_de_zero(self):
        casa = self._casa_sem_preco("sem-preco-palavra")
        [linha] = self._quebrar(casa).json()["movements"]
        assert linha["cost_status"] == "desconhecido"

    def test_o_dono_ve_o_custo_a_null_e_nunca_a_zero(self):
        """`null` é "não se conhece"; `0,000000` seria uma afirmação falsa."""
        casa = self._casa_sem_preco("sem-preco-null")
        self._quebrar(casa)
        linha = _pagina(
            _sessao(casa.dono.email).get(
                f"/api/v1/stock/movements?artigo={casa.farinha.id}"
            )
        )["results"][0]
        assert linha["cost_status"] == "desconhecido"
        assert linha["unit_cost"] is None

    def test_o_ledger_grava_cost_is_estimate(self):
        """A coluna que distingue "estimado" de "confirmado" deixa de mentir."""
        casa = self._casa_sem_preco("sem-preco-coluna")
        self._quebrar(casa)
        with tenant_scope(casa.tenant.id):
            movimento = StockMovement.objects.get(
                tenant_id=casa.tenant.id, movement_type="waste"
            )
        assert movimento.unit_cost == Decimal("0")
        assert movimento.cost_is_estimate is True

    def test_com_preco_conhecido_nada_disto_muda(self):
        casa = _casa("com-preco")
        casa.farinha = _artigo(casa, nome="Farinha")
        _receber(
            casa, casa.farinha, casa.loja,
            _lote(casa, casa.farinha, codigo="COM"),
            quantidade=Decimal("1000"), custo=Decimal("0.004"),
        )
        [linha] = self._quebrar(casa).json()["movements"]
        assert linha["cost_status"] == "conhecido"

    def test_a_cobertura_do_desperdicio_conta_as_linhas_sem_preco(self):
        """"7 quebras hoje" e "7 quebras hoje, 4 sem preço" não são a mesma frase."""
        casa = self._casa_sem_preco("cobertura")
        self._quebrar(casa)
        resumo = _corpo(_sessao(casa.staff.email).get("/api/v1/stock/alerts/summary"))
        assert resumo["wasted_today_count"] == 1
        assert resumo["wasted_today_lines_without_cost"] == 1


# ===========================================================================
# 5. A unidade no corpo (decisão 11)
# ===========================================================================
class TestAUnidadeDaQuebra:
    """Entre `g` e `kg` há um factor de 1000 e o ledger não tem desfazer.

    A versão aprovada da ADR escrevia *"quantity: Decimal>0 (unidade BASE)"*
    contra um formulário que apresenta a unidade **mostrada** ao lado do campo
    e só normaliza a vírgula decimal. Um número sem unidade explícita num corpo
    de escrita é uma convenção, e convenções não sobrevivem a dois ecrãs.
    """

    def _casa(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")  # base g, apresentação kg
        _receber(
            casa, casa.farinha, casa.loja,
            _lote(casa, casa.farinha, codigo="F-1"),
            quantidade=Decimal("5000"), custo=Decimal("0.002"),
        )
        return casa

    def _quebrar(self, casa: SimpleNamespace, *, quantidade: str, unidade: str) -> Any:
        return _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.loja.id),
                "quantity": quantidade,
                "unit": unidade,
                "reason": "spoiled",
            },
            format="json",
        )

    def test_dois_quilos_sao_dois_mil_gramas_no_ledger(self):
        casa = self._casa("kg")
        resposta = self._quebrar(casa, quantidade="2", unidade="kg")
        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        assert linha["quantity"]["base"] == "-2000.000"

    def test_dois_gramas_sao_dois_gramas(self):
        casa = self._casa("g")
        resposta = self._quebrar(casa, quantidade="2", unidade="g")
        assert resposta.status_code == 201, resposta.content
        [linha] = resposta.json()["movements"]
        assert linha["quantity"]["base"] == "-2.000"

    def test_uma_unidade_que_nao_e_do_artigo_e_400(self):
        """Não existe motor genérico de conversão (ADR 0011)."""
        casa = self._casa("unidade-errada")
        resposta = self._quebrar(casa, quantidade="2", unidade="l")
        assert resposta.status_code == 400
        assert "unit" in resposta.json()

    def test_o_201_devolve_a_quantidade_nas_duas_formas(self):
        """Para a frase de confirmação dizer "2 kg" a quem escreveu 2."""
        casa = self._casa("quarteto")
        [linha] = self._quebrar(casa, quantidade="2", unidade="kg").json()["movements"]
        assert linha["quantity"] == {
            "base": "-2000.000",
            "base_unit": "g",
            "display": "-2.000",
            "display_unit": "kg",
        }

    def test_sem_unidade_o_corpo_e_recusado(self):
        """Obrigatório: a omissão não cai em "unidade base" por convenção."""
        casa = self._casa("sem-unidade")
        resposta = _sessao(casa.staff.email).post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(casa.farinha.id),
                "location": str(casa.loja.id),
                "quantity": "2",
                "reason": "spoiled",
            },
            format="json",
        )
        assert resposta.status_code == 400
        assert "unit" in resposta.json()


# ===========================================================================
# 6. A fuga por aritmética: um teste que lê o SQL
# ===========================================================================
class TestOContadorNaoReconstroiOCusto:
    """A decisão 10 só é segura enquanto o `COUNT` ficar fora do `GROUP BY`.

    Um `COUNT(id)` não tem euros em ponta nenhuma — não há numerador nem
    denominador —, logo nenhuma sequência de observações reconstrói o custo
    unitário a partir dele. **Mas** agrupar a contagem por `unit_cost` serve o
    custo unitário na chave do grupo, e a fuga volta pela mesma porta com outro
    nome. É o defeito exacto que a ADR 0032 mediu no `stock_summary`, e por
    isso este teste lê o **SQL** e não o JSON.
    """

    #: O `GROUP BY` de uma query, se o tiver. Grosseiro e suficiente: o que
    #: interessa é se `unit_cost` aparece **depois** do `GROUP BY`.
    _GROUP_BY = re.compile(r"\bGROUP BY\b(.*)", re.IGNORECASE | re.DOTALL)

    def _casa_com_tres_custos(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha")
        api = _sessao(casa.dono.email)
        for indice, custo in enumerate(("0.001", "0.002", "0.003")):
            lote = _lote(casa, casa.farinha, codigo=f"F-{indice}", dias=10 + indice)
            _receber(
                casa, casa.farinha, casa.loja, lote,
                quantidade=Decimal("1000"), custo=Decimal(custo),
            )
            assert api.post(
                "/api/v1/stock/movements/waste",
                {
                    "product": str(casa.farinha.id),
                    "location": str(casa.loja.id),
                    "lot": str(lote.id),
                    "quantity": "0.100",
                    "unit": "kg",
                    "reason": "spoiled",
                },
                format="json",
            ).status_code == 201
        casa.api = api
        return casa

    @pytest.mark.parametrize(
        "caminho",
        [
            "/api/v1/stock/alerts/summary",
            "/api/v1/stock/levels",
            "/api/v1/stock/alerts",
            "/api/v1/stock/summary",
            "/api/v1/stock/alerts/waste",
        ],
    )
    def test_nenhuma_query_destas_rotas_agrupa_por_unit_cost(self, caminho: str):
        """Varre as cinco leituras, e não só a que a adenda nomeia.

        A fuga é a mesma em qualquer uma: basta um `values()` com `unit_cost`
        para a **cardinalidade** passar a contar preços distintos. É o defeito
        que a ADR 0032 mediu no `stock_summary`, e o teste tem de ser sobre o
        SQL porque o JSON não tem ali chave de dinheiro nenhuma.
        """
        casa = self._casa_com_tres_custos("sql-" + caminho.replace("/", "-"))
        with CaptureQueriesContext(connection) as capturadas:
            resposta = casa.api.get(caminho)
        assert resposta.status_code == 200, resposta.content

        for query in capturadas.captured_queries:
            agrupamento = self._GROUP_BY.search(query["sql"])
            if agrupamento is None:
                continue
            assert "unit_cost" not in agrupamento.group(1), (
                "um agregado desta rota voltou para dentro de um "
                "values().annotate() que inclui o custo unitário: o número de "
                "linhas passa a variar com o número de custos distintos e o "
                f"custo reconstrói-se.\nSQL: {query['sql'][:400]}"
            )

    def test_o_contador_nao_varia_com_o_numero_de_custos_distintos(self):
        """A mesma fuga, medida pelo JSON: três custos, três quebras, não nove."""
        casa = self._casa_com_tres_custos("json-do-resumo")
        resumo = _corpo(casa.api.get("/api/v1/stock/alerts/summary"))
        assert resumo["wasted_today_count"] == 3

    def test_os_quatro_contadores_novos_chegam_aos_tres_papeis(self):
        """A decisão 10: são contagens e não euros, logo não têm papel.

        A razão é de **navegação**: os dois números em euros eram as duas
        únicas portas para a lista de desperdício, e a decisão 4 diz que essa
        lista tem de chegar ao `staff`. Sem contador, a rota existia sem ter
        quem lá entrasse.
        """
        casa = self._casa_com_tres_custos("tres-papeis")
        quatro = (
            "wasted_today_count",
            "wasted_week_count",
            "wasted_today_lines_without_cost",
            "wasted_week_lines_without_cost",
        )
        do_staff = _corpo(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts/summary")
        )
        do_dono = _corpo(casa.api.get("/api/v1/stock/alerts/summary"))
        for chave in quatro:
            assert chave in do_staff, chave
            assert do_staff[chave] == do_dono[chave], chave
        # E os euros continuam a ser só do dono.
        assert "wasted_today_eur" not in do_staff
        assert "wasted_today_eur" in do_dono


# ===========================================================================
# 7. Os dois relógios, e a janela de calendário
# ===========================================================================
class TestOsDoisRelogios:
    """A validade é dia **civil**; o desperdício é dia **de negócio**.

    Os dois no mesmo ecrã e os dois certos: a lei não sabe a que horas a
    pastelaria abre, e o fecho do dia não sabe o que diz a embalagem. Quem os
    unificar parte uma das duas verdades.

    Todos os testes deste bloco fixam o fuso com `override_settings` e nenhum o
    herda do ambiente: o Django lê o `backend/.env` da máquina de quem
    desenvolve, esse ficheiro não está no repositório, e um teste de relógio
    que dependa dele afirma coisas diferentes em máquinas diferentes
    (CLAUDE.md).
    """

    #: O domingo em que o relógio **atrasa** em Portugal (WEST → WET): 25 de
    #: outubro de 2026, às 02:00 locais. É o dia em que
    #: `agora − timedelta(days=7)` e `hoje − timedelta(days=6)` divergem.
    DOMINGO_DA_MUDANCA = date(2026, 10, 25)

    def test_a_semana_e_aritmetica_de_calendario_no_dia_da_mudanca_da_hora(self):
        """Sete voltas ao calendário, não 168 horas.

        `agora − timedelta(days=7)` difere numa hora no domingo da mudança e
        essa hora põe um dia inteiro no balde errado: a janela passaria a
        começar às 03:00 em vez das 04:00, e a quebra das 03:30 de há sete dias
        entrava num período que não é o dela.
        """
        fuso = ZoneInfo(FUSO)
        inicio_do_dia = time(4, 0)
        agora = datetime(2026, 10, 25, 20, 0, tzinfo=fuso)

        with override_settings(TIME_ZONE=FUSO, USE_TZ=True):
            desde, ate = selectors.janela_de_desperdicio(
                periodo="semana", inicio_do_dia=inicio_do_dia, agora=agora
            )
            assert ate == agora
            # Sete dias de negócio **incluindo hoje**: 19 de outubro às 04:00.
            assert timezone.localtime(desde).date() == date(2026, 10, 19)
            assert timezone.localtime(desde).time() == inicio_do_dia

            # E a hora é mesmo a do estabelecimento, não a de há 168 horas.
            ingenua = agora - timedelta(days=7)
            assert timezone.localtime(ingenua).time() != inicio_do_dia

    def test_a_janela_bate_certo_com_a_do_reporting_no_dia_da_mudanca(self):
        """O `inventory` não pode importar o `reporting` (ADR 0029, d6).

        Duplicam-se três linhas e paga-se a duplicação com este teste: a janela
        de "esta semana" tem de ser **a mesma** que o `7d` do painel, incluindo
        no dia em que o relógio muda. O teste importa os dois lados; o código
        de produção não o pode fazer, e é essa a fronteira.
        """
        from apps.reporting import periodos

        fuso = ZoneInfo(FUSO)
        inicio_do_dia = time(4, 0)
        with override_settings(TIME_ZONE=FUSO, USE_TZ=True):
            for hora in (0, 1, 2, 3, 4, 5, 12, 23):
                agora = datetime(2026, 10, 25, hora, 30, tzinfo=fuso)
                desde, ate = selectors.janela_de_desperdicio(
                    periodo="semana", inicio_do_dia=inicio_do_dia, agora=agora
                )
                do_reporting = periodos.janela_do_periodo(
                    key="7d", inicio_do_dia=inicio_do_dia, agora=agora
                )
                assert desde == do_reporting.desde, hora
                assert ate == do_reporting.ate, hora

    def test_o_dia_de_hoje_tambem_bate_certo_com_o_do_reporting(self):
        """E no outro domingo, o que adianta: 29 de março de 2026."""
        from apps.reporting import periodos

        fuso = ZoneInfo(FUSO)
        inicio_do_dia = time(4, 0)
        with override_settings(TIME_ZONE=FUSO, USE_TZ=True):
            for hora in (2, 3, 4, 5, 20):
                agora = datetime(2026, 3, 29, hora, 15, tzinfo=fuso)
                desde, _ate = selectors.janela_de_desperdicio(
                    periodo="hoje", inicio_do_dia=inicio_do_dia, agora=agora
                )
                assert desde == periodos.janela_do_periodo(
                    key="today", inicio_do_dia=inicio_do_dia, agora=agora
                ).desde, hora

    def test_as_duas_da_manha_sao_ontem_para_a_quebra_e_hoje_para_a_validade(self):
        """A frase da ADR, medida: às 02:00 as duas respostas estão certas.

        O "hoje" do desperdício ainda é ontem — a quebra das 02:00 pertence ao
        dia de negócio que começou às 04:00 de ontem — e o "expira hoje" já é o
        dia civil novo.
        """
        fuso = ZoneInfo(FUSO)
        inicio_do_dia = time(4, 0)
        duas_da_manha = datetime(2026, 6, 15, 2, 0, tzinfo=fuso)

        with override_settings(TIME_ZONE=FUSO, USE_TZ=True):
            desde, _ate = selectors.janela_de_desperdicio(
                periodo="hoje", inicio_do_dia=inicio_do_dia, agora=duas_da_manha
            )
            assert timezone.localtime(desde).date() == date(2026, 6, 14), (
                "o dia de negócio às 02:00 ainda é o de ontem"
            )
            # A validade não se desloca: o dia civil já virou.
            assert timezone.localdate(duas_da_manha) == date(2026, 6, 15)

    def test_a_hora_do_estabelecimento_viaja_no_resumo(self):
        """O rótulo lê "Deitado fora — hoje (desde as 04:00)" com dado do servidor.

        E é **por estabelecimento**: na pastelaria o dia começa no início da
        produção e não no fim do serviço de um restaurante.
        """
        with override_settings(TIME_ZONE=FUSO, USE_TZ=True):
            casa = _casa("hora-do-negocio", inicio_do_dia=time(6, 0))
            resumo = _corpo(
                _sessao(casa.staff.email).get("/api/v1/stock/alerts/summary")
            )
            assert resumo["business_day_starts_at"] == "06:00"
            assert resumo["wasted_since"][11:16] == "06:00"


# ===========================================================================
# 8. As formas do contrato que rebentavam o cliente em silêncio
# ===========================================================================
class TestAsFormasQueRebentavamOCliente:
    """Os `.optional()`/`.nullable()` que a adenda da ADR 0034 nomeou.

    Nenhum gate atravessa esta fronteira — um `pnpm typecheck` verde com um
    campo em falta no Zod é o ecrã a rebentar em runtime —, e por isso o que se
    prende aqui é o **lado do servidor**: a chave existe e tem a forma que o
    cliente vai declarar.
    """

    def test_a_validade_sai_como_data_e_nunca_como_instante(self):
        """Defeito (a): um instante tem fuso; a data da embalagem não muda."""
        casa = _casa("data-de-validade")
        farinha = _artigo(casa, nome="Farinha")
        _receber(
            casa, farinha, casa.loja, _lote(casa, farinha, codigo="F-1", dias=3),
            quantidade=Decimal("1000"),
        )
        nivel = _pagina(_sessao(casa.staff.email).get("/api/v1/stock/levels"))[
            "results"
        ][0]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", nivel["nearest_expiry"]["expires_at"])

    def test_um_artigo_sem_rotulo_de_validade_tem_kind_a_null(self):
        """O `expiry_kind` é `""` por omissão e o `tipoValidadeSchema` recusa `""`."""
        casa = _casa("sem-rotulo")
        farinha = _artigo(casa, nome="Farinha", expiry_kind="")
        _receber(
            casa, farinha, casa.loja, _lote(casa, farinha, codigo="F-1", dias=1),
            quantidade=Decimal("1000"),
        )
        nivel = _pagina(_sessao(casa.staff.email).get("/api/v1/stock/levels"))[
            "results"
        ][0]
        assert nivel["nearest_expiry"]["kind"] is None
        # E lê-se pela coluna estrita: sub-avisar é o erro caro.
        assert nivel["nearest_expiry"]["severity"] == "warning"

    def test_um_lote_sintetico_sai_com_lot_code_a_null_nos_quatro_sitios(self):
        """Sem isto, a primeira produção de receita rebentava a página."""
        casa = _casa("lote-sintetico")
        farinha = _artigo(casa, nome="Farinha", track_lots=False)
        sintetico = _lote(
            casa, farinha, codigo=f"__{farinha.id}__", dias=2
        )
        _receber(casa, farinha, casa.loja, sintetico, quantidade=Decimal("1000"))
        api = _sessao(casa.dono.email)
        assert api.post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(farinha.id),
                "location": str(casa.loja.id),
                "quantity": "0.100",
                "unit": "kg",
                "reason": "spoiled",
            },
            format="json",
        ).status_code == 201

        nivel = _pagina(api.get("/api/v1/stock/levels"))["results"][0]
        alerta = _pagina(api.get("/api/v1/stock/alerts?risco=expira"))["results"][0]
        movimento = _pagina(api.get(f"/api/v1/stock/movements?artigo={farinha.id}"))[
            "results"
        ][0]
        desperdicio = _pagina(api.get("/api/v1/stock/alerts/waste"))["results"][0]

        assert nivel["nearest_expiry"]["lot_code"] is None
        assert alerta["lot"]["lot_code"] is None
        assert movimento["lot_code"] is None
        assert desperdicio["lot_code"] is None

    def test_o_id_do_alerta_distingue_duas_prateleiras_do_mesmo_lote(self):
        """`expiry:<lot_id>` produzia **dois ids iguais** e o painel expandia a errada."""
        casa = _casa("id-do-alerta")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="F-1", dias=2)
        _receber(casa, farinha, casa.loja, lote, quantidade=Decimal("1000"))
        _receber(casa, farinha, casa.armazem, lote, quantidade=Decimal("500"))

        alertas = _pagina(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts?risco=expira")
        )["results"]
        assert len(alertas) == 2
        assert len({a["id"] for a in alertas}) == 2
        for alerta in alertas:
            assert alerta["id"] == f"expiry:{lote.id}:{alerta['location']['id']}"
            assert alerta["location"] is not None, (
                "agregar por lote punha o `location` a null e o POST da linha "
                "levaria \"\", que é 400"
            )

    def test_um_alerta_de_falta_nao_tem_localizacao_nem_lote(self):
        casa = _casa("falta-sem-local")
        sal = _artigo(casa, nome="Sal", minimo=Decimal("1000"))
        _receber(
            casa, sal, casa.loja, _lote(casa, sal, codigo="S-1", dias=None),
            quantidade=Decimal("100"),
        )
        alerta = _pagina(
            _sessao(casa.staff.email).get("/api/v1/stock/alerts?risco=falta")
        )["results"][0]
        assert alerta["id"] == f"missing:{sal.id}"
        assert alerta["location"] is None
        assert alerta["lot"] is None
        assert alerta["threshold_days"] is None
        assert alerta["min_quantity"]["base"] == "1000.000"

    def test_o_autor_e_o_nome_da_pertenca_e_nunca_o_email(self):
        casa = _casa("autor")
        farinha = _artigo(casa, nome="Farinha")
        _receber(
            casa, farinha, casa.loja, _lote(casa, farinha, codigo="F-1"),
            quantidade=Decimal("1000"),
        )
        api = _sessao(casa.staff.email)
        api.post(
            "/api/v1/stock/movements/waste",
            {
                "product": str(farinha.id),
                "location": str(casa.loja.id),
                "quantity": "0.100",
                "unit": "kg",
                "reason": "spoiled",
            },
            format="json",
        )
        linha = _pagina(api.get("/api/v1/stock/alerts/waste"))["results"][0]
        assert linha["created_by"] == "João Colaborador"
        assert "@" not in linha["created_by"]

    def test_o_rotulo_da_referencia_substitui_o_uuid_cru(self):
        """Defeito (b), resolvido **sem mudar o que se grava**.

        O `reference` continua a ser o id da contagem — há um índice parcial e
        dois lookups por essa string —, e o que o ecrã imprime é o rótulo.
        """
        casa = _casa("referencia")
        farinha = _artigo(casa, nome="Farinha")
        _receber(
            casa, farinha, casa.loja, _lote(casa, farinha, codigo="F-1"),
            quantidade=Decimal("1000"),
        )
        api = _sessao(casa.dono.email)
        contagem = api.post(
            "/api/v1/stock/counts", {"location": str(casa.loja.id)}, format="json"
        )
        assert contagem.status_code == 201, contagem.content
        contagem_id = contagem.json()["id"]
        assert api.post(
            f"/api/v1/stock/counts/{contagem_id}/lines",
            {"product": str(farinha.id), "quantity": "0.900"},
            format="json",
        ).status_code == 200
        assert api.post(
            f"/api/v1/stock/counts/{contagem_id}/closing",
            {"reason": "contagem de rotina"},
            format="json",
        ).status_code in (200, 201)

        linhas = _pagina(api.get(f"/api/v1/stock/movements?artigo={farinha.id}"))[
            "results"
        ]
        ajuste = next(linha for linha in linhas if linha["movement_type"] == "adjustment")
        assert ajuste["reference"] == contagem_id
        assert ajuste["reference_kind"] == "contagem"
        assert ajuste["reference_label"].startswith("Contagem de ")
        assert "Loja" in ajuste["reference_label"]
        # E o que vem de fora do módulo fica sem rótulo.
        recepcao = next(linha for linha in linhas if linha["movement_type"] == "receipt")
        assert recepcao["reference_kind"] is None
        assert recepcao["reference_label"] is None


# ===========================================================================
# 9. O âmbito do `?loja=`, e o mínimo que é do estabelecimento
# ===========================================================================
class TestOAmbitoDaLoja:
    """Defeito (c) a passar de aviso a regra escrita.

    O `?loja=` escopa **só** a quantidade, a repartição, a validade e o valor.
    O `status`, o `min_quantity` e o `filtro=falta` são sempre do
    estabelecimento: o mínimo é por artigo (ADR 0024) e compará-lo contra o
    saldo de uma loja inventava faltas.
    """

    def _casa(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        casa.farinha = _artigo(casa, nome="Farinha", minimo=Decimal("1000"))
        casa.lote = _lote(casa, casa.farinha, codigo="F-1", dias=20)
        # 400 g na loja e 800 g no armazém: 1200 g no total, acima do mínimo.
        _receber(casa, casa.farinha, casa.loja, casa.lote, quantidade=Decimal("400"))
        _receber(casa, casa.farinha, casa.armazem, casa.lote, quantidade=Decimal("800"))
        return casa

    def test_o_estado_e_o_minimo_nao_mudam_com_a_loja(self):
        casa = self._casa("minimo-do-estabelecimento")
        api = _sessao(casa.staff.email)
        so_na_loja = _pagina(api.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))[
            "results"
        ][0]

        assert so_na_loja["quantity"]["base"] == "400.000", "a quantidade é da loja"
        assert so_na_loja["min_quantity"]["base"] == "1000.000"
        assert so_na_loja["status"] == "ok", (
            "0,4 kg contra um mínimo de 1 kg lê-se como falta — e não é: o "
            "mínimo é do estabelecimento, que tem 1,2 kg"
        )

    def test_a_reparticao_so_traz_a_loja_pedida(self):
        casa = self._casa("reparticao-escopada")
        api = _sessao(casa.staff.email)
        so_na_loja = _pagina(api.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))[
            "results"
        ][0]
        assert [p["location"]["name"] for p in so_na_loja["by_location"]] == ["Loja"]

    def test_um_artigo_que_nao_esta_naquela_loja_nao_entra_na_lista(self):
        """`?loja=` é "o que está aqui", e não o catálogo com zeros ao lado.

        Um artigo que nunca passou por aquela prateleira não tem linha nenhuma
        a dizê-lo: o `status` vem do estabelecimento, logo apareceria como
        "ok" com quantidade zero — a frase mais confusa possível ao lado de um
        filtro de loja.
        """
        casa = _casa("artigo-noutra-loja")
        so_na_loja = _artigo(casa, nome="Só na loja")
        so_no_armazem = _artigo(casa, nome="Só no armazém")
        _receber(
            casa, so_na_loja, casa.loja,
            _lote(casa, so_na_loja, codigo="L-1", dias=None),
            quantidade=Decimal("1000"),
        )
        _receber(
            casa, so_no_armazem, casa.armazem,
            _lote(casa, so_no_armazem, codigo="A-1", dias=None),
            quantidade=Decimal("1000"),
        )

        api = _sessao(casa.staff.email)
        consolidado = _pagina(api.get("/api/v1/stock/levels"))
        na_loja = _pagina(api.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))

        assert consolidado["count"] == 2
        assert na_loja["count"] == 1
        assert na_loja["results"][0]["short_name"] == "Só na loja"

    def test_um_artigo_que_entrou_e_acabou_continua_a_aparecer(self):
        """`esgotado` é um estado do contrato e é o segundo pior da ordem.

        O que o tira da lista é nunca ter entrado, não ter chegado a zero —
        "não se avisa de falta do que nunca houve", mas avisa-se do que
        acabou.
        """
        casa = _casa("entrou-e-acabou")
        farinha = _artigo(casa, nome="Farinha")
        lote = _lote(casa, farinha, codigo="F-1", dias=None)
        _receber(casa, farinha, casa.loja, lote, quantidade=Decimal("1000"))
        _receber(casa, farinha, casa.loja, lote, quantidade=Decimal("-1000"))

        linha = _pagina(
            _sessao(casa.staff.email).get(f"/api/v1/stock/levels?loja={casa.loja.id}")
        )["results"][0]
        assert linha["status"] == "esgotado"
        assert linha["quantity"]["base"] == "0.000"
        assert linha["by_location"] == []

    def test_a_validade_mais_proxima_e_a_do_ambito_pedido(self):
        """Consulta (b): mostrar a validade de outra loja é uma frase falsa."""
        casa = _casa("validade-do-ambito")
        farinha = _artigo(casa, nome="Farinha")
        cedo = _lote(casa, farinha, codigo="CEDO", dias=2)
        tarde = _lote(casa, farinha, codigo="TARDE", dias=40)
        _receber(casa, farinha, casa.loja, tarde, quantidade=Decimal("1000"))
        _receber(casa, farinha, casa.armazem, cedo, quantidade=Decimal("1000"))

        api = _sessao(casa.staff.email)
        consolidado = _pagina(api.get("/api/v1/stock/levels"))["results"][0]
        na_loja = _pagina(api.get(f"/api/v1/stock/levels?loja={casa.loja.id}"))[
            "results"
        ][0]

        assert consolidado["nearest_expiry"]["lot_code"] == "CEDO"
        assert na_loja["nearest_expiry"]["lot_code"] == "TARDE"


# ===========================================================================
# 10. O que as rotas recusam, e o que elas valem
# ===========================================================================
class TestOQueAsRotasRecusam:
    """Uniões fechadas são 400, e não uma lista a fingir que filtrou."""

    def test_um_filtro_fora_da_uniao_e_400(self):
        casa = _casa("filtro-invalido")
        api = _sessao(casa.staff.email)
        assert api.get("/api/v1/stock/levels?filtro=caro").status_code == 400
        assert api.get("/api/v1/stock/alerts?risco=tudo").status_code == 400
        assert api.get("/api/v1/stock/alerts/waste?periodo=mes").status_code == 400

    def test_o_ledger_sem_artigo_e_400(self):
        """A pergunta é sempre "o que aconteceu a este artigo"."""
        casa = _casa("artigo-obrigatorio")
        api = _sessao(casa.staff.email)
        assert api.get("/api/v1/stock/movements").status_code == 400
        assert api.get("/api/v1/stock/movements?artigo=nao-e-uuid").status_code == 400

    def test_uma_loja_que_nao_e_uuid_e_400(self):
        casa = _casa("loja-invalida")
        assert (
            _sessao(casa.staff.email).get("/api/v1/stock/levels?loja=x").status_code
            == 400
        )

    def test_o_artigo_de_outro_estabelecimento_devolve_lista_vazia(self):
        """A RLS é a primeira rede e o filtro por tenant é a segunda."""
        casa = _casa("tenant-a")
        outra = _casa("tenant-b")
        farinha = _artigo(outra, nome="Farinha da outra casa")
        _receber(
            outra, farinha, outra.loja, _lote(outra, farinha, codigo="X-1"),
            quantidade=Decimal("1000"),
        )
        api = _sessao(casa.staff.email)
        assert _pagina(api.get("/api/v1/stock/levels"))["count"] == 0
        assert (
            _pagina(api.get(f"/api/v1/stock/movements?artigo={farinha.id}"))["count"]
            == 0
        )

    def test_as_quatro_listas_vem_no_envelope_do_drf(self):
        """`{count, next, previous, results}` e nunca `{items, total, page}`."""
        casa = _casa("envelope")
        api = _sessao(casa.staff.email)
        for caminho in (
            "/api/v1/stock/levels",
            "/api/v1/stock/alerts",
            "/api/v1/stock/alerts/waste",
        ):
            _pagina(api.get(caminho))

    def test_as_cinco_leituras_chegam_ao_colaborador(self):
        """Nenhuma rota de stock ganhou papel: o que muda é o payload."""
        casa = _casa("sem-papel")
        api = _sessao(casa.staff.email)
        farinha = _artigo(casa, nome="Farinha")
        for caminho in (
            "/api/v1/stock/levels",
            "/api/v1/stock/summary",
            "/api/v1/stock/alerts",
            "/api/v1/stock/alerts/summary",
            "/api/v1/stock/alerts/waste",
            f"/api/v1/stock/movements?artigo={farinha.id}",
        ):
            assert api.get(caminho).status_code == 200, caminho


# ===========================================================================
# 11. O valor do stock, e os saldos negativos
# ===========================================================================
class TestOValorDoStock:
    """Um `Sum` ingénuo soma os negativos e o stock vale menos por causa deles."""

    def test_um_saldo_negativo_nao_baixa_o_valor_do_stock(self):
        casa = _casa("valor-com-negativo")
        boa = _artigo(casa, nome="Farinha")
        ma = _artigo(casa, nome="Nata")
        _receber(
            casa, boa, casa.loja, _lote(casa, boa, codigo="B-1"),
            quantidade=Decimal("1000"), custo=Decimal("0.002"),
        )
        lote_mau = _lote(casa, ma, codigo="M-1")
        _receber(
            casa, ma, casa.loja, lote_mau,
            quantidade=Decimal("-500"), custo=Decimal("0.004"),
        )

        resumo = _corpo(_sessao(casa.dono.email).get("/api/v1/stock/summary"))
        assert resumo["stock_value_eur"] == "2.00", (
            "o saldo negativo da nata entrou no valor do stock"
        )

    def test_o_saldo_negativo_continua_visivel_na_lista(self):
        """É onde ele significa alguma coisa, e é o pior estado da ordem."""
        casa = _casa("negativo-visivel")
        boa = _artigo(casa, nome="Farinha")
        ma = _artigo(casa, nome="Nata")
        _receber(
            casa, boa, casa.loja, _lote(casa, boa, codigo="B-1", dias=None),
            quantidade=Decimal("1000"),
        )
        _receber(
            casa, ma, casa.loja, _lote(casa, ma, codigo="M-1", dias=None),
            quantidade=Decimal("-500"),
        )

        linhas = _pagina(_sessao(casa.staff.email).get("/api/v1/stock/levels"))[
            "results"
        ]
        assert [linha["status"] for linha in linhas] == ["negativo", "ok"]
        assert linhas[0]["short_name"] == "Nata"


# ===========================================================================
# 12. A procura e os filtros, no servidor
# ===========================================================================
class TestAProcuraEOsFiltrosSaoDoServidor:
    """O `filtrar()` do ecrã procurava **só nas 50 piores linhas**.

    Com paginação a sério isso cala as outras em silêncio — e porque a ordem é
    "o pior primeiro", cala-as exactamente onde ninguém nota (ADR 0034, d2).
    """

    def _casa(self, nome: str) -> SimpleNamespace:
        casa = _casa(nome)
        for indice in range(60):
            artigo = _artigo(casa, nome=f"Artigo {indice:02d}")
            _receber(
                casa, artigo, casa.loja,
                _lote(casa, artigo, codigo=f"L-{indice}", dias=None),
                quantidade=Decimal("1000"),
            )
        # O que se procura fica no fim da ordem alfabética, logo fora da
        # primeira página: é exactamente o caso que o filtro em JavaScript
        # perdia.
        raro = _artigo(casa, nome="Zimbro")
        _receber(
            casa, raro, casa.loja, _lote(casa, raro, codigo="Z-1", dias=None),
            quantidade=Decimal("1000"),
        )
        return casa

    def test_a_procura_atravessa_a_paginacao(self):
        casa = self._casa("procura")
        api = _sessao(casa.staff.email)
        primeira = _pagina(api.get("/api/v1/stock/levels"))
        assert primeira["count"] == 61
        assert len(primeira["results"]) == 50
        assert "Zimbro" not in [linha["short_name"] for linha in primeira["results"]]

        procurado = _pagina(api.get("/api/v1/stock/levels?q=zimbro"))
        assert procurado["count"] == 1
        assert procurado["results"][0]["short_name"] == "Zimbro"

    def test_o_filtro_de_falta_atravessa_a_paginacao(self):
        casa = self._casa("filtro-falta")
        # Um artigo em falta, alfabeticamente no fim.
        vazio = _artigo(casa, nome="Zz Vazio", minimo=Decimal("1000"))
        _receber(
            casa, vazio, casa.loja, _lote(casa, vazio, codigo="V-1", dias=None),
            quantidade=Decimal("10"),
        )
        api = _sessao(casa.staff.email)
        em_falta = _pagina(api.get("/api/v1/stock/levels?filtro=falta"))
        assert em_falta["count"] == 1
        assert em_falta["results"][0]["short_name"] == "Zz Vazio"
