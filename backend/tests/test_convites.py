"""Convites e activação, ponta a ponta (ADR 0010).

Este ficheiro existe para medir três coisas que não se vêem por revisão, e todas
as outras asserções são acessórias a elas.

**1. O uuid do link é argumento e não credencial.** A tabela dos convites tem
política de RLS normal, e quem a lê é a activação, de dentro do
`tenant_scope(uuid que vem do link)`. A prova de que isto funciona é dupla: um
uuid forjado dá zero linhas lidas (`test_um_uuid_forjado_le_zero_linhas...`) e a
recusa é **indistinguível** das outras quatro
(`test_as_seis_recusas_de_activacao_sao_indistinguiveis`).

**2. A ordem das leituras fecha um oráculo de enumeração.** Casa-se o convite
primeiro; o nome do estabelecimento só aparece numa resposta **depois** de a
pertença existir. Sem isso, um uuid adivinhado devolvia "foste convidado para a
Pastelaria Alfa" sem token nenhum — e qualquer pessoa com um script enumerava a
lista de clientes do StockFlow. O teste é
`test_nenhuma_recusa_revela_o_nome_do_estabelecimento`.

**3. A aceitação nunca define password numa conta que já tem uma.** A password é
global e a pertença é por tenant, pelo que "convite + definir password" dava a
quem pode convidar a tomada de uma conta existente, com os outros
estabelecimentos dela lá dentro. O teste que falha se alguém inverter isto é o
`test_aceitar_com_a_propria_sessao_nao_toca_na_password`, e ele não se contenta
com comparar hashes: entra na conta com a password **antiga** no fim.

## Porque é que todos levam `transactional_db`

O mesmo motivo do `tests/test_rls_isolation.py` e do `test_autenticacao.py`: com
a transação do pytest-django por fora, o `set_config('app.tenant_id', ..., true)`
que o `tenant_scope` corre só reverte no fim **dela**, e não no fim do bloco
`with`. As asserções sobre o que se vê fora de âmbito passariam a medir um âmbito
ainda aberto.

## O guarda de âmbito do `conftest.py` está a trabalhar neste ficheiro

Nenhum teste aqui tem a marca `sem_ambito_de_rls`, logo o guarda está montado e
levanta se alguma query tocar no `accounts_invitation`, no `accounts_membership`
ou no `accounts_tenant` fora de um âmbito que a alcance. Isso torna **cada**
activação deste ficheiro uma afirmação de que o convite é lido dentro do âmbito
que o link escolheu — a propriedade central da ADR 0010 — em vez de uma leitura
sem âmbito que devolveria zero linhas em silêncio.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache
from django.db import IntegrityError, connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.middleware import CODIGO_SEM_SESSAO, SESSION_TENANT_KEY
from apps.accounts.models import (
    EstadoDoConvite,
    Invitation,
    Membership,
    Papel,
    Tenant,
    User,
)
from apps.accounts.selectors import membership_no_ambito
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    CODIGO_CONVITE_DE_OUTRA_CONTA,
    CODIGO_CONVITE_EXIGE_SESSAO,
    CODIGO_CONVITE_INVALIDO,
    CODIGO_CONVITE_NAO_PENDENTE,
    CODIGOS_DE_RECUSA_DE_CONVITE,
    LIMITE_DO_FRAGMENTO,
    VALIDADE_DO_CONVITE,
    conceder_pertenca,
    criar_convite,
    criar_tenant,
)
from apps.accounts.views import STATUS_DA_RECUSA_DE_CONVITE
from apps.shared.db import tenant_scope

URL_CONVITES = "/api/v1/convites"
URL_ATIVAR = "/api/v1/auth/ativar"
URL_LOGIN = "/api/v1/auth/login"
URL_SESSAO = "/api/v1/auth/sessao"

#: A password das contas do cenário, e a que quem activa escolhe. Não se chama
#: `PASSWORD` pela razão escrita no comando `criar_estabelecimento`: o `S105` do
#: ruff trata um literal atribuído a um nome com "password" dentro como
#: credencial em código, e esta casa não tem supressões de lint.
CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"
CREDENCIAL_NOVA = "farinha-de-centeio-e-mel-42"

#: Curta e só dígitos: falha em três dos quatro `AUTH_PASSWORD_VALIDATORS`.
CREDENCIAL_FRACA = "12345"

#: O backend vai explícito no `force_login`: sem ele o Django escolhe o primeiro
#: dos `AUTHENTICATION_BACKENDS`, que é o `AxesStandaloneBackend`, cujo `get_user`
#: herdado devolve `None` — a sessão ficava escrita e o pedido seguinte vinha
#: anónimo.
BACKEND = BACKEND_DE_SESSAO


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos e seis contas, uma por situação que interessa."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa: a única que pode convidar.
    ana: User
    #: `manager` em Alfa: não pode convidar, e é o teste do papel.
    bento: User
    #: `owner` em Beta: serve o isolamento entre estabelecimentos e o caso de
    #: quem aceita um convite **já** com sessão e estabelecimento ativo noutro.
    dinis: User
    #: Conta com password **utilizável** e sem pertença em Alfa. É a conta que a
    #: activação nunca pode tocar.
    elsa: User
    #: Conta sem password utilizável, como a que um convite anterior ou o
    #: `criar_estabelecimento` deixam. Esta a activação completa.
    fabio: User
    #: `is_active = False`.
    gina: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo.

    Sem isto, o `AnonRateThrottle` de 60/min acumula entre testes do mesmo
    processo — e este ficheiro faz muitos pedidos anónimos à activação — e um
    teste começa a falhar por causa dos que correram antes.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    bento = User.objects.create_user("bento@alfa.pt", CREDENCIAL_VALIDA)
    dinis = User.objects.create_user("dinis@beta.pt", CREDENCIAL_VALIDA)
    elsa = User.objects.create_user("elsa@externa.pt", CREDENCIAL_VALIDA)
    # `password=None` deixa a conta com password inutilizável, que é como um
    # convite a cria (ver o `UserManager`).
    fabio = User.objects.create_user("fabio@externa.pt")
    gina = User.objects.create_user("gina@externa.pt", CREDENCIAL_VALIDA, is_active=False)

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
        conceder_pertenca(
            user=bento, tenant_id=alfa.id, role=Papel.MANAGER, display_name="Bento Dias"
        )
    with tenant_scope(beta.id):
        conceder_pertenca(
            user=dinis, tenant_id=beta.id, role=Papel.OWNER, display_name="Dinis Lima"
        )

    return Cenario(
        alfa=alfa,
        beta=beta,
        ana=ana,
        bento=bento,
        dinis=dinis,
        elsa=elsa,
        fabio=fabio,
        gina=gina,
    )


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _cliente(user: User | None = None, tenant_id: UUID | None = None, **kwargs: Any) -> Client:
    """Um cliente, com (ou sem) sessão e com (ou sem) estabelecimento ativo."""
    cliente = Client(**kwargs)
    if user is not None:
        cliente.force_login(user, backend=BACKEND)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


def _post(cliente: Client, url: str, corpo: dict[str, Any] | None = None) -> Any:
    """`POST` com corpo JSON, que é o único que estas views aceitam."""
    return cliente.post(url, data=corpo or {}, content_type="application/json")


def _convidar(
    cliente: Client,
    *,
    email: str,
    papel: str = Papel.STAFF,
    nome: str = "Pessoa Convidada",
) -> Any:
    return _post(cliente, URL_CONVITES, {"email": email, "papel": papel, "nome": nome})


def _convite_criado(cenario: Cenario, **kwargs: Any) -> tuple[str, str]:
    """Cria um convite em Alfa pelo endpoint e devolve `(id, fragmento)`."""
    resposta = _convidar(_cliente(cenario.ana, cenario.alfa.id), **kwargs)
    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    return corpo["convite"]["id"], corpo["fragmento"]


def _ativar(cliente: Client, fragmento: str, password: str = "") -> Any:
    return _post(cliente, URL_ATIVAR, {"fragmento": fragmento, "password": password})


def _token_do(fragmento: str) -> str:
    return fragmento.split(".", 1)[1]


def _convite_no_ambito(tenant_id: UUID, convite_id: str) -> Invitation:
    """Lê a linha do convite dentro do âmbito — é a única forma de a ler."""
    with tenant_scope(tenant_id):
        return Invitation.objects.get(pk=convite_id)


def _expirar(tenant_id: UUID, convite_id: str) -> None:
    """Põe a validade no passado.

    Escreve por `update()` e fora de `services.py` de propósito: não há caso de
    uso que expire um convite — ele expira pela passagem do tempo —, e a
    alternativa era um `freezegun` só para isto.
    """
    with tenant_scope(tenant_id):
        Invitation.objects.filter(pk=convite_id).update(
            expires_at=timezone.now() - VALIDADE_DO_CONVITE,
            updated_at=timezone.now(),
        )


# ---------------------------------------------------------------------------
# 1. Criar, e o segredo que sai uma vez
# ---------------------------------------------------------------------------
def test_o_owner_convida_e_o_segredo_sai_uma_vez(cenario: Cenario) -> None:
    """201 com o convite **e** o fragmento, e o fragmento não volta a aparecer."""
    resposta = _convidar(
        _cliente(cenario.ana, cenario.alfa.id),
        email="nova@externa.pt",
        papel=Papel.MANAGER,
        nome="Nova Pessoa",
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["convite"]["email"] == "nova@externa.pt"
    assert corpo["convite"]["papel"] == Papel.MANAGER
    assert corpo["convite"]["nome"] == "Nova Pessoa"
    assert corpo["convite"]["estado"] == EstadoDoConvite.PENDENTE
    assert corpo["fragmento"].startswith(f"{cenario.alfa.id}.")

    # E a listagem, que é o outro sítio onde este convite aparece, não o traz.
    lista = _cliente(cenario.ana, cenario.alfa.id).get(URL_CONVITES)
    assert lista.status_code == 200
    assert _token_do(corpo["fragmento"]) not in lista.content.decode()
    assert "token" not in json.dumps(lista.json()["results"][0])


def test_o_que_a_tabela_guarda_e_o_sha256_e_nao_o_token(cenario: Cenario) -> None:
    """Quem lê a tabela — um backup, um `pg_dump`, o dono da BD — não pode usar
    nenhum convite.

    É a diferença entre guardar o token e guardar o seu hash, e sem este teste a
    afirmação ficava só no docstring do modelo.
    """
    convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")
    token = _token_do(fragmento)

    convite = _convite_no_ambito(cenario.alfa.id, convite_id)

    assert convite.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in convite.token_hash
    assert len(convite.token_hash) == 64


def test_o_fragmento_tem_o_comprimento_que_o_contrato_declara(cenario: Cenario) -> None:
    """O `LIMITE_DO_FRAGMENTO` é o `max_length` do serializer da activação.

    Sendo exato e não um teto arredondado, mexer no `BYTES_DO_TOKEN` sem mexer
    nele faria a activação recusar os seus próprios links — e esta asserção é o
    que torna isso vermelho aqui em vez de em produção.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    assert len(fragmento) == LIMITE_DO_FRAGMENTO


