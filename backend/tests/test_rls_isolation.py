"""O isolamento entre tenants, provado ponta a ponta (ADR 0005 e ADR 0007).

A ADR 0005 prometeu este ficheiro para o passo 4 e a ADR 0007 deu-lhe a forma
completa. O que aqui se prova não é que o código filtra por tenant — é que **a
base de dados não devolve** as linhas do outro tenant, mesmo quando o código
não filtra nada. Por isso o endpoint de lista do harness abaixo é
deliberadamente `Membership.objects.all()`, sem `get_queryset` filtrado: se
passar, passou porque a política do Postgres o filtrou.

Isso é o oposto do que o código de produção deve fazer. O CLAUDE.md e o
SECURITY.md §1 exigem os **dois** controlos — `get_queryset` filtrado por
`request.tenant` *e* RLS — e um ViewSet real leva os dois. Aqui remove-se um
para medir o outro; é a única razão pela qual estas views existem.

## Porque é que todos os testes levam `transaction=True`

Com a transação do pytest-django por fora, o `set_config('app.tenant_id', ...,
true)` do `tenant_scope` só reverte no fim **dela**, não no fim do bloco `with`.
O GUC ficava colado ao resto do teste e as asserções de "fora de âmbito não se
vê nada" passavam a medir um âmbito ainda aberto — seriam testes vazios a dar
confiança. É a mesma razão que está escrita no `tests/test_tenant_scope.py`.

## O que a ligação é

`stockflow_app`: `NOSUPERUSER`, `NOBYPASSRLS`, dona de nenhuma tabela, sujeita à
política (ADR 0006). Quem o afirma é o `tests/test_db_roles.py` — sem essa
guarda, estes testes podiam passar pela razão errada.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection
from django.db.utils import ProgrammingError
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, path
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import (
    MembershipInfo,
    Papel,
    PertenceAoTenant,
    TemPapel,
    TenantContext,
    TenantOption,
    dispensa_declarada,
    membership_atual,
    opcao_de_tenant,
    tenant_scope_exempt,
    utilizador_atual,
)
from apps.accounts.middleware import (
    CODIGO_DESCONHECIDO,
    CODIGO_DIVERGENTE,
    CODIGO_SEM_SESSAO,
    SESSION_TENANT_KEY,
    TENANT_HEADER,
)
from apps.accounts.models import Invitation, Membership, Tenant, User
from apps.accounts.selectors import membership_no_ambito
from apps.accounts.services import conceder_pertenca, criar_tenant, revogar_pertenca
from apps.shared.db import (
    TenantScopeConflict,
    current_tenant,
    in_system_scope,
    system_scope,
    tenant_scope,
)
from apps.shared.models import OutboxEvent
from tests.conftest import LeituraSemAmbito

#: O backend tem de ir explícito no `force_login`. Sem ele o Django escolhe o
#: primeiro de `AUTHENTICATION_BACKENDS`, que é o `AxesStandaloneBackend` — e
#: esse herda o `get_user` do `BaseBackend`, que devolve `None`: a sessão ficava
#: escrita e o pedido seguinte vinha anónimo. No login a sério o problema não
#: existe, porque o backend guardado é o que **autenticou** (o `ModelBackend`).
BACKEND = "django.contrib.auth.backends.ModelBackend"

URL_LISTA = "/api/v1/testes/membros/"
URL_SEM_AMBITO = "/api/v1/testes/sem-ambito/"
URL_CONTEXTO = "/api/v1/testes/contexto/"
URL_EXPLODE = "/api/v1/testes/escreve-e-falha/"


# ---------------------------------------------------------------------------
# Harness: views que existem só para medir a RLS. Ver o docstring do módulo.
# ---------------------------------------------------------------------------
class _MembroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ["id", "display_name", "role"]


class _ListaDeMembros(generics.ListAPIView):
    """Lista **sem** filtro por tenant, de propósito.

    É um endpoint de lista e não de detalhe porque a queryset de uma lista é
    avaliada durante a **serialização**, já dentro da resposta — que é
    precisamente o ponto da ADR 0005: o âmbito tem de durar até lá.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    serializer_class = _MembroSerializer
    queryset = Membership.objects.order_by("display_name")


class _DetalheDeMembro(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, PertenceAoTenant]
    serializer_class = _MembroSerializer
    queryset = Membership.objects.order_by("display_name")


class _SoParaDonos(generics.ListAPIView):
    permission_classes = [IsAuthenticated, PertenceAoTenant, TemPapel.exige(Papel.OWNER)]
    serializer_class = _MembroSerializer
    queryset = Membership.objects.order_by("display_name")


class _Contexto(APIView):
    """Devolve o que o `accounts.api` publica no pedido, para o poder assertar."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]

    def get(self, request: Request) -> Response:
        membership = membership_atual(request)
        utilizador = utilizador_atual(request)
        assert membership is not None
        assert utilizador is not None
        return Response(
            {
                "tenant_id": str(request.tenant.id),
                "tenant_name": request.tenant.name,
                "role": request.tenant.role,
                "display_name": membership.display_name,
                "email": utilizador.email,
                "ambito_aberto": str(current_tenant()),
                "tipo_do_tenant": type(request.tenant).__name__,
            }
        )


class _EscreveEDevolve500(APIView):
    """Escreve e devolve 5xx **sem** levantar, que é o caso que o rollback cobre.

    Se a view levantasse, o `atomic` do `tenant_scope` desfazia a transação pela
    exceção e o ramo do middleware nunca corria. O DRF apanha a exceção *dentro*
    da view e devolve uma resposta: é aí que `transaction.set_rollback(True)`
    deixa de ser higiene (ADR 0005).

    Escreve por `update()` direto e num `GET` — as duas coisas são erradas em
    produção (escritas vivem em `services.py`, e um `GET` não escreve) e aqui
    são o que mantém o harness sem plumbing de CSRF.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]

    def get(self, request: Request) -> Response:
        Membership.objects.filter(tenant_id=request.tenant.id).update(
            display_name="escrito por uma view que falhou",
            updated_at=timezone.now(),
        )
        return Response({"detail": "algo correu mal"}, status=500)


