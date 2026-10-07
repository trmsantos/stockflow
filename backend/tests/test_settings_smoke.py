"""Smoke tests da camada de configuração.

Não testam regras de negócio: testam que os quatro módulos de settings
importam, que os defaults perigosos ficam desligados e que o formatter de logs
não deixa passar campos fora da allowlist.

Nenhum destes testes toca na base de dados. O ambiente vem do `clean_env` do
`conftest.py` — nunca do shell de quem corre a suite.
"""

from __future__ import annotations

import copy
import json
import logging
import sys

import pytest
from django.conf import settings

from config.log import JsonFormatter, RequestContextFilter
from tests.conftest import reload_settings as _reload


def test_base_e_dev_importam(clean_env: None) -> None:
    base = _reload("base")
    dev = _reload("dev")

    assert base.DEBUG is False, "o default do base tem de ser fechado"
    assert base.ALLOWED_HOSTS == []
    assert dev.DEBUG is True
    assert dev.SECURE_SSL_REDIRECT is False
    assert dev.SECURE_HSTS_SECONDS == 0
    # Portas do ADR 0002: proxy, API e Vite.
    assert "http://localhost:8090" in dev.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:8010" in dev.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5183" in dev.CSRF_TRUSTED_ORIGINS


def test_debug_desligado_em_test_e_prod(prod_env: None) -> None:
    assert settings.DEBUG is False, "as settings ativas na suite são as de teste"
    assert _reload("test").DEBUG is False
    assert _reload("prod").DEBUG is False


def test_prod_traz_o_bloco_de_seguranca(prod_env: None) -> None:
    prod = _reload("prod")

    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_HSTS_SECONDS == 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.X_FRAME_OPTIONS == "DENY"
    # TLS verificado na ligação à BD (SECURITY.md §3).
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"


def test_prod_nao_muta_os_dicionarios_do_base(prod_env: None) -> None:
    """O `import *` traz a *referência* dos dicionários do `base`.

    Se o `prod.py` mutasse um deles em vez de construir um novo, a configuração
    de quem importasse o `base` noutro ambiente mudava com ele — e em produção
    isso é uma setting de segurança a aparecer onde não devia (ou a
    desaparecer). Este teste existe para travar essa mutação.

    Nota sobre o que **não** se pode assertar aqui: `django.conf.settings`
    guarda os objetos que o `config.settings.test` ligou no arranque da suite, e
    um `_reload("base")` cria dicionários novos. Depois do primeiro reload,
    `settings.DATABASES` é um objeto órfão, sem relação com o que o `prod.py`
    acabou de ler: uma asserção sobre ele passa aconteça o que acontecer no
    `prod.py`. O peso está em comparar o módulo `base` consigo mesmo, antes e
    depois de o `prod` ser lido.
    """
    base = _reload("base")
    antes = copy.deepcopy(
        {
            "DATABASES": base.DATABASES,
            "CONTENT_SECURITY_POLICY": base.CONTENT_SECURITY_POLICY,
            "REST_FRAMEWORK": base.REST_FRAMEWORK,
        }
    )

    prod = _reload("prod")

    # O prod mudou mesmo alguma coisa (senão o teste passava por vacuidade).
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"
    assert prod.CONTENT_SECURITY_POLICY["DIRECTIVES"]["upgrade-insecure-requests"] is True
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 1

    # E o base ficou exatamente como estava.
    assert base.DATABASES == antes["DATABASES"]
    assert base.CONTENT_SECURITY_POLICY == antes["CONTENT_SECURITY_POLICY"]
    assert base.REST_FRAMEWORK == antes["REST_FRAMEWORK"]
    assert "sslmode" not in base.DATABASES["default"].get("OPTIONS", {})

    # Objetos distintos até ao nível que o prod toca: é isto que impede uma
    # mutação futura de se propagar.
    assert prod.DATABASES is not base.DATABASES
    assert prod.DATABASES["default"] is not base.DATABASES["default"]
    assert prod.CONTENT_SECURITY_POLICY is not base.CONTENT_SECURITY_POLICY
    assert prod.REST_FRAMEWORK is not base.REST_FRAMEWORK


