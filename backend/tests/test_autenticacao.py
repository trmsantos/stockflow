"""A autenticação de sessão, ponta a ponta (ADR 0010, ADR 0007).

Antes deste ficheiro não havia **um único teste de login** no repositório, e
isso já custou uma vez: uma recursão infinita no `progressive_cooloff` punha
*todos* os logins a 500, o admin incluído, e passou por duas razões que se
somaram — o `config/settings/test.py` desliga o axes (`AXES_ENABLED = False`) e
não havia teste nenhum a atravessar o caminho do login. Foi encontrada por
acaso.

Daí a forma deste ficheiro, e duas regras que valem para quem o alargar:

1. **os testes passam pelo HTTP.** O que se mede é o status, o corpo e o estado
   da sessão depois do pedido, não o valor de retorno de uma função. A perda do
   429 do lockout, por exemplo, só se vê no status: a decisão é tomada igual nos
   dois casos (ver `test_o_lockout_responde_429_com_corpo_json`);
2. **o lockout é testado com o axes LIGADO** (`axes_ligado`, abaixo). Um teste
   de lockout com o axes desligado não testa o lockout: testa que a função que
   decide o bloqueio não é chamada.

## Porque é que todos levam `transactional_db`

O mesmo motivo do `tests/test_rls_isolation.py`: com a transação do
pytest-django por fora, o `set_config('app.tenant_id', ..., true)` que o
`tenant_scope` corre só reverte no fim **dela**, e não no fim do bloco `with`.
O GUC ficava colado ao resto do teste e as asserções sobre o que se vê fora de
âmbito passariam a medir um âmbito ainda aberto. O caminho do login abre um
âmbito por candidato, logo isto não é teoria aqui.

## O guarda de âmbito do `conftest.py` está a trabalhar neste ficheiro

Ele levanta quando uma query toca numa tabela com política de RLS fora de um
âmbito que a alcance. Como o login lê o `accounts_membership` e o
`accounts_tenant` (para o nome), cada teste que faça login é também uma
afirmação de que essas leituras acontecem **dentro** de `tenant_scope` — e
nenhum teste aqui tem a marca `sem_ambito_de_rls`. É a prova mais barata de que
a ordem da ADR 0007 está respeitada: se alguém puser a descoberta antes do
âmbito, estes testes ficam vermelhos em vez de devolverem uma lista vazia em
silêncio.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache
from django.test import Client, override_settings

from apps.accounts.middleware import CODIGO_DESCONHECIDO, SESSION_TENANT_KEY
from apps.accounts.models import Membership, Papel, RotaDeMenu, Tema, Tenant, User
from apps.accounts.serializers import ErroOutSerializer
from apps.accounts.services import (
    CODIGO_CREDENCIAIS_INVALIDAS,
    CODIGOS_DE_RECUSA,
    EstadoDaSessao,
    conceder_pertenca,
    criar_tenant,
    revogar_pertenca,
)
from apps.accounts.views import STATUS_DA_RECUSA
from apps.shared.db import tenant_scope
from config.lockout import CODIGO_CONTA_BLOQUEADA, DETALHE_CONTA_BLOQUEADA

URL_LOGIN = "/api/v1/auth/login"
URL_LOGOUT = "/api/v1/auth/logout"
URL_SESSAO = "/api/v1/auth/sessao"
URL_TENANT_ATIVO = "/api/v1/auth/tenant-ativo"

#: A password das contas do cenário. Longa e sem relação com nenhum dos emails,
#: para o `UserAttributeSimilarityValidator` não entrar na conversa onde ele não
#: é o objeto do teste (só o é no do comando).
#:
#: Não se chama `PASSWORD` pela razão escrita no comando `criar_estabelecimento`:
#: o `S105` do ruff trata um literal atribuído a um nome com "password" dentro
#: como credencial em código, e esta casa não tem supressões de lint.
CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"

#: O backend vai explícito no `force_login`, como no `test_rls_isolation.py`:
#: sem ele o Django escolhe o primeiro dos `AUTHENTICATION_BACKENDS`, que é o
#: `AxesStandaloneBackend`, cujo `get_user` herdado devolve `None` — a sessão
#: ficava escrita e o pedido seguinte vinha anónimo.
BACKEND = "django.contrib.auth.backends.ModelBackend"


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos e quatro contas, uma por situação que interessa."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa e em mais nada: o caso de 98% dos utilizadores.
    ana: User
    #: `staff` nos **dois**: a contabilista da ADR 0007, e é ela que obriga o
    #: login a não escolher âmbito nenhum.
    carla: User
    #: Existe no `accounts_user` e não tem pertença em sítio nenhum. Saber um
    #: email não compra nada (ADR 0007).
    bruno: User
    #: `is_active = False`, com pertença ativa em Alfa: a conta desativada tem
    #: de ser recusada pelo mesmo corpo das credenciais erradas.
    dora: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo.

    Sem isto, o `AnonRateThrottle` de 60/min acumula entre testes do mesmo
    processo — e este ficheiro faz muitos pedidos anónimos ao login — e um teste
    começa a falhar por causa dos que correram antes.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    carla = User.objects.create_user("carla@contabilidade.pt", CREDENCIAL_VALIDA)
    bruno = User.objects.create_user("bruno@sem-pertenca.pt", CREDENCIAL_VALIDA)
    dora = User.objects.create_user("dora@alfa.pt", CREDENCIAL_VALIDA, is_active=False)

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
        conceder_pertenca(
            user=carla,
            tenant_id=alfa.id,
            role=Papel.STAFF,
            display_name="Carla (contabilidade)",
        )
        conceder_pertenca(
            user=dora, tenant_id=alfa.id, role=Papel.MANAGER, display_name="Dora"
        )
    with tenant_scope(beta.id):
        conceder_pertenca(
            user=carla, tenant_id=beta.id, role=Papel.STAFF, display_name="Carla"
        )

    return Cenario(alfa=alfa, beta=beta, ana=ana, carla=carla, bruno=bruno, dora=dora)


@pytest.fixture
def axes_ligado() -> Iterator[None]:
    """Liga o `django-axes` só neste teste, e é a razão de esta fixture existir.

    O `config/settings/test.py` tem `AXES_ENABLED = False` com um motivo
    legítimo — ligado por omissão, o lockout trancava contas usadas por outros
    testes da suite, porque o contador é por conta e persiste entre pedidos. Mas
    essa linha é **metade** da razão pela qual a recursão do `progressive_cooloff`
    passou por um `/review`: com o axes desligado, o `AxesStandaloneBackend` não
    corre, o `AxesMiddleware` não substitui resposta nenhuma, e um teste que
    "exercite o lockout" exercita o caminho em que ele não existe.

    Logo a inversão: a setting fica desligada para a suite e **ligada aqui**,
    nos testes que são sobre o lockout. O que esta fixture compra é o caminho
    real — backend do axes à cabeça, `user_login_failed` a escrever no
    `axes_accessattempt`, `AxesMiddleware` a trocar a resposta — e o que ela
    custa é que os testes que a usam têm de ser os únicos a tocar na conta que
    trancam. As linhas de tentativas desaparecem com o `flush` do
    `transactional_db` entre testes.
    """
    with override_settings(AXES_ENABLED=True):
        yield


def _post(cliente: Client, url: str, corpo: dict[str, Any] | None = None) -> Any:
    """`POST` com corpo JSON, que é o único que estas views aceitam.

    As views levam `parser_classes = [JSONParser]` de propósito (ver o docstring
    do `views.py`): um formulário HTML de outro domínio consegue fazer `POST` de
    `multipart/form-data` sem preflight, e um corpo JSON não.
    """
    return cliente.post(url, data=corpo or {}, content_type="application/json")


def _entrar(email: str, password: str = CREDENCIAL_VALIDA) -> Client:
    """Um cliente com sessão, aberta pelo **endpoint real** e não por `force_login`.

    É o caminho que interessa: um `force_login` escreve a sessão à mão e
    saltava precisamente a parte que a ADR 0007 fixa (a ordem
    `authenticate` → `login` → descoberta).
    """
    cliente = Client()
    resposta = _post(cliente, URL_LOGIN, {"email": email, "password": password})
    assert resposta.status_code == 200, resposta.content
    return cliente


def _corpo(resposta: Any) -> dict[str, Any]:
    return resposta.json()


# ---------------------------------------------------------------------------
# 1. Caminho feliz: o que o login devolve em cada uma das três situações
# ---------------------------------------------------------------------------
def test_login_com_um_estabelecimento_fica_com_ele_ativo(cenario: Cenario) -> None:
    """Um candidato confirmado escreve-se na sessão (ADR 0007).

    E o `SessaoOut` sai inteiro: é o contrato que o `types.ts` do frontend
    carrega, por isso o teste afirma os cinco campos e não só o estado, e cada
    um deles por igualdade — um campo novo no `utilizador` cai aqui.
    """
    cliente = Client()

    resposta = _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})

    assert resposta.status_code == 200
    corpo = _corpo(resposta)
    assert corpo["estado"] == EstadoDaSessao.ATIVA
    # O `tema` entra aqui porque esta asserção é de igualdade e não de inclusão:
    # é o que faz um campo novo no contrato cair num teste em vez de aparecer no
    # `types.ts` sem ninguém olhar. O valor é o default (ADR 0016) — a Ana nunca
    # trocou de tema, e o que se troca mede-se no `tests/test_preferencias.py`.
    assert corpo["utilizador"] == {
        "id": str(cenario.ana.pk),
        "email": "ana@alfa.pt",
        "tema": Tema.ESCURO.value,
    }
    # O `demonstracao` entra aqui pela mesma razão do `tema` acima: a asserção é
    # de igualdade, logo um campo novo no contrato cai num teste em vez de
    # aparecer no `types.ts` sem ninguém olhar. `False` porque este
    # estabelecimento foi criado pelo `criar_tenant` normal — o de demonstração
    # tem o seu ficheiro (ADR 0018).
    assert corpo["tenant_ativo"] == {
        "id": str(cenario.alfa.id),
        "nome": "Pastelaria Alfa",
        "papel": Papel.OWNER.value,
        "demonstracao": False,
    }
    assert corpo["tenants"] == [corpo["tenant_ativo"]]
    # O menu vem **na resposta do login**, já resolvido e filtrado pelo papel
    # (ADR 0011): é o que a sidebar precisa no primeiro paint, sem um segundo
    # round trip. Este estabelecimento nunca configurou nada, logo o que sai são
    # os defaults do registo de rotas, que é código — e a Ana é `owner`, logo vê
    # também o item dos convites. O contrato do item está fixado em
    # `tests/test_menu.py`; aqui afirma-se só que ele chega por este caminho.
    assert [item["route_id"] for item in corpo["menu"]] == list(RotaDeMenu.values)
    assert all(item["visivel"] is True for item in corpo["menu"])
    # A sessão nomeia o âmbito — é o que o `TenantMiddleware` vai ler no pedido
    # seguinte, e é a única coisa que o login lhe deixa.
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)


def test_login_com_dois_estabelecimentos_nao_escolhe_nenhum(cenario: Cenario) -> None:
    """A contabilista: 200, a lista, e **sem** âmbito até haver escolha.

    Adivinhar qual dos dois seria escolher o âmbito em nome de quem tem de o
    escolher — e com a RLS por baixo, escolher mal é mostrar dados do
    estabelecimento errado.

    A ordem da lista é por nome ("Café Beta" antes de "Pastelaria Alfa") e não a
    de inserção no `tenant_ids`: é uma lista que uma pessoa lê num seletor.
    """
    cliente = Client()

    resposta = _post(
        cliente, URL_LOGIN, {"email": "carla@contabilidade.pt", "password": CREDENCIAL_VALIDA}
    )

    assert resposta.status_code == 200
    corpo = _corpo(resposta)
    assert corpo["estado"] == EstadoDaSessao.ESCOLHA_PENDENTE
    assert corpo["tenant_ativo"] is None
    assert [t["nome"] for t in corpo["tenants"]] == ["Café Beta", "Pastelaria Alfa"]
    # O papel é por estabelecimento, e vem do Membership confirmado em cada um.
    assert {t["papel"] for t in corpo["tenants"]} == {Papel.STAFF.value}
    assert SESSION_TENANT_KEY not in cliente.session


def test_login_de_quem_nao_tem_pertenca_nenhuma_entra_mas_sem_estabelecimento(
    cenario: Cenario,
) -> None:
    """Zero candidatos é 200 com lista vazia, não um erro (ADR 0007).

    O Bruno existe no `accounts_user` e não tem `Membership` em sítio nenhum:
    autentica-se e não alcança dado nenhum. É a propriedade que compensa o
    `accounts_user` não ter política — saber um email não compra nada.
    """
    resposta = _post(
        Client(), URL_LOGIN, {"email": "bruno@sem-pertenca.pt", "password": CREDENCIAL_VALIDA}
    )

    assert resposta.status_code == 200
    corpo = _corpo(resposta)
    assert corpo["estado"] == EstadoDaSessao.SEM_ESTABELECIMENTO
    assert corpo["tenant_ativo"] is None
    assert corpo["tenants"] == []


def test_o_email_e_insensivel_a_caixa_no_login(cenario: Cenario) -> None:
    """`Ana@ALFA.pt` e `ana@alfa.pt` são a mesma conta (ADR 0007).

    Quem o decide é o `UserManager.get_by_natural_key`, pelo índice funcional
    `LOWER(email)` — não um `.lower()` no serializer. Este teste é o que impede
    que alguém o acrescente lá e crie uma terceira definição.
    """
    resposta = _post(Client(), URL_LOGIN, {"email": "Ana@ALFA.pt", "password": CREDENCIAL_VALIDA})

    assert resposta.status_code == 200
    # E o email sai na forma canónica, que é a que está na linha.
    assert _corpo(resposta)["utilizador"]["email"] == "ana@alfa.pt"


# ---------------------------------------------------------------------------
# 2. A recusa é genérica, e é a mesma nas três situações
# ---------------------------------------------------------------------------
def test_as_tres_recusas_de_credenciais_sao_indistinguiveis(cenario: Cenario) -> None:
    """Password errada, email inexistente e conta inativa: **o mesmo** corpo.

    É o teste que impede o oráculo de enumeração de contas. Com respostas
    diferentes, quem tem uma lista de emails descobre num pedido por email quais
    deles são clientes do StockFlow — e o `accounts_user` é a tabela sem
    política, legível por qualquer ligação da app (ADR 0007, `SECURITY.md` §3).

    A Dora é o caso que se esquece: `is_active = False` **com** pertença ativa
    em Alfa. O `ModelBackend` recusa-a no `user_can_authenticate`, logo cai no
    mesmo sítio — mas só porque ninguém escreveu um ramo próprio para ela.
    """
    respostas = [
        _post(Client(), URL_LOGIN, {"email": "ana@alfa.pt", "password": "nao-confere"}),
        _post(Client(), URL_LOGIN, {"email": "nao-existe@alfa.pt", "password": CREDENCIAL_VALIDA}),
        _post(Client(), URL_LOGIN, {"email": "dora@alfa.pt", "password": CREDENCIAL_VALIDA}),
    ]

    for resposta in respostas:
        assert resposta.status_code == 400
        assert _corpo(resposta)["code"] == CODIGO_CREDENCIAIS_INVALIDAS

    corpos = {resposta.content for resposta in respostas}
    assert len(corpos) == 1, f"as recusas distinguem-se entre si: {corpos}"


def test_uma_recusa_de_credenciais_nao_abre_sessao(cenario: Cenario) -> None:
    cliente = Client()

    _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": "nao-confere"})

    assert SESSION_KEY not in cliente.session
    assert _corpo(cliente.get(URL_SESSAO))["estado"] == EstadoDaSessao.ANONIMO


def test_um_corpo_invalido_da_400_por_campo_e_nao_tenta_autenticar(
    cenario: Cenario,
) -> None:
    """A outra forma do 400, e o `views.py` diz que são duas de propósito.

    Um campo em falta sai na forma do DRF (por campo, para um formulário o
    mostrar ao lado do input) e **não** em `{code, detail}`. Sem password não há
    tentativa de autenticação nenhuma, logo o axes também não conta nada: um
    pedido sem credenciais não é uma tentativa.
    """
    resposta = _post(Client(), URL_LOGIN, {"email": "ana@alfa.pt"})

    assert resposta.status_code == 400
    corpo = _corpo(resposta)
    assert "password" in corpo
    assert "code" not in corpo


# ---------------------------------------------------------------------------
# 3. `GET /auth/sessao`: relata, e repara
# ---------------------------------------------------------------------------
def test_a_sessao_de_um_anonimo_e_200_e_nao_403(transactional_db: None) -> None:
    """O arranque da SPA tem de poder perguntar "há sessão?" sem ter sessão.

    Com `IsAuthenticated`, isto respondia 403 — e o cliente passava a ter de
    distinguir *dois* 403 diferentes (o do DRF e o do `TenantMiddleware`) no seu
    caminho mais crítico.
    """
    resposta = Client().get(URL_SESSAO)

    assert resposta.status_code == 200
    assert _corpo(resposta) == {
        "estado": EstadoDaSessao.ANONIMO,
        "utilizador": None,
        "tenant_ativo": None,
        "tenants": [],
        "menu": [],
    }


def test_a_sessao_devolve_o_cookie_de_csrf(transactional_db: None) -> None:
    """`ensure_csrf_cookie`, e é o que dispensa um endpoint de CSRF (ADR 0010).

    Sem este cookie, o `POST /auth/login` não tem com que ser assinado e o
    cliente não consegue entrar — e o `http.ts` do frontend falha antes de
    enviar o pedido, de propósito, em vez de levar um 403 que ninguém sabe ler.
    """
    resposta = Client().get(URL_SESSAO)

    assert settings.CSRF_COOKIE_NAME in resposta.cookies


def test_a_sessao_repara_um_estabelecimento_que_deixou_de_ser_concedido(
    cenario: Cenario,
) -> None:
    """Revogar a pertença: o `GET` seguinte limpa a chave em vez de se contradizer.

    A verificação é por pedido e não há cache (ADR 0007), logo a revogação vale
    imediatamente. O que este teste fixa é a parte que faltava: a resposta não
    pode trazer `tenant_ativo: null` **e** deixar na sessão um estabelecimento
    que ela própria acabou de dizer que não vale — isso dava um cliente a
    mostrar o seletor enquanto todos os outros endpoints respondiam 403.
    """
    cliente = _entrar("ana@alfa.pt")
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)

    with tenant_scope(cenario.alfa.id):
        assert revogar_pertenca(user=cenario.ana, tenant_id=cenario.alfa.id) is True

    corpo = _corpo(cliente.get(URL_SESSAO))

    assert corpo["estado"] == EstadoDaSessao.SEM_ESTABELECIMENTO
    assert corpo["tenant_ativo"] is None
    assert corpo["tenants"] == []
    assert SESSION_TENANT_KEY not in cliente.session
    # E continua autenticada: revogar uma pertença não é terminar a sessão.
    assert SESSION_KEY in cliente.session


def test_a_sessao_nao_escolhe_um_estabelecimento_por_ela(cenario: Cenario) -> None:
    """Reparar não é escolher, mesmo quando só há um candidato.

    Com a sessão da Carla sem estabelecimento ativo e **um** candidato de cada
    vez não seria ambíguo — e este `GET` continua a não o activar. Quem escolhe
    o âmbito é o `login` (uma vez, na entrada) e o `POST /auth/tenant-ativo`:
    dois escritores para a mesma decisão é uma a mais.
    """
    cliente = _entrar("carla@contabilidade.pt")
    with tenant_scope(cenario.beta.id):
        revogar_pertenca(user=cenario.carla, tenant_id=cenario.beta.id)

    corpo = _corpo(cliente.get(URL_SESSAO))

    assert corpo["estado"] == EstadoDaSessao.ESCOLHA_PENDENTE
    assert corpo["tenant_ativo"] is None
    assert [t["nome"] for t in corpo["tenants"]] == ["Pastelaria Alfa"]
    assert SESSION_TENANT_KEY not in cliente.session


# ---------------------------------------------------------------------------
# 4. `POST /auth/tenant-ativo`: a sessão escolhe, a política concede
# ---------------------------------------------------------------------------
def test_a_troca_de_estabelecimento_escreve_o_ambito_na_sessao(cenario: Cenario) -> None:
    cliente = _entrar("carla@contabilidade.pt")

    resposta = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(cenario.beta.id)})

    assert resposta.status_code == 200
    corpo = _corpo(resposta)
    assert corpo["estado"] == EstadoDaSessao.ATIVA
    assert corpo["tenant_ativo"]["id"] == str(cenario.beta.id)
    assert corpo["tenant_ativo"]["nome"] == "Café Beta"
    # A lista continua lá: o seletor não fica vazio depois de escolher.
    assert len(corpo["tenants"]) == 2
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.beta.id)


def test_a_troca_para_um_estabelecimento_alheio_e_recusada(cenario: Cenario) -> None:
    """O `tenant_id` do corpo é argumento e não credencial (ADR 0007).

    A Ana tem pertença em Alfa e pede Beta, onde **existe** uma pertença — a da
    Carla. A recusa vem da política: dentro de `tenant_scope(Beta)` a query leva
    `user_id = <o da Ana>` no `WHERE` e devolve zero linhas. Nenhuma linha de
    Beta é lida no caminho, nem para ser descartada depois em Python.
    """
    cliente = _entrar("ana@alfa.pt")

    resposta = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(cenario.beta.id)})

    assert resposta.status_code == 403
    assert _corpo(resposta)["code"] == CODIGO_DESCONHECIDO
    # E a sessão não foi tocada: uma recusa não muda o âmbito.
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)


def test_um_uuid_forjado_da_a_mesma_recusa_que_um_alheio(cenario: Cenario) -> None:
    """"Não existe" e "não é teu" respondem igual, e tem de ser assim.

    A diferença entre as duas respostas seria um oráculo de "este uuid é um
    estabelecimento do StockFlow". Aqui não há diferença porque não há
    comparação nenhuma em código: a política devolve zero linhas nos dois casos.
    """
    cliente = _entrar("ana@alfa.pt")

    alheio = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(cenario.beta.id)})
    forjado = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(uuid4())})

    assert forjado.status_code == alheio.status_code == 403
    assert forjado.content == alheio.content


def test_o_tenant_ids_propoe_e_nao_concede(cenario: Cenario) -> None:
    """Um uuid no array sem `Membership` ativo não abre porta nenhuma.

    É a propriedade que a ADR 0007 pede ao `tenant_ids`, aqui medida pelo
    endpoint: repõe-se à mão no array o uuid de uma pertença revogada — que é o
    que um tenant apagado deixaria lá — e o `tenant-ativo` continua a recusar.

    O teste também diz o contrário do que se poderia supor ao ler o código: o
    `escolher_tenant_ativo` **não** filtra pelo array. Se filtrasse, a recusa
    aqui vinha do array e não da política, e o array passava a ser fonte de
    autorização.
    """
    cliente = _entrar("ana@alfa.pt")
    with tenant_scope(cenario.alfa.id):
        revogar_pertenca(user=cenario.ana, tenant_id=cenario.alfa.id)
    User.objects.filter(pk=cenario.ana.pk).update(tenant_ids=[cenario.alfa.id])

    resposta = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(cenario.alfa.id)})

    assert resposta.status_code == 403
    assert _corpo(resposta)["code"] == CODIGO_DESCONHECIDO


def test_um_tenant_id_que_nao_e_uuid_da_400_de_validacao(cenario: Cenario) -> None:
    cliente = _entrar("ana@alfa.pt")

    resposta = _post(cliente, URL_TENANT_ATIVO, {"tenant_id": "a-pastelaria-do-ze"})

    assert resposta.status_code == 400
    assert "tenant_id" in _corpo(resposta)


# ---------------------------------------------------------------------------
# 5. Quem não tem sessão não termina sessão nem escolhe âmbito
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", [URL_LOGOUT, URL_TENANT_ATIVO])
def test_um_anonimo_nao_alcanca_os_endpoints_autenticados(
    transactional_db: None, url: str
) -> None:
    """403 do DRF, sem `code`: quem chega aqui sem sessão tem um bug no cliente.

    O importante é que **não** é um 403 do `TenantMiddleware`: estas views são
    dispensadas de âmbito, logo o middleware deixa-as passar e quem recusa é o
    `IsAuthenticated`. Se a dispensa desaparecesse, o código seria `sem_sessao` e
    o login deixaria de funcionar — daí a asserção sobre a ausência de `code`.
    """
    resposta = _post(Client(), url, {"tenant_id": str(uuid4())})

    assert resposta.status_code == 403
    assert "code" not in _corpo(resposta)


def test_o_logout_fecha_a_sessao(cenario: Cenario) -> None:
    cliente = _entrar("ana@alfa.pt")

    resposta = _post(cliente, URL_LOGOUT)

    assert resposta.status_code == 200
    assert _corpo(resposta)["estado"] == EstadoDaSessao.ANONIMO
    # O `logout()` faz `flush()`: o utilizador e o âmbito saem os dois.
    assert SESSION_KEY not in cliente.session
    assert SESSION_TENANT_KEY not in cliente.session
    assert _corpo(cliente.get(URL_SESSAO))["estado"] == EstadoDaSessao.ANONIMO


# ---------------------------------------------------------------------------
# 6. Rotação da chave de sessão — confirmada, não presumida
# ---------------------------------------------------------------------------
def test_a_chave_de_sessao_roda_no_login(cenario: Cenario) -> None:
    """O `SECURITY.md` §5 exige rotação depois do login; o Django fá-la.

    Medido e não presumido: semeia-se uma sessão anónima (é o que um visitante
    tem depois de a aplicação lhe escrever qualquer coisa na sessão), guarda-se
    a chave, faz-se login, e a chave tem de ser outra. Sem rotação, quem
    conseguisse fixar uma chave de sessão num browser antes do login continuava
    a tê-la depois — *session fixation*.
    """
    cliente = Client()
    sessao = cliente.session
    sessao["qualquer-coisa"] = "antes do login"
    sessao.save()
    chave_antes = sessao.session_key
    cliente.cookies[settings.SESSION_COOKIE_NAME] = chave_antes

    _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})

    assert chave_antes is not None
    assert cliente.session.session_key != chave_antes


def test_entrar_noutra_conta_descarta_a_sessao_anterior_e_nao_o_ambito_novo(
    cenario: Cenario,
) -> None:
    """O caminho do `flush`, e a razão da ordem da ADR 0007.

    Login como Ana (âmbito de Alfa na sessão) e, no mesmo cliente, login como
    Carla. O `login()` do Django vê um utilizador diferente e faz `flush()` —
    apaga a sessão inteira, incluindo o `tenant_id` de Alfa. Se o
    `iniciar_sessao` escrevesse o âmbito **antes** do `login()`, o `flush`
    comia-o em silêncio e a Carla ficava com uma sessão autenticada sem
    estabelecimento; como a Carla tem dois, o sintoma seria invisível aqui e
    visível com a Ana. Logo o teste faz os dois sentidos.
    """
    cliente = _entrar("ana@alfa.pt")
    chave_da_ana = cliente.session.session_key
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)

    # Entrar como a Carla: dois estabelecimentos, logo nenhum ativo — e o de
    # Alfa que lá estava **não** pode sobreviver.
    corpo = _corpo(
        _post(
            cliente,
            URL_LOGIN,
            {"email": "carla@contabilidade.pt", "password": CREDENCIAL_VALIDA},
        )
    )
    assert corpo["estado"] == EstadoDaSessao.ESCOLHA_PENDENTE
    assert cliente.session.session_key != chave_da_ana
    assert SESSION_TENANT_KEY not in cliente.session

    # E o sentido oposto: entrar como a Ana por cima disto escreve o âmbito
    # **depois** do flush, que é o que a ordem garante.
    corpo = _corpo(
        _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})
    )
    assert corpo["estado"] == EstadoDaSessao.ATIVA
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)


def test_a_chave_de_sessao_nao_roda_na_troca_de_estabelecimento(
    cenario: Cenario,
) -> None:
    """E é deliberado (ADR 0007), não um esquecimento.

    A rotação é um controlo de fixação ligado à **autenticação**, e esta sessão
    já tinha acesso a esta conta antes e depois da troca. O que a troca precisa é
    de registo, e é o que leva.
    """
    cliente = _entrar("carla@contabilidade.pt")
    chave = cliente.session.session_key

    _post(cliente, URL_TENANT_ATIVO, {"tenant_id": str(cenario.beta.id)})

    assert cliente.session.session_key == chave


# ---------------------------------------------------------------------------
# 7. CSRF — o controlo que o `csrf_exempt` do DRF teria removido
# ---------------------------------------------------------------------------
def test_o_login_sem_token_de_csrf_e_recusado(cenario: Cenario) -> None:
    """*Login CSRF*, e sem o `csrf_protect` das views isto passava.

    O `as_view()` do DRF embrulha a view em `csrf_exempt` e delega a verificação
    ao `SessionAuthentication`, que só a faz quando **encontra** um utilizador na
    sessão. Num login o pedido é anónimo por definição: ninguém verificava nada,
    e um atacante podia fazer o browser da vítima entrar na conta *dele* — e
    passar a ver o que ela lá fizesse.

    As duas metades são necessárias. Sem a segunda, o teste passava com o CSRF
    desligado e uma qualquer outra recusa a dar o 403.
    """
    cliente = Client(enforce_csrf_checks=True)

    sem_token = _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})

    assert sem_token.status_code == 403

    # A mesma chamada, com o token que o `GET /auth/sessao` devolve: 200.
    cliente.get(URL_SESSAO)
    token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
    com_token = cliente.post(
        URL_LOGIN,
        data={"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA},
        content_type="application/json",
        headers={"x-csrftoken": token},
    )

    assert com_token.status_code == 200


def test_um_corpo_form_encoded_nao_chega_a_view(cenario: Cenario) -> None:
    """415, e é a via que não precisa de token de CSRF para ser disparada.

    Um `<form>` numa página de outro domínio faz `POST` de
    `multipart/form-data` ou de `application/x-www-form-urlencoded` sem
    preflight de CORS; um corpo `application/json` não. O `JSONParser` sozinho
    nas views fecha essa via antes de qualquer código nosso correr — é a segunda
    camada por baixo do token.
    """
    resposta = Client().post(
        URL_LOGIN, data={"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA}
    )

    assert resposta.status_code == 415


# ---------------------------------------------------------------------------
# 8. O lockout, com o axes LIGADO. É por isto que este ficheiro existe.
# ---------------------------------------------------------------------------
def test_o_lockout_responde_429_com_corpo_json(cenario: Cenario, axes_ligado: None) -> None:
    """O caminho completo do lockout, do primeiro 400 ao 429 com `code`.

    Três coisas de uma vez, e nenhuma delas se pode medir com o axes desligado:

    1. **o lockout dispara.** As primeiras `AXES_FAILURE_LIMIT - 1` falhas dão
       400 `credenciais_invalidas`; a última dá 429. É a asserção que a recursão
       do `progressive_cooloff` teria feito falhar — lá, *todas* as tentativas
       davam 500;
    2. **o 429 chega ao cliente.** A decisão é tomada pelo axes dentro do
       `authenticate()`, marcando `request.axes_locked_out` no `HttpRequest`, e é
       o `AxesMiddleware` que substitui a resposta da view. Passar ao service o
       `Request` do DRF em vez do `HttpRequest` fazia a marca ficar no invólucro
       (o `Request` do DRF não tem `__setattr__`), o middleware não a via, e o
       cliente recebia o 400 de credenciais como se nada fosse — decisão tomada,
       resposta perdida. Este teste é o que distingue os dois casos;
    3. **o corpo é JSON com `code` estável** (`conta_bloqueada`), que é o item de
       dívida que o `SECURITY.md` §5 nomeava. Sem o `AXES_LOCKOUT_CALLABLE`, o
       axes responderia o `AXES_COOLOFF_MESSAGE` em `text/plain` e o cliente não
       saberia distinguir este 429 do 429 do throttle do DRF.
    """
    cliente = Client()
    erradas = {"email": "ana@alfa.pt", "password": "nao-confere"}

    for tentativa in range(1, settings.AXES_FAILURE_LIMIT):
        resposta = _post(cliente, URL_LOGIN, erradas)
        assert resposta.status_code == 400, f"tentativa {tentativa}"
        assert _corpo(resposta)["code"] == CODIGO_CREDENCIAIS_INVALIDAS

    bloqueada = _post(cliente, URL_LOGIN, erradas)

    assert bloqueada.status_code == 429
    assert bloqueada["Content-Type"].startswith("application/json")
    # Igualdade exacta: o corpo tem **estas** duas chaves e mais nenhuma.
    assert _corpo(bloqueada) == {
        "code": CODIGO_CONTA_BLOQUEADA,
        "detail": DETALHE_CONTA_BLOQUEADA,
    }
    # E o corpo não devolve a conta a quem a escreveu: um email numa resposta a
    # um pedido não autenticado é reconhecimento gratuito.
    assert "ana@alfa.pt" not in bloqueada.content.decode()


def test_a_password_correta_nao_contorna_o_lockout(
    cenario: Cenario, axes_ligado: None
) -> None:
    """Depois de trancada, a conta não abre nem com as credenciais certas.

    É a asserção que separa "o lockout existe" de "o lockout funciona": o
    `AxesStandaloneBackend` é o **primeiro** dos `AUTHENTICATION_BACKENDS` e
    recusa antes de qualquer verificação de password, pelo que o
    `ModelBackend` nunca chega a ser chamado. Se a ordem dos backends se
    invertesse, este teste ficava vermelho e o anterior continuava verde.
    """
    cliente = Client()
    for _ in range(settings.AXES_FAILURE_LIMIT):
        _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": "nao-confere"})

    certas = _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})

    assert certas.status_code == 429
    assert _corpo(certas)["code"] == CODIGO_CONTA_BLOQUEADA
    assert SESSION_KEY not in cliente.session


def test_o_lockout_e_por_conta_e_nao_pela_caixa_do_email(
    cenario: Cenario, axes_ligado: None
) -> None:
    """Variar a caixa do email não reparte o contador (`config/lockout.py`).

    O axes não normaliza nada — não há um `lower()` no pacote — e sem o
    `AXES_USERNAME_CALLABLE` estas cinco tentativas davam duas chaves de três e
    de duas no `axes_accessattempt`, o `max()` do `get_failures` devolvia 3, e o
    limite de 5 nunca era atingido. O lockout deixava de existir para quem
    alternasse maiúsculas, de graça e sem esperar.
    """
    cliente = Client()
    grafias = ["ana@alfa.pt", "Ana@alfa.pt", "ANA@ALFA.PT", "ana@Alfa.pt", "AnA@aLfA.pT"]
    assert len(grafias) == settings.AXES_FAILURE_LIMIT

    respostas = [
        _post(cliente, URL_LOGIN, {"email": grafia, "password": "nao-confere"})
        for grafia in grafias
    ]

    assert [r.status_code for r in respostas[:-1]] == [400] * (len(grafias) - 1)
    assert respostas[-1].status_code == 429


# ---------------------------------------------------------------------------
# 9. Invariantes do contrato que não se vêem por HTTP
# ---------------------------------------------------------------------------
def test_o_mapa_de_status_cobre_exatamente_os_codigos_de_recusa() -> None:
    """Igualdade de conjuntos, nos dois sentidos.

    Um código sem status dava `KeyError` dentro da view — um 500 numa recusa de
    login, que é o pior sítio possível para um 500. Um status a mais descrevia um
    código que não existe, e o próximo leitor acreditava nele.
    """
    assert set(STATUS_DA_RECUSA) == set(CODIGOS_DE_RECUSA)


def test_o_corpo_de_uma_recusa_tem_exatamente_os_campos_declarados(
    cenario: Cenario,
) -> None:
    """O corpo é construído à mão e o schema é declarado à parte: fecha-se aqui.

    O `ErroOutSerializer` existe só para entrar no `schema.yml` — as recusas são
    `Response({"code": ..., "detail": ...})` escritas à mão, como as do
    `TenantMiddleware`. São portanto dois sítios a descrever a mesma forma, e
    este teste é o que os mantém de acordo: um campo acrescentado ao serializer
    sem sair na resposta prometia ao cliente gerado um campo que nunca chega.

    As duas recusas de hoje, porque são caminhos diferentes (400 do service do
    login, 403 do da troca de estabelecimento).
    """
    declarados = set(ErroOutSerializer().fields)
    assert declarados == {"code", "detail"}

    credenciais = _post(
        Client(), URL_LOGIN, {"email": "ana@alfa.pt", "password": "nao-confere"}
    )
    tenant = _post(
        _entrar("ana@alfa.pt"), URL_TENANT_ATIVO, {"tenant_id": str(cenario.beta.id)}
    )

    assert set(_corpo(credenciais)) == declarados
    assert set(_corpo(tenant)) == declarados


def test_se_a_descoberta_falhar_a_sessao_e_descartada(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Se a descoberta falhar, a view faz `flush()`" (ADR 0007), e aqui falha.

    Nunca fica uma sessão autenticada com um estabelecimento que não se
    confirmou: sem o `flush`, o `login()` já tinha escrito a sessão e o
    utilizador ficava com uma sessão válida num estado que ninguém desenhou —
    autenticado, sem âmbito, e sem forma de o obter a não ser voltar a entrar.
    """
    from apps.accounts import services

    def explode(user: User) -> tuple[Any, ...]:
        raise RuntimeError("a base de dados desapareceu a meio da descoberta")

    monkeypatch.setattr(services, "_tenants_confirmados", explode)
    cliente = Client(raise_request_exception=False)

    resposta = _post(cliente, URL_LOGIN, {"email": "ana@alfa.pt", "password": CREDENCIAL_VALIDA})

    assert resposta.status_code == 500
    assert SESSION_KEY not in cliente.session
    assert SESSION_TENANT_KEY not in cliente.session