def test_a_validade_e_de_sete_dias(cenario: Cenario) -> None:
    convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")

    convite = _convite_no_ambito(cenario.alfa.id, convite_id)
    restante = convite.expires_at - timezone.now()

    assert VALIDADE_DO_CONVITE - restante < timezone.timedelta(minutes=1)


def test_convidar_duas_vezes_o_mesmo_email_e_recusado_por_campo(cenario: Cenario) -> None:
    """400 com a mensagem no campo `email`, e não um `code` estável.

    É uma afirmação sobre o email submetido, logo é um erro de formulário, que o
    cliente mostra ao lado do input. E não revela nada: "já existe um convite
    **neste estabelecimento**" é verdade apenas dentro do âmbito de quem
    pergunta.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    assert _convidar(cliente, email="nova@externa.pt").status_code == 201

    repetido = _convidar(cliente, email="nova@externa.pt")

    assert repetido.status_code == 400
    assert "email" in repetido.json()
    assert "code" not in repetido.json()


def test_convidar_quem_ja_e_membro_e_recusado_por_campo(cenario: Cenario) -> None:
    """O Bento já é `manager` em Alfa: convidá-lo seria mudar-lhe o papel por
    um caminho que ninguém chamaria "mudar o papel"."""
    recusa = _convidar(_cliente(cenario.ana, cenario.alfa.id), email="bento@alfa.pt")

    assert recusa.status_code == 400
    assert "email" in recusa.json()


def test_a_caixa_do_email_nao_abre_um_segundo_convite(cenario: Cenario) -> None:
    """`Nova@x.pt` e `nova@x.pt` são a mesma conta, logo são o mesmo convite."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    assert _convidar(cliente, email="nova@externa.pt").status_code == 201

    recusa = _convidar(cliente, email="NOVA@Externa.PT")

    assert recusa.status_code == 400
    assert "email" in recusa.json()


