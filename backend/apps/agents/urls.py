"""Rotas do `agents`: o assistente (ADR 0027, decisão 4).

Caminhos em inglês como os vizinhos; `trailing_slash=False` e `SimpleRouter`,
pelas razões medidas no `accounts/urls.py` (o `APPEND_SLASH` responde 301 a um
`POST` sem barra e o browser repete em `GET`). Sem `app_name`: entram no
`include((api_v1_patterns, "api"))` do `config/urls.py`.

Com âmbito, como tudo o que não declara o contrário: nenhuma destas views leva
`tenant_scope_exempt`, e a lista fechada do `tests/test_rls_isolation.py` ganha
as três rotas do lado com âmbito.
"""

from rest_framework.routers import SimpleRouter

from apps.agents.views import ConversaViewSet

router = SimpleRouter(trailing_slash=False)
router.register("assistant/conversations", ConversaViewSet, basename="conversa")

urlpatterns = [*router.urls]
