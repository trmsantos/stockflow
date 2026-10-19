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

from decimal import Decimal
from pathlib import Path

import environ
from celery.schedules import crontab
from csp.constants import NONCE, NONE, SELF

from config.env import admin_path, optional, required, required_db

#: Raiz do projeto backend (onde vivem `manage.py`, `pyproject.toml` e `.env`).
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

# O `.env` já está no ambiente: quem o lê é o `config/settings/__init__.py`, que
# o Python importa antes deste módulo e antes de qualquer módulo de ambiente.
# Aqui só se lê `os.environ` — ver o docstring desse ficheiro para a razão da
# ordem, que não é arbitrária.

# ---------------------------------------------------------------------------
# Segredos e ligações — obrigatórios, sem default (SECURITY.md §1 "Fuga de
# segredos": um default é um segredo commitado com outro nome).
# ---------------------------------------------------------------------------
SECRET_KEY = required(env, "DJANGO_SECRET_KEY")

DATABASES = {"default": required_db(env, "DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Sem ATOMIC_REQUESTS, e não por economia: abriria a transação em volta da
# *view*, dentro da cadeia de middleware, onde nenhum middleware lhe consegue
# pôr o `set_config` da RLS. A transação do pedido é aberta pelo
# `TenantMiddleware` a envolver o `get_response()`, e é lá que o
# `set_config('app.tenant_id', ...)` vive — não nos services, cujo
# `@transaction.atomic` passa a ser um savepoint dentro dela (ADR 0005).
DATABASES["default"]["ATOMIC_REQUESTS"] = False

# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
DEBUG = False
ALLOWED_HOSTS: list[str] = []

#: Os dois endpoints de saúde ficam fora do redirect para HTTPS. Aqui e não no
#: `prod.py` porque a razão não é de ambiente: o `SecurityMiddleware` responde
#: 301 a qualquer pedido em `http` quando o `SECURE_SSL_REDIRECT` está ligado, e
#: o healthcheck corre **de dentro** do contentor, em HTTP simples, sem proxy
#: pelo meio a pôr o `X-Forwarded-Proto`. Sem esta dispensa o `HEALTHCHECK`
#: recebia um 301 para o domínio público — que o `curl -f` conta como sucesso,
#: logo o contentor ficava "saudável" sem nunca ter tocado na aplicação; e com
#: `-L` saía para a Internet e verificava outra instância.
#:
#: O que se abre é exatamente isto: dois paths que não leem a sessão, não
#: aceitam corpo, não escrevem nada e respondem `ok`. Os regex são comparados
#: contra o path sem a barra inicial (`SecurityMiddleware.process_request`), e
#: a coerência entre esta lista e as rotas reais está fixada em
#: `tests/test_health.py` — duplicar os paths aqui é o preço de as settings não
#: poderem importar `config.urls`.
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]

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
    # Pelo `ArrayField` do `accounts.User.tenant_ids` (ADR 0007). Não cria
    # tabela nenhuma: registra os lookups e as verificações de sistema dos
    # campos específicos do Postgres.
    "django.contrib.postgres",
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
    # Sem models e sem migrações: está instalado só para o `manage.py` encontrar
    # o `semear_demonstracao`. É um sumidouro de escrita (ADR 0018, decisão 3) e
    # um contrato do import-linter proíbe que alguém o importe.
    "apps.demo.apps.DemoConfig",
]

