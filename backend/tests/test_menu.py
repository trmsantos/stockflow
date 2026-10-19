"""O menu por tenant, ponta a ponta (ADR 0009 e ADR 0011).

Este ficheiro existe para medir quatro coisas que não se vêem por revisão. As
outras asserções são acessórias a elas.

**1. A linha nasce na primeira escrita, e os defaults vivem em código.** Um
estabelecimento que nunca abriu o painel tem o menu completo **com zero linhas
na tabela** (`test_sem_linhas_o_menu_e_o_dos_defaults`). É a decisão da ADR 0011
e a razão de o `accounts.criar_tenant` não semear nada.

**2. A política de RLS isola a configuração de um cliente da de outro.** Esconder
um item é apresentação, mas a linha que o diz é configuração de um tenant, e
configuração de um tenant não é legível por outro. A prova é tripla: uma queryset
**sem filtro** dentro do âmbito de Alfa não vê as linhas de Beta
(`test_a_queryset_sem_filtro_dentro_do_ambito_de_alfa_nao_ve_beta`), fora de
âmbito não vê nenhuma (`test_fora_de_ambito_nao_se_ve_item_de_menu_nenhum`), e
uma escrita para outro tenant de dentro do âmbito é recusada pela própria
política (`test_a_politica_recusa_escrever_o_menu_de_outro_tenant`).

**3. O filtro por papel é autorização e não preferência** (ADR 0011). Medido com
as duas restrições reais que existem — os `convites` são do `owner` porque a ADR
0010 o decidiu e porque é o que o `ConviteViewSet` impõe, e o `painel` é do
`owner` porque a ADR 0013 o decidiu e porque é o que as permissões do
`reporting` impõem —, em
`test_as_rotas_do_owner_desaparecem_do_menu_de_quem_nao_e_owner`. As outras cinco
não são restritas, e o `apps/accounts/menu.py` diz porquê: inventar restrições
era responder à Q7 sem ninguém ter perguntado. Que sejam exactamente estas duas
está fechado nos dois sentidos em
`test_as_rotas_restritas_sao_duas_e_as_duas_sao_do_owner`.

**4. O `PUT` é uma substituição total.** O que não vem no corpo volta ao default,
e a resposta é a configuração **inteira e sem filtro de papel** — o contrário
seria um caminho para perder configuração a cada leitura-escrita
(`test_a_resposta_do_put_nao_e_filtrada_pelo_papel`).

## Porque é que todos levam `transactional_db`

O mesmo motivo do `tests/test_rls_isolation.py` e do `test_convites.py`: com a
transação do pytest-django por fora, o `set_config('app.tenant_id', ..., true)`
que o `tenant_scope` corre só reverte no fim **dela** e não no fim do bloco
`with`. As asserções sobre o que se vê fora de âmbito passariam a medir um
âmbito ainda aberto.

## O guarda de âmbito do `conftest.py` está a trabalhar neste ficheiro

Só um teste tem a marca `sem_ambito_de_rls` — o que faz a leitura sem âmbito de
propósito. Em todos os outros o guarda está montado, pelo que **cada**
`GET /auth/sessao` deste ficheiro é também uma afirmação de que o menu é lido
dentro de um âmbito: o endpoint da sessão é dispensado de âmbito (ADR 0010) e o
`_sessao` abre o seu, como faz para confirmar cada candidato. Sem o guarda, uma
leitura sem âmbito devolvia um menu vazio e passava por "este tenant não
configurou nada".
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.utils import ProgrammingError
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.accounts.menu import (
    REGISTO_DE_ROTAS,
    TODOS_OS_PAPEIS,
    RotaDoRegisto,
    rotas_do_registo,
)
from apps.accounts.middleware import CODIGO_SEM_SESSAO, SESSION_TENANT_KEY
from apps.accounts.models import Papel, RotaDeMenu, Tenant, TenantMenuItem, User
from apps.accounts.selectors import projeccao_de_menu
from apps.accounts.serializers import ItemDeMenuOutSerializer, RotaDeMenuOutSerializer
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    conceder_pertenca,
    criar_tenant,
    guardar_menu,
)
from apps.shared.db import TenantScopeConflict, tenant_scope

URL_MENU = "/api/v1/menu"
URL_ROTAS = "/api/v1/menu/rotas"
URL_SESSAO = "/api/v1/auth/sessao"

BACKEND = BACKEND_DE_SESSAO


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos; em Alfa um `owner`, um `manager` e um `staff`."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa: a única conta que configura o menu (ADR 0011).
    ana: User
    #: `manager` em Alfa: o teste do papel no endpoint de escrita.
    bento: User
    #: `staff` em Alfa: o teste do filtro por papel na resposta.
    clara: User
    #: `owner` em Beta: o isolamento entre estabelecimentos.
    dinis: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt")
    bento = User.objects.create_user("bento@alfa.pt")
    clara = User.objects.create_user("clara@alfa.pt")
    dinis = User.objects.create_user("dinis@beta.pt")

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana")
        conceder_pertenca(
            user=bento, tenant_id=alfa.id, role=Papel.MANAGER, display_name="Bento"
        )
        conceder_pertenca(user=clara, tenant_id=alfa.id, role=Papel.STAFF, display_name="Clara")
    with tenant_scope(beta.id):
        conceder_pertenca(user=dinis, tenant_id=beta.id, role=Papel.OWNER, display_name="Dinis")

    return Cenario(alfa=alfa, beta=beta, ana=ana, bento=bento, clara=clara, dinis=dinis)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _cliente(user: User | None = None, tenant_id: UUID | None = None) -> Client:
    cliente = Client()
    if user is not None:
        cliente.force_login(user, backend=BACKEND)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


def _put(cliente: Client, corpo: Any) -> Any:
    return cliente.put(URL_MENU, data=corpo, content_type="application/json")


def _menu_da_sessao(cliente: Client) -> list[dict[str, Any]]:
    resposta = cliente.get(URL_SESSAO)
    assert resposta.status_code == 200, resposta.content
    return resposta.json()["menu"]


def _item(
    route_id: str,
    *,
    grupo: str = "Grupo",
    ordem: int = 10,
    visivel: bool = True,
    rotulo: str | None = None,
) -> dict[str, Any]:
    """Um item do corpo do `PUT`, com os quatro campos configuráveis."""
    return {
        "route_id": route_id,
        "grupo": grupo,
        "ordem": ordem,
        "visivel": visivel,
        "rotulo": rotulo,
    }


def _item_do_menu(menu: list[dict[str, Any]], route_id: str) -> dict[str, Any]:
    """O item de uma rota dentro de uma projecção.

    Por `route_id` e nunca por posição: a projecção traz **sempre** as rotas
    todas (as que não estão configuradas vêm com os defaults), logo o índice 0
    não é o item que o teste acabou de escrever — é o de menor `ordem`.
    """
    encontrados = [item for item in menu if item["route_id"] == route_id]
    assert len(encontrados) == 1, f"{route_id} aparece {len(encontrados)} vezes em {menu}"
    return encontrados[0]


def _linhas_no_ambito(tenant_id: UUID) -> list[TenantMenuItem]:
    """As linhas da tabela, lidas dentro do âmbito — a única forma de as ler."""
    with tenant_scope(tenant_id):
        return list(TenantMenuItem.objects.order_by("route_id"))


# ---------------------------------------------------------------------------
# 1. O registo: a lista fechada, e o que ela promete ao frontend
# ---------------------------------------------------------------------------
def test_o_enum_tem_exatamente_os_ids_do_registo_do_shell() -> None:
    """A lista fechada do backend é a união que o `types.ts` carrega (ADR 0009).

    Os oito valores: os cinco ecrãs que o `frontend/src/shell/registo-de-rotas.ts`
    escreveu primeiro, o `convites`, o `painel` (2026-10-06, quando o painel de
    gestão saiu do Início para rota própria) e o `configuracao` (2026-10-07, ADR
    0017). Um id a mais aqui **faz o `pnpm typecheck` do frontend falhar** até o
    `Record<RotaId, EntradaDoRegisto>` dele o ter: é essa a propriedade que se
    compra, e é por isso que acrescentar um id é uma mudança que atravessa as duas
    pontas e não uma linha num enum.

    Um id a menos é o mesmo problema ao contrário: o `Record` do shell fica com
    uma propriedade em excesso e também não compila.

    **O `configuracao` foi a prova disto a correr, e não uma sonda.** O docstring
    do `registo-de-rotas.ts` usava exactamente este id como exemplo hipotético do
    `TS2741` ("a simular o enum do backend a crescer"); quando ele entrou a
    sério, o erro que apareceu foi aquele, com esta palavra.
    """
    assert list(RotaDeMenu.values) == [
        "inicio",
        "painel",
        "alertas",
        # O assistente (ADR 0027, decisão 10), a 2026-10-15: o sétimo id a
        # atravessar as duas pontas pela ordem da ADR 0009 — primeiro aqui,
        # depois o `gen:api`, e o `Record` do shell não compila até ter a rota.
        "assistente",
        "stock",
        "contar",
        "receber",
    ]


def test_o_registo_cobre_o_enum_nos_dois_sentidos() -> None:
    """Uma rota no enum sem entrada no registo não tem defaults nem papéis.

    E uma entrada no registo com um id que o enum não tem nunca seria aceite pelo
    `ChoiceField` do serializer: ficava no registo a produzir um item de menu que
    nenhum `PUT` consegue configurar.
    """
    assert set(REGISTO_DE_ROTAS) == set(RotaDeMenu.values)
    assert [rota.route_id for rota in rotas_do_registo()] == list(RotaDeMenu.values)


def test_as_rotas_restritas_sao_tres_e_as_tres_sao_do_owner() -> None:
    """Uma lista fechada de restrições, e cada uma com a permissão que a justifica.

    `convites` é do `owner` porque a ADR 0010 o decidiu e porque é o que o
    `ConviteViewSet` impõe. `painel` é do `owner` porque o dono do produto o
    decidiu a 2026-10-06 — o painel de gestão mostra o resultado do mês, a folha
    salarial e o custo por cargo — e porque é o que o `reporting` impõe nos três
    endpoints. `configuracao` é do `owner` porque a ADR 0017 o decidiu e porque é
    o que o `EstabelecimentoView` impõe em leitura **e** em escrita. Nos três
    casos, mostrar o item a quem não o pode usar era pôr no menu um caminho que
    acaba em 403.

    As outras cinco estão abertas aos três papéis: dizer que um `staff` não pode
    ver o Stock é uma decisão de produto que ninguém tomou (Q7).

    **Este teste chamava-se "a única rota restrita", passou a nomear duas, e
    agora três.** Ele existe exactamente para isso: tornar visível no diff cada
    restrição nova, com a mesma pergunta a fazer nesse dia — que
    `permission_classes` a justifica? Não é um teste que se relaxa quando uma
    entra; é um teste que se **reescreve**, e a diferença é que reescrevê-lo
    obriga a responder à pergunta. Três vezes, três respostas.
    """
    restritas = {
        rota.route_id: sorted(rota.papeis)
        for rota in rotas_do_registo()
        if rota.papeis != TODOS_OS_PAPEIS
    }
    assert restritas == {
        RotaDeMenu.PAINEL: [Papel.OWNER],
        # Nenhum papel: a rota existe, o menu não a mostra a ninguém (ADR 0027
        # d10, segunda adenda) — a entrada é o lançador global.
        RotaDeMenu.ASSISTENTE: [],
    }, (
        "a lista de rotas restritas a um subconjunto de papéis mudou. Esconder "
        "um item que um papel não pode usar é autorização (ADR 0011), logo cada "
        "entrada tem de corresponder à permissão real do ecrã que serve — e não "
        "a uma ordem entre papéis, que este projeto não tem (Q7)."
    )


def test_o_contrato_do_item_de_menu_e_a_tupla_da_adr() -> None:
    """A forma do item é `(route_id, grupo, ordem, visivel, rotulo)` e mais nada.

    Em especial **não** tem `campo`: a projecção que a configuração transporta
    não pode ter o predicado de rota de campo, senão uma empresa promovia uma
    rota de escritório para o telemóvel (ADR 0009, adenda 2). E não tem
    `caminho`: a árvore de rotas é código, e um menu que nomeasse caminhos punha
    o deep link a depender da configuração.
    """
    assert set(ItemDeMenuOutSerializer().fields) == {
        "route_id",
        "grupo",
        "ordem",
        "visivel",
        "rotulo",
    }
    assert set(RotaDeMenuOutSerializer().fields) == {
        "route_id",
        "papeis_permitidos",
        "campo",
    }


# ---------------------------------------------------------------------------
# 2. Sem linhas: o menu é o dos defaults (ADR 0011)
# ---------------------------------------------------------------------------
#: O que a projeção por omissão mostra: a união inteira **menos** o assistente,
#: que tem rota mas nenhum papel no registo (segunda adenda à ADR 0027 d10: a
#: entrada é o lançador global, não o menu).
ROTAS_NO_MENU = [rota for rota in RotaDeMenu.values if rota != RotaDeMenu.ASSISTENTE]


def test_sem_linhas_o_menu_e_o_dos_defaults(cenario: Cenario) -> None:
    """"Os defaults vivem em código e a linha nasce na primeira escrita."

    O estabelecimento acabou de ser criado pelo `criar_tenant` e **não** tem
    linha nenhuma de menu: é a prova de que o `accounts.criar_tenant` não as
    semeia (não poderia — o `accounts` não importa nada — e não deve: um default
    guardado é um default que deixa de poder mudar).
    """
    assert _linhas_no_ambito(cenario.alfa.id) == []

    menu = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))

    assert [item["route_id"] for item in menu] == ROTAS_NO_MENU
    assert all(item["visivel"] is True for item in menu)
    assert all(item["rotulo"] is None for item in menu), (
        "`rotulo` tem de vir `null` quando o tenant não sobrepôs nada: é o "
        "cliente que faz `rotulo ?? registo.rotulo`, e resolvê-lo no servidor "
        "prendia o tenant a um default que ele nunca escolheu."
    )
    # **`grupo` vem `null` em todos**, como o `rotulo`, e desde 2026-10-07 pela
    # mesma razão: o nome por omissão de um grupo é copy do produto e vive no
    # registo do cliente, que o resolve (`entrada.grupo ?? registo.grupo`). Antes
    # disto vinha resolvido, e como o `PUT` é substituição total a primeira
    # gravação congelava "Inventário" na linha do tenant — nenhuma tradução a
    # voltava a alcançar (ADR 0019, decisão 5).
    assert all(item["grupo"] is None for item in menu), (
        "`grupo` tem de vir `null` quando o tenant não sobrepôs nada: é o cliente "
        "que faz `grupo ?? registo.grupo`, e resolvê-lo no servidor prendia o "
        "tenant a um default que ele nunca escolheu — e numa língua só."
    )
    assert [item["ordem"] for item in menu] == [10, 15, 20, 30, 40, 50]


def test_sem_estabelecimento_ativo_o_menu_vem_vazio(cenario: Cenario) -> None:
    """Sem tenant não há configuração por tenant, logo não há menu.

    É o estado `escolha_pendente` e os seus irmãos: o cliente não mostra sidebar
    nenhuma nesses três estados, e devolver o menu de um estabelecimento que
    ninguém escolheu era escolher em nome de quem tem de escolher.
    """
    corpo = _cliente(cenario.ana).get(URL_SESSAO).json()
    assert corpo["tenant_ativo"] is None
    assert corpo["menu"] == []


def test_um_anonimo_nao_tem_menu(transactional_db: None) -> None:
    corpo = Client().get(URL_SESSAO).json()
    assert corpo["estado"] == "anonimo"
    assert corpo["menu"] == []


# ---------------------------------------------------------------------------
# 3. O `PUT` de substituição total
# ---------------------------------------------------------------------------
def test_o_owner_guarda_o_menu_e_a_sessao_passa_a_devolve_lo(cenario: Cenario) -> None:
    """O caminho feliz: esconder, reordenar e renomear numa intenção só."""
    corpo = [
        _item(RotaDeMenu.RECEBER, grupo="Dia a dia", ordem=10, rotulo="Entradas"),
        _item(RotaDeMenu.CONTAR, grupo="Dia a dia", ordem=20),
        _item(RotaDeMenu.INICIO, grupo="Gestão", ordem=30),
        _item(RotaDeMenu.PAINEL, grupo="Gestão", ordem=35),
        _item(RotaDeMenu.ALERTAS, grupo="Gestão", ordem=40),
        _item(RotaDeMenu.ASSISTENTE, grupo="Gestão", ordem=45),
        _item(RotaDeMenu.STOCK, grupo="Gestão", ordem=50, visivel=False),
    ]

    resposta = _put(_cliente(cenario.ana, cenario.alfa.id), corpo)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json() == corpo, (
        "a resposta do PUT é a configuração como ficou, pela ordem configurada: "
        "um cliente que a volte a enviar não pode perder nada."
    )
    assert len(_linhas_no_ambito(cenario.alfa.id)) == len(RotaDeMenu.values)

    # E a sessão devolve o mesmo, que é por onde a sidebar o lê (ADR 0011).
    # Menos o assistente: a configuração guarda-o, mas nenhum papel o vê no menu
    # (segunda adenda à ADR 0027 d10) — a projeção filtra pelos papéis do registo.
    assert _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id)) == [
        item for item in corpo if item["route_id"] != RotaDeMenu.ASSISTENTE
    ]


def test_um_item_escondido_continua_a_viajar_na_projeccao(cenario: Cenario) -> None:
    """`visivel: false` é apresentação e sai no contrato com o seu valor.

    Quem esconde é o cliente. Filtrar no servidor transformava "esconder" num
    controlo de acesso falso (ADR 0009) e deixava o painel sem forma de voltar a
    mostrar o item.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.STOCK, grupo="Gestão", ordem=10, visivel=False)],
    )

    menu = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))
    assert _item_do_menu(menu, RotaDeMenu.STOCK) == {
        "route_id": RotaDeMenu.STOCK,
        "grupo": "Gestão",
        "ordem": 10,
        "visivel": False,
        "rotulo": None,
    }


