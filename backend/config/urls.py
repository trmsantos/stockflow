"""Rotas de topo.

A API vive toda sob `/api/v1/` (ARCHITECTURE.md §5). As rotas de cada módulo
entram em `api_v1_patterns` com um `include("apps.<m>.urls")` quando a feature
correspondente for construída — por agora só existe o schema.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView

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
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "api"))),
]
