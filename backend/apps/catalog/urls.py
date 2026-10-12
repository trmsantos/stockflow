"""Rotas do `catalog`: artigos, embalagens, fornecedores (ADR 0021, fatia 2).

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do `config/urls.py`.
`trailing_slash=False` e `SimpleRouter`.

Caminhos em inglês (contrato). Basenames em português (interno).
"""

from rest_framework.routers import SimpleRouter

from apps.catalog.views import FornecedorViewSet, ProdutoViewSet

router = SimpleRouter(trailing_slash=False)
router.register("products", ProdutoViewSet, basename="produto")
router.register("suppliers", FornecedorViewSet, basename="fornecedor")

urlpatterns = [*router.urls]
