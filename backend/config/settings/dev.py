"""Desenvolvimento local. Nada aqui é usado em produção.

As portas do host são as do ADR 0002 — nenhuma default, para não colidir com
outros projetos na mesma máquina: proxy 8090, API 8010, Vite 5183.
"""

from config.settings.base import *
from config.settings.base import CONTENT_SECURITY_POLICY, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    # `backend` é o nome do serviço na rede interna do compose: é por aí que o
    # proxy fala com o Django.
    default=["localhost", "127.0.0.1", "[::1]", "backend"],
)

# O browser carrega a app pelo proxy (8090) ou pelo Vite (5183) e a API pode
# ser chamada diretamente em 8010. Todas as origens precisam de estar aqui ou
# o POST leva 403 do CSRF.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:8090",
        "http://127.0.0.1:8090",
        "http://localhost:8010",
        "http://127.0.0.1:8010",
        "http://localhost:5183",
        "http://127.0.0.1:5183",
    ],
)

# Sem TLS em dev: forçar HTTPS aqui só dá redirects para um serviço que não
# existe, e o HSTS ficaria colado ao browser para todo o `localhost`.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Swagger disponível em `/api/v1/docs/` durante o desenvolvimento.
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)

# O Swagger UI vem de um CDN (não temos o pacote sidecar), por isso em dev — e
# só em dev — o CDN entra na CSP. A política de produção continua `'self'`.
#
# Isto é mais largo do que devia e está nomeado como dívida: a CSP é global à
# aplicação, logo o `unpkg` fica autorizado em **todas** as respostas do Django,
# incluindo o HTML do admin — que é o alvo de maior valor do SECURITY.md §5. O
# `django-csp` permite política por view (`@csp_replace`), e a saída limpa é o
# `drf-spectacular[sidecar]`, que tira o CDN e faz a política voltar a `'self'`
# em todos os ambientes. Em produção o `API_DOCS_ENABLED` é `False` e este
# ficheiro não é lido, logo o alcance é o ambiente de desenvolvimento.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        **CONTENT_SECURITY_POLICY["DIRECTIVES"],
        "script-src": [*CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"], "https://unpkg.com"],
        "style-src": [*CONTENT_SECURITY_POLICY["DIRECTIVES"]["style-src"], "https://unpkg.com"],
    },
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
