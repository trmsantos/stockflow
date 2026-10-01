"""Os quatro endpoints da autenticação de sessão (ADR 0010).

É o primeiro `views.py` do repositório, e por isso este docstring fixa quatro
coisas que vão valer para todos os que vierem depois.

| Endpoint | Quem pode | Estado que escreve |
|---|---|---|
| `POST /api/v1/auth/login` | qualquer um | abre a sessão, escolhe o âmbito se houver um só |
| `POST /api/v1/auth/logout` | autenticado | fecha a sessão |
| `GET  /api/v1/auth/sessao` | qualquer um | repara a sessão (ver `services.sessao_atual`) |
| `POST /api/v1/auth/tenant-ativo` | autenticado | escreve o âmbito escolhido |

**1. A view é fina e a lógica está em `services.py`.** O que cada método aqui
faz é: validar o corpo com um serializer, chamar **uma** função de service,
serializar o resultado. A ordem obrigatória do login — `authenticate()` →
`login()` → descoberta — não está aqui de propósito: é uma regra que não pode
ser escrita de outra maneira e a view não é sítio para a guardar.

**2. As quatro são dispensadas de âmbito, e a dispensa é declarada na view.**
`@tenant_scope_exempt` (ADR 0007): estas correm **antes** de existir tenant na
sessão, como o login. O default do `TenantMiddleware` é ter âmbito, logo sem a
declaração as quatro respondiam 403 `sem_sessao` — incluindo o login, o que é
um impasse perfeito. A alternativa (reconhecer estes paths dentro do middleware)
é a lista de paths nas settings que a ADR 0007 rejeita, escondida num
`startswith`. A lista das dispensas de hoje está fechada num teste
(`tests/test_rls_isolation.py`), que falha nos dois sentidos.

O `tenant-ativo` é o caso que mostra porque é que a dispensa tem de ser
declarada e não inferida: se **não** fosse dispensado, o middleware teria aberto
o âmbito antigo antes da view e a troca levantaria `TenantScopeConflict` ao
tentar abrir o novo. Trocar de estabelecimento acontece **entre** pedidos, e não
dentro de um (ADR 0007).

**3. O CSRF é reposto à mão, e sem esta linha não existiria.** O `as_view()` do
DRF embrulha a view em `csrf_exempt`, porque o DRF prefere verificar o token
dentro do `SessionAuthentication` — mas o `SessionAuthentication.enforce_csrf`
só corre quando **encontra** um utilizador na sessão. Num `POST /auth/login` o
pedido é anónimo por definição: o DRF não encontra utilizador, não verifica
nada, e o `CsrfViewMiddleware` já tinha sido instruído a não verificar. O
resultado era um endpoint de login sem protecção de CSRF nenhuma — *login CSRF*,
em que um atacante faz o browser da vítima entrar na conta **dele** e passa a ver
o que ela lá faz. O `@method_decorator(csrf_protect, name="dispatch")` repõe a
verificação dentro da view, para anónimos incluídos, e há um teste que a mede
com `Client(enforce_csrf_checks=True)`. Nada é desligado em sítio nenhum
(CLAUDE.md).

O token chega ao cliente pelo `GET /auth/sessao`, que leva `ensure_csrf_cookie`
e que a SPA chama no arranque de qualquer forma — é por isso que a ADR 0010 não
precisa de um endpoint de CSRF.

**4. O `request` que vai para o service é o do Django, não o do DRF.** O
`Request` do DRF proxia as *leituras* de atributo para o `HttpRequest` por
baixo (`__getattr__`), mas não tem `__setattr__`: uma **escrita** fica no
invólucro e nunca chega ao pedido real. Isso tem uma consequência concreta e
silenciosa: o axes marca o lockout com `request.axes_locked_out = True` de
dentro do `authenticate()`, e o `AxesMiddleware` lê esse atributo no
`HttpRequest`. Passar o `Request` do DRF fazia a decisão de lockout ser tomada
e a resposta 429 ser **perdida** — o cliente recebia o 400 de credenciais como
se nada fosse, e nenhum teste que não medisse o status o apanharia. O
`_pedido_django` abaixo resolve isso num sítio só.

## Códigos estáveis que estas views devolvem

* `400 credenciais_invalidas` — login recusado. Email inexistente, password
  errada e conta inativa dão **o mesmo** corpo: distinguir confirmava a um
  estranho quais os emails são clientes;
* `403 tenant_desconhecido` — o estabelecimento pedido no `tenant-ativo` não tem
  pertença ativa de quem pede. É o mesmo código do `TenantMiddleware`, porque é
  a mesma condição e o cliente já sabe o que fazer com ele;
* `429 conta_bloqueada` — lockout do axes. **Não** sai daqui: o
  `AxesMiddleware` substitui a resposta desta view, e o corpo JSON está em
  `config/lockout.py`. Está no `@extend_schema` porque o cliente o recebe deste
  endpoint, e um contrato que só descreve o caminho feliz é meio contrato;
* `403` sem `code` nenhum — é o do DRF para um anónimo a pedir `logout` ou
  `tenant-ativo`. Fica como é: o cliente que chega lá sem sessão tem um bug, e
  não vale inventar um código para o descrever.

## Duas colisões de status que o `schema.yml` não consegue descrever, ditas aqui

Nenhuma é um defeito, as duas são limitações do formato, e calá-las produzia um
cliente gerado que promete mais do que o servidor cumpre:

* **o 400 tem duas formas.** Um corpo inválido (campo em falta, email mal
  formado) sai na forma normal do DRF, `{"email": ["..."]}`, por campo — é o que
  um formulário precisa de mostrar ao lado de cada input. A recusa de
  credenciais sai em `{code, detail}`, que é para o cliente **ramificar**. O
  `@extend_schema` declara a segunda, porque é a que tem um código estável;
* **o 429 tem duas origens.** O lockout do axes responde `{code, detail}` com
  `conta_bloqueada`; o `AnonRateThrottle`/`UserRateThrottle` do DRF responde
  `{detail}` **sem** `code`, e aplica-se a todos os endpoints do projeto. O
  schema declara o primeiro.

A consequência prática para quem escreve o cliente é uma só, e o `errors.ts` do
frontend já a cumpre: o `code` lê-se **defensivamente** (`string | null`) e
nunca se assume presente só porque o status é 400 ou 429.

## Só JSON, e é a segunda camada do controlo do ponto 3

As três views de escrita levam `parser_classes = [JSONParser]`, retirando o
`MultiPartParser` que o `base.py` põe por omissão (está lá para o upload de
faturas). A razão é a mesma do `csrf_protect`: um formulário HTML numa página de
outro domínio consegue fazer `POST` de `multipart/form-data` **sem** pedir
autorização ao browser, enquanto um corpo `application/json` obriga a um
preflight de CORS que a política de mesma origem recusa. O token de CSRF é o
controlo; isto é o que fecha a via que não precisa de token nenhum para chegar
aqui, e custa uma linha por view. Um pedido form-encoded leva 415 antes de
qualquer código nosso correr.

Efeito lateral que vale registar: o axes guarda o `request.POST` na coluna
`post_data` do `axes_accessattempt`, e com corpos JSON o `request.POST` está
vazio — logo nenhuma password passa pela tabela de tentativas, nem em claro nem
mascarada.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import tenant_scope_exempt
from apps.accounts.middleware import CODIGO_DESCONHECIDO
from apps.accounts.serializers import (
    ErroOutSerializer,
    LoginInSerializer,
    SessaoOutSerializer,
    TenantAtivoInSerializer,
)
from apps.accounts.services import (
    CODIGO_CREDENCIAIS_INVALIDAS,
    RecusaDeSessao,
    SessaoOut,
    escolher_tenant_ativo,
    iniciar_sessao,
    sessao_atual,
    terminar_sessao,
)

__all__ = [
    "STATUS_DA_RECUSA",
    "LoginView",
    "LogoutView",
    "SessaoView",
    "TenantAtivoView",
]

#: O status de cada código de recusa. O mapa vive aqui e não em `services.py`
#: porque um status HTTP é transporte, e um service que o soubesse era um service
#: a saber HTTP. Está fechado contra o `CODIGOS_DE_RECUSA` dos services por um
#: teste, nos dois sentidos: um código sem status dava `KeyError` (500 numa
#: recusa de login) e um status a mais descrevia um código que não existe.
STATUS_DA_RECUSA: dict[str, int] = {
    CODIGO_CREDENCIAIS_INVALIDAS: status.HTTP_400_BAD_REQUEST,
    CODIGO_DESCONHECIDO: status.HTTP_403_FORBIDDEN,
}


def _pedido_django(request: Request | HttpRequest) -> HttpRequest:
    """O `HttpRequest` por baixo do `Request` do DRF — ver o ponto 4 do módulo.

    `getattr` com default e não `request._request` direto: assim a função
    responde também por um `HttpRequest` puro, o que a torna chamável de um
    teste que não passe pelo DRF sem um ramo de `isinstance`.
    """
    return getattr(request, "_request", request)


def _resposta(sessao: SessaoOut) -> Response:
    """A resposta de sucesso das quatro views: sempre a mesma forma."""
    return Response(SessaoOutSerializer(sessao).data)


def _resposta_de_recusa(recusa: RecusaDeSessao) -> Response:
    """`{code, detail}` com o status do código. A forma do `TenantMiddleware`."""
    return Response(
        {"code": recusa.codigo, "detail": recusa.detalhe},
        status=STATUS_DA_RECUSA[recusa.codigo],
    )


@tenant_scope_exempt
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """`POST /api/v1/auth/login` — email e password, devolve a sessão.

    `AllowAny` e não o `IsAuthenticated` do default: é o endpoint por onde se
    passa a estar autenticado.

    Quem está autenticado e volta a fazer login é servido normalmente, e o
    `login()` do Django faz `flush()` à sessão anterior se for outra conta — o
    que fecha o caminho em que uma sessão de A ficava com o `tenant_id` de A e o
    utilizador B.
    """

    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="auth_login",
        summary="Iniciar sessão",
        request=LoginInSerializer,
        responses={
            status.HTTP_200_OK: SessaoOutSerializer,
            status.HTTP_400_BAD_REQUEST: ErroOutSerializer,
            status.HTTP_429_TOO_MANY_REQUESTS: ErroOutSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        corpo = LoginInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        try:
            sessao = iniciar_sessao(
                _pedido_django(request),
                email=corpo.validated_data["email"],
                password=corpo.validated_data["password"],
            )
        except RecusaDeSessao as recusa:
            return _resposta_de_recusa(recusa)
        return _resposta(sessao)


@tenant_scope_exempt
@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    """`POST /api/v1/auth/logout` — fecha a sessão e devolve o estado `anonimo`.

    `IsAuthenticated`: só se termina uma sessão que existe. Um anónimo leva o
    403 do DRF, que é correcto e não precisa de código próprio — repetir o
    logout é um bug do cliente, não um caso de uso.

    `POST` e não `GET`, apesar de não levar corpo: um `GET` que fecha a sessão é
    disparável por um `<img>` numa página qualquer, e a protecção de CSRF não se
    aplica a métodos seguros.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="auth_logout",
        summary="Terminar sessão",
        request=None,
        responses={status.HTTP_200_OK: SessaoOutSerializer},
    )
    def post(self, request: Request) -> Response:
        return _resposta(terminar_sessao(_pedido_django(request)))