@tenant_scope_exempt
class _SemAmbito(APIView):
    """Dispensada de âmbito, e não ganha nenhum por acidente."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        ativo = current_tenant()
        return Response(
            {
                "ambito_aberto": None if ativo is None else str(ativo),
                "tem_tenant_no_request": hasattr(request, "tenant"),
            }
        )


urlpatterns = [
    path("api/v1/testes/membros/", _ListaDeMembros.as_view()),
    path("api/v1/testes/membros/<uuid:pk>/", _DetalheDeMembro.as_view()),
    path("api/v1/testes/donos/", _SoParaDonos.as_view()),
    path("api/v1/testes/contexto/", _Contexto.as_view()),
    path("api/v1/testes/escreve-e-falha/", _EscreveEDevolve500.as_view()),
    path("api/v1/testes/sem-ambito/", _SemAmbito.as_view()),
]

#: Aponta a resolução de URLs para este módulo. O `ROOT_URLCONF` de produção não
#: tem endpoints de domínio ainda, e inventar um em `apps/accounts/views.py` para
#: medir a RLS seria enviar código de teste para produção.
com_urls_do_harness = override_settings(ROOT_URLCONF=__name__)


# ---------------------------------------------------------------------------
# Cenário: dois tenants, um membro em cada
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    alfa: Tenant
    beta: Tenant
    ana: User
    bruno: User
    carla: User
    pertenca_de_ana: UUID
    pertenca_de_bruno: UUID


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo.

    Sem isto, o `AnonRateThrottle` de 60/min acumula entre testes do mesmo
    processo e um teste começa a falhar por causa dos que correram antes.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """Dois tenants com uma pertença cada, e uma terceira pessoa sem nenhuma.

    Tudo pelas funções de `apps/accounts/services.py`: é o que prova, de
    passagem, que criar um tenant de dentro do âmbito do próprio uuid funciona —
    e é a única forma de o fazer com a política a comparar `id`.
    """
    # Sem password: nenhum destes testes autentica por credenciais (o
    # `force_login` escreve a sessão diretamente) e `password=None` deixa a
    # conta com password inutilizável, que é como um convite a cria.
    ana = User.objects.create_user(email="ana@alfa.pt")
    bruno = User.objects.create_user(email="bruno@beta.pt")
    carla = User.objects.create_user(email="carla@contabilidade.pt")

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        pertenca_de_ana = conceder_pertenca(
            user=ana,
            tenant_id=alfa.id,
            role=Papel.OWNER,
            display_name="Ana Silva",
        ).id
    with tenant_scope(beta.id):
        pertenca_de_bruno = conceder_pertenca(
            user=bruno,
            tenant_id=beta.id,
            role=Papel.MANAGER,
            display_name="Bruno Costa",
        ).id

    return Cenario(
        alfa=alfa,
        beta=beta,
        ana=ana,
        bruno=bruno,
        carla=carla,
        pertenca_de_ana=pertenca_de_ana,
        pertenca_de_bruno=pertenca_de_bruno,
    )


def _cliente(user: User, tenant_id: UUID | str | None = None, **kwargs: Any) -> Client:
    """Sessão autenticada, com (ou sem) tenant ativo escrito na sessão."""
    cliente = Client(**kwargs)
    cliente.force_login(user, backend=BACKEND)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


# ---------------------------------------------------------------------------
# 1. Um endpoint de lista nunca mostra a linha do outro tenant
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_a_lista_do_tenant_a_nunca_ve_a_linha_de_b(cenario: Cenario) -> None:
    """E a queryset da view não filtra nada: quem filtra é a política."""
    resposta = _cliente(cenario.ana, cenario.alfa.id).get(URL_LISTA)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["count"] == 1
    assert [linha["display_name"] for linha in corpo["results"]] == ["Ana Silva"]
    # Nem o nome, nem o id, nem o papel do outro tenant aparecem em lado nenhum.
    assert "Bruno" not in resposta.content.decode()
    assert str(cenario.pertenca_de_bruno) not in resposta.content.decode()


@com_urls_do_harness
def test_o_isolamento_e_simetrico(cenario: Cenario) -> None:
    """A assimetria seria o sinal de um filtro em código em vez de política."""
    resposta = _cliente(cenario.bruno, cenario.beta.id).get(URL_LISTA)

    assert resposta.status_code == 200
    assert [linha["display_name"] for linha in resposta.json()["results"]] == ["Bruno Costa"]


@com_urls_do_harness
def test_o_detalhe_de_uma_linha_de_outro_tenant_da_404_e_nao_403(cenario: Cenario) -> None:
    """404 é a resposta certa: 403 confirmaria a existência do objeto.

    E chega-se lá sem uma linha de código de autorização: a linha de Beta não é
    legível dentro do âmbito de Alfa, logo o `get_object()` levanta
    `DoesNotExist` antes de o `has_object_permission` ser chamado.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    assert cliente.get(f"{URL_LISTA}{cenario.pertenca_de_ana}/").status_code == 200
    assert cliente.get(f"{URL_LISTA}{cenario.pertenca_de_bruno}/").status_code == 404


