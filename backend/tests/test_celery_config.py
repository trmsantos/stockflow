"""A configuração efetiva do Celery, não a que está escrita nas settings.

O `app.config_from_object("django.conf:settings", namespace="CELERY")` só lê as
settings com o prefixo `CELERY_`. Um prefixo errado (`CELERYD_`, `CELERY_TASK_`
onde a chave é outra, um nome inventado) é **ignorado em silêncio**: a setting
fica no ficheiro, ninguém a lê, e o worker corre com o default do Celery. Estas
asserções são sobre o `app.conf`, do lado de dentro, e é isso que as torna
úteis.

Também se verifica aqui o `DJANGO_SETTINGS_MODULE` por omissão dos
entrypoints — o `config/__init__.py` importa a app Celery, logo o default que
estiver no `config/celery.py` decide as settings de qualquer processo que
importe `config` sem a variável definida.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.conf import settings

from config.celery import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_acks_late_e_reject_on_worker_lost() -> None:
    """Perder uma tarefa é pior do que repetir uma: as tarefas são idempotentes
    por `event_id` (ARCHITECTURE.md §4)."""
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True


def test_limites_de_tempo() -> None:
    assert app.conf.task_time_limit == 10 * 60
    assert app.conf.task_soft_time_limit == 9 * 60
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit, (
        "o soft limit tem de disparar antes do hard limit, senão nunca corre"
    )


def test_visibility_timeout_maior_que_o_time_limit() -> None:
    """Senão o broker reentrega a tarefa a outro worker enquanto ela corre.

    Com `task_acks_late`, a mensagem só é confirmada no fim; se o
    `visibility_timeout` expirar antes, a mesma tarefa passa a correr duas
    vezes em paralelo.
    """
    visibility_timeout = app.conf.broker_transport_options["visibility_timeout"]

    assert visibility_timeout > app.conf.task_time_limit


def test_serializacao_so_em_json() -> None:
    """`pickle` no broker é execução remota de código (SECURITY.md §1)."""
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert list(app.conf.accept_content) == ["json"]


def test_prefetch_de_um_e_reciclagem_do_worker() -> None:
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.worker_max_tasks_per_child == 200


def test_fuso_horario() -> None:
    assert app.conf.timezone == "Europe/Lisbon"
    assert app.conf.enable_utc is True


def test_em_teste_as_tarefas_correm_em_processo() -> None:
    """Sem worker nem Redis na suite, e com as exceções a propagar.

    Se o `CELERY_TASK_ALWAYS_EAGER` do `config/settings/test.py` deixasse de ser
    lido, os testes que chamem uma tarefa passariam a tentar falar com um broker
    que não existe.
    """
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert app.conf.task_always_eager is True
    assert app.conf.task_eager_propagates is True
    assert app.conf.broker_url == "memory://"


# ---------------------------------------------------------------------------
# DJANGO_SETTINGS_MODULE por omissão
# ---------------------------------------------------------------------------
def _default_settings_module(caminho_relativo: str) -> str:
    """Extrai o literal do `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)`.

    Por AST e não em runtime: durante a suite a variável já está definida (vem
    do `pyproject.toml`), logo o `setdefault` é um no-op e não há nada para
    observar no processo.
    """
    arvore = ast.parse((BACKEND_DIR / caminho_relativo).read_text(encoding="utf-8"))
    for node in ast.walk(arvore):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setdefault"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "DJANGO_SETTINGS_MODULE"
            and isinstance(node.args[1], ast.Constant)
        ):
            return str(node.args[1].value)
    raise AssertionError(
        f"{caminho_relativo} não tem "
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "<módulo>")'
    )


@pytest.mark.parametrize("entrypoint", ["config/celery.py", "config/wsgi.py", "config/asgi.py"])
def test_entrypoints_de_servidor_fazem_default_para_prod(entrypoint: str) -> None:
    """Os três têm de concordar.

    O `config/__init__.py` importa a app Celery, por isso um default de `dev` no
    `config/celery.py` fixava `dev` em qualquer processo que importasse `config`
    sem a variável definida — incluindo um worker de produção, que passava a
    correr com `DEBUG=True`, a BD sem `sslmode=verify-full` e o email para a
    consola. Em silêncio.
    """
    assert _default_settings_module(entrypoint) == "config.settings.prod"


def test_manage_py_faz_default_para_dev() -> None:
    """O `manage.py` é CLI de desenvolvimento e fica em `dev` de propósito."""
    assert _default_settings_module("manage.py") == "config.settings.dev"