def test_uma_rota_fora_do_corpo_volta_ao_default(cenario: Cenario) -> None:
    """Substituição total: o que não vem no corpo não está configurado.

    É a mesma coisa que uma rota sem linha na tabela, e é essa equivalência que
    faz "repor o default" ser um `PUT` sem o item em vez de uma coluna a mais.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    _put(cliente, [_item(r, grupo="Tudo", ordem=10) for r in RotaDeMenu.values])
    assert len(_linhas_no_ambito(cenario.alfa.id)) == len(RotaDeMenu.values)

    resposta = _put(cliente, [_item(RotaDeMenu.STOCK, grupo="Só esta", ordem=99)])

    assert resposta.status_code == 200, resposta.content
    assert len(_linhas_no_ambito(cenario.alfa.id)) == 1
    por_id = {item["route_id"]: item for item in resposta.json()}
    assert por_id[RotaDeMenu.STOCK]["grupo"] == "Só esta"
    # A rota que ficou fora do corpo volta ao default — e o default do `grupo`
    # é **`null`**, não a palavra: quem resolve é o cliente.
    assert por_id[RotaDeMenu.INICIO]["grupo"] is None
    assert por_id[RotaDeMenu.INICIO]["ordem"] == 10


def test_um_corpo_vazio_repoe_os_defaults(cenario: Cenario) -> None:
    """`[]` é o botão "repor tudo", e **não** "esconder tudo".

    Esconder escreve-se com `visivel: false` em cada item, que é explícito.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    _put(cliente, [_item(RotaDeMenu.STOCK, grupo="Antes", ordem=10)])

    resposta = _put(cliente, [])

    assert resposta.status_code == 200, resposta.content
    assert _linhas_no_ambito(cenario.alfa.id) == []
    assert [item["route_id"] for item in resposta.json()] == list(RotaDeMenu.values)


