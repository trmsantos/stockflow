"""Rotas do `inventory` (ADR 0021, fatia 2; ADR 0024, fatia 4; ADR 0025, fatia 5;
ADR 0030, contagens).

Rotas:
- /locations — CRUD de localizações
- /stock/summary, /stock/by-location, /stock/by-product, /stock/alerts — painel read-only
- /stock/movements/waste, /stock/movements/adjustment, /stock/movements/transfer —
  movimentos manuais
- /stock/counts, /stock/counts/{id}/lines, /stock/counts/{id}/closing — contagem física

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do `config/urls.py`.
`trailing_slash=False` e `SimpleRouter`.
"""

from rest_framework.routers import SimpleRouter

from apps.inventory.views import (
    ContagemViewSet,
    LocalizacaoViewSet,
    StockMovementViewSet,
    StockPanelViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("locations", LocalizacaoViewSet, basename="localizacao")
router.register("stock", StockPanelViewSet, basename="stock")
router.register("stock/movements", StockMovementViewSet, basename="stock-movements")
router.register("stock/counts", ContagemViewSet, basename="stock-counts")

urlpatterns = [*router.urls]
