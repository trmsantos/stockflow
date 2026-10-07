"""Os dois endpoints de saúde, e as propriedades que os tornam úteis.

O que aqui se prova não é que `/healthz` devolve 200 — é que continua a
devolver 200 **nas condições em que um healthcheck corre**: de dentro do
contentor, sem sessão, sem cookies, sem tenant, sem throttle e sem base de
dados. Cada uma dessas condições é uma forma de o endpoint ficar
permanentemente vermelho e de o orquestrador reiniciar contentores em ciclo,
que é um modo de falha pior do que não ter healthcheck nenhum.

A propriedade mais fácil de perder num refactor é a de zero queries: basta
alguém trocar a view por um `APIView` (e herdar o `IsAuthenticated` e o
`AnonRateThrottle` do `base.py`) ou acrescentar uma verificação "só para
confirmar que a base de dados está lá" — que é exatamente o que o `/readyz`
existe para não obrigar ninguém a fazer no `/healthz`.

Ver `config/health.py` para o desenho e para a diferença entre liveness e
readiness.
"""

from __future__ import annotations

from typing import NoReturn

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, OperationalError, connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator

from apps.accounts.api import dispensa_declarada
from config import health
from tests.conftest import reload_settings as _reload

URL_HEALTHZ = "/healthz"
URL_READYZ = "/readyz"

#: Um endpoint da API, para servir de controlo: é servido **com** âmbito e leva
#: o `IsAuthenticated` do `base.py`. Sempre que um teste aqui afirma que a
#: saúde é uma exceção, este é o caso normal com que se compara.
URL_DA_API = "/api/v1/schema/"


# ---------------------------------------------------------------------------
# 1. Liveness: 200 nas condições em que um healthcheck corre
# ---------------------------------------------------------------------------
def test_healthz_responde_200_sem_sessao_sem_cookies_e_sem_tenant() -> None:
    """O pedido que o `HEALTHCHECK` do Docker faz, tal como o faz.

    Sem `login()`, sem cookies e sem `tenant_id` na sessão. Com o default do
    `TenantMiddleware` — ter âmbito — isto seria 403 `sem_sessao`; com o
    `IsAuthenticated` do DRF seria 403 também. É a dispensa declarada na view
    que o torna 200.
    """
    cliente = Client()

    resposta = cliente.get(URL_HEALTHZ)

    assert resposta.status_code == 200
    assert not cliente.cookies, "um healthcheck não manda cookies"
    # E também não recebe nenhum: um endpoint que criasse sessão por pedido
    # enchia a `django_session` a um pedido a cada 10 segundos por contentor.
    assert "Set-Cookie" not in resposta


def test_healthz_nao_revela_nada_e_nao_e_cacheavel() -> None:
    """Corpo mínimo: sem versão, sem nome de host, sem lista de dependências.

    A asserção é de igualdade exata, de propósito. Qualquer campo que alguém
    acrescente — "só a versão, para saber o que está em produção" — falha aqui,
    que é onde a conversa deve acontecer.
    """
    resposta = Client().get(URL_HEALTHZ)

    assert resposta.content == health.CORPO_OK
    assert resposta["Content-Type"] == "text/plain; charset=utf-8"
    # Uma resposta de saúde guardada em cache é uma resposta que mente.
    assert resposta["Cache-Control"] == "no-store"


def test_healthz_nao_toca_na_base_de_dados(db: None) -> None:
    """Zero queries. É a propriedade que mais facilmente se perde.

    Também é a prova de que não se abriu âmbito de tenant: o `tenant_scope`
    corre `SELECT set_config('app.tenant_id', %s, true)` como primeira
    instrução da transação do pedido (ADR 0005), logo uma transação aberta
    aparecia aqui como uma query.
    """
    with CaptureQueriesContext(connection) as queries:
        resposta = Client().get(URL_HEALTHZ)

    assert resposta.status_code == 200
    assert list(queries.captured_queries) == [], (
        "o /healthz tocou na base de dados. Se a verificação que precisas é da "
        "base de dados, o endpoint é o /readyz: um healthcheck que falha quando "
        "o Postgres cai faz o orquestrador reiniciar contentores que estão bons."
    )


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_healthz_so_responde_a_get_e_head(metodo: str) -> None:
    """405 para tudo o que não seja um método seguro, e sem abrir transação.

    Um endpoint sem autenticação não tem razão para aceitar um corpo de
    pedido. O `Client()` do Django não impõe CSRF, pelo que o que este teste
    mede é o contrato da **view** — ver o teste seguinte para o que um POST
    leva em produção.
    """
    resposta = getattr(Client(), metodo)(URL_HEALTHZ)

    assert resposta.status_code == 405
    assert sorted(resposta["Allow"].replace(" ", "").split(",")) == ["GET", "HEAD"]


