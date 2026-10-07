"""A camada de settings recusa configuração inválida no arranque.

O `base.py` promete "falha fechada" no docstring, mas o `environ.Env` só levanta
quando a variável **não existe**: `DATABASE_URL=""` arrancava em silêncio com
`ENGINE = None` e `REDIS_URL=""` produzia `CELERY_BROKER_URL = "/0"`. Quem
cumpre a promessa é o `config/env.py`, e é isso que se testa aqui.

Nenhum destes testes toca na base de dados: a validação acontece a ler as
settings, antes de haver ligação.
"""

from __future__ import annotations

import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import clear_url_caches, reverse

from config.env import admin_path
from tests.conftest import reload_settings


# ---------------------------------------------------------------------------
# Obrigatórias em qualquer ambiente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome", ["DATABASE_URL", "DJANGO_SECRET_KEY"])
def test_variavel_obrigatoria_vazia_nao_arranca(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, nome: str
) -> None:
    monkeypatch.setenv(nome, "")

    with pytest.raises(ImproperlyConfigured, match=nome):
        reload_settings("base")


@pytest.mark.parametrize("nome", ["DATABASE_URL", "DJANGO_SECRET_KEY"])
def test_variavel_obrigatoria_ausente_nao_arranca(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, nome: str
) -> None:
    monkeypatch.delenv(nome)

    with pytest.raises(ImproperlyConfigured, match=nome):
        reload_settings("base")


# O django-environ avisa antes de devolver o dicionário sem ENGINE; o aviso é
# esperado neste teste e é precisamente o que o `required_db` transforma em erro.
@pytest.mark.filterwarnings("ignore:Engine not recognized from url:UserWarning")
def test_database_url_irreconhecivel_nao_arranca(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem esta validação ficava `DATABASES["default"]["ENGINE"] = None`.

    O Django aceita isso no arranque e só parte no primeiro acesso à BD, longe
    da causa.
    """
    monkeypatch.setenv("DATABASE_URL", "isto-nao-e-uma-url")

    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL"):
        reload_settings("base")


def test_redis_url_vazio_cai_no_default_em_vez_de_gerar_barra_zero(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", "")

    base = reload_settings("base")

    assert base.REDIS_URL == "redis://localhost:6389"
    assert base.CELERY_BROKER_URL == "redis://localhost:6389/0"
    assert base.CELERY_RESULT_BACKEND == "redis://localhost:6389/1"
    assert base.CACHES["default"]["LOCATION"] == "redis://localhost:6389/2"


# ---------------------------------------------------------------------------
# Obrigatórias só em produção
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "nome",
    ["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "DJANGO_ADMIN_URL", "REDIS_URL"],
)
def test_variavel_de_prod_vazia_nao_arranca(
    prod_env: None, monkeypatch: pytest.MonkeyPatch, nome: str
) -> None:
    monkeypatch.setenv(nome, "")

    with pytest.raises(ImproperlyConfigured, match=nome):
        reload_settings("prod")


def test_allowed_hosts_so_com_separadores_nao_arranca(
    prod_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", " , , ")

    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        reload_settings("prod")


def test_prod_com_o_ambiente_completo_arranca(prod_env: None) -> None:
    """Contraprova: sem ela, os testes acima passavam com qualquer erro."""
    prod = reload_settings("prod")

    assert prod.ALLOWED_HOSTS == ["stockflow.example.pt"]
    assert prod.CSRF_TRUSTED_ORIGINS == ["https://stockflow.example.pt"]
    assert prod.ADMIN_URL == "gestao-interna/"
    assert prod.REDIS_URL == "redis://redis:6379"


def test_espacos_nas_pontas_sao_removidos(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um segredo montado de um ficheiro traz `\\n` no fim com frequência.

    Dois processos a discordar de um `\\n` no `DJANGO_SECRET_KEY` invalidam
    sessões de forma difícil de diagnosticar.
    """
    esperado = "chave-de-teste-com-espacos-em-volta"
    monkeypatch.setenv("DJANGO_SECRET_KEY", f"  {esperado}  \n")

    assert reload_settings("base").SECRET_KEY == esperado


# ---------------------------------------------------------------------------
# Path do admin
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("gestao-interna", "gestao-interna/"),
        ("gestao-interna/", "gestao-interna/"),
        ("/gestao-interna", "gestao-interna/"),
        ("/gestao-interna/", "gestao-interna/"),
        ("  gestao-interna  ", "gestao-interna/"),
    ],
)
def test_admin_path_normaliza(valor: str, esperado: str) -> None:
    assert admin_path(valor) == esperado


@pytest.mark.parametrize("valor", ["", "   ", "/", "///"])
def test_admin_path_recusa_a_raiz(valor: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="DJANGO_ADMIN_URL"):
        admin_path(valor)


@pytest.fixture
def urlconf_restaurada():
    """Reconstrói a URLconf no fim, para não contaminar os outros testes."""
    yield
    importlib.reload(importlib.import_module("config.urls"))
    clear_url_caches()


def test_admin_url_sem_barra_final_continua_a_resolver(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    urlconf_restaurada: None,
) -> None:
    """Era este o erro silencioso: `/gestao-internalogin/`.

    O `path()` do Django concatena o prefixo com as rotas do admin sem
    acrescentar separador. Em produção a variável é obrigatória e escrita à
    mão, por isso é exatamente onde a barra se esquece.
    """
    monkeypatch.setenv("DJANGO_ADMIN_URL", "gestao-interna")

    base = reload_settings("base")
    assert base.ADMIN_URL == "gestao-interna/"

    with override_settings(ADMIN_URL=base.ADMIN_URL):
        importlib.reload(importlib.import_module("config.urls"))
        clear_url_caches()

        assert reverse("admin:login") == "/gestao-interna/login/"
        assert reverse("admin:index") == "/gestao-interna/"