def test_o_indice_parcial_e_a_rede_por_baixo_da_verificacao(cenario: Cenario) -> None:
    """A regra em código tem uma rede na base de dados, e é ela que apanha a corrida.

    Duas chamadas simultâneas passariam as duas pela verificação em Python; o que
    impede duas linhas pendentes para o mesmo email é o
    `invitation_pendente_uniq`. Aqui a escrita é directa, a saltar o service, que
    é a única forma de medir a constraint em vez da verificação.
    """
    convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")
    original = _convite_no_ambito(cenario.alfa.id, convite_id)

    with tenant_scope(cenario.alfa.id), pytest.raises(IntegrityError):
        Invitation.objects.create(
            tenant_id=cenario.alfa.id,
            email=original.email,
            role=Papel.STAFF,
            display_name="Outra",
            token_hash="0" * 64,
            expires_at=timezone.now() + VALIDADE_DO_CONVITE,
        )


def test_depois_de_revogar_o_mesmo_email_pode_ser_convidado_outra_vez(
    cenario: Cenario,
) -> None:
    """A condição do índice parcial deixa de cobrir a linha revogada."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")

    assert _post(cliente, f"{URL_CONVITES}/{convite_id}/revogar").status_code == 200

    assert _convidar(cliente, email="nova@externa.pt").status_code == 201


# ---------------------------------------------------------------------------
# 2. Quem pode convidar, e o isolamento entre estabelecimentos
# ---------------------------------------------------------------------------
def test_um_manager_nao_convida(cenario: Cenario) -> None:
    """Convidar é só do `owner` no v1 (ADR 0010).

    É também o único mecanismo que hoje sustenta a regra "nenhum convite concede
    papel acima do de quem convida": `owner` é o papel mais alto, logo a regra é
    verdadeira por construção. Uma ordem entre papéis é a Q7 e não se inventa
    aqui.
    """
    recusa = _convidar(_cliente(cenario.bento, cenario.alfa.id), email="nova@externa.pt")

    assert recusa.status_code == 403
    with tenant_scope(cenario.alfa.id):
        assert not Invitation.objects.exists()


def test_um_anonimo_nao_alcanca_os_convites(cenario: Cenario) -> None:
    """403 `sem_sessao`, do `TenantMiddleware`, antes de a view correr.

    Os endpoints de convites **não** são dispensados de âmbito: é o default a
    funcionar, e é o que distingue esta família da activação.
    """
    for resposta in (
        Client().get(URL_CONVITES),
        _post(Client(), URL_CONVITES, {"email": "x@y.pt", "papel": "staff", "nome": "X"}),
    ):
        assert resposta.status_code == 403
        assert resposta.json()["code"] == CODIGO_SEM_SESSAO


def test_a_listagem_so_mostra_os_convites_do_estabelecimento_ativo(
    cenario: Cenario,
) -> None:
    _convite_criado(cenario, email="nova@externa.pt")
    with tenant_scope(cenario.beta.id):
        criar_convite(
            tenant_id=cenario.beta.id,
            email="outra@externa.pt",
            role=Papel.STAFF,
            display_name="Outra Pessoa",
            convidado_por=cenario.dinis,
        )

    lista = _cliente(cenario.ana, cenario.alfa.id).get(URL_CONVITES).json()

    assert lista["count"] == 1
    assert lista["results"][0]["email"] == "nova@externa.pt"
    assert "outra@externa.pt" not in json.dumps(lista)


def test_a_listagem_nao_cresce_em_queries_com_o_numero_de_convites(
    cenario: Cenario,
) -> None:
    """A asserção de N+1, e é comparativa em vez de um número fixo.

    O selector não leva `select_related` porque nada do `ConviteOutSerializer`
    atravessa uma relação — em particular o `invited_by`, que está na tabela e
    **não** no contrato. Isso é uma afirmação sobre queries, logo mede-se.

    Comparativa e não `assertNumQueries(3)`: o número absoluto inclui a sessão, o
    `accounts_user` e a pertença do middleware, e mexer em qualquer um deles
    faria falhar um teste que não é sobre eles. O que interessa é a **derivada**:
    cinco convites não custam mais queries do que um.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    _convite_criado(cenario, email="uma@externa.pt")

    with CaptureQueriesContext(connection) as com_um:
        assert cliente.get(URL_CONVITES).json()["count"] == 1

    for i in range(4):
        _convite_criado(cenario, email=f"mais{i}@externa.pt")

    with CaptureQueriesContext(connection) as com_cinco:
        assert cliente.get(URL_CONVITES).json()["count"] == 5

    assert len(com_cinco) == len(com_um), (
        "o número de queries cresceu com o número de convites: alguém pôs no "
        f"contrato um campo que atravessa uma relação ({len(com_um)} -> "
        f"{len(com_cinco)})."
    )


