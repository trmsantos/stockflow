"""Produção. O bloco obrigatório está em SECURITY.md §2 — copiado aqui na
íntegra, linha por linha, para que uma auditoria possa comparar os dois
ficheiros lado a lado. Os `...` do documento estão expandidos nos valores
concretos.

`uv run manage.py check --deploy` tem de passar **sem warnings**
(SECURITY.md §2 e §9).
"""

from config.env import admin_path, optional, required, required_list
from config.settings.base import *
from config.settings.base import CONTENT_SECURITY_POLICY, DATABASES, REST_FRAMEWORK, env

#: Nº de proxies de confiança à frente do Django. Lido aqui porque é usado em
#: dois sítios que têm de concordar: a identidade do cliente no throttle do DRF
#: (logo abaixo) e no lockout do axes (bloco "IP do cliente atrás do proxy", no
#: fim do ficheiro, onde a convenção está explicada por inteiro).
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=1)

# --- SECURITY.md §2 -------------------------------------------------------
DEBUG = False
ALLOWED_HOSTS = required_list(env, "ALLOWED_HOSTS")
SECRET_KEY = required(env, "DJANGO_SECRET_KEY")  # >= 50 chars, rotacionável

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = required_list(env, "CSRF_TRUSTED_ORIGINS")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [  # mínimo 12 chars, não comum, não numérico
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# O spread mantém as chaves de base (schema, paginação, renderers): substituir
# o dicionário todo faria a API de produção divergir da de desenvolvimento e do
# cliente gerado pelo `pnpm gen:api`.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min", "anon": "60/min"},
    # Atrás do proxy, a identidade do cliente anónimo. Ver o comentário no
    # `base.py` e o bloco do ipware no fim deste ficheiro: o DRF conta a
    # posição do cliente a partir da *direita* do X-Forwarded-For
    # (`addrs[-NUM_PROXIES]`), que é a ponta que o proxy escreve e o cliente
    # não controla.
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# --- fim do bloco de SECURITY.md §2 ---------------------------------------

# O TLS termina no proxy (ARCHITECTURE.md §1). Sem isto o Django vê http e o
# SECURE_SSL_REDIRECT entra em ciclo de redirects. O header só é de confiar
# porque o proxy o reescreve sempre — nunca o deixa passar do cliente.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# TLS verificado na ligação à BD, com verificação de hostname (SECURITY.md §3).
# `verify-full` precisa de uma CA: por default o libpq usa
# ~/.postgresql/root.crt; em contentor passa-se o caminho por ambiente.
DATABASE_SSLROOTCERT = env("DATABASE_SSLROOTCERT", default="")
# Dicionários novos em vez de mutar os do `base`: o `import *` traz a
# *referência* do dicionário, e mutá-la aqui mudava também a configuração de
# quem importasse o base noutro ambiente. Coberto por um teste em
# `tests/test_settings_smoke.py`.
DATABASES = {
    **DATABASES,
    "default": {
        **DATABASES["default"],
        "OPTIONS": {
            **DATABASES["default"].get("OPTIONS", {}),
            "sslmode": "verify-full",
            **({"sslrootcert": DATABASE_SSLROOTCERT} if DATABASE_SSLROOTCERT else {}),
        },
    },
}

# Em produção nada tem default: sem estas variáveis — ou definidas vazias — o
# processo não arranca (`config/env.py`).
ADMIN_URL = admin_path(required(env, "DJANGO_ADMIN_URL"))
REDIS_URL = required(env, "REDIS_URL")
CELERY_BROKER_URL = optional(env, "CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = optional(env, "CELERY_RESULT_BACKEND", f"{REDIS_URL}/1")

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        **CONTENT_SECURITY_POLICY["DIRECTIVES"],
        "upgrade-insecure-requests": True,
    },
}

# ---------------------------------------------------------------------------
# IP do cliente atrás do proxy (SECURITY.md §5)
# ---------------------------------------------------------------------------
# O REMOTE_ADDR é o proxy: sem resolver o IP real, o axes conta as tentativas de
# todos os clientes no mesmo "IP" e o eixo IP do lockout desaparece. Estas
# settings só têm efeito com o `django-ipware` instalado — o
# `axes.helpers.get_client_ip_address` tem um `try: import ipware` e, sem ele,
# cai no REMOTE_ADDR sem dizer nada. Por isso o pacote é dependência do
# projeto, não um extra opcional.
#
# Convenção, e é ela que dá sentido aos números abaixo: cada proxy de confiança
# **acrescenta** à direita do X-Forwarded-For o endereço que viu (é o que faz o
# `$proxy_add_x_forwarded_for` do nginx e o default do Caddy). Logo:
#
#   X-Forwarded-For: <o que o cliente enviou>, <cliente real>, <proxy 1>, ...
#                     \_ não é de confiar _/  \____ escrito pelos proxies ____/
#
# O cliente real está a TRUSTED_PROXY_COUNT posições da direita. A esquerda é
# texto do cliente e não se usa para nada.
AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")
# `left-most` + `proxy_count = N - 1` + `IPWARE_STRICT = False` é a combinação
# que implementa a convenção acima. Medido com o python-ipware 4.1 instalado
# (cliente real 203.0.113.5, proxy 10.0.0.7, forjado 9.9.9.9):
#
#   ordem       count strict | "203.0.113.5" | "9.9.9.9, 203.0.113.5"
#   left-most   1     True   | None          | 9.9.9.9      <- era o que estava
#   right-most  1     True   | None          | 203.0.113.5
#   left-most   0     True   | 203.0.113.5   | 10.0.0.7
#   left-most   0     False  | 203.0.113.5   | 203.0.113.5  <- esta
#
# Ou seja: a configuração anterior, com o ipware instalado, devolvia o IP
# *forjado* e não resolvia o tráfego legítimo. `strict` recusa a cadeia toda
# quando o comprimento não bate exatamente com o esperado, e o comprimento
# depende do que o cliente enviou — não serve. Sem `strict`, o índice é
# contado a partir da direita e o prefixo do cliente é ignorado, seja ele
# comprido ou curto.
IPWARE_STRICT = False
AXES_IPWARE_PROXY_ORDER = "left-most"
# O `proxy_count` do ipware conta as entradas escritas *depois* do cliente na
# cadeia: com um só proxy à frente, o cliente é a última entrada e não há
# nenhuma depois dele, logo zero. Daí o `- 1`. O NUM_PROXIES do DRF conta a
# mesma topologia a partir de 1 (`addrs[-NUM_PROXIES]`), e é por isso que os
# dois números diferem de uma unidade para a mesma realidade.
AXES_IPWARE_PROXY_COUNT = max(TRUSTED_PROXY_COUNT - 1, 0)
