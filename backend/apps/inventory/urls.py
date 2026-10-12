"""Rotas do `inventory` (ADR 0021, fatia 2).

Nesta fatia: apenas localizações. O ledger vem na fatia 3.

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do `config/urls.py`.
`trailing_slash=False` e `SimpleRouter`.
"""

from rest_framework.routers import SimpleRouter

from apps.inventory.views import LocalizacaoViewSet

router = SimpleRouter(trailing_slash=False)
router.register("locations", LocalizacaoViewSet, basename="localizacao")

urlpatterns = [*router.urls]