def test_tocar_num_convite_de_outro_estabelecimento_da_404_e_nao_403(
    cenario: Cenario,
) -> None:
    """404 porque a linha não é legível, logo não há objeto sobre o qual negar.

    403 confirmaria que aquele `id` existe em algum sítio, que é informação sobre
    outro estabelecimento. Quem produz o 404 são as duas redes: a política do
    Postgres e o `get_queryset` filtrado por `request.tenant`.
    """
    with tenant_scope(cenario.beta.id):
        alheio = criar_convite(
            tenant_id=cenario.beta.id,
            email="outra@externa.pt",
            role=Papel.STAFF,
            display_name="Outra Pessoa",
            convidado_por=cenario.dinis,
        ).convite

    cliente = _cliente(cenario.ana, cenario.alfa.id)

    for url in (
        f"{URL_CONVITES}/{alheio.id}/reenviar",
        f"{URL_CONVITES}/{alheio.id}/revogar",
    ):
        assert _post(cliente, url).status_code == 404

    # E o convite alheio ficou como estava: nem token novo, nem revogado.
    with tenant_scope(cenario.beta.id):
        depois = Invitation.objects.get(pk=alheio.id)
    assert depois.token_hash == alheio.token_hash
    assert depois.revoked_at is None


# ---------------------------------------------------------------------------
# 3. Reenviar e revogar
# ---------------------------------------------------------------------------
def test_reenviar_roda_o_token_e_invalida_o_anterior(cenario: Cenario) -> None:
    """Reenviar não deixa dois links vivos, e é essa a propriedade."""
    convite_id, primeiro = _convite_criado(cenario, email="nova@externa.pt")
    antes = _convite_no_ambito(cenario.alfa.id, convite_id)

    resposta = _post(
        _cliente(cenario.ana, cenario.alfa.id), f"{URL_CONVITES}/{convite_id}/reenviar"
    )

    assert resposta.status_code == 200
    segundo = resposta.json()["fragmento"]
    assert segundo != primeiro
    depois = _convite_no_ambito(cenario.alfa.id, convite_id)
    assert depois.token_hash != antes.token_hash
    assert depois.expires_at > antes.expires_at

    # O link antigo passa a ser um link qualquer, e o novo funciona.
    assert _ativar(Client(), primeiro, CREDENCIAL_NOVA).status_code == 400
    assert _ativar(Client(), segundo, CREDENCIAL_NOVA).status_code == 200


def test_reenviar_um_convite_expirado_e_o_caminho_previsto(cenario: Cenario) -> None:
    """Criar nunca mexe num convite que já existe: quem quer um token novo reenvia.

    É a consequência deliberada de o índice parcial não poder incluir
    `expires_at > now()` — `now()` não é imutável e o Postgres recusa-o num
    índice.
    """
    convite_id, _antigo = _convite_criado(cenario, email="nova@externa.pt")
    _expirar(cenario.alfa.id, convite_id)
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    assert _convidar(cliente, email="nova@externa.pt").status_code == 400

    resposta = _post(cliente, f"{URL_CONVITES}/{convite_id}/reenviar")

    assert resposta.status_code == 200
    assert _ativar(Client(), resposta.json()["fragmento"], CREDENCIAL_NOVA).status_code == 200


def test_revogar_impede_a_activacao(cenario: Cenario) -> None:
    convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    revogado = _post(
        _cliente(cenario.ana, cenario.alfa.id), f"{URL_CONVITES}/{convite_id}/revogar"
    )

    assert revogado.status_code == 200
    assert revogado.json()["estado"] == EstadoDoConvite.REVOGADO
    assert _ativar(Client(), fragmento, CREDENCIAL_NOVA).status_code == 400
    assert not User.objects.filter(email="nova@externa.pt").exists()


def test_revogar_e_idempotente(cenario: Cenario) -> None:
    """Um duplo clique no botão não é um erro."""
    convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    url = f"{URL_CONVITES}/{convite_id}/revogar"

    primeira = _post(cliente, url)
    segunda = _post(cliente, url)

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert primeira.json() == segunda.json()


def test_um_convite_revogado_nao_ressuscita(cenario: Cenario) -> None:
    """Revogar é final: quem quer convidar outra vez cria um convite novo."""
    convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    assert _post(cliente, f"{URL_CONVITES}/{convite_id}/revogar").status_code == 200

    recusa = _post(cliente, f"{URL_CONVITES}/{convite_id}/reenviar")

    assert recusa.status_code == 409
    assert recusa.json()["code"] == CODIGO_CONVITE_NAO_PENDENTE


def test_um_convite_aceite_nao_se_reenvia_nem_se_revoga(cenario: Cenario) -> None:
    """Revogar um convite aceite daria a impressão de ter cortado um acesso que
    continuava lá — a pior forma de falhar que uma operação de segurança tem.

    Quem retira o acesso é o `revogar_pertenca`, e a mensagem do 409 di-lo.
    """
    convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")
    assert _ativar(Client(), fragmento, CREDENCIAL_NOVA).status_code == 200
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    for operacao in ("reenviar", "revogar"):
        recusa = _post(cliente, f"{URL_CONVITES}/{convite_id}/{operacao}")
        assert recusa.status_code == 409, operacao
        assert recusa.json()["code"] == CODIGO_CONVITE_NAO_PENDENTE

    # E a pertença criada pela aceitação continua lá: nada foi desfeito.
    with tenant_scope(cenario.alfa.id):
        assert Membership.objects.filter(user__email="nova@externa.pt").exists()


