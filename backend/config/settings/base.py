"""Configuração comum a todos os ambientes.

Os módulos `dev`, `prod` e `test` fazem `from config.settings.base import *` e
só declaram o que muda. Este ficheiro nunca é usado diretamente como
`DJANGO_SETTINGS_MODULE`.

Regras que este ficheiro impõe (CLAUDE.md, SECURITY.md):

* **Zero defaults para segredos.** `DJANGO_SECRET_KEY` e `DATABASE_URL` não têm
  fallback: sem eles — ou definidos vazios — o processo não arranca, em dev ou
  em prod. Quem impõe isso é o `config/env.py`: o `environ.Env` sozinho só
  levanta quando a variável *não existe*, e aceita `VAR=""` como valor.
* Defaults seguros: `DEBUG = False`, cookies `httpOnly`, `ALLOWED_HOSTS` vazio.
  É o `dev.py` que abre, não o `prod.py` que fecha.
* Infraestrutura sem segredo (Redis, portas) tem default de desenvolvimento,
  fixado no ADR 0002. O `prod.py` volta a exigi-la sem default.
"""

from pathlib import Path

import environ
from csp.constants import NONCE, NONE, SELF

from config.env import admin_path, optional, required, required_db

#: Raiz do projeto backend (onde vivem `manage.py`, `pyproject.toml` e `.env`).
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

# O `.env` é uma conveniência de desenvolvimento e de CI local. Em produção as
# variáveis vêm do orquestrador / Docker secrets e este ficheiro não existe.
_ENV_FILE = BASE_DIR / ".env"
if _ENV_FILE.is_file():
    env.read_env(_ENV_FILE)

# ---------------------------------------------------------------------------
# Segredos e ligações — obrigatórios, sem default (SECURITY.md §1 "Fuga de
# segredos": um default é um segredo commitado com outro nome).
# ---------------------------------------------------------------------------
SECRET_KEY = required(env, "DJANGO_SECRET_KEY")