# ---------------------------------------------------------------------------
# 2. Sessão adulterada: 403 e zero linhas lidas, incluindo no middleware
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_a_sessao_adulterada_para_o_uuid_de_b_da_403(cenario: Cenario) -> None:
    """A sessão escolhe o âmbito; a política é que o concede.

    O valor da sessão não é uma credencial, é um argumento: forjá-lo escolhe um
    âmbito onde a query do middleware — que leva `user_id = <o meu>` no `WHERE`
    — não devolve nada.
    """
    cliente = _cliente(cenario.ana, cenario.beta.id)

    with CaptureQueriesContext(connection) as capturadas:
        resposta = cliente.get(URL_LISTA)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_DESCONHECIDO

    # Uma query só tocou no `accounts_membership`: a do middleware. Se a view
    # tivesse corrido, haveria uma segunda (a da lista) — e é essa a forma de
    # afirmar que nenhuma linha de Beta foi lida, nem para ser descartada
    # depois em Python.
    do_membership = [
        q["sql"] for q in capturadas.captured_queries if "accounts_membership" in q["sql"]
    ]
    assert len(do_membership) == 1, do_membership
    assert "Bruno" not in resposta.content.decode()


def test_a_query_do_middleware_devolve_zero_linhas_no_ambito_forjado(cenario: Cenario) -> None:
    """A mesma afirmação, agora no selector, sem passar pelo HTTP.

    As três asserções juntas dizem o que interessa: dentro do âmbito de Beta
    **existe** uma pertença, ela **não** é da Ana, e a query que o middleware
    faz para a Ana devolve `None`. É a política a responder, não um `if`.
    """
    with tenant_scope(cenario.beta.id):
        assert Membership.objects.count() == 1
        assert not Membership.objects.filter(user=cenario.ana).exists()
        assert (
            membership_no_ambito(user_id=cenario.ana.pk, tenant_id=cenario.beta.id) is None
        )


@com_urls_do_harness
def test_sem_tenant_na_sessao_da_403_com_o_codigo_de_sem_sessao(cenario: Cenario) -> None:
    resposta = _cliente(cenario.ana).get(URL_LISTA)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_SEM_SESSAO


@com_urls_do_harness
def test_um_anonimo_leva_403_antes_de_a_view_correr(transactional_db: None) -> None:
    """O `code` é o que o frontend lê: o status 403 também sai do DRF para
    anónimos, e ramificar pelo status não distinguia "faz login" de "escolhe o
    estabelecimento"."""
    resposta = Client().get(URL_LISTA)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_SEM_SESSAO


@com_urls_do_harness
def test_um_utilizador_sem_pertenca_nenhuma_leva_403(cenario: Cenario) -> None:
    """A Carla existe no `accounts_user` e não tem `Membership` em sítio nenhum.

    Saber um email não compra nada: é a propriedade que compensa o
    `accounts_user` não ter política.
    """
    cliente = _cliente(cenario.carla, cenario.alfa.id)

    resposta = cliente.get(URL_LISTA)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_DESCONHECIDO