# ---------------------------------------------------------------------------
# 4. Activação — o caminho feliz de uma conta nova
# ---------------------------------------------------------------------------
def test_activar_cria_a_conta_a_pertenca_e_a_sessao(cenario: Cenario) -> None:
    """Uma transação dentro do âmbito: password, `Membership` e `accepted_at`.

    E o `SessaoOut` sai com o estabelecimento já ativo, porque esta é a regra do
    login aplicada a um terceiro ponto de entrada: um candidato confirmado
    escreve-se na sessão.
    """
    convite_id, fragmento = _convite_criado(
        cenario, email="nova@externa.pt", papel=Papel.MANAGER, nome="Nova Pessoa"
    )
    cliente = Client()

    resposta = _ativar(cliente, fragmento, CREDENCIAL_NOVA)

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["estado"] == "ativa"
    assert corpo["utilizador"]["email"] == "nova@externa.pt"
    assert corpo["tenant_ativo"]["id"] == str(cenario.alfa.id)
    assert corpo["tenant_ativo"]["nome"] == "Pastelaria Alfa"
    assert corpo["tenant_ativo"]["papel"] == Papel.MANAGER

    # A sessão é real, não só uma resposta bonita.
    assert SESSION_KEY in cliente.session
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)

    # A pertença nasceu com o papel e o nome que o convite trazia.
    nova = User.objects.get_by_natural_key("nova@externa.pt")
    assert nova.has_usable_password()
    with tenant_scope(cenario.alfa.id):
        pertenca = membership_no_ambito(user_id=nova.pk, tenant_id=cenario.alfa.id)
    assert pertenca is not None
    assert pertenca.role == Papel.MANAGER
    assert pertenca.display_name == "Nova Pessoa"

    # E o convite ficou queimado.
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.ACEITE


def test_a_password_definida_na_activacao_serve_para_entrar(cenario: Cenario) -> None:
    """O fim do caminho: a conta nova entra pelo login normal."""
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")
    assert _ativar(Client(), fragmento, CREDENCIAL_NOVA).status_code == 200

    entrada = _post(
        Client(), URL_LOGIN, {"email": "nova@externa.pt", "password": CREDENCIAL_NOVA}
    )

    assert entrada.status_code == 200
    assert entrada.json()["estado"] == "ativa"


def test_uma_conta_sem_password_utilizavel_define_a_na_activacao(cenario: Cenario) -> None:
    """O Fábio existe e nunca teve password: é o estado que um convite deixa.

    Este é o outro lado da regra da password — ela só se define onde **não** há
    nenhuma, e aqui não há.
    """
    assert not cenario.fabio.has_usable_password()
    _convite_id, fragmento = _convite_criado(cenario, email="fabio@externa.pt")

    resposta = _ativar(Client(), fragmento, CREDENCIAL_NOVA)

    assert resposta.status_code == 200
    cenario.fabio.refresh_from_db()
    assert cenario.fabio.has_usable_password()
    assert cenario.fabio.check_password(CREDENCIAL_NOVA)


def test_o_token_e_de_uso_unico(cenario: Cenario) -> None:
    """A segunda activação do mesmo link dá a recusa genérica.

    O que faz o uso único não é a verificação em Python: é o `UPDATE ... WHERE
    accepted_at IS NULL`, que o Postgres serializa.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")
    assert _ativar(Client(), fragmento, CREDENCIAL_NOVA).status_code == 200

    segunda = _ativar(Client(), fragmento, CREDENCIAL_NOVA)

    assert segunda.status_code == 400
    assert segunda.json()["code"] == CODIGO_CONVITE_INVALIDO


def test_aceitar_um_convite_nao_troca_o_estabelecimento_ativo(cenario: Cenario) -> None:
    """Quem já estava a trabalhar num estabelecimento continua lá.

    Escolher por ele seria escolher em nome de quem tem de escolher (ADR 0007). O
    estabelecimento novo aparece na lista de candidatos, e a troca é um POST
    explícito ao `tenant-ativo`.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="dinis@beta.pt")
    cliente = _cliente(cenario.dinis, cenario.beta.id)

    resposta = _ativar(cliente, fragmento)

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["tenant_ativo"]["id"] == str(cenario.beta.id)
    assert {t["nome"] for t in corpo["tenants"]} == {"Café Beta", "Pastelaria Alfa"}
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.beta.id)


# ---------------------------------------------------------------------------
# 5. A regra da password, que é a que não se negocia
# ---------------------------------------------------------------------------
def test_um_email_ja_registado_exige_entrar_primeiro(cenario: Cenario) -> None:
    """409 `convite_exige_sessao`, e **nada** é escrito.

    A Elsa tem uma conta com password utilizável. Se a activação a aceitasse com
    uma password do corpo, quem pode convidar tomava a conta dela — com os outros
    estabelecimentos dela lá dentro.
    """
    convite_id, fragmento = _convite_criado(cenario, email="elsa@externa.pt")
    hash_antes = cenario.elsa.password

    recusa = _ativar(Client(), fragmento, "password-escolhida-pelo-atacante-9")

    assert recusa.status_code == 409
    assert recusa.json()["code"] == CODIGO_CONVITE_EXIGE_SESSAO
    cenario.elsa.refresh_from_db()
    assert cenario.elsa.password == hash_antes
    with tenant_scope(cenario.alfa.id):
        assert membership_no_ambito(user_id=cenario.elsa.pk, tenant_id=cenario.alfa.id) is None
    # E o convite **não** foi queimado: a Elsa ainda o pode aceitar como deve ser.
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.PENDENTE


def test_a_sessao_de_outra_conta_e_recusada(cenario: Cenario) -> None:
    """403 `convite_de_outra_conta`: nunca uma concessão à conta errada.

    A Ana está autenticada e abre o link que foi enviado à Elsa. A pertença que
    este convite cria é para o email do convite e para mais nenhum.
    """
    convite_id, fragmento = _convite_criado(cenario, email="elsa@externa.pt")

    recusa = _ativar(_cliente(cenario.ana, cenario.alfa.id), fragmento, CREDENCIAL_NOVA)

    assert recusa.status_code == 403
    assert recusa.json()["code"] == CODIGO_CONVITE_DE_OUTRA_CONTA
    cenario.elsa.refresh_from_db()
    assert cenario.elsa.check_password(CREDENCIAL_VALIDA)
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.PENDENTE