def test_guardar_duas_vezes_nao_duplica_linhas(cenario: Cenario) -> None:
    """A unicidade `(tenant, route_id)` é a rede; a substituição é o mecanismo."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    corpo = [_item(RotaDeMenu.STOCK, grupo="Gestão", ordem=10)]

    _put(cliente, corpo)
    _put(cliente, corpo)

    assert len(_linhas_no_ambito(cenario.alfa.id)) == 1


def test_o_rotulo_sobreposto_sai_e_o_vazio_e_a_ausencia(cenario: Cenario) -> None:
    """`""` na coluna e `null` no contrato são a mesma ausência, num sítio só."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    _put(cliente, [_item(RotaDeMenu.STOCK, rotulo="Armazém")])
    assert _linhas_no_ambito(cenario.alfa.id)[0].rotulo == "Armazém"
    assert _item_do_menu(_menu_da_sessao(cliente), RotaDeMenu.STOCK)["rotulo"] == "Armazém"

    _put(cliente, [_item(RotaDeMenu.STOCK, rotulo=None)])
    assert _linhas_no_ambito(cenario.alfa.id)[0].rotulo == ""
    assert _item_do_menu(_menu_da_sessao(cliente), RotaDeMenu.STOCK)["rotulo"] is None


def test_o_menu_da_sessao_custa_uma_query(cenario: Cenario) -> None:
    """A projecção é **uma** query, e não uma por rota.

    O custo do menu na sessão é uma transação curta e uma query (ver o
    `_sessao`); um N+1 aqui aparecia no caminho crítico do primeiro paint da
    sidebar, que é precisamente o que a ADR 0011 compra ao pô-lo na sessão.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(r, grupo="Tudo", ordem=10) for r in RotaDeMenu.values],
    )

    with tenant_scope(cenario.alfa.id), CaptureQueriesContext(connection) as queries:
        projeccao_de_menu(tenant_id=cenario.alfa.id, papel=Papel.OWNER)

    assert len(queries.captured_queries) == 1, queries.captured_queries


# ---------------------------------------------------------------------------
# 4. Validação: o que o serializer recusa, e com que forma
# ---------------------------------------------------------------------------
def test_um_route_id_inventado_e_400_no_campo(cenario: Cenario) -> None:
    """A lista fechada é o que impede a tabela de ser um armazém chave/valor.

    O id usado era `configuracao` — e a 2026-10-07 este teste começou a devolver
    200, porque a ADR 0017 o tornou uma rota a sério. É o modo de falha mais
    benigno que um teste destes tem (um id inventado que passa a existir) e ainda
    assim vale a nota: **um teste cujo valor de controlo é plausível acaba por
    deixar de ser um controlo.** O `fornecedores` é o próximo candidato óbvio a
    existir, pelo que o que entrou aqui é um id que nenhuma ADR pode querer.
    """
    resposta = _put(_cliente(cenario.ana, cenario.alfa.id), [_item("nao-e-uma-rota")])

    assert resposta.status_code == 400
    assert "route_id" in resposta.json()["0"]
    assert _linhas_no_ambito(cenario.alfa.id) == []


def test_uma_rota_repetida_e_400_e_nao_um_integrityerror(cenario: Cenario) -> None:
    """A unicidade na base de dados é a rede; a recusa legível vem do serializer.

    Sem o `MenuInListSerializer`, isto era um `IntegrityError` — 500 numa
    situação que é um erro de cliente.
    """
    resposta = _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.STOCK, ordem=10), _item(RotaDeMenu.STOCK, ordem=20)],
    )

    assert resposta.status_code == 400
    assert "stock" in str(resposta.json())
    assert _linhas_no_ambito(cenario.alfa.id) == []


@pytest.mark.parametrize(
    ("alteracao", "campo"),
    [
        ({"ordem": 99999}, "ordem"),
        ({"ordem": -1}, "ordem"),
        ({"grupo": "x" * 51}, "grupo"),
        ({"rotulo": "y" * 51}, "rotulo"),
        ({"rotulo": ""}, "rotulo"),
    ],
)
def test_os_limites_das_colunas_sao_400_e_nao_500(
    cenario: Cenario, alteracao: dict[str, Any], campo: str
) -> None:
    """O teto do serializer é o da coluna: a recusa é por campo, não do Postgres.

    O `rotulo` vazio entra na lista de propósito: um rótulo em branco não é um
    rótulo, e quem quer o default manda `null`.
    """
    item = _item(RotaDeMenu.STOCK) | alteracao

    resposta = _put(_cliente(cenario.ana, cenario.alfa.id), [item])

    assert resposta.status_code == 400
    assert campo in resposta.json()["0"], resposta.json()


def test_um_campo_em_falta_e_400(cenario: Cenario) -> None:
    """O corpo é a configuração inteira: "mantém o que estava" não é uma intenção."""
    item = _item(RotaDeMenu.STOCK)
    del item["ordem"]

    resposta = _put(_cliente(cenario.ana, cenario.alfa.id), [item])

    assert resposta.status_code == 400
    assert "ordem" in resposta.json()["0"]


def test_um_corpo_que_nao_e_lista_e_400(cenario: Cenario) -> None:
    """A entidade que este `PUT` substitui **é** a lista."""
    resposta = _put(_cliente(cenario.ana, cenario.alfa.id), _item(RotaDeMenu.STOCK))

    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# 5. Permissões: só o `owner`, e só com estabelecimento ativo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("papel", [Papel.MANAGER, Papel.STAFF])
def test_quem_nao_e_owner_nao_configura_o_menu(cenario: Cenario, papel: str) -> None:
    """ADR 0011: "Editar: `owner`, nos dois casos, no v1 (Q7 aberta)".

    403 e não 404: não há objecto nenhum a esconder — o que se recusa é a
    operação, e quem a pede tem pertença ativa neste estabelecimento.
    """
    user = cenario.bento if papel == Papel.MANAGER else cenario.clara
    cliente = _cliente(user, cenario.alfa.id)

    assert _put(cliente, [_item(RotaDeMenu.STOCK)]).status_code == 403
    assert cliente.get(URL_ROTAS).status_code == 403
    assert _linhas_no_ambito(cenario.alfa.id) == []


def test_sem_estabelecimento_na_sessao_o_middleware_recusa_antes_da_view(
    cenario: Cenario,
) -> None:
    """O default é ter âmbito: estas duas views não declaram dispensa nenhuma."""
    cliente = _cliente(cenario.ana)

    resposta = _put(cliente, [])

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_SEM_SESSAO


def test_um_anonimo_nao_chega_ao_menu(transactional_db: None) -> None:
    cliente = Client()
    assert cliente.get(URL_ROTAS).status_code == 403
    assert _put(cliente, []).status_code == 403


def test_o_registo_de_rotas_sai_inteiro_para_o_owner(cenario: Cenario) -> None:
    """O que o painel precisa: o que existe, os defaults, os papéis e o `campo`."""
    resposta = _cliente(cenario.ana, cenario.alfa.id).get(URL_ROTAS)

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert [rota["route_id"] for rota in corpo] == list(RotaDeMenu.values)
    assert corpo[0] == {
        "route_id": "inicio",
        "papeis_permitidos": ["owner", "manager", "staff"],
        "campo": False,
    }
    de_campo = {rota["route_id"] for rota in corpo if rota["campo"]}
    assert de_campo == {"contar", "receber"}, (
        "as rotas de campo são as desenhadas para 360px (ADR 0009). Este valor "
        "existe também no registo do frontend, que é quem gera a frase da "
        "gaveta de mobile — e nada casa as duas cópias."
    )


# ---------------------------------------------------------------------------
# 6. O filtro por papel, com o registo adulterado
# ---------------------------------------------------------------------------
def _restringir(
    monkeypatch: pytest.MonkeyPatch, route_id: str, *papeis: str
) -> RotaDoRegisto:
    """Restringe **uma** rota do registo a estes papéis, só para este teste.

    O filtro por papel mede-se com a restrição real (`convites`, do `owner`) em
    todos os testes menos um: o da resposta do `PUT`, que precisa de uma rota que
    **quem configura** não possa ver — e hoje não existe nenhuma invisível para o
    `owner`. Inventá-la no código de produção para o teste não ser vazio era
    responder à Q7 num teste.
    """
    original = REGISTO_DE_ROTAS[route_id]
    restrita = RotaDoRegisto(
        route_id=original.route_id,
        ordem_default=original.ordem_default,
        papeis=frozenset(papeis),
        campo=original.campo,
    )
    monkeypatch.setitem(REGISTO_DE_ROTAS, route_id, restrita)
    return restrita


@pytest.mark.parametrize("papel", [Papel.MANAGER, Papel.STAFF])
def test_as_rotas_do_owner_desaparecem_do_menu_de_quem_nao_e_owner(
    cenario: Cenario, papel: str
) -> None:
    """"Esconder um item que um `staff` não pode usar é autorização" (ADR 0011).

    A configuração é por tenant e a resposta é por **(tenant, papel)**: o mesmo
    estabelecimento, a mesma tabela (aqui sem linha nenhuma), três respostas. Os
    itens escondidos são os que levam a caminhos que o servidor recusa a quem não
    é `owner` — o `/convites`, que o `ConviteViewSet` recusa; o `/painel`, que o
    `reporting` recusa nos três endpoints; e a `/configuracao`, que o
    `EstabelecimentoView` recusa em leitura e em escrita. Um menu que os mostrasse
    apontava para um 403.

    **Eram um, passaram a dois a 2026-10-06 e a três a 2026-10-07**, e o teste é
    nomeado pelo critério (as rotas do `owner`) e não pela lista, para cada
    entrada nova não obrigar a inventar um nome — mas a asserção continua a ser
    pela lista exacta, que é o que faz cada entrada nova aparecer no diff.
    """
    user = cenario.bento if papel == Papel.MANAGER else cenario.clara

    do_owner = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))
    do_outro = _menu_da_sessao(_cliente(user, cenario.alfa.id))

    so_do_owner = {RotaDeMenu.PAINEL}
    assert so_do_owner <= {item["route_id"] for item in do_owner}
    assert so_do_owner.isdisjoint({item["route_id"] for item in do_outro})
    assert len(do_outro) == len(do_owner) - len(so_do_owner)


def test_o_filtro_por_papel_nao_depende_da_configuracao_do_tenant(
    cenario: Cenario,
) -> None:
    """Configurar um item restrito não o torna visível a quem não o pode ver.

    É a diferença entre apresentação e autorização: o `visivel` do tenant decide
    o primeiro, e o registo decide o segundo. Um `owner` que ponha o item do
    painel visível e no topo não o dá ao `staff` — e é essa assimetria que faz
    deste filtro um controlo e não uma preferência.

    Era o item dos **convites** até 2026-10-07, e passou a ser o do painel porque
    os convites deixaram de ser uma rota do menu: viraram a secção Equipa das
    Definições (ADR 0019, decisão 7). A propriedade medida é a mesma — o que
    mudou foi qual é a rota restrita que sobrou.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.PAINEL, grupo="Topo", ordem=1, visivel=True)],
    )

    do_staff = _menu_da_sessao(_cliente(cenario.clara, cenario.alfa.id))

    assert RotaDeMenu.PAINEL not in {item["route_id"] for item in do_staff}
    # E o `owner` vê o que configurou, para a asserção acima não passar por o
    # `PUT` ter falhado em silêncio.
    do_owner = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))
    assert do_owner[0] == {
        "route_id": RotaDeMenu.PAINEL,
        "grupo": "Topo",
        "ordem": 1,
        "visivel": True,
        "rotulo": None,
    }


