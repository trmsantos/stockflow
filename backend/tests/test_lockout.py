"""Defesa do login: escada de bloqueio e identificação do cliente.

Nada disto existia, e foi por isso que uma recursão infinita no
`config/lockout.py` passou à frente de um `/review`: com o
`AxesStandaloneBackend` à cabeça dos `AUTHENTICATION_BACKENDS`, *todos* os
logins davam 500 e nenhum teste falhava.

Nenhum teste deste ficheiro toca na base de dados — de propósito. O
`progressive_cooloff` está desenhado para não fazer queries (ver o docstring do
módulo), o que o torna testável sem Postgres; e a camada de armazenamento do
axes, onde ela aparece no caminho, é substituída por um duplo em memória.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_client_ip_address, get_client_username, get_cool_off
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import authenticate
from django.test import RequestFactory, override_settings

from config import lockout
from config.lockout import COOLOFF_STEPS, progressive_cooloff
from tests.conftest import reload_settings

#: Cenário usado nos testes de IP: um proxy de confiança, um cliente real e um
#: valor forjado pelo cliente no header.
PROXY_IP = "10.0.0.7"
CLIENTE_IP = "203.0.113.5"
FORJADO_IP = "9.9.9.9"

#: Credenciais que não conferem: os testes de recursão só querem percorrer o
#: caminho do axes, nunca autenticar ninguém.
CREDENCIAIS_ERRADAS = {"username": "ana@exemplo.pt", "password": "nao-confere"}


def _request(**atributos: Any):
    """Pedido de login com os atributos que o axes põe no request."""
    request = RequestFactory().post("/api/v1/auth/login/", {"username": "ana@exemplo.pt"})
    for nome, valor in atributos.items():
        setattr(request, nome, valor)
    return request


# ---------------------------------------------------------------------------
# A escada
# ---------------------------------------------------------------------------
def test_o_primeiro_degrau_e_o_piso_da_janela_de_contagem() -> None:
    """Trava a descida do primeiro degrau (SECURITY.md §5).

    O valor devolvido pelo `progressive_cooloff` é ao mesmo tempo o tempo de
    bloqueio e a janela em que as falhas são contadas
    (`axes/attempts.py:17` → `handlers/database.py:389`, que filtra por
    `attempt_time__gte=threshold`). Com o primeiro degrau a 1 minuto — como
    estava — um atacante a tentar uma password a cada 70 s nunca tranca: cada
    linha sai da janela antes de a quinta falha existir.
    """
    assert COOLOFF_STEPS[0] >= timedelta(minutes=30)
    assert list(COOLOFF_STEPS) == sorted(COOLOFF_STEPS), "a escada tem de ser crescente"
    assert COOLOFF_STEPS[-1] == timedelta(hours=24)


@pytest.mark.parametrize(
    ("excesso", "esperado"),
    [
        (0, timedelta(minutes=30)),
        (1, timedelta(hours=1)),
        (2, timedelta(hours=4)),
        (3, timedelta(hours=12)),
        (4, timedelta(hours=24)),
        (5, timedelta(hours=24)),
        (50, timedelta(hours=24)),
    ],
)
def test_cada_degrau_da_escada(excesso: int, esperado: timedelta) -> None:
    """Um caso por degrau, mais o teto, contando a partir do limite de falhas."""
    falhas = settings.AXES_FAILURE_LIMIT + excesso

    assert progressive_cooloff(_request(axes_failures_since_start=falhas)) == esperado


def test_abaixo_do_limite_de_falhas_fica_no_primeiro_degrau() -> None:
    for falhas in range(settings.AXES_FAILURE_LIMIT):
        assert progressive_cooloff(_request(axes_failures_since_start=falhas)) == COOLOFF_STEPS[0]


def test_sem_request_devolve_o_teto() -> None:
    """É assim que o axes o chama nos comandos de gestão: sem contexto."""
    assert progressive_cooloff() == COOLOFF_STEPS[-1]
    assert progressive_cooloff(None) == COOLOFF_STEPS[-1]


def test_falhas_a_none_ou_ausentes_caem_no_primeiro_degrau() -> None:
    """Os dois estados reais do atributo no caminho da decisão de lockout.

    O `AxesProxyHandler.update_request` põe `axes_failures_since_start = None`
    no início de cada pedido (`handlers/proxy.py:96`) e o número real só é
    atribuído em `handlers/database.py:247`, depois de o `get_cool_off` já ter
    sido chamado. Um pedido que nunca passou pelo axes não tem o atributo.
    """
    assert progressive_cooloff(_request(axes_failures_since_start=None)) == COOLOFF_STEPS[0]

    sem_atributo = _request()
    assert not hasattr(sem_atributo, "axes_failures_since_start")
    assert progressive_cooloff(sem_atributo) == COOLOFF_STEPS[0]


@override_settings(AXES_FAILURE_LIMIT=lambda request, credentials: 3)
def test_aceita_um_axes_failure_limit_callable() -> None:
    """`AXES_FAILURE_LIMIT` pode ser um callable (`axes/helpers.py:446`).

    A aritmética direta sobre `settings.AXES_FAILURE_LIMIT` dava `TypeError`
    nesse caso; a função usa o helper `get_failure_limit`, que resolve a
    setting sem voltar ao `get_cool_off`.
    """
    assert progressive_cooloff(_request(axes_failures_since_start=3)) == COOLOFF_STEPS[0]
    assert progressive_cooloff(_request(axes_failures_since_start=5)) == COOLOFF_STEPS[2]


# ---------------------------------------------------------------------------
# Ausência de recursão no caminho real
# ---------------------------------------------------------------------------
class _SemTentativas:
    """Duplo do queryset de `AccessAttempt`: zero falhas, zero base de dados.

    Substitui só a camada de armazenamento. Todo o resto do percurso —
    `is_allowed` → `is_locked` → `get_failures` → `get_user_attempts` →
    `get_cool_off_threshold` → `get_cool_off` → `progressive_cooloff` — corre
    tal como em produção, que é precisamente o percurso onde estava a recursão.
    """

    def filter(self, **kwargs: object) -> _SemTentativas:
        return self

    def aggregate(self, *args: object, **kwargs: object) -> dict[str, None]:
        return {"failures_since_start__sum": None}

    def delete(self) -> tuple[int, dict[str, int]]:
        return 0, {}


@pytest.fixture
def sem_tentativas_na_bd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        AccessAttempt.objects,
        "filter",
        lambda **kwargs: _SemTentativas(),
    )


@pytest.fixture
def vigia_reentrada(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Faz o `progressive_cooloff` falhar se for chamado de dentro de si mesmo.

    A recursão original era `progressive_cooloff` → `AxesProxyHandler.get_failures`
    → `get_user_attempts` → `get_cool_off_threshold` → `get_cool_off` →
    `progressive_cooloff`. Um `RecursionError` demora ~1000 níveis a aparecer;
    esta sentinela falha ao segundo, com uma mensagem que diz o que aconteceu.
    """
    profundidade: list[int] = []
    original = lockout.progressive_cooloff

    def vigiado(request: object = None) -> timedelta:
        if profundidade:
            raise AssertionError(
                "progressive_cooloff reentrou: alguma coisa nesta função voltou "
                "a chamar uma API do axes que passa pelo get_cool_off."
            )
        profundidade.append(1)
        try:
            return original(request)
        finally:
            profundidade.pop()

    # O axes resolve `AXES_COOLOFF_TIME` por `import_string` a cada chamada, por
    # isso é o atributo do módulo que tem de ser substituído.
    monkeypatch.setattr(lockout, "progressive_cooloff", vigiado)
    return profundidade