def test_aceitar_com_a_propria_sessao_nao_toca_na_password(cenario: Cenario) -> None:
    """**O teste que falha se alguém inverter a regra da password.**

    A Elsa entra com a password dela, abre o link, e o corpo do POST leva uma
    password diferente — que é exactamente o que um cliente ingénuo enviaria, e
    exactamente o que um atacante enviaria. O convite é aceite, a pertença nasce,
    e a password **não muda**.

    Três asserções, e as três são necessárias: o hash é o mesmo (prova que não
    houve `set_password`), a password nova **não** serve para entrar (prova que o
    hash não foi substituído por outro equivalente), e a antiga serve (prova que
    a conta não ficou inutilizável). Sem a terceira, um `set_unusable_password`
    acidental passava.
    """
    convite_id, fragmento = _convite_criado(
        cenario, email="elsa@externa.pt", papel=Papel.STAFF, nome="Elsa (contabilidade)"
    )
    hash_antes = cenario.elsa.password
    cliente = _cliente(cenario.elsa)

    resposta = _ativar(cliente, fragmento, "password-escolhida-pelo-atacante-9")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["estado"] == "ativa"

    cenario.elsa.refresh_from_db()
    assert cenario.elsa.password == hash_antes, "a activação redefiniu a password"
    assert not cenario.elsa.check_password("password-escolhida-pelo-atacante-9")
    assert cenario.elsa.check_password(CREDENCIAL_VALIDA)

    # E o login com a password **antiga** continua a funcionar, que é a forma de
    # medir isto por fora em vez de por dentro.
    entrada = _post(
        Client(), URL_LOGIN, {"email": "elsa@externa.pt", "password": CREDENCIAL_VALIDA}
    )
    assert entrada.status_code == 200

    # A pertença nasceu, com o nome e o papel do convite.
    with tenant_scope(cenario.alfa.id):
        pertenca = membership_no_ambito(user_id=cenario.elsa.pk, tenant_id=cenario.alfa.id)
    assert pertenca is not None
    assert pertenca.display_name == "Elsa (contabilidade)"
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.ACEITE


