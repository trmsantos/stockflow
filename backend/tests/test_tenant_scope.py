"""A fronteira transacional da RLS, provada contra o Postgres (ADR 0005).

A asserção que dá razão de ser a esta ADR é uma só, e está em
`test_a_saida_do_ambito_o_guc_nao_sobrevive_na_mesma_ligacao`: **à saída do
bloco, na mesma ligação, o `app.tenant_id` já não vale o que valia lá dentro.**
É a asserção que a versão com GUC de sessão falha — com `CONN_MAX_AGE = 60` a
ligação é persistente, e o pedido seguinte servido por ela herdava o tenant do
anterior, com a RLS convencida de que estava a isolar.

Todos os testes do mecanismo levam `django_db(transaction=True)`. Não é
preferência: com a transação do pytest-django por fora, o `set_config` local só
reverte no fim dela, o `pg_backend_pid` continua o mesmo e a asserção central
passava sempre — seria um teste vazio a dar confiança.

## Duas coisas que estes testes descobriram, e que não estavam nos documentos

1. **À saída do âmbito o GUC não volta a NULL, volta a `''`.** `app.tenant_id` é
   um *placeholder* e o valor de arranque de um placeholder é a string vazia.
   Consequência: `current_setting('app.tenant_id', true)::uuid` — que é o que
   `SECURITY.md` §3 escreve — levanta `invalid input syntax for type uuid: ""`
   na segunda transação de cada ligação, em vez de devolver zero linhas. A
   política tem de comparar contra `NULLIF(..., '')::uuid`. Está nos dois testes
   que se seguem e no cabeçalho da migração.

2. **O role da ligação é o `stockflow_app`** — sem `SUPERUSER`, sem `BYPASSRLS`
   e dono de nada (ADR 0006). A base de dados de teste é criada e migrada pelo
   `stockflow_owner` e os testes correm como a app: quem faz a troca é o
   `django_db_setup` em `tests/conftest.py`. Consequência para este ficheiro: a
   RLS é imposta em **todos** os testes e não só nos quatro que pediam uma
   fixture para trocar de role, e essa fixture deixou de existir. A guarda que
   afirma de que role se trata mudou de casa para `tests/test_db_roles.py`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import connection
from django.db.utils import DataError, ProgrammingError
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from apps.shared.db import TenantScopeConflict, current_tenant, system_scope, tenant_scope
from apps.shared.events import DomainEvent
from apps.shared.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    request_log_context,
)
from apps.shared.outbox import OutboxEvent, publish
from apps.shared.tasks import TenantIdRequired, TenantTask
from config.celery import app
from config.log import CONTEXT_FIELDS, JsonFormatter, RequestContextFilter

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _escalar(sql: str, params: list[object] | None = None) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        linha = cursor.fetchone()
    assert linha is not None
    return linha[0]


def _guc(nome: str) -> object:
    """O valor cru do GUC, como o Postgres o devolve."""
    return _escalar("SELECT current_setting(%s, true)", [nome])


def _predicado_da_politica() -> object:
    """O lado direito da comparação da política, tal como ela o escreve."""
    return _escalar("SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid")


def _pid() -> object:
    return _escalar("SELECT pg_backend_pid()")


# ---------------------------------------------------------------------------
# O mecanismo: o GUC vive na transação e não lhe sobrevive
# ---------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_dentro_do_ambito_o_guc_tem_o_uuid_do_tenant() -> None:
    with tenant_scope(TENANT_A) as tenant:
        assert tenant == TENANT_A
        assert _guc("app.tenant_id") == str(TENANT_A)
        assert _predicado_da_politica() == TENANT_A
        assert current_tenant() == TENANT_A


@pytest.mark.django_db(transaction=True)
def test_a_saida_do_ambito_o_guc_nao_sobrevive_na_mesma_ligacao() -> None:
    """A asserção central da ADR 0005.

    O `pg_backend_pid` antes e depois prova que é a **mesma** ligação: sem isso
    o teste podia estar a observar uma ligação nova, onde nada teria
    sobrevivido de qualquer maneira e a asserção não diria nada.
    """
    pid_antes = _pid()

    with tenant_scope(TENANT_A):
        assert _guc("app.tenant_id") == str(TENANT_A)

    assert _pid() == pid_antes, "a ligação mudou; o teste não prova nada"

    # O que a política avalia: NULL, logo a linha não casa, zero linhas, sem
    # erro. É o comportamento que a ADR promete para pedidos sem tenant.
    assert _predicado_da_politica() is None
    assert current_tenant() is None

    # E o valor cru, medido: string vazia, **não** NULL. É por isso que a
    # política leva `NULLIF` — sem ele, o cast `''::uuid` levantava aqui.
    assert _guc("app.tenant_id") == ""
    with pytest.raises(DataError, match="invalid input syntax for type uuid"):
        _escalar("SELECT current_setting('app.tenant_id', true)::uuid")


# A leitura da outbox sob `system_scope()` é sem tenant por desenho — é como o
# consumidor lê a linha — e o guarda de âmbito do `conftest.py` não distingue
# "sem âmbito nenhum" de "âmbito de sistema". Daí a marca, aqui e nos dois
# testes do disjunto de sistema mais abaixo.
@pytest.mark.sem_ambito_de_rls
@pytest.mark.django_db(transaction=True)
def test_uma_excecao_dentro_do_ambito_desfaz_a_transacao_e_fecha_o_guc() -> None:
    evento = _EventoDeTeste(tenant_id=TENANT_A, quantidade=Decimal("1.000"))

    with pytest.raises(RuntimeError, match="a receção correu mal"), tenant_scope(TENANT_A):
        publish(evento)
        raise RuntimeError("a receção correu mal")

    assert _predicado_da_politica() is None
    with system_scope():
        assert OutboxEvent.objects.count() == 0


# ---------------------------------------------------------------------------
# Reentrância e conflitos
# ---------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_o_mesmo_tenant_e_reentrante() -> None:
    with tenant_scope(TENANT_A), tenant_scope(TENANT_A):
        assert current_tenant() == TENANT_A
        assert _guc("app.tenant_id") == str(TENANT_A)

    assert current_tenant() is None


@pytest.mark.django_db(transaction=True)
def test_um_segundo_tenant_no_mesmo_bloco_levanta() -> None:
    """Porque o `set_config` do bloco interior não se restaura à saída.

    Medido: com um savepoint pelo meio, um `RELEASE` deixa o valor do bloco
    interior a valer até ao fim da transação de topo. Trocar de tenant a meio
    contaminava o resto do pedido — e a política continuava a "isolar", pelo
    tenant errado.
    """
    with tenant_scope(TENANT_A), pytest.raises(TenantScopeConflict, match=str(TENANT_B)):
        with tenant_scope(TENANT_B):
            pytest.fail("não devia ter entrado")


@pytest.mark.django_db(transaction=True)
def test_system_scope_dentro_de_tenant_scope_levanta() -> None:
    """Um service a correr num pedido não escala para âmbito de sistema."""
    with tenant_scope(TENANT_A), pytest.raises(TenantScopeConflict, match="escalada"):
        with system_scope():
            pytest.fail("não devia ter entrado")


@pytest.mark.django_db(transaction=True)
def test_tenant_scope_dentro_de_system_scope_levanta() -> None:
    """O consumidor da outbox fecha o âmbito de sistema antes de abrir o do
    tenant — senão o `app.tenant_id` ficava colado à transação de sistema."""
    with system_scope(), pytest.raises(TenantScopeConflict, match="system_scope"):
        with tenant_scope(TENANT_A):
            pytest.fail("não devia ter entrado")


def test_current_tenant_fora_de_qualquer_ambito_e_none() -> None:
    """E não é erro: login, healthcheck, admin e anónimo vivem aqui."""
    assert current_tenant() is None


@pytest.mark.django_db(transaction=True)
def test_um_tenant_id_que_nao_e_uuid_nao_chega_ao_set_config() -> None:
    with pytest.raises(ValueError, match="não é um UUID"), tenant_scope("'; drop table --"):
        pytest.fail("não devia ter entrado")

    assert _predicado_da_politica() is None


@pytest.mark.django_db(transaction=True)
def test_o_tenant_em_string_e_normalizado_para_uuid() -> None:
    """O Celery serializa os argumentos em JSON: uma tarefa recebe texto."""
    with tenant_scope(str(TENANT_A)) as tenant:
        assert tenant == TENANT_A
        assert current_tenant() == TENANT_A


# ---------------------------------------------------------------------------
# Eventos e outbox
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class _EventoDeTeste(DomainEvent):
    quantidade: Decimal


def test_o_payload_de_um_evento_guarda_o_decimal_como_string() -> None:
    """Um Decimal que passe por float a caminho do JSON perde exatidão."""
    evento = _EventoDeTeste(tenant_id=TENANT_A, quantidade=Decimal("12.345"))

    payload = evento.payload()

    assert payload["quantidade"] == "12.345"
    assert payload["tenant_id"] == str(TENANT_A)
    assert payload["event_id"] == str(evento.event_id)
    # E é mesmo serializável, sem `default=`:
    assert json.loads(json.dumps(payload))["quantidade"] == "12.345"


def test_o_payload_recusa_float() -> None:
    @dataclass(frozen=True, kw_only=True, slots=True)
    class _ComFloat(DomainEvent):
        quantidade: float

    with pytest.raises(TypeError, match="Decimal"):
        _ComFloat(tenant_id=TENANT_A, quantidade=1.5).payload()


def test_o_event_type_e_o_caminho_importavel_da_classe() -> None:
    assert _EventoDeTeste.event_type() == f"{__name__}._EventoDeTeste"


@pytest.mark.django_db(transaction=True)
def test_publicar_fora_de_um_ambito_levanta() -> None:
    evento = _EventoDeTeste(tenant_id=TENANT_A, quantidade=Decimal("1"))

    with pytest.raises(TenantScopeConflict, match="fora de um tenant_scope"):
        publish(evento)


@pytest.mark.django_db(transaction=True)
def test_publicar_um_evento_de_outro_tenant_levanta() -> None:
    evento = _EventoDeTeste(tenant_id=TENANT_B, quantidade=Decimal("1"))

    with tenant_scope(TENANT_A), pytest.raises(TenantScopeConflict, match=str(TENANT_B)):
        publish(evento)


# ---------------------------------------------------------------------------
# A política RLS da outbox
#
# Sem fixture nenhuma: a ligação destes testes é a do `stockflow_app`, que não é
# dona da tabela e não tem `BYPASSRLS` (ADR 0006). Antes era preciso trocar de
# role para a política ser avaliada; agora ela vale em todos os testes, e quem o
# prova é `tests/test_db_roles.py`.
# ---------------------------------------------------------------------------
def _publicar(tenant: UUID) -> OutboxEvent:
    with tenant_scope(tenant):
        return publish(_EventoDeTeste(tenant_id=tenant, quantidade=Decimal("2.500")))


@pytest.mark.django_db(transaction=True)
def test_a_politica_da_outbox_isola_por_tenant() -> None:
    linha_a = _publicar(TENANT_A)
    linha_b = _publicar(TENANT_B)

    with tenant_scope(TENANT_A):
        visiveis = set(OutboxEvent.objects.values_list("id", flat=True))
    assert visiveis == {linha_a.id}

    with tenant_scope(TENANT_B):
        visiveis = set(OutboxEvent.objects.values_list("id", flat=True))
    assert visiveis == {linha_b.id}


@pytest.mark.sem_ambito_de_rls  # é esta leitura que o teste existe para provar
@pytest.mark.django_db(transaction=True)
def test_sem_ambito_a_outbox_devolve_zero_linhas_sem_erro() -> None:
    """Falha fechada, e sem exceção: é o que a ADR promete para um pedido sem
    tenant, e o que o `NULLIF` da política torna verdade em qualquer transação
    da ligação."""
    _publicar(TENANT_A)
    _publicar(TENANT_B)

    assert OutboxEvent.objects.count() == 0


@pytest.mark.sem_ambito_de_rls
@pytest.mark.django_db(transaction=True)
def test_o_system_scope_ve_as_linhas_de_todos_os_tenants() -> None:
    """O disjunto `app.scope = 'system'`, que só esta tabela tem: o consumidor
    da outbox não é um pedido e não tem tenant nenhum."""
    linha_a = _publicar(TENANT_A)
    linha_b = _publicar(TENANT_B)

    with system_scope():
        visiveis = set(OutboxEvent.objects.values_list("id", flat=True))

    assert visiveis == {linha_a.id, linha_b.id}


@pytest.mark.django_db(transaction=True)
def test_a_politica_tambem_recusa_escrever_para_outro_tenant() -> None:
    """A política não tem `WITH CHECK`, logo o `USING` vale também nas escritas.

    A verificação de âmbito do `publish()` apanha isto primeiro e com uma
    mensagem melhor; aqui escreve-se por baixo dela, para provar que a rede
    existe mesmo (SECURITY.md §1: a RLS é a rede, não a regra).
    """
    with tenant_scope(TENANT_A), pytest.raises(ProgrammingError, match="row-level security"):
        OutboxEvent.objects.create(
            id=uuid4(),
            tenant_id=TENANT_B,
            event_type="tests.Forjado",
            payload={},
        )


# ---------------------------------------------------------------------------
# Celery: `tenant_id` obrigatório, corpo com âmbito
# ---------------------------------------------------------------------------
@app.task(name="tests.tarefa_com_tenant")
def tarefa_com_tenant(tenant_id: str, nota: str = "") -> str:
    return f"{current_tenant()}|{nota}"


@app.task(name="tests.tarefa_sem_tenant")
def tarefa_sem_tenant(nota: str = "") -> str:  # pragma: no cover - nunca corre
    return nota


class _TarefaDispensada(TenantTask):
    tenant_scope_exempt = True


@app.task(name="tests.tarefa_dispensada", base=_TarefaDispensada)
def tarefa_dispensada() -> str | None:
    tenant = current_tenant()
    return str(tenant) if tenant is not None else None


def test_toda_a_tarefa_herda_o_tenant_task() -> None:
    """Não há outra forma de declarar uma tarefa: é o `task_cls` do app."""
    assert issubclass(app.Task, TenantTask)
    assert isinstance(tarefa_com_tenant, TenantTask)
    assert tarefa_com_tenant.tenant_scope_exempt is False


def test_uma_tarefa_sem_tenant_id_recusa_ao_enfileirar() -> None:
    """A recusa é de quem publica, não de quem executa."""
    with pytest.raises(TenantIdRequired, match="tests.tarefa_sem_tenant"):
        tarefa_sem_tenant.delay(nota="olá")

    with pytest.raises(TenantIdRequired, match="tenant_id"):
        tarefa_com_tenant.apply_async(kwargs={"nota": "olá"})


def test_um_tenant_id_a_none_tambem_recusa() -> None:
    with pytest.raises(TenantIdRequired, match="None"):
        tarefa_com_tenant.delay(tenant_id=None)


def test_um_tenant_id_que_nao_e_uuid_recusa_ao_enfileirar() -> None:
    with pytest.raises(TenantIdRequired, match="não é um UUID"):
        tarefa_com_tenant.delay(tenant_id="a-pastelaria-do-ze")


@pytest.mark.django_db(transaction=True)
def test_o_corpo_da_tarefa_corre_dentro_do_ambito() -> None:
    resultado = tarefa_com_tenant.delay(tenant_id=str(TENANT_A), nota="fatura")

    assert resultado.get() == f"{TENANT_A}|fatura"
    assert current_tenant() is None
    assert _predicado_da_politica() is None


@pytest.mark.django_db(transaction=True)
def test_o_tenant_id_tambem_pode_ir_por_posicao() -> None:
    assert tarefa_com_tenant.delay(str(TENANT_A)).get() == f"{TENANT_A}|"


@pytest.mark.django_db(transaction=True)
def test_a_tarefa_dispensada_corre_sem_ambito() -> None:
    """E não ganha nenhum por acidente: se toca em dados de um tenant, abre o
    âmbito ela mesma."""
    assert tarefa_dispensada.delay().get() is None


# ---------------------------------------------------------------------------
# Contexto de log: `request_id`, `tenant_id`, `user_id`
# ---------------------------------------------------------------------------
class _Coletor(logging.Handler):
    """Handler com o filtro real montado, que é o que se está a testar.

    O `caplog` do pytest não serve: instala-se no logger raiz e o logger `apps`
    tem `propagate = False` nas settings, pelo que nada lhe chegaria.
    """

    def __init__(self) -> None:
        super().__init__()
        self.registos: list[logging.LogRecord] = []
        self.addFilter(RequestContextFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.registos.append(record)


@pytest.fixture
def coletor() -> Iterator[_Coletor]:
    handler = _Coletor()
    logger = logging.getLogger("apps")
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def test_as_chaves_do_contexto_sao_as_que_o_filtro_espera() -> None:
    """Um campo renomeado num dos lados passava a sair sempre a `None`."""
    assert set(request_log_context()) == set(CONTEXT_FIELDS)


def test_fora_de_um_pedido_os_campos_existem_a_none(coletor: _Coletor) -> None:
    """O formato da linha é o mesmo em qualquer processo."""
    logging.getLogger("apps.teste").info("sem pedido")

    registo = coletor.registos[-1]
    assert (registo.request_id, registo.tenant_id, registo.user_id) == (None, None, None)


def test_o_filtro_de_logs_carrega_um_request_id_real(
    rf: RequestFactory, coletor: _Coletor
) -> None:
    def vista(request: HttpRequest) -> HttpResponse:
        logging.getLogger("apps.teste").info("dentro da vista")
        return HttpResponse(status=204)

    request = rf.get("/qualquer/")
    response = RequestContextMiddleware(vista)(request)

    request_id = request.request_id
    assert request_id
    assert response[REQUEST_ID_HEADER] == request_id
    # O da vista e o da linha de acesso do próprio middleware.
    assert [r.request_id for r in coletor.registos] == [request_id, request_id]
    # E sai na linha JSON, que é o que chega ao agregador.
    linha = json.loads(JsonFormatter().format(coletor.registos[0]))
    assert linha["request_id"] == request_id
    assert linha["message"] == "dentro da vista"


def test_o_request_id_nao_vem_do_cliente(rf: RequestFactory) -> None:
    """Texto não confiável a entrar no sistema de logs: mil pedidos com o mesmo
    valor tornariam a correlação inútil."""
    request = rf.get("/qualquer/", headers={"x-request-id": "forjado-pelo-cliente"})

    RequestContextMiddleware(lambda _: HttpResponse(status=204))(request)

    assert request.request_id != "forjado-pelo-cliente"


def test_o_contexto_e_limpo_no_fim_do_pedido(rf: RequestFactory) -> None:
    RequestContextMiddleware(lambda _: HttpResponse(status=204))(rf.get("/qualquer/"))

    assert request_log_context() == {"request_id": None, "tenant_id": None, "user_id": None}


@pytest.mark.django_db(transaction=True)
def test_o_tenant_id_dos_logs_vem_do_ambito_da_rls(
    rf: RequestFactory, coletor: _Coletor
) -> None:
    """É o mesmo campo no pedido e na tarefa: vem do âmbito, não do request."""

    def vista(request: HttpRequest) -> HttpResponse:
        with tenant_scope(TENANT_A):
            logging.getLogger("apps.teste").info("dentro do âmbito")
        return HttpResponse(status=200)

    RequestContextMiddleware(vista)(rf.get("/qualquer/"))

    assert coletor.registos[0].tenant_id == str(TENANT_A)
    # A linha de acesso é escrita depois de o âmbito fechar.
    assert coletor.registos[-1].tenant_id is None


def _user_id_logado(
    rf: RequestFactory, coletor: _Coletor, user: AbstractBaseUser
) -> str | None:
    request = rf.get("/qualquer/")
    request.COOKIES[settings.SESSION_COOKIE_NAME] = "sessao-de-teste"
    request.user = user

    RequestContextMiddleware(lambda _: HttpResponse(status=200))(request)

    return coletor.registos[-1].user_id


@pytest.mark.django_db
def test_o_user_id_dos_logs_vai_em_hash(rf: RequestFactory, coletor: _Coletor) -> None:
    """Nunca o pk nem nada que identifique: é um HMAC com a SECRET_KEY.

    Estável para o mesmo utilizador (senão não correlacionava nada) e diferente
    entre utilizadores (senão não distinguia nada). Um digest simples do pk
    cumpria estas duas e não servia: o espaço de chaves primárias é pequeno e
    enumera-se em segundos, o que devolvia a identidade que o hash esconde. É a
    chave secreta no HMAC que fecha essa porta.
    """
    # O `AUTH_USER_MODEL` é o `accounts.User`: sem `username`, e o email é o
    # `USERNAME_FIELD` (ADR 0007). `get_user_model()` em vez do import direto —
    # `django.contrib.auth.models.User` continua importável e a sua tabela já
    # não existe.
    User = get_user_model()
    ana = User.objects.create_user(email="ana@exemplo.pt")
    beto = User.objects.create_user(email="beto@exemplo.pt")

    de_ana = _user_id_logado(rf, coletor, ana)
    de_beto = _user_id_logado(rf, coletor, beto)

    assert de_ana is not None
    assert de_ana == _user_id_logado(rf, coletor, ana)
    assert de_ana != de_beto
    assert de_ana != str(ana.pk)
    assert len(de_ana) == 16
    assert set(de_ana) <= set("0123456789abcdef")
    linha = json.dumps(json.loads(JsonFormatter().format(coletor.registos[-1])))
    for pii in (beto.email, "/qualquer/"):
        assert pii not in linha


def test_sem_utilizador_autenticado_o_user_id_fica_a_none(
    rf: RequestFactory, coletor: _Coletor
) -> None:
    request = rf.get("/qualquer/")
    request.COOKIES[settings.SESSION_COOKIE_NAME] = "sessao-de-teste"
    request.user = AnonymousUser()

    RequestContextMiddleware(lambda _: HttpResponse(status=200))(request)

    assert coletor.registos[-1].user_id is None


def test_a_linha_de_acesso_nao_leva_o_path(rf: RequestFactory, coletor: _Coletor) -> None:
    """Leva a `route`, o padrão de URL. O path pode transportar dados do
    utilizador; a `route` responde à mesma pergunta sem os levar."""
    caminho = "/produtos/nif-123456789/"

    RequestContextMiddleware(lambda _: HttpResponse(status=200))(rf.get(caminho))

    linha = json.loads(JsonFormatter().format(coletor.registos[-1]))
    assert "nif-123456789" not in json.dumps(linha)
    assert linha["route"] is None
    assert linha["status_code"] == 200
    assert linha["method"] == "GET"


def test_um_extra_explicito_ganha_ao_contexto(coletor: _Coletor) -> None:
    """Quem loga em nome de outro tenant — o consumidor da outbox — diz qual."""
    logging.getLogger("apps.teste").info("evento", extra={"tenant_id": str(TENANT_B)})

    assert coletor.registos[-1].tenant_id == str(TENANT_B)


# ---------------------------------------------------------------------------
# Ordem na cadeia de middleware
# ---------------------------------------------------------------------------
def test_o_contexto_de_log_e_o_primeiro_middleware() -> None:
    """ARCHITECTURE.md §4: o `request_id` existe antes de qualquer coisa poder
    falhar — um 404 antes da view, uma recusa do middleware de segurança."""
    assert settings.MIDDLEWARE[0] == "apps.shared.middleware.RequestContextMiddleware"


def test_atomic_requests_continua_desligado() -> None:
    """Abriria a transação em volta da view, dentro da cadeia de middleware,
    onde nenhum middleware lhe consegue pôr o `set_config` (ADR 0005)."""
    assert settings.DATABASES["default"]["ATOMIC_REQUESTS"] is False
