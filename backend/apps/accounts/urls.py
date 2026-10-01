"""Rotas da autenticação de sessão, sob `/api/v1/auth/` (ADR 0010).

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do
`config/urls.py`, logo o namespace é o `api` de todos os endpoints da API e os
nomes resolvem-se por `reverse("api:login")`. Um `app_name` aqui daria
`api:accounts:login` e punha o nome do módulo no meio de um nome de rota, que é
detalhe de arrumação interna a aparecer no contrato.

## Sem barra final, e é a convenção da API e não um descuido

`auth/login` e não `auth/login/`. A razão é o `APPEND_SLASH` do
`CommonMiddleware`: num `POST` para um path que precisa da barra, o Django
responde 301 e o browser repete o pedido em **GET**, sem corpo — o login
"falhava" com um 405 e sem nada no log que explicasse porquê. É o mesmo motivo
pelo qual o `/healthz` não tem barra (`config/urls.py`), e é também a forma que
os caminhos do cliente já usam (`frontend/src/features/*/api.ts`). O
`api/v1/schema/` tem barra porque é do drf-spectacular, não nossa.

Nomes em português porque são o contrato público (`sessao`, `tenant-ativo`), e
`tenant-ativo` com hífen porque é um path e não um identificador.
"""

from django.urls import path

from apps.accounts.views import LoginView, LogoutView, SessaoView, TenantAtivoView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/logout", LogoutView.as_view(), name="logout"),
    path("auth/sessao", SessaoView.as_view(), name="sessao"),
    path("auth/tenant-ativo", TenantAtivoView.as_view(), name="tenant-ativo"),
]
