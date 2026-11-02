"""Rotas do `recipes` (ADR 0035, fatia A).

Rotas:

- `/recipes` — a lista das fichas técnicas e a gravação de uma nova
- `/recipes/{id}` — a ficha, e o `PATCH` que a altera

**Não há `/recipes/{id}/lines`**, e isso é o contrato e não um esquecimento: as
linhas viajam dentro do corpo, por substituição total (ADR 0035, decisão 4). A
contagem e a receção têm sub-recurso de linhas porque são **percursos**; uma
ficha técnica escreve-se de uma vez, num formulário com um botão de gravar.

**Não há `PUT` nem `DELETE`**: o primeiro seria um método publicado sem quem o
sirva, e o segundo apagava a ficha técnica de mercadoria que já entrou no
ledger — arquiva-se com `PATCH {is_active: false}`. Quem o impõe é o
`http_method_names` do `ReceitaViewSet`.

O `POST /recipes/{id}/production` é da **fatia B**, e entra aqui quando entrar.

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do
`config/urls.py`. `trailing_slash=False` e `SimpleRouter`.
"""

from rest_framework.routers import SimpleRouter

from apps.recipes.views import ReceitaViewSet

router = SimpleRouter(trailing_slash=False)
router.register("recipes", ReceitaViewSet, basename="receita")

urlpatterns = [*router.urls]