def test_argon2_a_frente_e_minimo_de_12_chars(prod_env: None) -> None:
    argon2 = "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert _reload("base").PASSWORD_HASHERS[0] == argon2
    assert _reload("prod").PASSWORD_HASHERS[0] == argon2
    # A suite corre com MD5 por velocidade, e é o único sítio onde isso vale
    # (ver o comentário em `config/settings/test.py`).
    assert settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]

    minimo = [
        validator
        for validator in settings.AUTH_PASSWORD_VALIDATORS
        if validator["NAME"].endswith("MinimumLengthValidator")
    ]
    assert minimo[0]["OPTIONS"]["min_length"] == 12


def test_sessao_expira_com_14_dias_de_inatividade() -> None:
    assert settings.SESSION_COOKIE_AGE == 14 * 24 * 60 * 60
    # Sem isto os 14 dias contariam desde o login, não desde o último pedido.
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_COOKIE_HTTPONLY is True


def test_csp_sem_unsafe_inline_e_sem_frames() -> None:
    directives = settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]

    assert directives["default-src"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert all("unsafe-inline" not in str(value) for value in directives.values())


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="apps.inventory",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="movimento registado",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_descarta_extra_fora_da_allowlist() -> None:
    record = _record(event="stock.movement.recorded", nif="123456789", email="a@b.pt")

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "movimento registado"
    assert payload["event"] == "stock.movement.recorded"
    # PII fora da allowlist não chega ao output — falha fechada.
    assert "nif" not in payload
    assert "email" not in payload


def test_request_context_filter_garante_os_campos_de_correlacao() -> None:
    record = _record()

    assert RequestContextFilter().filter(record) is True

    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] is None
    assert payload["tenant_id"] is None
    assert payload["user_id"] is None


# ---------------------------------------------------------------------------
# Onde a allowlist do `config/log.py` acaba. Os dois testes seguintes afirmam
# que os `%`-args e o traceback **passam em claro** — não é o comportamento
# desejável, é o comportamento real, e fica fixado em código para a convenção
# do docstring do `config/log.py` (PII só em `extra=`) não se perder em prosa.
# Se um dia houver um scrubber, estes dois testes é que mudam de sinal.
# ---------------------------------------------------------------------------
def test_allowlist_nao_cobre_a_mensagem_nem_os_percent_args() -> None:
    record = logging.LogRecord(
        name="apps.purchasing",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="fatura de %s para o NIF %s",
        args=("cliente@exemplo.pt", "123456789"),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "fatura de cliente@exemplo.pt para o NIF 123456789"


def test_allowlist_nao_cobre_o_traceback_da_excecao() -> None:
    try:
        raise ValueError("DETAIL: Key (nif)=(123456789) already exists.")
    except ValueError:
        record = logging.LogRecord(
            name="apps.purchasing",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="falha ao gravar o fornecedor",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "123456789" in payload["exception"]


@pytest.mark.parametrize(
    ("modulo", "esperado"),
    [("base", 0), ("dev", 0), ("test", 0), ("prod", 1)],
)
def test_num_proxies_definido_em_todos_os_ambientes(
    prod_env: None, modulo: str, esperado: int
) -> None:
    """Sem `NUM_PROXIES` o DRF usa o `X-Forwarded-For` cru como identidade.

    `BaseThrottle.get_ident` só ignora o header quando a setting existe: a
    `None` devolve o header todo concatenado, e o limite de `60/min` para
    anónimos contorna-se a rodar um valor qualquer no header. `0` = usa só o
    `REMOTE_ADDR`; em prod é o nº de proxies de confiança.
    """
    assert _reload(modulo).REST_FRAMEWORK["NUM_PROXIES"] == esperado