def test_get_cool_off_do_axes_nao_recorre() -> None:
    """O caminho mais curto do axes até esta função, sem duplos nenhuns."""
    assert get_cool_off(_request()) == COOLOFF_STEPS[0]


@override_settings(AXES_ENABLED=True)
def test_is_allowed_do_axes_nao_recorre(
    sem_tentativas_na_bd: None, vigia_reentrada: list[int]
) -> None:
    """A decisão de lockout completa, pela API que continha o ciclo."""
    request = _request()
    credenciais = {"username": "ana@exemplo.pt"}

    assert AxesProxyHandler.is_allowed(request, credenciais) is True
    # E a sentinela confirma que a função foi chamada (senão o teste não
    # provava nada) e nunca a mais de um nível.
    assert vigia_reentrada == []
    assert AxesProxyHandler.get_failures(request, credenciais) == 0


@override_settings(
    AXES_ENABLED=True,
    AUTHENTICATION_BACKENDS=["axes.backends.AxesStandaloneBackend"],
)
def test_authenticate_com_axes_ligado_nao_recorre(
    monkeypatch: pytest.MonkeyPatch,
    sem_tentativas_na_bd: None,
    vigia_reentrada: list[int],
) -> None:
    """`authenticate()` com o axes ligado: era aqui que dava `RecursionError`.

    Só o `AxesStandaloneBackend` nos `AUTHENTICATION_BACKENDS`: o
    `ModelBackend` iria buscar o utilizador à BD e não há Postgres nesta
    máquina.

    O `user_login_failed` do axes fica neutralizado. Esse ramo abre uma
    transação e escreve em três tabelas (`handlers/database.py:179`), o que
    exige Postgres; e passa pelo mesmo `get_cool_off` que os testes acima já
    cobrem — não é o ramo onde a recursão se manifestava primeiro, porque o
    backend corre antes dele.
    """
    monkeypatch.setattr(
        AxesProxyHandler,
        "user_login_failed",
        classmethod(lambda cls, *args, **kwargs: None),
    )

    # Sem lockout, o backend do axes devolve None e nenhum outro backend
    # autentica: o esperado é None, não uma exceção — e muito menos um
    # RecursionError.
    assert authenticate(request=_request(), **CREDENCIAIS_ERRADAS) is None
    assert vigia_reentrada == []


