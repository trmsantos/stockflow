"""Rotas do `inventory` (ADR 0021, fatia 2; ADR 0024, fatia 4).

Rotas:
- /locations — CRUD de localizações
- /stock/summary, /stock/by-location, /stock/by-product, /stock/alerts — painel read-only

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do `config/urls.py`.
`trailing_slash=False` e `SimpleRouter`.
"""

from rest_framework.routers import SimpleRouter

from apps.inventory.views import LocalizacaoViewSet, StockPanelViewSet

router = SimpleRouter(trailing_slash=False)
router.register("locations", LocalizacaoViewSet, basename="localizacao")
router.register("stock", StockPanelViewSet, basename="stock")

urlpatterns = [*router.urls]