@tenant_scope_exempt
@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessaoView(APIView):
    """`GET /api/v1/auth/sessao` — quem está autenticado, onde, e onde mais pode.

    `AllowAny` e 200 com `estado = anonimo` para um pedido sem sessão: o
    arranque da SPA tem de poder perguntar "há sessão?" sem ter sessão. Com
    `IsAuthenticated`, a pergunta respondia 403 e o cliente passava a distinguir
    dois 403 diferentes no seu caminho mais crítico.

    `ensure_csrf_cookie` é o que dispensa um endpoint de CSRF próprio (ADR
    0010): a SPA chama isto no arranque, o cookie `csrftoken` vem na resposta, e
    o `POST /auth/login` já tem com que o assinar. Note-se que o `login()` do
    Django **roda** o token (`rotate_token`), pelo que o cookie muda na resposta
    do login — o cliente lê-o do cookie a cada pedido e não o guarda, logo isso
    é transparente para ele.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_sessao",
        summary="Estado da sessão",
        responses={status.HTTP_200_OK: SessaoOutSerializer},
    )
    def get(self, request: Request) -> Response:
        return _resposta(sessao_atual(_pedido_django(request)))


@tenant_scope_exempt
@method_decorator(csrf_protect, name="dispatch")
class TenantAtivoView(APIView):
    """`POST /api/v1/auth/tenant-ativo` — escolhe o estabelecimento da sessão.

    O `tenant_id` do corpo é **argumento e não credencial**: quem o verifica é a
    política, dentro do `tenant_scope` que o service abre, contra a pertença de
    quem pede. Esta view não o compara com nada — se comparasse, haveria duas
    verificações e uma delas acabaria por ser a única.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="auth_tenant_ativo",
        summary="Escolher o estabelecimento ativo",
        request=TenantAtivoInSerializer,
        responses={
            status.HTTP_200_OK: SessaoOutSerializer,
            status.HTTP_403_FORBIDDEN: ErroOutSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        corpo = TenantAtivoInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        try:
            sessao = escolher_tenant_ativo(
                _pedido_django(request),
                tenant_id=corpo.validated_data["tenant_id"],
            )
        except RecusaDeSessao as recusa:
            return _resposta_de_recusa(recusa)
        return _resposta(sessao)