@pytest.mark.parametrize("url", [URL_HEALTHZ, URL_READYZ])
def test_um_post_e_recusado_duas_vezes_e_a_primeira_e_o_csrf(url: str) -> None:
    """Em produção um POST leva 403 do CSRF e nunca chega ao 405 da view.

    Medido com o gunicorn e o `config.settings.prod`: `POST /healthz` sem token
    responde 403, porque o `CsrfViewMiddleware` corre antes da resolução da
    view. O `require_safe` é a segunda recusa, e é a que vale se um dia alguém
    puser um `@csrf_exempt` aqui — daí existirem as duas.

    O `enforce_csrf_checks=True` é o que faz o cliente de teste comportar-se
    como um browser: sem ele, a suite media 405 e produção respondia 403.
    """
    resposta = Client(enforce_csrf_checks=True).post(url)

    assert resposta.status_code == 403


def test_healthz_responde_a_head() -> None:
    """O HEAD é o pedido mais barato que prova o mesmo, e há healthchecks que o
    usam. Se o `require_safe` fosse um `require_GET`, estes falhariam com 405 e
    o contentor ficava permanentemente unhealthy."""
    assert Client().head(URL_HEALTHZ).status_code == 200


# ---------------------------------------------------------------------------
# 2. Fora do âmbito de tenant e fora do throttle
# ---------------------------------------------------------------------------
def test_as_duas_views_de_saude_declaram_dispensa_de_ambito() -> None:
    """A dispensa é declarada na view (ADR 0007) e o default é ter âmbito.

    A lista fechada das dispensas do `ROOT_URLCONF` está afirmada nos dois
    sentidos em `tests/test_rls_isolation.py`; aqui fixa-se a razão pela qual
    estas duas a têm: sem dispensa, o `TenantMiddleware` abria uma transação
    por cada verificação — a cada 10 segundos, por contentor — e respondia 403.
    """
    for caminho in (URL_HEALTHZ, URL_READYZ):
        assert dispensa_declarada(resolve(caminho).func), caminho


def test_healthz_esta_fora_do_throttle() -> None:
    """Com o limite de anónimos a 1/min, cinco verificações seguidas dão 200.

    Um 429 no healthcheck derruba o contentor, e o `AnonRateThrottle` do
    `base.py` conta por IP — o contentor partilharia o contador com o tráfego
    anónimo que venha do mesmo endereço. O teste falha no dia em que estas views
    passarem a ser do DRF e herdarem o `DEFAULT_THROTTLE_CLASSES`.
    """
    cache.clear()
    # O resto da configuração do DRF fica como está: o que se mexe é o limite,
    # e só o limite.
    limite_de_um = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"user": "1/min", "anon": "1/min"},
    }

    with override_settings(REST_FRAMEWORK=limite_de_um):
        estados = [Client().get(URL_HEALTHZ).status_code for _ in range(5)]

    assert estados == [200] * 5


def test_nenhum_dos_dois_entra_no_schema_da_api() -> None:
    """Não são API: não têm cliente gerado nem lugar no `pnpm gen:api`.

    Vivem fora do `SCHEMA_PATH_PREFIX` (`/api/v1`) e não são views do DRF, e é
    a soma das duas coisas que os mantém fora do `schema.yml`.
    """
    caminhos = SchemaGenerator().get_schema(request=None, public=True).get("paths") or {}

    assert URL_HEALTHZ not in caminhos
    assert URL_READYZ not in caminhos


# ---------------------------------------------------------------------------
# 3. O `Host` e o redirect para HTTPS — as duas formas de nunca chegar à view
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=["stockflow.example.pt"])
def test_o_host_do_pedido_tem_de_estar_em_allowed_hosts() -> None:
    """O contrato do `HEALTHCHECK` do Dockerfile, fixado pelos dois lados.

    O `CommonMiddleware` chama `request.get_host()` em **todos** os pedidos,
    logo um `Host` fora do `ALLOWED_HOSTS` é 400 antes de qualquer view — e o
    healthcheck chega com o `Host` do contentor (`127.0.0.1:8000`), enquanto o
    `ALLOWED_HOSTS` de produção tem o domínio real. A resolução é o healthcheck
    mandar `Host: <domínio que está em ALLOWED_HOSTS>`, e não um `*` na lista
    (proibido pelo CLAUDE.md) nem `localhost` acrescentado a ela.

    Este teste existe para que a próxima pessoa veja o modo de falha escrito em
    código antes de o "corrigir" na setting errada.
    """
    cliente = Client()

    com_o_header_certo = cliente.get(URL_HEALTHZ, headers={"host": "stockflow.example.pt"})
    com_o_host_do_contentor = cliente.get(URL_HEALTHZ, headers={"host": "127.0.0.1:8000"})

    assert com_o_header_certo.status_code == 200
    assert com_o_host_do_contentor.status_code == 400