def test_a_resposta_do_put_nao_e_filtrada_pelo_papel(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `PUT` devolve a configuração **inteira**, e isso evita perder dados.

    Com a resposta filtrada, um painel que a lesse e a voltasse a enviar apagava
    a configuração das rotas que o seu papel não vê — num endpoint de
    substituição total, filtrar a resposta é um caminho para perder dados.
    """
    _restringir(monkeypatch, RotaDeMenu.CONTAR, Papel.STAFF)

    resposta = _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.CONTAR, grupo="Campo", ordem=10)],
    )

    assert resposta.status_code == 200, resposta.content
    assert RotaDeMenu.CONTAR in {item["route_id"] for item in resposta.json()}
    # E a mesma conta, na sessão, não a vê: é lá que o filtro se aplica.
    menu = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))
    assert RotaDeMenu.CONTAR not in {item["route_id"] for item in menu}


def test_uma_linha_de_uma_rota_desconhecida_e_ignorada(cenario: Cenario) -> None:
    """O caso do rolling deploy: linha escrita pela versão nova, lida pela antiga.

    Inalcançável por um pedido (o `ChoiceField` valida contra o mesmo enum) e
    não inalcançável na base de dados. Ignorar a linha é o comportamento certo:
    uma entrada a mais não é razão para o menu não montar.
    """
    with tenant_scope(cenario.alfa.id):
        TenantMenuItem.objects.create(
            tenant_id=cenario.alfa.id,
            route_id="rota-de-uma-versao-futura",
            grupo="Futuro",
            ordem=1,
        )

    menu = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))

    assert [item["route_id"] for item in menu] == ROTAS_NO_MENU


# ---------------------------------------------------------------------------
# 7. A política de RLS, medida e não presumida
# ---------------------------------------------------------------------------
def test_a_queryset_sem_filtro_dentro_do_ambito_de_alfa_nao_ve_beta(
    cenario: Cenario,
) -> None:
    """`TenantMenuItem.objects.all()` **sem** filtro: quem filtra é a política.

    É o oposto do que o código de produção faz — o `selectors` filtra também por
    `tenant_id`, porque o `SECURITY.md` §1 exige os dois controlos. Aqui
    retira-se um para medir o outro.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.STOCK, grupo="Alfa", ordem=10)],
    )
    _put(
        _cliente(cenario.dinis, cenario.beta.id),
        [_item(RotaDeMenu.STOCK, grupo="Beta", ordem=20)],
    )

    with tenant_scope(cenario.alfa.id):
        visiveis = list(TenantMenuItem.objects.all())
    assert [(linha.grupo, linha.ordem) for linha in visiveis] == [("Alfa", 10)]

    with tenant_scope(cenario.beta.id):
        visiveis = list(TenantMenuItem.objects.all())
    assert [(linha.grupo, linha.ordem) for linha in visiveis] == [("Beta", 20)]


