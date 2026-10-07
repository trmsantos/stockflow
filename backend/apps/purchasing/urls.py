"""Rotas do `purchasing`: o recurso `/documents` (ADR 0021, decisão 9).

Sem `app_name`, como o `accounts/urls.py`: estas entram no
`include((api_v1_patterns, "api"))` do `config/urls.py`, logo o namespace é o
`api` de todos os endpoints e os nomes resolvem-se por
`reverse("api:documento-imagem")`. Um `app_name` aqui daria
`api:purchasing:documento-imagem` e punha o nome do módulo no meio de um nome de
rota, que é detalhe de arrumação interna a aparecer no contrato.

`trailing_slash=False` e `SimpleRouter`, pelas duas razões já medidas no
`accounts/urls.py`: o `APPEND_SLASH` do `CommonMiddleware` responde 301 a um
`POST` para um path que precisa da barra, e o browser repete o pedido em **GET** e
sem corpo — um upload "falhava" com um 405 e nada no log que o explicasse. E
`SimpleRouter` porque o `DefaultRouter` acrescenta uma raiz de API navegável, que
é um endpoint a mais a enumerar o que existe.

O caminho é `documents` em inglês, como os campos: é a decisão 9 da ADR 0021
(*"caminhos e campos em inglês, como os vizinhos"*). O `basename` é `documento`
em português porque não é contrato — é o prefixo dos nomes de rota, que só este
repositório vê.
"""

from rest_framework.routers import SimpleRouter

from apps.purchasing.views import DocumentoViewSet

router = SimpleRouter(trailing_slash=False)
router.register("documents", DocumentoViewSet, basename="documento")

urlpatterns = [*router.urls]