@override_settings(SECURE_SSL_REDIRECT=True)
def test_a_saude_nao_e_redirecionada_para_https(db: None) -> None:
    """O healthcheck corre em HTTP simples, de dentro do contentor.

    Sem o `SECURE_REDIRECT_EXEMPT` do `base.py`, o `SecurityMiddleware`
    responderia 301 para `https://<domínio>` — que o `curl -f` conta como
    sucesso (o contentor ficava "saudável" sem tocar na aplicação) e que um
    `curl -fL` seguiria para fora do contentor, verificando outra instância.

    O `Client()` é construído **dentro** do override porque o
    `SecurityMiddleware` lê a setting no `__init__` e cada cliente monta a sua
    cadeia de middleware. O controlo é um endpoint normal: esse **é**
    redirecionado, senão este teste passava por o redirect não estar ligado.

    O `db` é pelo `/readyz`, que faz o seu `SELECT 1` de verdade — é o único
    teste deste bloco que precisa da base de dados, e precisa por isso.
    """
    cliente = Client()

    assert cliente.get(URL_HEALTHZ).status_code == 200
    assert cliente.get(URL_READYZ).status_code == 200
    assert cliente.get(URL_DA_API).status_code == 301


def test_a_lista_de_paths_isentos_de_redirect_e_exatamente_a_da_saude(
    prod_env: None,
) -> None:
    """A duplicação entre `SECURE_REDIRECT_EXEMPT` e as rotas, fixada.

    As settings não podem importar `config.urls` (importaria modelos durante a
    leitura das settings), logo os dois paths estão escritos nos dois sítios. O
    que impede que divirjam é este teste: cada regex da lista tem de resolver
    para uma view de `config/health.py`, e cada endpoint de saúde tem de estar
    na lista. E em produção o redirect está ligado — sem isso a lista não
    protegia nada.
    """
    prod = _reload("prod")
    assert prod.SECURE_SSL_REDIRECT is True

    paths_isentos = {
        regex.removeprefix("^").removesuffix("$") for regex in prod.SECURE_REDIRECT_EXEMPT
    }

    assert paths_isentos == {URL_HEALTHZ.lstrip("/"), URL_READYZ.lstrip("/")}
    for path in paths_isentos:
        assert resolve(f"/{path}").func.__module__ == health.__name__


# ---------------------------------------------------------------------------
# 4. Readiness: a que **inclui** a base de dados
# ---------------------------------------------------------------------------
class _LigacaoMorta:
    """Uma ligação cujo `cursor()` levanta o que o psycopg levanta em baixo.

    O `django.db.OperationalError` é o que o Django devolve quando o servidor
    não aceita a ligação; é subclasse de `DatabaseError`, que é o que o
    `_a_base_de_dados_responde` apanha. A alternativa — apontar o `DATABASES`
    para uma porta morta — deixava a alias `default` alterada para os testes
    seguintes e dependia de nada estar à escuta nessa porta na máquina de quem
    corre a suite.
    """

    def cursor(self) -> NoReturn:
        raise OperationalError("could not connect to server: Connection refused")


def test_readyz_faz_uma_ida_e_volta_a_base_de_dados(db: None) -> None:
    """A diferença que justifica o segundo endpoint, medida.

    Um `ensure_connection()` não serviria: com `CONN_MAX_AGE = 60` a ligação é
    persistente e o `ensure_connection` de uma ligação já aberta não fala com o
    servidor — devolvia 200 sobre uma ligação morta.
    """
    with CaptureQueriesContext(connection) as queries:
        resposta = Client().get(URL_READYZ)

    assert resposta.status_code == 200
    assert resposta.content == health.CORPO_OK
    sqls = [q["sql"].strip().upper() for q in queries.captured_queries]
    assert any(sql.startswith("SELECT 1") for sql in sqls), sqls


def test_readyz_da_503_e_healthz_continua_200_quando_a_base_de_dados_cai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A assimetria é a razão de existirem dois endpoints.

    Com o Postgres em baixo: o `/readyz` diz "não me mandes tráfego" (503, e o
    balanceador tira a instância da rotação, que recupera sozinha quando a
    dependência voltar) e o `/healthz` continua verde, porque o processo está
    bom e reiniciá-lo não repara uma dependência externa — reiniciaria **todos**
    os contentores ao mesmo tempo, no pior momento possível.

    O corpo do 503 não leva a exceção: a mensagem de um erro de ligação
    transporta host, porta e nome da base de dados.
    """
    monkeypatch.setattr(health, "connections", {DEFAULT_DB_ALIAS: _LigacaoMorta()})

    ready = Client().get(URL_READYZ)
    live = Client().get(URL_HEALTHZ)

    assert ready.status_code == 503
    assert ready.content == health.CORPO_INDISPONIVEL
    assert b"Connection refused" not in ready.content
    assert live.status_code == 200


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_readyz_so_responde_a_get_e_head(metodo: str) -> None:
    """Sem `db`: o 405 é decidido antes da view, logo nada chega ao `SELECT 1`."""
    assert getattr(Client(), metodo)(URL_READYZ).status_code == 405