def test_a_sessao_de_outra_conta_nao_bloqueia_uma_conta_sem_credencial(
    cenario: Cenario,
) -> None:
    """A assimetria dos dois ramos, medida — e é uma decisão, não um acidente.

    O Fábio existe **sem** password utilizável, e quem abre o link do convite
    dele tem a sessão da Ana. Ao contrário do caso da Elsa, isto é aceite: a
    recusa `convite_de_outra_conta` existe para proteger uma credencial que já
    existe, e aqui não existe nenhuma — quem tem o link está a estabelecer a
    identidade, não a assumir uma.

    A consequência é que a sessão passa a ser a do Fábio: o `login()` do Django
    faz `flush()` à sessão anterior quando é outra conta, que é o mesmo
    comportamento do `POST /auth/login` (ver o docstring da `LoginView`). Sem
    isto, alguém num computador partilhado com a sessão de outra pessoa aberta
    ficava sem forma de aceitar o seu próprio convite.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="fabio@externa.pt")
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = _ativar(cliente, fragmento, CREDENCIAL_NOVA)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["utilizador"]["email"] == "fabio@externa.pt"
    cenario.fabio.refresh_from_db()
    assert cenario.fabio.check_password(CREDENCIAL_NOVA)
    # E a sessão deixou de ser a da Ana, em vez de ficarem as duas misturadas.
    assert cliente.session[SESSION_KEY] == str(cenario.fabio.pk)


def test_uma_conta_inativa_leva_a_recusa_generica(cenario: Cenario) -> None:
    """Activar dava pertença a uma conta que não consegue entrar.

    E a recusa é a genérica: dizer ao portador do link que a conta está
    desativada não lhe serve para nada e é informação sobre uma conta que não é
    dele.
    """
    convite_id, fragmento = _convite_criado(cenario, email="gina@externa.pt")

    recusa = _ativar(Client(), fragmento, CREDENCIAL_NOVA)

    assert recusa.status_code == 400
    assert recusa.json()["code"] == CODIGO_CONVITE_INVALIDO
    with tenant_scope(cenario.alfa.id):
        assert membership_no_ambito(user_id=cenario.gina.pk, tenant_id=cenario.alfa.id) is None
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.PENDENTE


# ---------------------------------------------------------------------------
# 6. O oráculo de enumeração, fechado nas duas pontas
# ---------------------------------------------------------------------------
def _recusas_de_activacao(cenario: Cenario) -> dict[str, Any]:
    """As seis formas de um link não servir, cada uma com a sua resposta."""
    _id_usado, usado = _convite_criado(cenario, email="usada@externa.pt")
    assert _ativar(Client(), usado, CREDENCIAL_NOVA).status_code == 200

    id_expirado, expirado = _convite_criado(cenario, email="expirada@externa.pt")
    _expirar(cenario.alfa.id, id_expirado)

    id_revogado, revogado = _convite_criado(cenario, email="revogada@externa.pt")
    assert (
        _post(
            _cliente(cenario.ana, cenario.alfa.id),
            f"{URL_CONVITES}/{id_revogado}/revogar",
        ).status_code
        == 200
    )

    _id_vivo, vivo = _convite_criado(cenario, email="viva@externa.pt")
    token_vivo = _token_do(vivo)

    return {
        "usado": usado,
        "expirado": expirado,
        "revogado": revogado,
        # O token é real, o estabelecimento é inventado: é o uuid forjado.
        "uuid_forjado": f"{uuid4()}.{token_vivo}",
        # O estabelecimento é real, o token não existe.
        "token_inexistente": f"{cenario.alfa.id}.{'z' * 43}",
        "fragmento_mal_formado": "isto-nao-tem-separador-nenhum",
    }


def test_as_seis_recusas_de_activacao_sao_indistinguiveis(cenario: Cenario) -> None:
    """**Um** código e **um** corpo para as seis.

    É a propriedade que impede um estranho com um link de descobrir se aquele
    estabelecimento existe, se o convite já foi usado, se foi revogado ou se
    apenas expirou. O que a garante não é disciplina a escrever o mesmo literal
    seis vezes: é o `_convite_invalido()` dos services, uma função que os seis
    caminhos levantam.
    """
    respostas = {
        nome: _ativar(Client(), fragmento, CREDENCIAL_NOVA)
        for nome, fragmento in _recusas_de_activacao(cenario).items()
    }

    assert {nome: r.status_code for nome, r in respostas.items()} == dict.fromkeys(
        respostas, 400
    )
    corpos = {json.dumps(r.json(), sort_keys=True) for r in respostas.values()}
    assert len(corpos) == 1, f"as recusas são distinguíveis pelo corpo: {corpos}"
    assert json.loads(corpos.pop())["code"] == CODIGO_CONVITE_INVALIDO


def test_nenhuma_recusa_revela_o_nome_do_estabelecimento(cenario: Cenario) -> None:
    """O oráculo de enumeração de clientes, fechado pela **ordem das leituras**.

    Casa-se o convite primeiro, e o nome do estabelecimento só é lido depois de a
    pertença existir — pelo caminho normal da sessão, dentro do âmbito de cada
    candidato. Se alguém trocar a ordem (ou puser um `select_related("tenant")`
    no selector do convite e usar o nome na mensagem), um uuid adivinhado passa a
    responder "foste convidado para a Pastelaria Alfa" sem token nenhum.
    """
    fragmentos = _recusas_de_activacao(cenario)
    fragmentos["exige_sessao"] = _convite_criado(cenario, email="elsa@externa.pt")[1]

    for nome, fragmento in fragmentos.items():
        conteudo = _ativar(Client(), fragmento, CREDENCIAL_NOVA).content.decode()
        assert "Pastelaria Alfa" not in conteudo, nome
        assert "Café Beta" not in conteudo, nome
        assert str(cenario.alfa.id) not in conteudo, nome


def test_um_uuid_forjado_le_zero_linhas_no_ambito_que_escolheu(cenario: Cenario) -> None:
    """A outra metade: não é só a resposta que não diz nada — não há leitura.

    O uuid do link é **argumento e não credencial**. Forjá-lo escolhe um âmbito
    onde nenhum `token_hash` existe, e a política devolve zero linhas sem erro.
    Nenhuma linha do convite real é lida no caminho, nem para ser descartada
    depois em Python — que é a mesma propriedade que o
    `test_a_query_do_middleware_devolve_zero_linhas_no_ambito_forjado` prova para
    a sessão.
    """
    _convite_id, _fragmento = _convite_criado(cenario, email="nova@externa.pt")
    forjado = uuid4()

    with tenant_scope(forjado):
        assert Invitation.objects.count() == 0
        assert not Invitation.objects.exists()

    # E dentro do âmbito certo o convite existe — senão o zero acima não dizia
    # nada sobre a política.
    with tenant_scope(cenario.alfa.id):
        assert Invitation.objects.count() == 1


def test_um_convite_de_outro_estabelecimento_nao_se_activa_com_o_uuid_proprio(
    cenario: Cenario,
) -> None:
    """Trocar o uuid do link pelo de outro estabelecimento não transporta o convite.

    É a tentativa óbvia contra este desenho: tenho um token de Beta, ponho o uuid
    de Alfa. O `token_hash` de Beta não é visível no âmbito de Alfa, logo a
    leitura devolve zero linhas e a recusa é a genérica.
    """
    with tenant_scope(cenario.beta.id):
        criado = criar_convite(
            tenant_id=cenario.beta.id,
            email="nova@externa.pt",
            role=Papel.OWNER,
            display_name="Nova Pessoa",
            convidado_por=cenario.dinis,
        )

    trocado = f"{cenario.alfa.id}.{_token_do(criado.fragmento)}"
    recusa = _ativar(Client(), trocado, CREDENCIAL_NOVA)

    assert recusa.status_code == 400
    assert recusa.json()["code"] == CODIGO_CONVITE_INVALIDO
    assert not User.objects.filter(email="nova@externa.pt").exists()

    # E o convite verdadeiro, com o uuid verdadeiro, funciona: o teste acima não
    # passou por o convite estar quebrado.
    assert _ativar(Client(), criado.fragmento, CREDENCIAL_NOVA).status_code == 200


# ---------------------------------------------------------------------------
# 7. A password de quem activa, e o convite que não se queima por nada
# ---------------------------------------------------------------------------
def test_uma_password_fraca_da_400_por_campo_e_nao_queima_o_convite(
    cenario: Cenario,
) -> None:
    """A validação corre **antes** da marca de aceite, e é por isso que o link sobrevive.

    Se fosse ao contrário, quem escrevesse uma password curta na primeira
    tentativa ficava sem forma de entrar — e sem forma de pedir outro convite,
    porque o que ele tem é um link.
    """
    convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    recusa = _ativar(Client(), fragmento, CREDENCIAL_FRACA)

    assert recusa.status_code == 400
    assert "password" in recusa.json()
    assert "code" not in recusa.json()
    assert _convite_no_ambito(cenario.alfa.id, convite_id).estado == EstadoDoConvite.PENDENTE

    # E com uma password que passa, o mesmo link funciona.
    assert _ativar(Client(), fragmento, CREDENCIAL_NOVA).status_code == 200


def test_sem_password_numa_conta_nova_da_400_por_campo(cenario: Cenario) -> None:
    """Quem decide que a password é obrigatória é o servidor, depois de casar o
    convite: o serializer não pode saber que email está em jogo."""
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    recusa = _ativar(Client(), fragmento)

    assert recusa.status_code == 400
    assert "password" in recusa.json()


def test_um_corpo_sem_fragmento_da_400_por_campo(cenario: Cenario) -> None:
    """A validação de forma é do serializer, e sai por campo."""
    recusa = _post(Client(), URL_ATIVAR, {"password": CREDENCIAL_NOVA})

    assert recusa.status_code == 400
    assert "fragmento" in recusa.json()


# ---------------------------------------------------------------------------
# 8. CSRF — a activação é um endpoint anónimo de escrita (SECURITY.md §5)
# ---------------------------------------------------------------------------
def test_a_activacao_sem_token_de_csrf_e_recusada(cenario: Cenario) -> None:
    """As duas metades, porque uma só não prova nada.

    O `as_view()` do DRF embrulha a view em `csrf_exempt` e o
    `SessionAuthentication` só verifica o token quando **encontra** um utilizador
    na sessão. A activação de uma conta nova é anónima por definição, logo nasceria
    sem protecção de CSRF nenhuma — e o que um atacante consegue com isso é fazer
    o browser de quem tem o link queimar um token de uso único, ou aceitar com a
    conta da vítima um convite para um estabelecimento dele.

    Sem a segunda metade, este teste passava com o CSRF desligado e uma qualquer
    outra recusa a dar o 403. **Um endpoint dispensado de âmbito dispensa-se do
    âmbito e não do CSRF.**
    """
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")
    cliente = Client(enforce_csrf_checks=True)

    sem_token = _ativar(cliente, fragmento, CREDENCIAL_NOVA)

    assert sem_token.status_code == 403
    assert not User.objects.filter(email="nova@externa.pt").exists()

    # A mesma chamada, com o token que o `GET /auth/sessao` devolve: 200.
    cliente.get(URL_SESSAO)
    token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
    com_token = cliente.post(
        URL_ATIVAR,
        data={"fragmento": fragmento, "password": CREDENCIAL_NOVA},
        content_type="application/json",
        headers={"x-csrftoken": token},
    )

    assert com_token.status_code == 200, com_token.content


def test_criar_um_convite_sem_token_de_csrf_e_recusado(cenario: Cenario) -> None:
    """Aqui o controlo já vinha do `SessionAuthentication` — e mede-se de qualquer forma.

    Num pedido autenticado o DRF **encontra** o utilizador na sessão e verifica o
    token por si, pelo que este endpoint não tinha o buraco do anónimo. A
    asserção existe porque "é autenticado, logo está coberto" é exactamente o
    tipo de raciocínio que deixou o login sem CSRF.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id, enforce_csrf_checks=True)

    sem_token = _convidar(cliente, email="nova@externa.pt")

    assert sem_token.status_code == 403
    with tenant_scope(cenario.alfa.id):
        assert not Invitation.objects.exists()

    cliente.get(URL_SESSAO)
    com_token = cliente.post(
        URL_CONVITES,
        data={"email": "nova@externa.pt", "papel": Papel.STAFF, "nome": "Nova"},
        content_type="application/json",
        headers={"x-csrftoken": cliente.cookies[settings.CSRF_COOKIE_NAME].value},
    )

    assert com_token.status_code == 201, com_token.content


