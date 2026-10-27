"""Rotas do `inventory` (ADR 0021, fatia 2; ADR 0025, fatia 5; ADR 0030,
contagens; ADR 0034, os sete recursos de `/stock`).

Rotas:
- /locations — CRUD de localizações
- /stock/levels, /stock/summary — o ecrã de Stock (linhas e os quatro números)
- /stock/alerts, /stock/alerts/summary, /stock/alerts/waste — o ecrã de Alertas
- /stock/movements — o ledger de um artigo (`?artigo=` obrigatório)
- /stock/movements/waste, /stock/movements/adjustment, /stock/movements/transfer —
  movimentos manuais
- /stock/counts, /stock/counts/{id}/lines, /stock/counts/{id}/closing — contagem física

O `GET /stock/by-location` e o `GET /stock/by-product` **morreram inteiros**
(ADR 0034, decisão 1): eram de grão lote, exigiam um filtro obrigatório e não
tinham consumidor nenhum — nem o cliente, nem o assistente, nem o `reporting`.

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
