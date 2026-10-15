"""Rotas de topo.

A API vive toda sob `/api/v1/` (ARCHITECTURE.md §5). As rotas de cada módulo
entram em `api_v1_patterns` com um `include("apps.<m>.urls")` quando a feature
correspondente for construída — hoje existem o schema e os quatro endpoints de
autenticação do `accounts` (ADR 0010).

Fora do `/api/v1/` vivem três coisas, e cada uma por uma razão diferente: o
admin (path não óbvio, SECURITY.md §5), o `/healthz` e o `/readyz`. Os dois
últimos não são API — não têm cliente gerado, não entram no `schema.yml` e são
consumidos por infraestrutura (o `HEALTHCHECK` do Docker e o orquestrador).
Ver `config/health.py`.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView

from apps.accounts.api import dispensar_ambito
from config.health import healthz, readyz

api_v1_patterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # As quatro rotas de `/api/v1/auth/`. São dispensadas de âmbito de tenant, e
    # a dispensa é declarada nas views (`apps/accounts/views.py`), não aqui: o
    # `dispensar_ambito` abaixo existe só para o admin, cujas views não são
    # nossas para lhes pôr um atributo. A lista fechada das dispensas está em
    # `tests/test_rls_isolation.py` e falha nos dois sentidos.
    path("", include("apps.accounts.urls")),
    # O recurso `/documents` (ADR 0021, fatia 1). Com âmbito, como tudo o que não
    # declara o contrário: nenhuma destas views leva `tenant_scope_exempt`, e é
    # essa ausência que as torna normais. A lista fechada das dispensas em
    # `tests/test_rls_isolation.py` **não cresce** com esta feature, e é o gate
    # principal da ADR 0020 (adenda 2, gate 3).
    path("", include("apps.purchasing.urls")),
    # Catálogo: produtos, embalagens, fornecedores (ADR 0021, fatia 2).
    path("", include("apps.catalog.urls")),
    # Inventário: localizações (ADR 0021, fatia 2). O ledger vem na fatia 3.
    path("", include("apps.inventory.urls")),
    # O assistente (ADR 0027): `/assistant/conversations`. Com âmbito, como
    # tudo o que não declara o contrário; as três rotas entram no lado com
    # âmbito da lista fechada do `tests/test_rls_isolation.py`.
    path("", include("apps.agents.urls")),
]

if settings.API_DOCS_ENABLED:
    # Versão "split" do Swagger UI: entrega o script de arranque num pedido
    # separado em vez de o pôr inline, o que o torna compatível com a CSP sem
    # 'unsafe-inline' (SECURITY.md §2).
    api_v1_patterns += [
        path(
            "docs/",
            SpectacularSwaggerSplitView.as_view(url_name="api:schema"),
            name="docs",
        ),
    ]

urlpatterns = [
    # Saúde do processo, primeiro na lista: a resolução de URLs é uma varredura
    # linear e estas são as rotas mais pedidas de todas (uma por contentor a
    # cada poucos segundos).
    #
    # Sem barra final, e não é estética: com a rota a `healthz/`, um pedido a
    # `/healthz` levava um 301 do `APPEND_SLASH` do `CommonMiddleware` — e um
    # healthcheck com `curl -f` trata 301 como sucesso, pelo que o contentor
    # ficava "saudável" sem nunca ter chegado à view. O caminho tem de ser
    # exatamente o que o `HEALTHCHECK` do Dockerfile pede.
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # Path do admin fora do default, numa variável só (`ADMIN_PATH`) que
    # alimenta este lado e o proxy (SECURITY.md §5). O path não é um controlo:
    # está commitado. A restrição por IP existe no proxy mas o seu default não
    # restringe nada — dizer aqui "é imposto no proxy" descrevia um controlo que
    # não está ligado. O que está à frente do admin hoje é o rate limit de 5/min
    # e o lockout do axes.
    #
    # O `dispensar_ambito` é a declaração de que o admin é servido **sem**
    # âmbito de tenant, e é a única forma de a fazer para views que não são
    # nossas: o default do `TenantMiddleware` é ter âmbito, e um operador do
    # StockFlow não tem `tenant_id` na sessão — sem esta linha, o admin
    # responderia 403 `sem_sessao` em todos os pedidos, incluindo o login.
    # A alternativa era reconhecer o path do admin dentro do middleware, que é
    # a lista de paths nas settings que a ADR 0007 rejeita, escondida num
    # `startswith`. Aqui a dispensa fica onde tem de ficar: nas views.
    # O que o admin vê continua a ser só o que não tem política — `Tenant` e
    # `Membership` não estão registados (`apps/accounts/admin.py`).
    path(settings.ADMIN_URL, dispensar_ambito(admin.site.urls)),
    # Com âmbito, como tudo o que não declara o contrário. Um utilizador
    # autenticado com estabelecimento ativo lê o schema; um operador do
    # StockFlow sem tenant na sessão leva 403 — e o `pnpm gen:api` não usa
    # este endpoint, usa o comando `manage.py spectacular`.
    path("api/v1/", include((api_v1_patterns, "api"))),
]
