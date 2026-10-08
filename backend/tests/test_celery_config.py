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

E, desde 2026-10-08, o **`beat`**: a entrada agendada (o consumidor da outbox, a
cada 5 s) e o serviço do `docker/compose.yml` que a corre. O serviço entra neste
ficheiro e não noutro porque o que se afirma dele é configuração de Celery que
não cabe nas settings: onde o agendador guarda o estado é uma consequência do
`read_only` e do `tmpfs` do contentor, e as três linhas só se leem juntas lá.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.conf import settings

from apps.shared.tasks import consumir_outbox
from config.celery import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
COMPOSE = BACKEND_DIR.parent / "docker" / "compose.yml"


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


# ---------------------------------------------------------------------------
# O `beat`: a única entrada agendada, e onde ele guarda o estado
# ---------------------------------------------------------------------------
def test_o_beat_agenda_o_consumidor_da_outbox_a_cada_cinco_segundos() -> None:
    """A entrada do `beat`, lida do `app.conf` e não do ficheiro de settings.

    O `beat_schedule` é uma setting com prefixo `CELERY_`, logo está sujeita ao
    modo de falha que este ficheiro inteiro existe para apanhar: um prefixo
    errado é ignorado em silêncio e o agendador corre sem entrada nenhuma — a
    outbox deixava de ser lida e **nada** falhava.

    O nome da tarefa é comparado com o `name` da tarefa real e não com um
    literal. É a asserção que apanha o defeito de 2026-10-08 do outro lado: um
    nome que não casa com nenhuma tarefa registada dá `Received unregistered
    task`, e o `beat` publicaria para o vazio a cada cinco segundos.
    """
    entrada = app.conf.beat_schedule["consumir-outbox"]

    assert entrada["task"] == consumir_outbox.name == "shared.consumir_outbox"
    assert entrada["schedule"] == 5.0
    # `expires`: um worker em baixo uma hora deixaria 720 passagens na fila, e ao
    # voltar corria-as todas para fazer o trabalho de uma.
    assert entrada["options"]["expires"] == 60
    assert entrada["schedule"] < entrada["options"]["expires"], (
        "uma mensagem que expira antes do intervalo seguinte é uma passagem que "
        "nunca corre"
    )


def _servico_do_compose(nome: str) -> dict[str, Any]:
    """Um serviço do `docker/compose.yml`, lido como YAML.

    Por `yaml.safe_load` e não por `grep`: o que interessa é a relação entre três
    campos do **mesmo** serviço, e casar isso com expressões regulares num
    ficheiro de 300 linhas dava um teste que passa com o bloco errado. O PyYAML
    já está instalado (é dependência do `drf-spectacular`), logo isto não
    acrescenta dependência nenhuma.
    """
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return compose["services"][nome]


def test_o_beat_guarda_o_estado_no_tmpfs_do_contentor() -> None:
    """As três linhas que têm de concordar, afirmadas juntas.

    O `beat` guarda a última execução de cada entrada num ficheiro. O default é
    o directório de trabalho — `/app` na imagem — e o contentor corre com
    `read_only: true`: sem `--schedule`, o processo morre no arranque e o
    sintoma é a outbox a parar de ser lida, não um erro no sítio do defeito.

    Logo as três condições são uma: `read_only`, `/tmp` em `tmpfs`, e o
    `--schedule` a apontar para lá. Este teste é o que as liga — mexer numa sem
    as outras fica vermelho aqui em vez de ficar verde e partido.
    """
    beat = _servico_do_compose("beat")
    comando = beat["command"]

    assert beat["read_only"] is True
    assert "beat" in comando, "este serviço devia correr o agendador"
    caminho = comando[comando.index("--schedule") + 1]
    # A asserção é a **relação** entre os dois campos e não o caminho literal: o
    # que tem de ser verdade é que o `--schedule` cai dentro de uma montagem
    # escrevível declarada por este serviço. Mudar o ficheiro para outra montagem
    # continua a passar; tirar a montagem e deixar o caminho, não.
    montagens = beat["tmpfs"]
    assert any(caminho.startswith(f"{montagem}/") for montagem in montagens), (
        f"o --schedule aponta para {caminho}, fora das montagens escrevíveis "
        f"deste serviço ({montagens}) — num rootfs read_only o beat morre no "
        f"arranque"
    )


def test_o_beat_nao_herda_o_healthcheck_http_da_imagem() -> None:
    """Pela mesma razão do `worker`, e é obrigatório dizê-lo.

    A imagem é partilhada com o `backend` e traz um `HEALTHCHECK` que faz um
    pedido HTTP a `127.0.0.1:8000`. Um agendador não serve HTTP: sem isto fica
    `unhealthy` para sempre, o que num orquestrador é um ciclo de reinícios de um
    processo que está bem — e no CI é o gate da stack a falhar por uma razão que
    não é a que ele testa.
    """
    assert _servico_do_compose("beat")["healthcheck"] == {"disable": True}
    assert _servico_do_compose("worker")["healthcheck"] == {"disable": True}


def test_so_ha_um_beat_e_ele_nao_e_uma_flag_do_worker() -> None:
    """Duas instâncias publicam cada entrada duas vezes.

    O `celery worker --beat` existe e é expressamente para desenvolvimento:
    amarra o agendador ao ciclo de vida de um worker, logo um `--scale worker=3`
    inocente passava a ter três agendadores. Este teste é o que o impede de
    entrar por distracção.
    """
    worker = _servico_do_compose("worker")["command"]

    assert "--beat" not in worker
    assert "-B" not in worker