def test_o_membership_de_outro_tenant_nunca_aparece_na_resposta(
    cenario: Cenario,
) -> None:
    """A RLS por baixo do login, medida no corpo da resposta.

    A Ana entra e a resposta não pode conter nada de Beta — nem o nome, nem o
    uuid. Não há filtro em código nenhum a garanti-lo: o nome do tenant é lido
    dentro de `tenant_scope(Alfa)`, onde a linha de Beta não é legível.
    """
    conteudo = _entrar("ana@alfa.pt").get(URL_SESSAO).content.decode()

    assert "Café Beta" not in conteudo
    assert str(cenario.beta.id) not in conteudo
    assert "Carla" not in conteudo


def test_o_login_nao_le_tabelas_com_politica_fora_de_ambito(cenario: Cenario) -> None:
    """O guarda de âmbito do `conftest.py` a ser usado como asserção.

    Este teste não tem `pytest.mark.sem_ambito_de_rls`, logo o guarda está
    montado: qualquer leitura do `accounts_membership` ou do `accounts_tenant`
    fora de um `tenant_scope` levantaria `LeituraSemAmbito` aqui. Está escrito à
    parte dos outros, com este nome, para que o motivo de uma falha futura seja
    legível — nos outros testes a mesma falha apareceria como "o login
    rebentou".

    E uma âncora: a descoberta tem de ter lido **alguma coisa**, senão o teste
    passava sem tocar nas tabelas que interessam.
    """
    corpo = _corpo(_entrar("carla@contabilidade.pt").get(URL_SESSAO))

    assert len(corpo["tenants"]) == 2
    with tenant_scope(cenario.alfa.id):
        assert Membership.objects.filter(user=cenario.carla).exists()