def test_o_menu_de_um_tenant_nao_mexe_no_do_outro(cenario: Cenario) -> None:
    """A substituição total de Beta não toca nas linhas de Alfa.

    O `DELETE` corre dentro do âmbito de quem pede e a política limita-o às
    linhas desse tenant — e é por isso que um `PUT` não precisa de dizer de que
    estabelecimento é.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.STOCK, grupo="Alfa", ordem=10)],
    )

    _put(_cliente(cenario.dinis, cenario.beta.id), [])

    assert [linha.grupo for linha in _linhas_no_ambito(cenario.alfa.id)] == ["Alfa"]
    menu = _menu_da_sessao(_cliente(cenario.ana, cenario.alfa.id))
    assert _item_do_menu(menu, RotaDeMenu.STOCK)["grupo"] == "Alfa"


@pytest.mark.sem_ambito_de_rls  # é esta leitura que o teste existe para provar
def test_fora_de_ambito_nao_se_ve_item_de_menu_nenhum(cenario: Cenario) -> None:
    """Sem `app.tenant_id`, a política devolve zero linhas — e não levanta.

    O "não levanta" é o `NULLIF` do predicado: sem ele, `''::uuid` dava
    `invalid input syntax for type uuid: ""` e o pedido sem tenant respondia 500
    (SECURITY.md §3). A marca está aqui porque esta leitura é o objecto do teste.
    """
    _put(
        _cliente(cenario.ana, cenario.alfa.id),
        [_item(RotaDeMenu.STOCK, grupo="Alfa", ordem=10)],
    )

    assert TenantMenuItem.objects.count() == 0


def test_a_politica_recusa_escrever_o_menu_de_outro_tenant(cenario: Cenario) -> None:
    """Sem `WITH CHECK` separado, o `USING` também decide as escritas.

    Dentro de `tenant_scope(Alfa)` não há forma de escrever uma linha de Beta: o
    erro é de privilégio (`new row violates row-level security policy`) e não de
    integridade.
    """
    with tenant_scope(cenario.alfa.id), pytest.raises(ProgrammingError, match="row-level"):
        TenantMenuItem.objects.create(
            tenant_id=cenario.beta.id,
            route_id=RotaDeMenu.STOCK,
            grupo="escrita para o tenant errado",
            ordem=10,
        )


def test_guardar_menu_fora_do_ambito_levanta_em_vez_de_apagar_nada(
    cenario: Cenario,
) -> None:
    """O esquecimento falha fechado, e com o nome da tabela na mensagem.

    Sem a guarda, o `DELETE` e o `INSERT` corriam contra zero linhas **sem
    erro** — a forma silenciosa do mesmo bug (ADR 0005).
    """
    with pytest.raises(TenantScopeConflict, match="accounts_tenantmenuitem"):
        guardar_menu(tenant_id=cenario.alfa.id, itens=[])

    with tenant_scope(cenario.beta.id), pytest.raises(TenantScopeConflict):
        guardar_menu(tenant_id=cenario.alfa.id, itens=[])