# ---------------------------------------------------------------------------
# 3. Revogar corta no pedido seguinte, não na sessão seguinte
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_um_membership_desativado_corta_o_acesso_no_pedido_seguinte(cenario: Cenario) -> None:
    """A verificação é por pedido e não há cache: é isso que o torna imediato.

    Ninguém toca em sessões para revogar um acesso — a sessão guarda um UUID que
    o utilizador já conhece e zero autorização.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    assert cliente.get(URL_LISTA).status_code == 200

    with tenant_scope(cenario.alfa.id):
        assert revogar_pertenca(user=cenario.ana, tenant_id=cenario.alfa.id) is True

    resposta = cliente.get(URL_LISTA)

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_DESCONHECIDO
    # E a sessão continua lá, intacta: é o pedido que é recusado.
    assert cliente.session[SESSION_TENANT_KEY] == str(cenario.alfa.id)


# ---------------------------------------------------------------------------
# 4. A política do `accounts_tenant`, que é sobre `id`
# ---------------------------------------------------------------------------
def test_dentro_do_ambito_de_alfa_so_existe_um_tenant(cenario: Cenario) -> None:
    """Dois tenants na tabela, um visível. O predicado é `id = app.tenant_id`."""
    with tenant_scope(cenario.alfa.id):
        assert Tenant.objects.count() == 1
        assert Tenant.objects.get().id == cenario.alfa.id

    with tenant_scope(cenario.beta.id):
        assert Tenant.objects.count() == 1
        assert Tenant.objects.get().id == cenario.beta.id


@pytest.mark.sem_ambito_de_rls  # é esta leitura que o teste existe para provar
def test_fora_de_ambito_nao_existe_tenant_nenhum(cenario: Cenario) -> None:
    """Falha fechada, e sem erro: zero linhas é o que a ADR 0005 promete.

    Sem a política do `accounts_tenant`, esta contagem era 2 — e qualquer
    ligação autenticada lia a lista completa de clientes com os seus nomes, que
    é a ameaça "acesso a dados de outro tenant" do SECURITY.md §1 na forma mais
    literal.
    """
    assert Tenant.objects.count() == 0
    assert Membership.objects.count() == 0


def test_criar_um_tenant_com_outro_id_e_recusado_pela_propria_politica(
    transactional_db: None,
) -> None:
    """Sem `WITH CHECK` separado, o `USING` vale também nas escritas.

    É a mecânica que torna o registo possível (inserir com `id = app.tenant_id`
    passa) e ao mesmo tempo impede que o âmbito de um tenant crie outro.
    """
    with tenant_scope(uuid4()), pytest.raises(ProgrammingError, match="row-level security"):
        Tenant.objects.create(id=uuid4(), name="tenant forjado")


# ---------------------------------------------------------------------------
# 5. A imposição de constraints **não** está sujeita à RLS
# ---------------------------------------------------------------------------
def test_a_unicidade_ve_uma_linha_que_a_ligacao_nao_consegue_ler(cenario: Cenario) -> None:
    """Afirmação verificável, e não citação da documentação do Postgres.

    "Referential integrity checks, such as unique or primary key constraints and
    foreign key references, always bypass row security" — medido aqui: dentro do
    âmbito de Alfa, a linha de pertença de Beta **não é legível** (primeira
    asserção) e no entanto a chave primária colide com ela (segunda). O índice
    único viu uma linha que o `SELECT` não vê.

    É o mecanismo em que a deteção de duplicados vai assentar: o `nif_hmac`
    único e global do SECURITY.md §3 é exatamente esta forma — uma coluna única
    que atravessa tenants numa tabela com política, onde a colisão prova a
    existência de uma linha que não se pode ler.

    ## A versão que a ADR imaginou não é construtível, e é bom saber porquê

    Colidir com o `(user, tenant)` de uma linha de Beta obrigava a inserir uma
    linha com `tenant_id = Beta`, e essa nem chega ao índice: o `USING` da
    política (que, sem `WITH CHECK`, também vale nas escritas) recusa-a antes —
    é o teste seguinte. A colisão que funciona é na **chave primária**, que é um
    UUID global e não leva o tenant no prefixo. A propriedade provada é a mesma.

    A Carla é usada de propósito: a Ana já tem pertença em Alfa, logo uma
    inserção em nome dela colidiria também no `(user, tenant)` — contra uma
    linha *visível* — e o teste deixava de dizer o que quer dizer.
    """
    with tenant_scope(cenario.alfa.id):
        assert not Membership.objects.filter(pk=cenario.pertenca_de_bruno).exists()

        with pytest.raises(IntegrityError, match="accounts_membership_pkey"):
            Membership.objects.create(
                id=cenario.pertenca_de_bruno,
                user=cenario.carla,
                tenant_id=cenario.alfa.id,
                role=Papel.STAFF,
                display_name="colisão de chave primária",
            )


def test_a_politica_recusa_a_escrita_para_outro_tenant_antes_da_unicidade(
    cenario: Cenario,
) -> None:
    """A verificação de RLS do `INSERT` corre antes de o índice ser tocado.

    Daí a forma do teste anterior. O erro é de privilégio
    (`new row violates row-level security policy`), não de integridade.
    """
    with tenant_scope(cenario.alfa.id), pytest.raises(ProgrammingError, match="row-level"):
        Membership.objects.create(
            id=uuid4(),
            user=cenario.carla,
            tenant_id=cenario.beta.id,
            role=Papel.STAFF,
            display_name="escrita para o tenant errado",
        )


# ---------------------------------------------------------------------------
# 6. O guarda do `conftest.py` — com o teste que o guarda não pode ter sozinho
# ---------------------------------------------------------------------------
def test_o_guarda_de_ambito_levanta_na_leitura_proibida(transactional_db: None) -> None:
    """A leitura proibida, feita de propósito.

    Sem este teste, um guarda quebrado — uma lista de relações vazia, um
    prefixo de SQL mal comparado — ficava verde e calado, que é a classe de
    defeito que ele existe para apanhar. Aqui a query é a mesma que o teste
    marcado com `sem_ambito_de_rls` faz sem levantar, e a diferença é só a
    marca: é isso que prova que é o guarda a levantar e não a política.
    """
    assert current_tenant() is None

    with pytest.raises(LeituraSemAmbito, match="accounts_membership"):
        Membership.objects.count()


def test_o_guarda_de_ambito_nao_levanta_dentro_do_ambito(transactional_db: None) -> None:
    """A outra metade: dentro de âmbito não estorva ninguém."""
    with tenant_scope(uuid4()):
        assert Membership.objects.count() == 0
        assert Tenant.objects.count() == 0


def test_o_guarda_de_ambito_nao_levanta_no_consumidor_da_outbox(
    transactional_db: None,
) -> None:
    """Âmbito de sistema é âmbito: a leitura do consumidor é legítima.

    É a forma exata do consumidor da outbox (ARCHITECTURE.md §4): ler a linha
    sob `system_scope()`, sem tenant, porque é a linha que **diz** de que tenant
    se trata. Antes do `in_system_scope()` o guarda não distinguia isto de uma
    leitura fora de âmbito e a saída era marcar o teste com
    `sem_ambito_de_rls` — dispensar o guarda inteiro para calar um caso que ele
    devia reconhecer.

    As duas metades são necessárias: sem a segunda, o guarda podia ter sido
    desligado em vez de corrigido.
    """
    assert current_tenant() is None

    with system_scope():
        assert in_system_scope() is True
        assert OutboxEvent.objects.count() == 0

    with pytest.raises(LeituraSemAmbito, match="shared_outboxevent"):
        OutboxEvent.objects.count()


def test_o_ambito_de_sistema_nao_e_um_passe_geral(transactional_db: None) -> None:
    """E o guarda sabe qual é a diferença, porque a lê do predicado da política.

    Só o `shared_outboxevent` tem o disjunto `app.scope = 'system'` (ADR 0005).
    Dentro de `system_scope()` o `app.tenant_id` está a NULL, logo uma leitura
    do `accounts_membership` a partir de lá devolve **zero linhas sem erro** —
    o defeito silencioso de sempre, agora com um âmbito aberto a dar-lhe
    aparência de legitimidade. Tratar "âmbito de sistema" como "âmbito
    qualquer" tirava esse caso ao guarda.

    É também a forma errada de escrever o consumidor da outbox, e a mensagem
    diz qual é a certa: ler a linha, fechar o bloco, reentrar em
    `tenant_scope(row.tenant_id)`.
    """
    with system_scope():
        with pytest.raises(LeituraSemAmbito, match="app.scope"):
            Membership.objects.count()

        with pytest.raises(LeituraSemAmbito, match="accounts_tenant"):
            Tenant.objects.count()

        # E a da outbox, que é a única com o disjunto, continua a passar.
        assert OutboxEvent.objects.count() == 0


def test_o_guarda_de_ambito_cobre_as_tabelas_com_politica(transactional_db: None) -> None:
    """A lista vem do `pg_policy`, logo cobre as de hoje e as de amanhã.

    O `accounts_invitation` é a prova de que "as de amanhã" não era uma promessa:
    entrou no guarda sozinho, sem ninguém acrescentar uma linha ao `conftest.py`,
    porque a lista é lida do catálogo no arranque da sessão de testes. E tem de
    estar coberto — é a tabela que a activação lê, e lê-la fora de
    `tenant_scope` devolveria zero linhas em silêncio, que é exatamente a forma
    silenciosa do bug que a ADR 0010 fecha.

    O `accounts_user` **não** está coberto, e é deliberado: é a tabela sem
    política, e é por lá que o login tem de entrar antes de existir âmbito.
    """
    for consulta in (
        Membership.objects.count,
        Tenant.objects.count,
        Invitation.objects.count,
        OutboxEvent.objects.count,
    ):
        with pytest.raises(LeituraSemAmbito):
            consulta()

    # E a prova de que o guarda não é um "levanta sempre": esta passa.
    assert User.objects.count() == 0


# ---------------------------------------------------------------------------
# 7. O header `X-Tenant-ID` só pode causar 409
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_o_header_que_bate_com_a_sessao_nao_muda_nada(cenario: Cenario) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = cliente.get(URL_LISTA, headers={TENANT_HEADER: str(cenario.alfa.id)})

    assert resposta.status_code == 200


@com_urls_do_harness
def test_o_header_que_divirja_da_sessao_da_409(cenario: Cenario) -> None:
    """O multi-tab: trocar de tenant num separador muda o outro no fetch
    seguinte, e o 409 é o que diz ao cliente para recarregar em vez de mostrar
    dados do estabelecimento errado."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = cliente.get(URL_LISTA, headers={TENANT_HEADER: str(cenario.beta.id)})

    assert resposta.status_code == 409
    assert resposta.json()["code"] == CODIGO_DIVERGENTE