# ---------------------------------------------------------------------------
# Identificação do cliente atrás do proxy
# ---------------------------------------------------------------------------
@pytest.fixture
def ip_como_em_producao(prod_env: None):
    """Aplica ao processo de teste a configuração de IP do `prod.py`.

    Os valores vêm do módulo, não estão escritos aqui: se alguém voltar a pôr
    `AXES_IPWARE_PROXY_COUNT = TRUSTED_PROXY_COUNT` ou `strict`, estes testes
    ficam vermelhos.
    """
    prod = reload_settings("prod")
    with override_settings(
        AXES_IPWARE_META_PRECEDENCE_ORDER=prod.AXES_IPWARE_META_PRECEDENCE_ORDER,
        AXES_IPWARE_PROXY_ORDER=prod.AXES_IPWARE_PROXY_ORDER,
        AXES_IPWARE_PROXY_COUNT=prod.AXES_IPWARE_PROXY_COUNT,
        IPWARE_STRICT=prod.IPWARE_STRICT,
    ):
        yield prod


def _request_do_proxy(x_forwarded_for: str):
    return RequestFactory().post(
        "/api/v1/auth/login/",
        {"username": "ana@exemplo.pt"},
        HTTP_X_FORWARDED_FOR=x_forwarded_for,
        REMOTE_ADDR=PROXY_IP,
    )


def test_ipware_esta_instalado() -> None:
    """Sem o pacote, as três `AXES_IPWARE_*` do `prod.py` são letra morta.

    O `axes.helpers` faz `try: import ipware` e, sem ele, `IPWARE_INSTALLED`
    fica `False` e o `get_client_ip_address` devolve o `REMOTE_ADDR` — atrás do
    proxy, o mesmo endereço para todos os clientes. O lockout por par
    (IP, utilizador) degradava-se para só-utilizador em silêncio.
    """
    from axes import helpers

    assert helpers.IPWARE_INSTALLED is True


@pytest.mark.parametrize(
    ("cenario", "x_forwarded_for"),
    [
        ("cliente direto, o proxy escreve uma entrada", CLIENTE_IP),
        ("cliente a forjar uma entrada", f"{FORJADO_IP}, {CLIENTE_IP}"),
        ("cliente a forjar uma cadeia", f"{FORJADO_IP}, 8.8.8.8, {CLIENTE_IP}"),
    ],
)
def test_x_forwarded_for_forjado_resolve_para_o_cliente_real(
    ip_como_em_producao: object, cenario: str, x_forwarded_for: str
) -> None:
    """O cliente controla a *esquerda* do header; o proxy escreve a direita.

    Com um proxy de confiança, o endereço real é a última entrada, e é a única
    que conta. Tudo o que o cliente meta antes é ignorado, independentemente do
    comprimento.
    """
    resolvido = get_client_ip_address(_request_do_proxy(x_forwarded_for))

    assert resolvido == CLIENTE_IP, cenario