def test_os_estados_da_sessao_sao_exatamente_os_quatro_de_hoje() -> None:
    """Lista fechada: um estado novo é uma mudança de contrato, e aparece no diff.

    O `estado` viaja no enum do OpenAPI, logo o `types.ts` commitado carrega a
    união e o `switch` do frontend deixa de poder esquecer um ramo. Um valor
    acrescentado aqui sem o frontend saber quebra o gate de diff do CI — que é o
    efeito desejado — e um valor que **nada** produz é uma promessa que ninguém
    cumpre, que é o motivo de não existir um `mfa_pendente` ainda.
    """
    assert [e.value for e in EstadoDaSessao] == [
        "anonimo",
        "sem_estabelecimento",
        "escolha_pendente",
        "ativa",
    ]


def test_o_estado_ativa_implica_tenant_ativo_e_o_inverso(cenario: Cenario) -> None:
    """O invariante que o frontend vai assumir, afirmado nos quatro estados.

    `estado == "ativa"` se e só se `tenant_ativo != null`. Sem isto, o cliente
    tinha de verificar as duas coisas em cada ecrã — e um dia verificava só uma.
    """
    observados: dict[str, bool] = {}
    for email in ("bruno@sem-pertenca.pt", "carla@contabilidade.pt", "ana@alfa.pt"):
        corpo = _corpo(_entrar(email).get(URL_SESSAO))
        observados[corpo["estado"]] = corpo["tenant_ativo"] is not None
    observados[EstadoDaSessao.ANONIMO] = (
        _corpo(Client().get(URL_SESSAO))["tenant_ativo"] is not None
    )

    assert observados == {
        EstadoDaSessao.ANONIMO: False,
        EstadoDaSessao.SEM_ESTABELECIMENTO: False,
        EstadoDaSessao.ESCOLHA_PENDENTE: False,
        EstadoDaSessao.ATIVA: True,
    }
