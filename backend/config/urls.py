"""Rotas de topo.

A API vive toda sob `/api/v1/` (ARCHITECTURE.md §5). As rotas de cada módulo
entram em `api_v1_patterns` com um `include("apps.<m>.urls")` quando a feature
correspondente for construída — por agora só existe o schema.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView

from apps.accounts.api import dispensar_ambito

api_v1_patterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
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
    # Path do admin fora do default e configurável por instalação
    # (SECURITY.md §5). O acesso por IP/VPN é imposto no proxy.
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