INSTALLED_APPS = [*DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

# Ordem: contexto de log (gera o `request_id`) → segurança → CSP (gera o nonce
# antes de qualquer template) → sessão → CSRF → autenticação → mensagens →
# clickjacking → axes (precisa do `request.user`, por isso vem depois do
# AuthenticationMiddleware).
# O `RequestContextMiddleware` é o primeiro de propósito (ARCHITECTURE.md §4):
# um pedido recusado pelo middleware de segurança, um 404 antes da view ou uma
# exceção na resolução da URL têm de ser logados já com `request_id`, senão
# essas linhas — as que interessam — ficam sem nada que as ligue ao resto.
# O `TenantMiddleware` vive em `apps.accounts` (ADR 0003) e é o **último** —
# não a seguir ao AuthenticationMiddleware. Precisa do `request.user`, e é ele
# que abre a transação do pedido (ADR 0005): ser o último deixa a escrita da
# sessão (`SESSION_SAVE_EVERY_REQUEST`) e o `AccessAttempt` do axes de fora
# dela, em autocommit, que é onde têm de estar.
MIDDLEWARE = [
    "apps.shared.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # **Depois da sessão e acima do `TenantMiddleware`** (ADR 0019): a língua
    # tem de estar activa quando um service levanta uma recusa, e as recusas
    # acontecem dentro do âmbito que o `TenantMiddleware` abre.
    #
    # O que ele faz é olhar para o `Accept-Language` do browser e activar a
    # língua. É o **mesmo sinal** que o `navigator.language` dá ao React, logo os
    # dois lados concordam sem nada a ligá-los — nem contrato, nem coluna, nem
    # espelho em `localStorage` (que foi o que o tema custou, ADR 0016).
    #
    # Ele também acrescenta `Vary: Accept-Language` a tudo o que passa por aqui,
    # e isso é a razão de ele estar no `MIDDLEWARE` em vez de um
    # `translation.activate()` numa view: sem o header, uma resposta com texto
    # traduzido guardada em cache sai na língua errada ao pedido seguinte.
    #
    # **E o `django.conf.urls.i18n` não é encaminhado**, de propósito: o
    # `set_language` é um POST anónimo que escreve o cookie `django_language`, e
    # esse cookie **ganha** ao `Accept-Language` aqui. Um cookie velho passava a
    # mandar no lado da API sem mandar no lado do React — os dois sinais a
    # divergir, que é exactamente a propriedade que esta escolha compra. É
    # também a família de endpoint que o `SECURITY.md` §5 obriga a proteger.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "apps.accounts.middleware.TenantMiddleware",
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
#: O `USERNAME_FIELD` é `email` e a tabela é deliberadamente pequena: credencial
#: e flags, e mais nada. O nome exibido e o papel vivem no `Membership`, que tem
#: política RLS (ADR 0007).
AUTH_USER_MODEL = "accounts.User"

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
# O nome do campo que transporta a conta, e sem ele o eixo por utilizador
# desaparece **em silêncio**. Medido no pacote instalado: o
# `axes.helpers.get_client_username` devolve
# `credentials.get(settings.AXES_USERNAME_FORM_FIELD)`, cujo default é
# `"username"`; com login por email esse `get` devolve `None` e o contador por
# conta passa a agrupar todas as tentativas sob a chave `None`. É a mesma classe
# de defeito do `django-ipware` (SECURITY.md §5): a configuração parece estar
# lá e o controlo não está. Fixado em `tests/test_lockout.py`.
AXES_USERNAME_FORM_FIELD = "email"
# E o valor desse campo é normalizado antes de virar chave do contador. O axes
# **não** o normaliza — medido no pacote instalado, não há um `lower()` no
# django-axes 8.3.1 —, e a unicidade do email é insensível à caixa (ADR 0007 +
# `accounts.models`): `ana@x.pt` e `Ana@x.pt` são uma conta na base de dados e
# seriam duas chaves no `AccessAttempt`. Cinco tentativas repartidas entre as
# duas grafias não trancavam nada, e o eixo (IP, conta) fragmenta-se da mesma
# forma. Path em string pela razão do `AXES_COOLOFF_TIME` abaixo; o callable
# está em `config/lockout.py`, ao lado do outro gancho do axes, e delega a
# normalização no `accounts.api` — uma definição só de "a mesma conta".
AXES_USERNAME_CALLABLE = "config.lockout.axes_username"
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
# O corpo do 429, que sem este gancho não é JSON: o `get_lockout_response` do
# axes responde o `AXES_COOLOFF_MESSAGE` em `text/plain`, e o cliente ficava sem
# `code` para distinguir o lockout do 429 do throttle do DRF. A ADR 0010 fecha
# essa dívida (nomeada no SECURITY.md §5) com o código `conta_bloqueada`. Path em
# string pela razão do `AXES_COOLOFF_TIME`; o callable está em
# `config/lockout.py`, ao lado dos outros dois ganchos do axes.
AXES_LOCKOUT_CALLABLE = "config.lockout.lockout_response"
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
    # O balde `documentos` é o das **escritas** de `/api/v1/documents` (ADR 0021,
    # decisão 9): cada página aceite custa uma rasterização e uma chamada a LLM a
    # jusante, e é o primeiro sítio onde o limite de custo do SECURITY.md §6
    # aterra. 20/min é o número da ADR 0020 e é folgado para o caso real — dez
    # páginas é o teto de um documento —, mas não para um script. O teto de custo
    # a sério continua a ser o teto de páginas por documento.
    "DEFAULT_THROTTLE_RATES": {
        "user": "600/min",
        "anon": "60/min",
        "documentos": "20/min",
        "catalogo": "20/min",
        "rececoes": "20/min",
        # As escritas do assistente (ADR 0027, decisão 4): cada pergunta é uma
        # tarefa com chamadas a um modelo pago. 10/min é folgado para uma
        # conversa e apertado para um script; o teto de custo a sério é o
        # orçamento diário por tenant, mais abaixo.
        "assistente": "10/min",
    },
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
    # **`False` porque as nossas views de `PATCH` não validam com `partial=True`.**
    #
    # Por omissão o drf-spectacular gera, para cada `PATCH`, um componente
    # `Patched<X>Request` com **todos** os campos opcionais — assume o
    # comportamento das views genéricas do DRF, onde um `PATCH` chama o
    # serializer com `partial=True`. As nossas não são genéricas: o
    # `PreferenciasInSerializer(data=request.data)` do `PATCH
    # /auth/preferencias` corre sem `partial`, logo o `tema` é obrigatório e um
    # corpo vazio é 400 (medido em `tests/test_preferencias.py`).
    #
    # Medido antes de pôr esta linha: o `types.ts` dizia `tema?: TemaEnum`, isto
    # é, o cliente compilava um corpo `{}` que o servidor recusa. Um `types.ts`
    # que descreve um pedido inválido como válido é a classe de mentira que este
    # gate existe para apanhar, e aqui mentia na direcção pior — a de deixar
    # passar.
    #
    # É global, e a condição para ela continuar verdadeira é uma frase: **nenhuma
    # view usa `partial=True`**. No dia em que uma usar, é esta linha que tem de
    # sair e o endpoint que tem de declarar o seu próprio `request`.
    "COMPONENT_SPLIT_PATCH": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # O schema descreve endpoints privados: não fica aberto a anónimos. O
    # `pnpm gen:api` usa o comando `manage.py spectacular`, não este endpoint.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    # O nome dos componentes de enum, onde o default não serve. O drf-spectacular
    # deriva-o do **nome do campo** (`papel` -> `PapelEnum`), o que dá dois
    # problemas que esta tabela resolve:
    #
    #   * o mesmo conjunto de valores em dois campos com nomes diferentes gera
    #     dois nomes para um componente só, e isso é um **warning** — logo exit 1
    #     no `spectacular --fail-on-warn` do `pnpm gen:api`. Acontece com o
    #     `Papel`, que é `papel` no convite e no estabelecimento e
    #     `papeis_permitidos` no registo de rotas do menu;
    #   * o `route_id` daria `RouteIdEnum`, e o nome que o registo de rotas do
    #     shell espera — e documenta — é `RotaIdEnum`
    #     (`frontend/src/shell/registo-de-rotas.ts`). É esse componente que faz o
    #     `Record<RotaId, EntradaDoRegisto>` ser exaustivo contra a lista do
    #     backend nos dois sentidos (ADR 0009), e um nome que mude sozinho
    #     quando alguém renomear um campo era uma dependência frágil no único
    #     gate de contrato que existe.
    #
    # Aponta para as classes `TextChoices` e não para listas copiadas: o nome
    # segue o conjunto de valores, e é o conjunto que o drf-spectacular compara.
    "ENUM_NAME_OVERRIDES": {
        "PapelEnum": "apps.accounts.models.Papel",
        "RotaIdEnum": "apps.accounts.models.RotaDeMenu",
        # Os três enums do recurso `/documents` (ADR 0021). Sem estas entradas o
        # drf-spectacular derivava o nome do **campo**, e dois campos chamados
        # `state` com conjuntos de valores diferentes — o do documento e o da
        # extração — dão dois componentes com o mesmo nome, que é um warning e
        # portanto exit 1 no `spectacular --fail-on-warn` do `pnpm gen:api`.
        "OrigemDoDocumentoEnum": "apps.purchasing.models.OrigemDoDocumento",
        "EstadoDoDocumentoEnum": "apps.purchasing.models.EstadoDoDocumento",
        "EstadoDaLeituraEnum": "apps.purchasing.models.EstadoDaLeitura",
        # O estado de um turno do assistente (ADR 0027, decisão 4). O campo
        # chama-se `status` como o da receção e o das linhas, e sem o nome aqui
        # era mais uma colisão a resolver com um sufixo numérico.
        "EstadoDaMensagemEnum": "apps.agents.models.EstadoDaMensagem",
        # Os dois conjuntos de `conservation`: o do artigo (três valores) e o da
        # temperatura registada numa receção (só as duas classes que o HACCP
        # mede). Dois campos com o mesmo nome e conjuntos diferentes davam
        # `Conservation500Enum` — o nome por colisão, que muda sozinho.
        "ConservacaoEnum": "apps.catalog.models.Conservacao",
        "ConservacaoMedidaEnum": ["chilled", "frozen"],
        # As três uniões do painel que se chamam `id` (ADR 0013, decisão 5).
        # Sem estas entradas, três conjuntos de valores diferentes partilhavam
        # o nome derivado do campo (`IdEnum`) e o drf-spectacular resolvia a
        # colisão com um sufixo de hash — `Id50cEnum`, um nome que muda sozinho
        # quando a lista muda, e um warning que é exit 1 no `pnpm gen:api`.
        #
        # O `IdDeCustoEnum` resolve uma segunda coisa de borla: o `part_of` de
        # `ComponenteDeCustoOut` tem o mesmo conjunto com outro nome de campo,
        # e um conjunto com dois nomes é o outro warning desta família.
        #
        # Os nomes são os que o `features/reporting/schemas.ts` já usa.
        "IdDeCustoEnum": [
            "purchases",
            "goods_consumed",
            "waste",
            "unknown_shrinkage",
            "payroll",
            "other",
        ],
        "IdDeSerieEnum": ["revenue", "purchases"],
        "IdDeParteDeSalariosEnum": [
            "base",
            "social_security",
            "subsidies",
            "meal_allowance",
            "insurance",
        ],
    },
}

# Uploads (SECURITY.md §2 e §4). Nenhuma destas settings é um teto de tamanho
# de ficheiro, e é fácil ler mal:
#   * DATA_UPLOAD_MAX_MEMORY_SIZE conta o corpo do pedido *excluindo* ficheiros
#     — protege contra um POST gigante de campos de formulário, não contra um
#     upload gigante;
#   * FILE_UPLOAD_MAX_MEMORY_SIZE só decide a partir de que tamanho o ficheiro
#     passa de memória para um temporário em disco. Acima do limite o Django
#     continua a aceitar o upload, só o escreve no disco.
# O teto real de uma foto de fatura são duas coisas que não estão aqui, e as duas
# **já existem** desde 2026-10-07 (esta nota dizia "passo 6 do kickoff" e "passo 3
# em diante", e um marcador de futuro obsoleto faz o leitor seguinte concluir que
# o controlo falta):
#   * `request_body { max_size 12MB }` no `docker/caddy/proxy.Caddyfile`;
#   * o `TAMANHO_MAXIMO_DO_FICHEIRO` do `apps/purchasing/ficheiros.py`, a 11 MiB
#     e **estritamente abaixo** do do proxy, com um teste que lê o Caddyfile e
#     afirma essa ordem — quem recusa primeiro tem de ser quem tem uma frase.
#     Esse módulo valida também o tipo, pelos bytes e não pelo `content_type`.
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
# `beat` — o agendador. Uma entrada só, e é o consumidor da outbox.
# ---------------------------------------------------------------------------
#: De quantos em quantos segundos a outbox é lida. **Cinco**, e o número é uma
#: troca medida: a rasterização de uma página arrancava em ~0 s com o `.delay()`
#: directo que esta feature substituiu e passa a arrancar em 0–5 s. O ecrã de
#: entrada de documento sonda a 2 s com um orçamento de 3 minutos (ADR 0021),
#: logo cinco segundos são duas sondagens e não um timeout.
#:
#: Descer isto não é de graça: cada passagem é uma tarefa, uma mensagem no broker
#: e pelo menos uma transação de leitura (`_candidatas`). Subir atrasa toda a
#: cadeia de uma receção. Cinco é o ponto em que a latência deixa de ser visível
#: no ecrã e o custo de polling continua a ser ruído.
INTERVALO_DO_CONSUMIDOR_DA_OUTBOX = 5.0

CELERY_BEAT_SCHEDULE = {
    "consumir-outbox": {
        "task": "shared.consumir_outbox",
        "schedule": INTERVALO_DO_CONSUMIDOR_DA_OUTBOX,
        # **`expires` não é adorno.** Sem ele, um worker em baixo durante uma hora
        # deixa 720 mensagens de consumo na fila e, ao voltar, corre-as todas —
        # 720 passagens a competir pelas mesmas linhas, quando uma só fazia o
        # mesmo trabalho. Com 60 s, o broker descarta as que já não servem. É o
        # equivalente, para uma tarefa periódica, do que o `acks_late` é para uma
        # tarefa de trabalho.
        "options": {"expires": 60},
    },
    # A purga das conversas do assistente (ADR 0027, decisão 2): uma vez por
    # dia, de madrugada, o `SystemTask` descobre os tenants pelo
    # `accounts_user.tenant_ids` e enfileira uma purga por tenant. `expires` de
    # uma hora: se o worker estiver em baixo de madrugada, a entrada corre
    # quando ele voltar; se estiver em baixo um dia, a de amanhã faz o mesmo
    # trabalho e a de hoje descarta-se.
    "purgar-conversas-expiradas": {
        "task": "agents.purgar_conversas_expiradas",
        "schedule": crontab(hour=4, minute=30),
        "options": {"expires": 60 * 60},
    },
}

# **Onde fica o ficheiro de estado do `beat` não se decide aqui**, e é uma
# escolha e não uma omissão. O `beat` guarda a última execução de cada entrada
# num ficheiro (`celerybeat-schedule`, no directório de trabalho por omissão) e o
# contentor corre com `read_only: true`: o caminho tem de ser `/tmp`, que é o
# `tmpfs` do serviço. Fica no `--schedule` do comando, em `docker/compose.yml`,
# ao lado do `read_only` e do `tmpfs` que o obrigam — que é o único sítio onde as
# três linhas se leem juntas e onde uma delas a mudar obriga a olhar para as
# outras. Uma setting aqui era a mesma verdade num segundo sítio, e com `/tmp`
# escrito à mão num ficheiro que corre também fora de contentor.
# Que o comando do compose e o `tmpfs` concordam é um teste
# (`tests/test_celery_config.py`).

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-pt"
TIME_ZONE = "Europe/Lisbon"
USE_I18N = True
USE_TZ = True

#: As línguas que a app serve. Lista fechada, com **duas** desde 2026-10-07
#: (ADR 0019, decisão 9).
#:
#: Com o idioma a vir do browser não se pode "não enviar" inglês: um browser
#: inglês recebe o que houver. Enquanto esta lista teve um elemento, um
#: `Accept-Language: en` caía no `LANGUAGE_CODE` e a app era inteiramente
#: portuguesa — coerente, porque uma app meio traduzida dá ao leitor inglês uma
#: parede de português exactamente onde a tarefa fica difícil.
#:
#: O inglês entrou no commit em que a última linha da lista fechada do
#: `frontend/scripts/check-textos.mjs` saiu, com a entrada equivalente no
#: `LINGUAS` do `frontend/src/lib/i18n.ts`. **A condição é verificada e não
#: prometida**: o `test_o_ingles_so_liga_com_a_lista_vazia` do
#: `tests/test_i18n.py` lê essa lista e falha nos dois sentidos.
#:
#: Os dois nomes ficam na língua **deles** e não traduzidos: é o que um selector
#: de idioma mostra, no dia em que houver um — ninguém procura "Inglês" numa
#: lista que está a ler em inglês.
LANGUAGES = [
    ("pt-pt", "Português (Portugal)"),
    ("en", "English"),
]

#: As traduções **do projecto**, e é esta linha que torna "pt é pt de Portugal"
#: verdade (ADR 0019, decisão 4).
#:
#: O Django funde os catálogos **depois** dos das apps instaladas e a fusão
#: sobrepõe, logo o nosso `locale/pt_PT/LC_MESSAGES/django.po` ganha ao `pt_PT`
#: do DRF — que é quase uma cópia do `pt_BR`. Medido antes de esta linha
#: existir: com `LANGUAGE_CODE = "pt-pt"`, um `UUIDField` inválido respondia
#: **"Must be a valid UUID."** em inglês, um `ChoiceField` respondia *"não é um
#: escolha válido"* e um `IntegerField` respondia *"Certifque-se"*. Mudar o
#: código de língua não corrige nada: `pt` dá as mesmas frases.
#:
#: O que o catálogo sobrepõe é uma lista fechada **derivada de uma medição** e
#: não adivinhada — ver `tests/test_i18n.py`, que varre o catálogo do DRF à
#: procura de marcadores pt-BR e falha se algum chegar ao utilizador.
LOCALE_PATHS = [BASE_DIR / "locale"]

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# ---------------------------------------------------------------------------
# Ficheiros estáticos
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Ficheiros de media: as imagens das faturas (ADR 0020, decisão 4)
# ---------------------------------------------------------------------------
# `MEDIA_ROOT` é um volume partilhado pelo `backend` e pelo `worker` no compose:
# o pedido escreve o original, o worker escreve a imagem normalizada. O gatilho
# para trocar por S3/MinIO está escrito na ADR 0020 — mais de uma réplica web, ou
# backups que tenham de incluir os blobs — e é `STORAGES`, não código.
MEDIA_ROOT = BASE_DIR / "media"

# **`MEDIA_URL` fica sem valor, e é deliberado.** O proxy nunca encaminha
# `/media/` (há um gate que o afirma com `curl -I`), logo um caminho emitido por
# um `.url()` acidental seria um link para 404 — ou, pior, um link que um dia
# alguém "corrige" encaminhando o directório inteiro. Com `None`, o
# `FileSystemStorage.url()` **levanta** em vez de o emitir, que é o
# comportamento que se quer de uma afordância que não deve existir.
#
# Quem serve as imagens é uma view com âmbito (`GET /documents/<id>/pages/<n>/
# image`), com `inline`, `nosniff` e `Cache-Control: private` — ADR 0021,
# decisão 9.
MEDIA_URL = None

# ---------------------------------------------------------------------------
# Extração de faturas (ADR 0021, fatia 1)
# ---------------------------------------------------------------------------
# O nome do modelo que lê um documento. **Vazio por omissão, e não é um
# esquecimento**: sem valor, a fronteira de `apps/agents/modelo.py` levanta uma
# excepção clara e a tarefa grava a tentativa com `status=erro` e uma razão
# legível. Não há cliente de LLM, nem chave de API, nem rede em nenhum ponto
# deste repositório — ligar a extração a sério é esta definição, uma credencial
# e um prompt.
#
# Não é lido do ambiente de propósito: uma variável de ambiente que ninguém
# consome é uma promessa de configuração que não existe. Passa a `env(...)` no
# dia em que houver cliente.
AGENTS_EXTRACTION_MODEL = ""

# ---------------------------------------------------------------------------
# Chat sobre stock (ADR 0027, decisões 7 e 9)
# ---------------------------------------------------------------------------
# O primeiro cliente de LLM do repositório, e **só o worker fala com a rede**: o
# processo web recusa 503 `assistente_indisponivel` quando uma das duas
# primeiras está vazia, antes de criar linha nenhuma, e nunca chama o modelo. A
# chave entra só pelo ambiente do `worker` (ver `docker/compose.yml`), nunca pelo
# do `backend`. Lidas com `optional`: uma variável vazia num `.env` é "desligado"
# e não um valor truncado (`config/env.py`).
#
# O modelo por omissão é o do dono (2026-10-15): o mais barato que faz tool-use,
# para a fase de testes custar o mínimo. Trocar de modelo é configuração; trocar
# de fornecedor é a fábrica `cliente()` de `apps/agents/modelo.py`.
AGENTS_CHAT_MODEL = optional(env, "AGENTS_CHAT_MODEL", "gpt-5-mini")
AGENTS_CHAT_API_KEY = optional(env, "AGENTS_CHAT_API_KEY", "")
# URL base de um fornecedor OpenAI-compatível (Google AI Studio, Groq, GitHub
# Models…). Vazia = api.openai.com. É o que permite usar um nível gratuito nesta
# fase sem tocar no código: o SDK é o mesmo, muda o destino.
AGENTS_CHAT_BASE_URL = optional(env, "AGENTS_CHAT_BASE_URL", "")
# Na API da OpenAI o parâmetro chama-se `max_completion_tokens`; aqui guarda o
# nome do `ARCHITECTURE.md` §6 ("cada chamada tem `max_tokens`").
AGENTS_CHAT_MAX_TOKENS = env.int("AGENTS_CHAT_MAX_TOKENS", default=1024)
# Por chamada, não por turno: um turno tem até `AGENTS_CHAT_MAX_TOOL_ITERATIONS`
# chamadas. O proxy corta o upstream aos 60 s, mas isto corre no worker.
AGENTS_CHAT_TIMEOUT_S = env.int("AGENTS_CHAT_TIMEOUT_S", default=30)
AGENTS_CHAT_MAX_TOOL_ITERATIONS = env.int("AGENTS_CHAT_MAX_TOOL_ITERATIONS", default=6)
# Os dois tetos diários (SECURITY.md §6), baixos de propósito e do dono:
# euros por tenant e perguntas por pessoa. Verificados no `POST` (429) e outra
# vez na tarefa antes de cada chamada (`erro/teto_de_custo`). `Decimal` e nunca
# `float`: é dinheiro (CLAUDE.md).
AGENTS_CHAT_DAILY_BUDGET_EUR = Decimal(optional(env, "AGENTS_CHAT_DAILY_BUDGET_EUR", "0.50"))
AGENTS_CHAT_DAILY_MESSAGES_PER_USER = env.int("AGENTS_CHAT_DAILY_MESSAGES_PER_USER", default=30)
# RGPD, decisão do dono: as conversas apagam-se aos 90 dias, tenant a tenant,
# pela entrada `purgar-conversas-expiradas` do `beat`.
AGENTS_CHAT_RETENTION_DAYS = env.int("AGENTS_CHAT_RETENTION_DAYS", default=90)
# Preço por milhão de tokens, em euros, por modelo. **Os tokens são a verdade e
# os euros derivam**: o que a tabela muda é o `cost_eur` gravado a partir de
# hoje, nunca os tokens. Um modelo fora da tabela custa 0,00 € e deixa um aviso
# no log — o teto diário em euros não o trava, e é por isso que o aviso existe.
# Valores de 2026-10-15 (USD 0,25 / 2,00 por milhão, a ~0,92 EUR/USD).
AGENTS_MODEL_PRICES_EUR_PER_MTOKEN = {
    "gpt-5-mini": {"input": Decimal("0.23"), "output": Decimal("1.85")},
}

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
