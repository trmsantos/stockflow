"""Rotas da autenticação, da activação, dos convites e do menu (ADR 0010 e 0011).

Sem `app_name`: estas entram no `include((api_v1_patterns, "api"))` do
`config/urls.py`, logo o namespace é o `api` de todos os endpoints da API e os
nomes resolvem-se por `reverse("api:login")`. Um `app_name` aqui daria
`api:accounts:login` e punha o nome do módulo no meio de um nome de rota, que é
detalhe de arrumação interna a aparecer no contrato.

## `/auth/` é a família dispensada de âmbito, e o prefixo é a regra

As cinco rotas sob `auth/` são as que correm **antes** de existir tenant na
sessão (ADR 0007 e ADR 0010): login, logout, sessão, troca de estabelecimento e
activação de convite. Os `convites` e o `menu` ficam **fora** do `auth/` de
propósito — são endpoints normais, com âmbito e só para o `owner`, e um
`/auth/convites` sugeria o contrário a quem lesse o path. A dispensa continua a
ser declarada na **view** e nunca inferida do prefixo
(`tenant_scope_exempt`); o prefixo é o que torna a regra legível, não o que a
impõe.

## Sem barra final, e é a convenção da API e não um descuido

`auth/login` e não `auth/login/`. A razão é o `APPEND_SLASH` do
`CommonMiddleware`: num `POST` para um path que precisa da barra, o Django
responde 301 e o browser repete o pedido em **GET**, sem corpo — o login
"falhava" com um 405 e sem nada no log que explicasse porquê. É o mesmo motivo
pelo qual o `/healthz` não tem barra (`config/urls.py`), e é também a forma que
os caminhos do cliente já usam (`frontend/src/features/*/api.ts`). O
`api/v1/schema/` tem barra porque é do drf-spectacular, não nossa.

É também por isso que o router dos convites leva `trailing_slash=False`: o
default do DRF é gerar `convites/`, e um `POST` para `convites` daria o mesmo 301
seguido de `GET` — ou seja, a criação de um convite a responder 405.
`SimpleRouter` e não `DefaultRouter`: o segundo acrescenta uma raiz de API
navegável, que é um endpoint a mais a enumerar o que existe e que o
`DEFAULT_RENDERER_CLASSES` só com JSON (`base.py`) não renderiza de qualquer
forma.

Nomes em português porque são o contrato público (`sessao`, `tenant-ativo`,
`ativar`, `convites`), e `tenant-ativo` com hífen porque é um path e não um
identificador. `ativar` casa com a rota `/ativar` da SPA, que é onde o link do
convite aterra.
"""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.accounts.views import (
    AtivacaoView,
    ConviteViewSet,
    LoginView,
    LogoutView,
    MenuView,
    RotasDeMenuView,
    SessaoView,
    TenantAtivoView,
)

router = SimpleRouter(trailing_slash=False)
router.register("convites", ConviteViewSet, basename="convite")

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/logout", LogoutView.as_view(), name="logout"),
    path("auth/sessao", SessaoView.as_view(), name="sessao"),
    path("auth/tenant-ativo", TenantAtivoView.as_view(), name="tenant-ativo"),
    path("auth/ativar", AtivacaoView.as_view(), name="ativar"),
    # O menu (ADR 0009 e ADR 0011). `menu/rotas` antes de `menu` por leitura e
    # não por necessidade — são paths distintos e o resolver não os confunde.
    #
    # O menu **efectivo** não está aqui: viaja no `GET /auth/sessao`. O que esta
    # família tem é o registo (o que existe para configurar) e a escrita da
    # configuração; um `GET /menu` seria uma terceira fonte para a mesma lista.
    #
    # Sem barra final, como o resto da API, e pela mesma razão medida: o
    # `APPEND_SLASH` do `CommonMiddleware` responderia 301 a um `PUT` para
    # `menu`, e o browser repetiria o pedido em **GET** e sem corpo — a
    # configuração "guardava" com um 405 e nada no log a explicá-lo.
    path("menu/rotas", RotasDeMenuView.as_view(), name="menu-rotas"),
    path("menu", MenuView.as_view(), name="menu"),
    *router.urls,
]