def test_um_corpo_form_encoded_nao_chega_as_views(cenario: Cenario) -> None:
    """415, e é a via que não precisa de token de CSRF para ser disparada.

    Um `<form>` numa página de outro domínio faz `POST` de `multipart/form-data`
    sem preflight de CORS; um corpo `application/json` não. O `JSONParser`
    sozinho fecha essa via antes de qualquer código nosso correr.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    resposta = Client().post(
        URL_ATIVAR, data={"fragmento": fragmento, "password": CREDENCIAL_NOVA}
    )

    assert resposta.status_code == 415


# ---------------------------------------------------------------------------
# 9. Invariantes do contrato que não se vêem por HTTP
# ---------------------------------------------------------------------------
def test_o_mapa_de_status_cobre_exatamente_os_codigos_de_recusa_de_convite() -> None:
    """Nos dois sentidos: um código sem status dava `KeyError` (500 numa recusa),
    e um status a mais ficava a descrever um código que não existe."""
    assert set(STATUS_DA_RECUSA_DE_CONVITE) == set(CODIGOS_DE_RECUSA_DE_CONVITE)


def test_os_status_dos_tres_codigos_que_a_adr_fixa_sao_os_que_ela_fixa() -> None:
    """A ADR 0010 e o pedido da feature fixam estes três pares. Ficam medidos."""
    assert STATUS_DA_RECUSA_DE_CONVITE[CODIGO_CONVITE_INVALIDO] == 400
    assert STATUS_DA_RECUSA_DE_CONVITE[CODIGO_CONVITE_EXIGE_SESSAO] == 409
    assert STATUS_DA_RECUSA_DE_CONVITE[CODIGO_CONVITE_DE_OUTRA_CONTA] == 403


def test_os_estados_de_um_convite_sao_exatamente_os_quatro_de_hoje() -> None:
    """Lista fechada: o `estado` viaja como enum no OpenAPI, logo o `types.ts`
    commitado carrega a união e o `switch` do frontend não pode esquecer um ramo.

    Um valor acrescentado aqui sem o frontend saber quebra o gate de diff do CI,
    que é o efeito desejado.
    """
    assert [e.value for e in EstadoDoConvite] == [
        "pendente",
        "expirado",
        "aceite",
        "revogado",
    ]


def test_o_backend_da_sessao_da_activacao_existe_nas_settings() -> None:
    """O `login()` da activação nomeia o backend, e um nome errado só aparecia em
    runtime — num `ValueError` dentro de uma activação, que é o pior sítio."""
    assert BACKEND_DE_SESSAO in settings.AUTHENTICATION_BACKENDS


def test_a_activacao_nao_le_tabelas_com_politica_fora_de_ambito(cenario: Cenario) -> None:
    """O guarda de âmbito do `conftest.py` usado como asserção.

    Este teste não tem `pytest.mark.sem_ambito_de_rls`, logo o guarda está
    montado: qualquer leitura do `accounts_invitation`, do `accounts_membership`
    ou do `accounts_tenant` fora de um `tenant_scope` levantaria
    `LeituraSemAmbito` aqui. É a prova mais barata de que o convite é lido
    **dentro** do âmbito que o link escolheu — e está escrito à parte, com este
    nome, para que o motivo de uma falha futura seja legível.

    E uma âncora: a activação tem de ter lido **alguma coisa**, senão o teste
    passava sem tocar nas tabelas que interessam.
    """
    _convite_id, fragmento = _convite_criado(cenario, email="nova@externa.pt")

    corpo = _ativar(Client(), fragmento, CREDENCIAL_NOVA).json()

    assert corpo["tenant_ativo"]["nome"] == "Pastelaria Alfa"
    with tenant_scope(cenario.alfa.id):
        assert Invitation.objects.filter(accepted_at__isnull=False).exists()