def test_cliente_numa_rede_privada_nao_e_impersonavel(ip_como_em_producao: object) -> None:
    """Regressão do caso que falha com `proxy_count=None`.

    Sem `proxy_count`, o python-ipware escolhe a primeira entrada *globalmente
    roteável* da cadeia: um cliente de LAN com um `9.9.9.9` forjado à frente
    resolvia para o valor forjado.
    """
    lan = "192.168.1.10"

    assert get_client_ip_address(_request_do_proxy(f"{FORJADO_IP}, {lan}")) == lan


def test_sem_x_forwarded_for_fica_o_remote_addr(ip_como_em_producao: object) -> None:
    request = RequestFactory().post("/api/v1/auth/login/", REMOTE_ADDR=PROXY_IP)

    assert get_client_ip_address(request) == PROXY_IP


def test_fora_de_producao_o_header_e_ignorado() -> None:
    """Em dev e em teste não há proxy: o `X-Forwarded-For` é texto do cliente.

    O default do axes para `AXES_IPWARE_META_PRECEDENCE_ORDER` é
    `("REMOTE_ADDR",)` e nem o `base.py` nem o `dev.py` o alteram, por isso o
    header não é lido. Fica em teste porque é uma garantia, não um acidente.
    """
    assert settings.AXES_IPWARE_META_PRECEDENCE_ORDER == ("REMOTE_ADDR",)
    assert get_client_ip_address(_request_do_proxy(f"{FORJADO_IP}, {CLIENTE_IP}")) == PROXY_IP


def test_throttle_de_anonimos_usa_a_mesma_ponta_do_header(prod_env: None) -> None:
    """O `NUM_PROXIES` do DRF e o `proxy_count` do ipware descrevem a mesma
    topologia, contada de formas diferentes (1 e 0 para um proxy).

    Reproduzido antes da correção: sem `NUM_PROXIES`, um `X-Forwarded-For`
    qualquer passava a ser a identidade do cliente anónimo e o limite de
    `60/min` contornava-se a rodar o header.
    """
    from rest_framework.throttling import AnonRateThrottle

    prod = reload_settings("prod")
    with override_settings(REST_FRAMEWORK=prod.REST_FRAMEWORK):
        ident = AnonRateThrottle().get_ident(_request_do_proxy(f"{FORJADO_IP}, {CLIENTE_IP}"))

    assert ident == CLIENTE_IP


# ---------------------------------------------------------------------------
# O campo que transporta a conta (SECURITY.md §5)
# ---------------------------------------------------------------------------
def test_o_contador_por_conta_do_axes_le_o_campo_email() -> None:
    """Sem `AXES_USERNAME_FORM_FIELD = "email"`, o eixo por conta desaparece.

    O `USERNAME_FIELD` do projeto é o `email` (ADR 0007), mas o default desta
    setting é `"username"` — e o `get_client_username` do axes vai buscar o nome
    exatamente a essa chave, seja em `credentials` seja no `request.POST`. Com o
    default, o `get` devolve `None` em **todos** os pedidos de login, o contador
    por conta agrupa a humanidade inteira sob a chave `None` e o eixo do
    SECURITY.md §5 que apanha password spraying (N IPs contra 1 conta) deixa de
    existir. Não há erro nem aviso: é a mesma classe de defeito do
    `django-ipware` — a configuração parece estar lá e o controlo não está.

    As duas metades do teste são necessárias: a primeira afirma que hoje
    funciona, a segunda que é **esta** setting que o faz. Sem a segunda, o teste
    passava com a setting apagada.
    """
    assert settings.AXES_USERNAME_FORM_FIELD == "email"
    # O eixo por conta existe nos parâmetros de lockout — `"username"` é o nome
    # interno do eixo no axes, não o nome do campo do formulário.
    assert "username" in settings.AXES_LOCKOUT_PARAMETERS

    pedido = RequestFactory().post("/api/v1/auth/login/", {"email": "ana@exemplo.pt"})

    assert get_client_username(pedido) == "ana@exemplo.pt"
    assert get_client_username(pedido, {"email": "ana@exemplo.pt"}) == "ana@exemplo.pt"

    with override_settings(AXES_USERNAME_FORM_FIELD="username"):
        assert get_client_username(pedido) is None
        assert get_client_username(pedido, {"email": "ana@exemplo.pt"}) is None