@com_urls_do_harness
def test_um_header_ilegivel_tambem_da_409(cenario: Cenario) -> None:
    """Não é um âmbito que se possa confirmar, e a resposta certa é a mesma."""
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = cliente.get(URL_LISTA, headers={TENANT_HEADER: "a-pastelaria-do-ze"})

    assert resposta.status_code == 409
    assert resposta.json()["code"] == CODIGO_DIVERGENTE


@com_urls_do_harness
def test_o_header_nunca_escolhe_ambito(cenario: Cenario) -> None:
    """A assimetria que torna o header inofensivo.

    Sessão sem tenant e header com um tenant onde a Ana **tem** pertença: se o
    header pudesse escolher, isto dava 200. Dá 403 `sem_sessao` — o header só
    pode recusar, nunca conceder.
    """
    cliente = _cliente(cenario.ana)

    resposta = cliente.get(URL_LISTA, headers={TENANT_HEADER: str(cenario.alfa.id)})

    assert resposta.status_code == 403
    assert resposta.json()["code"] == CODIGO_SEM_SESSAO


# ---------------------------------------------------------------------------
# 8. O que o middleware publica no pedido, e a lista fechada das dispensas
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_o_request_tenant_e_o_dataclass_e_nao_o_modelo(cenario: Cenario) -> None:
    """Um `request.tenant` que fosse um `Tenant` dava a qualquer view acesso a
    tudo o que aponta para o tenant, por travessia de relações."""
    resposta = _cliente(cenario.ana, cenario.alfa.id).get(URL_CONTEXTO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tipo_do_tenant"] == TenantContext.__name__
    assert corpo["tenant_id"] == str(cenario.alfa.id)
    # O nome do tenant só é legível **dentro** do âmbito: vem do
    # `select_related` da query do middleware, não de uma segunda leitura.
    assert corpo["tenant_name"] == "Pastelaria Alfa"
    assert corpo["role"] == Papel.OWNER.value
    # O nome exibido vem do `Membership` (tabela com política) e não do `User`.
    assert corpo["display_name"] == "Ana Silva"
    assert corpo["email"] == "ana@alfa.pt"
    # A resposta é serializada **ainda dentro** do âmbito (ADR 0005 §7).
    assert corpo["ambito_aberto"] == str(cenario.alfa.id)


@com_urls_do_harness
def test_uma_view_dispensada_e_servida_sem_ambito_e_sem_tenant(transactional_db: None) -> None:
    """E não ganha âmbito por acidente: se tocar em dados de um tenant, abre-o."""
    resposta = Client().get(URL_SEM_AMBITO)

    assert resposta.status_code == 200
    assert resposta.json() == {"ambito_aberto": None, "tem_tenant_no_request": False}


def test_a_lista_de_views_dispensadas_de_ambito_esta_fechada() -> None:
    """As dispensas de hoje, nos dois sentidos, sobre o `ROOT_URLCONF` real.

    A ADR 0007 lista as dispensas que vão existir — admin, healthcheck, login,
    logout, registo, listagem de tenants e troca de tenant. Hoje existem três
    famílias: o admin, os dois endpoints de saúde (`config/health.py`) e as
    **seis** de `/api/v1/auth/` (`apps/accounts/views.py`, ADR 0010 e ADR 0016).
    As que faltam são as duas da reposição de password, e é este teste que as
    obriga a aparecer aqui quando nascerem.

    As seis de `/auth/` estão aqui porque correm **antes** de existir tenant na
    sessão: é a condição do login da ADR 0007, e o `tenant-ativo` é o caso que
    mostra porque é que a dispensa tem de ser declarada e não inferida — sem
    ela, o middleware teria aberto o âmbito **antigo** antes da view e a troca
    levantaria `TenantScopeConflict`. O que cada uma delas toca em dados de
    tenant é aberto por elas, uma transação curta por candidato.

    O `preferencias` é a sexta e a mais recente (ADR 0016), e está aqui por uma
    razão que as outras cinco não têm: escreve numa tabela **sem política** — o
    `accounts_user`, que a ADR 0007 deixa sem RLS para o login poder ler antes de
    existir âmbito — e tem de funcionar em `escolha_pendente`, que é o estado em
    que ainda não há âmbito para abrir. Trocar de tema não toca em dado de tenant
    nenhum, e é por isso que esta dispensa não alarga a superfície que importa.

    O `ativar` é o caso que vale a pena ler duas vezes, porque é o único em que
    "dispensado de âmbito" **não** significa "sem âmbito": ele abre
    `tenant_scope(uuid que vem do fragmento do link)` e lê o convite lá dentro
    (ADR 0010). É por isso que `accounts_invitation` tem política normal e
    **não** entra no `SEM_POLITICA` do `tests/test_db_roles.py` — o link escolhe
    o âmbito, a política concede-o.

    E os três endpoints de **gestão** de convites aparecem no outro lado da
    asserção, com âmbito, que é o default: criar, reenviar e revogar são
    operações de dentro de um estabelecimento, feitas por quem tem sessão. As
    duas do `menu/` (ADR 0009 e ADR 0011) estão no mesmo lado e pelo mesmo
    critério — configurar o menu é uma operação de dentro de um
    estabelecimento. O `menu/rotas` não lê dados de tenant nenhum e **ainda
    assim** tem âmbito: a dispensa pede-se quando é necessária, e poupar uma
    transação é a razão mais fraca que existe para alargar a superfície sem
    âmbito.

    O `estabelecimento` (ADR 0017) é o caso mais limpo deste lado, e vale lê-lo
    ao lado do `preferencias`: os dois são ecrãs de configurações e estão em
    lados opostos desta asserção, porque as **tabelas** são diferentes. O das
    preferências escreve no `accounts_user`, que não tem política e tem de
    funcionar antes de haver âmbito; este lê e escreve o `accounts_tenant`, cuja
    política compara `id` com o GUC — dentro do âmbito a tabela tem no máximo uma
    linha visível, que é o que permite ao service fazer `get()` sem filtro e o que
    torna o IDOR impossível por construção em vez de por verificação.

    As duas da saúde estão aqui pelo mesmo critério das outras, e não por serem
    inofensivas: não abrem âmbito porque não leem dados de tenant nenhum, e não
    o abrem *de propósito* porque o `tenant_scope` abre uma transação por
    pedido (ADR 0005) e a verificação repete-se a cada poucos segundos, por
    contentor. Ver `tests/test_health.py` para as propriedades que as tornam
    servíveis sem âmbito.
    """
    rotas = list(_vistas(get_resolver(settings.ROOT_URLCONF).url_patterns))
    assert rotas, "âncora: o ROOT_URLCONF não tem rotas e o teste não diria nada"

    dispensadas = sorted({rota for rota, vista in rotas if dispensa_declarada(vista)})
    com_ambito = sorted({rota for rota, vista in rotas if not dispensa_declarada(vista)})

    assert dispensadas, "nenhuma view dispensada: o admin deixou de o estar?"
    fora_do_admin = [rota for rota in dispensadas if not rota.startswith(settings.ADMIN_URL)]
    assert fora_do_admin == [
        "api/v1/auth/ativar",
        "api/v1/auth/login",
        "api/v1/auth/logout",
        "api/v1/auth/preferencias",
        "api/v1/auth/sessao",
        "api/v1/auth/tenant-ativo",
        "healthz",
        "readyz",
    ], (
        "views dispensadas de âmbito fora do admin. A dispensa é uma decisão de "
        "isolamento: passa pelo security-reviewer e entra neste teste."
    )
    # As rotas dos convites vêm do `SimpleRouter`, que usa `re_path`: o padrão
    # em cru traz os `^$` e o grupo nomeado do `pk`. Fica como o resolver o vê,
    # porque é o resolver que o middleware consulta — normalizá-lo aqui era
    # escrever uma segunda versão da verdade neste teste.
    assert com_ambito == [
        "api/v1/^convites$",
        "api/v1/^convites/(?P<pk>[^/.]+)/reenviar$",
        "api/v1/^convites/(?P<pk>[^/.]+)/revogar$",
        # As cinco rotas de `/documents` (ADR 0021, fatia 1). Entram **todas** no
        # lado com âmbito, e é esse o gate principal daquela feature: a adenda 2
        # da ADR 0020 revogou a ponte com token anónimo, logo o
        # `fora_do_admin` acima **não cresceu em nenhuma entrada** e estas
        # aparecem aqui, que é o default.
        "api/v1/^documents$",
        "api/v1/^documents/(?P<pk>[^/.]+)$",
        "api/v1/^documents/(?P<pk>[^/.]+)/closing$",
        "api/v1/^documents/(?P<pk>[^/.]+)/files$",
        "api/v1/^documents/(?P<pk>[^/.]+)/pages/(?P<posicao>[0-9]{1,4})/image$",
        "api/v1/estabelecimento",
        "api/v1/menu",
        "api/v1/menu/rotas",
        "api/v1/schema/",
    ], (
        "o conjunto das views com âmbito mudou. O default é ter âmbito, logo "
        "uma view nova aparece aqui — e é isso que se quer."
    )


def test_o_admin_continua_a_ser_servido(transactional_db: None) -> None:
    """A dispensa do admin, medida pelo lado de fora.

    O `dispensar_ambito(admin.site.urls)` do `config/urls.py` é a linha mais
    fácil de perder num refactor, e perdê-la não dá erro nenhum: dá 403
    `sem_sessao` em **todos** os pedidos ao admin, incluindo a página de login,
    porque um operador do StockFlow não tem `tenant_id` na sessão. Daí este
    teste ir pelo HTTP e não pelo atributo.

    Duas rotas de propósito: o `login/` é um método ligado do `AdminSite`
    registado sem invólucro, logo é o caminho do `_involucro` do
    `accounts/api.py`; o índice é uma view embrulhada pelo `admin_view`, que é o
    caminho do `setattr` direto.
    """
    cliente = Client()

    assert cliente.get(f"/{settings.ADMIN_URL}login/").status_code == 200
    # Anónimo no índice: redireciona para o login do admin, não 403.
    indice = cliente.get(f"/{settings.ADMIN_URL}")
    assert indice.status_code == 302
    assert "login" in indice["Location"]


def _vistas(patterns: Any, prefixo: str = "") -> Iterator[tuple[str, Any]]:
    """Todas as views de uma árvore de URLs, com a rota completa."""
    for pattern in patterns:
        rota = prefixo + str(pattern.pattern)
        aninhados = getattr(pattern, "url_patterns", None)
        if aninhados is not None:
            yield from _vistas(aninhados, rota)
        else:
            yield rota, pattern.callback


# ---------------------------------------------------------------------------
# 9. Permissões e papéis
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_o_papel_do_membership_decide_e_nao_uma_flag_do_user(cenario: Cenario) -> None:
    """A Ana é `owner` em Alfa; o Bruno é `manager` em Beta.

    O papel é do par (utilizador, tenant) e vem do `Membership` confirmado
    **neste** pedido — a mesma pessoa é dona de um estabelecimento e
    colaboradora noutro.
    """
    assert _cliente(cenario.ana, cenario.alfa.id).get("/api/v1/testes/donos/").status_code == 200

    resposta = _cliente(cenario.bruno, cenario.beta.id).get("/api/v1/testes/donos/")

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == TemPapel.message


def test_pertence_ao_tenant_compara_o_tenant_id_do_objeto(cenario: Cenario) -> None:
    """A comparação do SECURITY.md §5, na sua forma mais directa.

    É a segunda rede: a primeira é a RLS, que faz a linha de Beta não ser
    legível dentro do âmbito de Alfa. Aqui o objeto é passado à mão, como
    aconteceria se uma queryset fosse construída fora do âmbito.
    """
    permissao = PertenceAoTenant()
    pedido = type("Pedido", (), {"tenant": None})()
    de_alfa = Membership(tenant_id=cenario.alfa.id)
    de_beta = Membership(tenant_id=cenario.beta.id)

    pedido.tenant = TenantContext(id=cenario.alfa.id, name="Alfa", role=Papel.OWNER.value)
    assert permissao.has_object_permission(pedido, None, de_alfa) is True
    assert permissao.has_object_permission(pedido, None, de_beta) is False

    # Sem contexto (view dispensada de âmbito) nega, e um objeto sem `tenant_id`
    # também: os dados de referência partilhados não se protegem por aqui.
    pedido.tenant = None
    assert permissao.has_object_permission(pedido, None, de_alfa) is False
    pedido.tenant = TenantContext(id=cenario.alfa.id, name="Alfa", role=Papel.OWNER.value)
    assert permissao.has_object_permission(pedido, None, object()) is False


def test_tem_papel_recusa_um_papel_inventado() -> None:
    """Uma permissão que nunca concede nada por o valor estar mal escrito é
    indistinguível de uma regra de negócio."""
    with pytest.raises(ValueError, match="papéis desconhecidos"):
        TemPapel.exige("gerente")

    with pytest.raises(ValueError, match="sem papéis"):
        TemPapel.exige()


def test_tem_papel_usado_em_cru_levanta_em_vez_de_negar_em_silencio() -> None:
    """`permission_classes = [TemPapel]` é um engano, e um 500 diz isso.

    A alternativa — negar tudo com a lista de papéis vazia — aparecia como uma
    regra de negócio ("este utilizador não pode") e ninguém procurava a causa.
    """
    with pytest.raises(ImproperlyConfigured, match="TemPapel.exige"):
        TemPapel().has_permission(None, None)


# ---------------------------------------------------------------------------
# 10. O 5xx desfaz a transação do pedido
# ---------------------------------------------------------------------------
@com_urls_do_harness
def test_uma_resposta_5xx_desfaz_o_que_a_view_escreveu(cenario: Cenario) -> None:
    """Sem o `set_rollback` do middleware, um 500 commitava escritas parciais."""
    cliente = _cliente(cenario.ana, cenario.alfa.id, raise_request_exception=False)

    resposta = cliente.get(URL_EXPLODE)

    assert resposta.status_code == 500
    with tenant_scope(cenario.alfa.id):
        assert Membership.objects.get().display_name == "Ana Silva"


# ---------------------------------------------------------------------------
# 11. O `tenant_ids`: índice, não autorização
# ---------------------------------------------------------------------------
def test_o_tenant_ids_espelha_as_pertencas_ativas(cenario: Cenario) -> None:
    """A contabilista nos dois tenants, e o array a acompanhar.

    O array é o único bit legível fora de âmbito e é o que parte a
    circularidade do bootstrap: propõe âmbitos. Não é recalculável por
    varredura — dentro de `tenant_scope(Alfa)` a política só mostra as
    pertenças de Alfa — e é por isso que é mantido pelas mesmas funções que
    escrevem o `Membership`.
    """
    assert cenario.carla.tenant_ids == []

    with tenant_scope(cenario.alfa.id):
        conceder_pertenca(
            user=cenario.carla,
            tenant_id=cenario.alfa.id,
            role=Papel.STAFF,
            display_name="Carla (contabilidade)",
        )
    with tenant_scope(cenario.beta.id):
        conceder_pertenca(
            user=cenario.carla,
            tenant_id=cenario.beta.id,
            role=Papel.STAFF,
            display_name="Carla",
        )

    cenario.carla.refresh_from_db()
    assert set(cenario.carla.tenant_ids) == {cenario.alfa.id, cenario.beta.id}

    with tenant_scope(cenario.alfa.id):
        revogar_pertenca(user=cenario.carla, tenant_id=cenario.alfa.id)

    cenario.carla.refresh_from_db()
    assert cenario.carla.tenant_ids == [cenario.beta.id]


def test_conceder_duas_vezes_nao_duplica_nada(cenario: Cenario) -> None:
    """Um convite reenviado atualiza; não levanta e não repete o uuid no array."""
    with tenant_scope(cenario.alfa.id):
        conceder_pertenca(
            user=cenario.ana,
            tenant_id=cenario.alfa.id,
            role=Papel.MANAGER,
            display_name="Ana Silva (gerência)",
        )
        assert Membership.objects.count() == 1
        assert Membership.objects.get().role == Papel.MANAGER.value

    cenario.ana.refresh_from_db()
    assert cenario.ana.tenant_ids == [cenario.alfa.id]


def test_o_tenant_ids_nao_concede_nada(cenario: Cenario) -> None:
    """Um uuid no array sem `Membership` ativo não abre porta nenhuma.

    É o modo de falha do array, e é o oposto do de um privilégio de leitura
    cross-tenant: propõe um âmbito que a política depois recusa.
    """
    with tenant_scope(cenario.alfa.id):
        revogar_pertenca(user=cenario.ana, tenant_id=cenario.alfa.id)

    # Repõe-se o uuid no array à mão, que é o que um tenant apagado deixaria lá.
    User.objects.filter(pk=cenario.ana.pk).update(tenant_ids=[cenario.alfa.id])

    with tenant_scope(cenario.alfa.id):
        assert membership_no_ambito(user_id=cenario.ana.pk, tenant_id=cenario.alfa.id) is None
        assert opcao_de_tenant(cenario.ana.pk, cenario.alfa.id) is None


# ---------------------------------------------------------------------------
# 12. `opcao_de_tenant` exige o âmbito, e o `MembershipInfo` é congelado
# ---------------------------------------------------------------------------
def test_a_opcao_de_tenant_dentro_do_ambito_devolve_a_opcao(cenario: Cenario) -> None:
    """A forma inteira, e é de igualdade: um campo novo cai aqui.

    Chamava-se `tenant_context` e devolvia `TenantContext` até 2026-10-07. Os
    dois chamadores reais convertiam-no num `TenantOption` na linha seguinte, e
    quem constrói o `TenantContext` a sério é o `TenantMiddleware` — nunca passou
    por aqui. A ADR 0018 tornou isso visível ao pedir um campo: acrescentar
    `demonstracao` ao `TenantContext` era pôr a bandeira do demo no contexto de
    autorização de **todos** os pedidos, que é a afordância que a decisão 1 dessa
    ADR não pode ter.
    """
    with tenant_scope(cenario.alfa.id):
        opcao = opcao_de_tenant(cenario.ana.pk, cenario.alfa.id)

    assert opcao == TenantOption(
        id=cenario.alfa.id,
        name="Pastelaria Alfa",
        role=Papel.OWNER.value,
        demonstracao=False,
    )


def test_a_opcao_de_tenant_fora_do_ambito_levanta_em_vez_de_devolver_none(
    cenario: Cenario,
) -> None:
    """Sem a guarda, o bug aparecia como "não tem acesso" em vez de como bug."""
    with pytest.raises(TenantScopeConflict, match="opcao_de_tenant"):
        opcao_de_tenant(cenario.ana.pk, cenario.alfa.id)

    with tenant_scope(cenario.beta.id), pytest.raises(TenantScopeConflict):
        opcao_de_tenant(cenario.ana.pk, cenario.alfa.id)


def test_o_contexto_do_pedido_e_imutavel() -> None:
    """Uma decisão de autorização que se pudesse mutar a meio do pedido mudava
    debaixo dos pés de quem já a tomou."""
    contexto = TenantContext(id=uuid4(), name="Alfa", role=Papel.OWNER.value)
    info = MembershipInfo(
        user_id=uuid4(),
        tenant_id=contexto.id,
        role=Papel.OWNER.value,
        display_name="Ana Silva",
    )

    for congelado, campo in ((contexto, "id"), (info, "role")):
        with pytest.raises(AttributeError):
            setattr(congelado, campo, "outro")