DATABASES = {"default": required_db(env, "DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Sem ATOMIC_REQUESTS: a transação é aberta explicitamente em `services.py`
# (`@transaction.atomic`), que é também onde o `SET LOCAL app.tenant_id` da RLS
# tem de viver (ARCHITECTURE.md §4, SECURITY.md §3).
DATABASES["default"]["ATOMIC_REQUESTS"] = False

# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
DEBUG = False
ALLOWED_HOSTS: list[str] = []

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

#: Path do admin. Não é `admin/` (SECURITY.md §5) e vem do ambiente para poder
#: ser diferente por instalação. Em `prod.py` passa a ser obrigatório.
#: Normalizado no `admin_path`: sem a barra final o `reverse('admin:login')`
#: devolve `/gestao-internalogin/` e o admin fica inacessível em silêncio.
ADMIN_URL = admin_path(optional(env, "DJANGO_ADMIN_URL", "gestao-interna/"))

#: UI de documentação da API (Swagger). O `schema.yml` para o `pnpm gen:api` é
#: gerado pelo comando `manage.py spectacular`, não por este endpoint.
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "axes",
    "csp",
]

# Pelos AppConfig: cada módulo tem `verbose_name` próprio e é onde as
# subscrições de eventos (`handlers.py`) se registam no `ready()`.
LOCAL_APPS = [
    "apps.shared.apps.SharedConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.purchasing.apps.PurchasingConfig",
    "apps.recipes.apps.RecipesConfig",
    "apps.agents.apps.AgentsConfig",
    "apps.billing.apps.BillingConfig",
    "apps.notifications.apps.NotificationsConfig",
]

INSTALLED_APPS = [*DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

# Ordem: segurança → CSP (gera o nonce antes de qualquer template) → sessão →
# CSRF → autenticação → mensagens → clickjacking → axes (precisa do
# `request.user`, por isso vem depois do AuthenticationMiddleware).
# O `TenantMiddleware` entra aqui no passo 3/4, a partir de `apps.accounts`
# (ADR 0003), imediatamente depois do AuthenticationMiddleware.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Autenticação, sessões e passwords (SECURITY.md §5)
# ---------------------------------------------------------------------------
# O AxesStandaloneBackend tem de ser o primeiro: é ele que recusa o pedido
# quando a conta/IP está em lockout, antes de qualquer verificação de password
# (obrigatório no django-axes 8.x).
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Sessões server-side em BD. 14 dias *inativas*: o SESSION_SAVE_EVERY_REQUEST
# reescreve a expiração a cada pedido, logo o contador só corre com o
# utilizador parado.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 14 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# O cliente React lê o cookie de CSRF para o mandar em `X-CSRFToken`
# (SECURITY.md §7), por isso este cookie — e só este — não é httpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Argon2id à frente (é o modo do Argon2PasswordHasher do Django). Os restantes
# ficam para validar hashes antigos e são re-hashados no login seguinte.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# django-axes — lockout de login por conta e pelo par (IP, conta)
# (SECURITY.md §5). Sobre o tempo de espera, ver `config/lockout.py`: o
# docstring diz o que a escada faz e o que ainda não faz.
# ---------------------------------------------------------------------------
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
# Dois contadores independentes; o axes faz `max()` sobre os grupos
# (`handlers/database.py get_failures`), logo ganha o mais restritivo:
#   1. o par (IP, utilizador) — o eixo fino. Sozinho não serve, mas é ele que
#      evita trancar um NAT partilhado inteiro por causa de um atacante, que é
#      o argumento para não usar `ip_address` isolado;
#   2. o utilizador — apanha password spraying (N IPs contra 1 conta), que o
#      par nunca apanha: cada IP conta em separado e nenhum chega ao limite.
# O que nenhum dos dois apanha, e é preciso dizê-lo: credential stuffing (1 IP,
# N contas, 3-4 tentativas em cada) não acumula em contador nenhum. A defesa
# para isso é rate limit por IP puro, e esse é do proxy, não do Django
# (SECURITY.md §5). Consequência aceite do contador por utilizador: quem
# souber o email de alguém tranca-lhe a conta 30 min com 5 passwords erradas.
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"], "username"]
# Path em string, resolvido pelo axes em runtime: importar o callable aqui
# puxaria `axes.conf` (que lê `django.conf.settings`) durante a leitura das
# próprias settings.
AXES_COOLOFF_TIME = "config.lockout.progressive_cooloff"
AXES_RESET_ON_SUCCESS = True
AXES_USE_ATTEMPT_EXPIRATION = True
AXES_LOCK_OUT_AT_FAILURE = True
AXES_HTTP_RESPONSE_CODE = 429
# `username` e `ip_address` são limpos dos dados de pedido antes de irem para o
# log de tentativas (SECURITY.md §1, "Exposição de dados em logs").
AXES_SENSITIVE_PARAMETERS = ["username", "ip_address", "password"]

# ---------------------------------------------------------------------------
# DRF (SECURITY.md §2)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min", "anon": "60/min"},
    # Nº de proxies de confiança à frente do Django. É o que decide a chave do
    # AnonRateThrottle: sem esta setting o DRF usa o `X-Forwarded-For` cru como
    # identidade (`BaseThrottle.get_ident`), e o limite de anónimos contorna-se
    # a rodar um header. `0` = ignora o header e usa só o `REMOTE_ADDR`; é o
    # default seguro e o valor correto em dev e em teste, onde não há proxy.
    # O `prod.py` sobrepõe-no com o TRUSTED_PROXY_COUNT do ambiente.
    "NUM_PROXIES": 0,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Só JSON: a browsable API renderiza HTML com estilos inline (choca com a
    # CSP) e expõe a forma da API a quem não precisa dela.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # Paginação desde o primeiro endpoint: acrescentá-la depois muda a forma de
    # todas as respostas de lista e quebra o cliente gerado.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "StockFlow API",
    "DESCRIPTION": (
        "Gestão de stock, validades, receitas e compras para restauração. "
        "Multi-tenant: cada pedido corre no contexto do tenant da sessão."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Separa `XRequest` de `X` nos componentes: o `pnpm gen:api` passa a gerar
    # tipos distintos para o que se envia e o que se recebe.
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # O schema descreve endpoints privados: não fica aberto a anónimos. O
    # `pnpm gen:api` usa o comando `manage.py spectacular`, não este endpoint.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}

# Uploads (SECURITY.md §2 e §4). Nenhuma destas settings é um teto de tamanho
# de ficheiro, e é fácil ler mal:
#   * DATA_UPLOAD_MAX_MEMORY_SIZE conta o corpo do pedido *excluindo* ficheiros
#     — protege contra um POST gigante de campos de formulário, não contra um
#     upload gigante;
#   * FILE_UPLOAD_MAX_MEMORY_SIZE só decide a partir de que tamanho o ficheiro
#     passa de memória para um temporário em disco. Acima do limite o Django
#     continua a aceitar o upload, só o escreve no disco.
# O teto real de uma foto de fatura são duas coisas que não estão aqui:
# `client_max_body_size` no proxy (passo 6 do kickoff) e um validador de
# tamanho/MIME no serializer do upload (passo 3 em diante).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# ---------------------------------------------------------------------------
# Content Security Policy (django-csp >= 4.0, formato novo)
# ---------------------------------------------------------------------------
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "base-uri": [SELF],
        # Scripts só do próprio domínio e com nonce. Nada de 'unsafe-inline'.
        "script-src": [SELF, NONCE],
        "style-src": [SELF],
        "img-src": [SELF, "data:"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
        "object-src": [NONE],
        "worker-src": [SELF],
        "manifest-src": [SELF],
    },
}

# ---------------------------------------------------------------------------
# Cache, Celery e Redis
# ---------------------------------------------------------------------------
# Sem segredo: default de desenvolvimento com a porta do ADR 0002. Índices
# separados para broker, resultados e cache — a pressão de memória de um não
# derruba os outros.
REDIS_URL = optional(env, "REDIS_URL", "redis://localhost:6389")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": optional(env, "CACHE_URL", f"{REDIS_URL}/2"),
        "KEY_PREFIX": "stockflow",
    },
}

CELERY_BROKER_URL = optional(env, "CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = optional(env, "CELERY_RESULT_BACKEND", f"{REDIS_URL}/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_TRACK_STARTED = True
# Ack depois de executar + devolver à fila se o worker morrer: as tarefas são
# idempotentes por `event_id` (ARCHITECTURE.md §4), logo re-executar é seguro e
# perder é que não é.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 10 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 9 * 60
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_RESULT_EXPIRES = 24 * 60 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Maior do que o TIME_LIMIT, senão uma tarefa lenta é reentregue a outro worker
# enquanto ainda corre.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 15 * 60}

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-pt"
TIME_ZONE = "Europe/Lisbon"
USE_I18N = True
USE_TZ = True

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# ---------------------------------------------------------------------------
# Ficheiros estáticos
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Logging estruturado (ARCHITECTURE.md §8) — ver `config/log.py`.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "config.log.RequestContextFilter"},
    },
    "formatters": {
        "json": {"()": "config.log.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Tentativas de login falhadas e lockouts: alimenta o alerta de
        # "falhas de login por IP" (ARCHITECTURE.md §8).
        "django.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "axes": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
