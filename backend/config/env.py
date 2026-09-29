"""Leitura de variáveis de ambiente que falha fechada.

O `environ.Env` levanta `ImproperlyConfigured` quando a variável **não existe**,
mas uma variável definida e vazia é para ele um valor legítimo. O resultado é o
oposto do que o docstring do `config/settings/base.py` promete: o processo
arranca em silêncio com configuração inválida e só parte mais tarde, longe da
causa.

Verificado por execução, antes deste módulo existir:

* `DATABASE_URL=""` → `env.db()` devolve `{"ENGINE": None, ...}` e o Django
  arranca; a falha aparece no primeiro acesso à BD, como erro de backend;
* `REDIS_URL=""` → `CELERY_BROKER_URL` fica `"/0"`;
* `ALLOWED_HOSTS=""` → lista vazia, ou seja, nenhum host aceite em produção.

Este módulo é a fronteira onde a promessa se cumpre:

* `required*` recusa o vazio com `ImproperlyConfigured` no momento em que as
  settings são lidas — o processo não arranca, que é o comportamento desejado;
* `optional` trata o vazio como "não definida", para que um `VAR=` sem valor num
  `.env` caia no default em vez de produzir um valor truncado;
* `admin_path` normaliza o path do admin, porque um `DJANGO_ADMIN_URL` sem barra
  final produz `reverse("admin:login") == "/gestao-internalogin/"` em silêncio.

Os valores são devolvidos já sem espaços nas pontas: um segredo montado a partir
de um ficheiro (Docker secret) traz `\\n` no fim com frequência, e um
`DJANGO_SECRET_KEY` que difere entre processos por causa de um `\\n` invalida
sessões de forma difícil de diagnosticar.
"""

from __future__ import annotations

import environ
from django.core.exceptions import ImproperlyConfigured


def _present(env: environ.Env, name: str) -> str:
    """Valor não vazio da variável `name`, sem espaços nas pontas.

    Levanta `ImproperlyConfigured` tanto se a variável não existir (o
    `environ.Env` já o faz) como se existir vazia (é o que este módulo
    acrescenta).
    """
    value = env.str(name).strip()
    if not value:
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} está definida mas vazia. "
            f"É obrigatória e não tem default: dá-lhe um valor "
            f"(ver .env.example e config/env.py)."
        )
    return value


def required(env: environ.Env, name: str) -> str:
    """String obrigatória. Sem ela — ou vazia — o processo não arranca."""
    return _present(env, name)


def required_list(env: environ.Env, name: str) -> list[str]:
    """Lista obrigatória separada por vírgulas, com pelo menos um elemento."""
    _present(env, name)
    items = [item.strip() for item in env.list(name) if item.strip()]
    if not items:
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} só tem separadores, sem valores. "
            f"Esperado: uma lista separada por vírgulas."
        )
    return items


def required_db(env: environ.Env, name: str) -> dict[str, object]:
    """Configuração de BD obrigatória, validada para ter um `ENGINE`.

    Sem a validação do `ENGINE` uma URL irreconhecível (ou vazia) dá um
    `DATABASES["default"]["ENGINE"] = None` que o Django aceita no arranque.
    """
    config: dict[str, object] = env.db_url_config(_present(env, name))
    if not config.get("ENGINE"):
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} não é uma URL de base de dados "
            f"reconhecida. Esperado, por exemplo: "
            f"postgres://utilizador:password@host:5432/nome."
        )
    return config


def optional(env: environ.Env, name: str, default: str) -> str:
    """Como `env(name, default=...)`, mas uma variável vazia cai no default.

    Usado nas variáveis de infraestrutura sem segredo (Redis, cache, path do
    admin): `REDIS_URL=` num `.env` passa a significar "usa o default de
    desenvolvimento" em vez de gerar `CELERY_BROKER_URL = "/0"`.
    """
    return env.str(name, default=default).strip() or default


def admin_path(value: str) -> str:
    """Normaliza o path do admin: sem barra à esquerda, com barra à direita.

    O `path()` do Django concatena o prefixo com as rotas do admin sem
    acrescentar separador: `"gestao-interna"` (sem barra) dá
    `reverse("admin:login") == "/gestao-internalogin/"`, que devolve 404 sem
    nenhum aviso. Em produção esta variável é obrigatória e escrita à mão, logo
    é exatamente onde o erro acontece.
    """
    path = value.strip().strip("/")
    if not path:
        raise ImproperlyConfigured(
            "DJANGO_ADMIN_URL não pode ser a raiz do site: o admin ficaria "
            "montado em '/' e taparia a API. Usa um path não óbvio "
            "(SECURITY.md §5)."
        )
    return f"{path}/"
