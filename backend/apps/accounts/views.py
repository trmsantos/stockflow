"""A autenticação de sessão, a activação de convites e a gestão deles (ADR 0010).

É o primeiro `views.py` do repositório, e por isso este docstring fixa quatro
coisas que vão valer para todos os que vierem depois.

**Duas famílias, e a fronteira entre elas é o `/auth/`.** Tudo o que vive sob
`/api/v1/auth/` é dispensado de âmbito de tenant, porque corre antes de existir
um; o resto é servido com âmbito, que é o default. A regra é legível no path, e
a lista fechada que a impõe está em `tests/test_rls_isolation.py`.

| Endpoint | Quem pode | Âmbito | Estado que escreve |
|---|---|---|---|
| `POST /auth/login` | qualquer um | dispensado | a sessão, e o âmbito se houver um só |
| `POST /auth/logout` | autenticado | dispensado | fecha a sessão |
| `GET  /auth/sessao` | qualquer um | dispensado | repara-a (ver `services.sessao_atual`) |
| `POST /auth/tenant-ativo` | autenticado | dispensado | o âmbito escolhido |
| `POST /auth/ativar` | qualquer um | **o do link** | password, pertença, convite, sessão |
| `/convites[/<id>/…]` | `owner` | o da sessão | cria, reenvia e revoga convites |

(Os paths são relativos a `/api/v1/`.)

**1. A view é fina e a lógica está em `services.py`.** O que cada método aqui
faz é: validar o corpo com um serializer, chamar **uma** função de service,
serializar o resultado. A ordem obrigatória do login — `authenticate()` →
`login()` → descoberta — não está aqui de propósito: é uma regra que não pode
ser escrita de outra maneira e a view não é sítio para a guardar.

**2. As cinco de `/auth/` são dispensadas de âmbito, e a dispensa é declarada
na view.** `@tenant_scope_exempt` (ADR 0007): estas correm **antes** de existir
tenant na sessão, como o login. O default do `TenantMiddleware` é ter âmbito,
logo sem a declaração respondiam 403 `sem_sessao` — incluindo o login, o que é
um impasse perfeito. A alternativa (reconhecer estes paths dentro do middleware)
é a lista de paths nas settings que a ADR 0007 rejeita, escondida num
`startswith`. A lista das dispensas de hoje está fechada num teste
(`tests/test_rls_isolation.py`), que falha nos dois sentidos.

O `tenant-ativo` é o caso que mostra porque é que a dispensa tem de ser
declarada e não inferida: se **não** fosse dispensado, o middleware teria aberto
o âmbito antigo antes da view e a troca levantaria `TenantScopeConflict` ao
tentar abrir o novo. Trocar de estabelecimento acontece **entre** pedidos, e não
dentro de um (ADR 0007).

Dispensado **não** quer dizer sem âmbito: o `ativar` abre `tenant_scope` ele
mesmo, com o uuid que vem do fragmento do link, e lê o convite lá dentro. É a
inversão da ADR 0007 com o link no lugar da sessão — e é por ela que a tabela
dos convites tem política normal em vez de entrar na lista das tabelas legíveis
sem âmbito. O `ConviteViewSet`, pelo contrário, **não** é dispensado: convidar é
uma operação de dentro de um estabelecimento.

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

Isto vale para **qualquer endpoint anónimo de escrita**, e o `ativar` é o
segundo: também ele é anónimo por definição no caminho de uma conta nova, logo
também ele nasceria sem CSRF. Está medido nas duas metades, com o mesmo
`enforce_csrf_checks=True` — o que falta ter o mesmo tratamento são as duas
views da reposição de password, que ainda não existem.

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

Os quatro códigos da família dos convites estão nos docstrings da `AtivacaoView`
e do `ConviteViewSet`, e os dois mapas de status estão fechados contra os dois
conjuntos de códigos dos services por um teste, nos dois sentidos.

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

Todas as views de escrita levam `parser_classes = [JSONParser]`, retirando o
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

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import Papel, PertenceAoTenant, TemPapel, tenant_scope_exempt
from apps.accounts.middleware import CODIGO_DESCONHECIDO
from apps.accounts.models import Invitation
from apps.accounts.selectors import convites_do_ambito
from apps.accounts.serializers import (
    AtivacaoInSerializer,
    ConviteCriadoOutSerializer,
    ConviteInSerializer,
    ConviteOutSerializer,
    ErroOutSerializer,
    LoginInSerializer,
    SessaoOutSerializer,
    TenantAtivoInSerializer,
)
from apps.accounts.services import (
    CODIGO_CONVITE_DE_OUTRA_CONTA,
    CODIGO_CONVITE_EXIGE_SESSAO,
    CODIGO_CONVITE_INVALIDO,
    CODIGO_CONVITE_NAO_PENDENTE,
    CODIGO_CREDENCIAIS_INVALIDAS,
    ConviteCriado,
    Recusa,
    RecusaDeConvite,
    RecusaDeSessao,
    SessaoOut,
    ativar_convite,
    criar_convite,
    escolher_tenant_ativo,
    iniciar_sessao,
    reenviar_convite,
    revogar_convite,
    sessao_atual,
    terminar_sessao,
)

__all__ = [
    "STATUS_DA_RECUSA",
    "STATUS_DA_RECUSA_DE_CONVITE",
    "AtivacaoView",
    "ConviteViewSet",
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

#: O mesmo, para a família dos convites, e fechado pelo mesmo teste contra o
#: `CODIGOS_DE_RECUSA_DE_CONVITE`. São dois mapas e não um porque os dois
#: conjuntos de códigos são de endpoints diferentes: juntá-los dava ao cliente
#: gerado a união de todos os códigos em cada resposta, a sugerir ramos que
#: aquele endpoint nunca devolve.
STATUS_DA_RECUSA_DE_CONVITE: dict[str, int] = {
    CODIGO_CONVITE_INVALIDO: status.HTTP_400_BAD_REQUEST,
    CODIGO_CONVITE_EXIGE_SESSAO: status.HTTP_409_CONFLICT,
    CODIGO_CONVITE_DE_OUTRA_CONTA: status.HTTP_403_FORBIDDEN,
    CODIGO_CONVITE_NAO_PENDENTE: status.HTTP_409_CONFLICT,
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


def _resposta_de_recusa(recusa: Recusa, mapa: dict[str, int]) -> Response:
    """`{code, detail}` com o status do código. A forma do `TenantMiddleware`.

    O mapa vai como argumento **obrigatório** porque há dois, um por família de
    códigos, e um default escolheria o errado em silêncio: um `KeyError` aqui é
    um 500 numa resposta de recusa, que é o pior sítio para o ter. Explícito, o
    pior caso é não compilar na cabeça de quem lê.

    Que os dois mapas cubram exatamente os dois conjuntos de códigos é garantido
    por dois testes, nos dois sentidos.
    """
    return Response(
        {"code": recusa.codigo, "detail": recusa.detalhe},
        status=mapa[recusa.codigo],
    )


def _resposta_de_validacao(erro: ValidationError) -> Response:
    """400 na forma por campo do DRF, a partir de um `ValidationError` do Django.

    O DRF não converte o `ValidationError` do `django.core.exceptions` — deixá-lo
    subir era um 500 numa recusa de validação. Os services desta app levantam-no
    **sempre** com dicionário (ver `_validar_password` e `_email_ja_convidado`),
    pelo que o `message_dict` existe; o `getattr` é a rede para o caso de alguém
    acrescentar um `raise ValidationError("texto")` sem dicionário, que sairia
    como erro não associado a campo nenhum em vez de 500.
    """
    return Response(
        getattr(erro, "message_dict", {"detail": erro.messages}),
        status=status.HTTP_400_BAD_REQUEST,
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
            return _resposta_de_recusa(recusa, STATUS_DA_RECUSA)
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
            return _resposta_de_recusa(recusa, STATUS_DA_RECUSA)
        return _resposta(sessao)


@tenant_scope_exempt
@method_decorator(csrf_protect, name="dispatch")
class AtivacaoView(APIView):
    """`POST /api/v1/auth/ativar` — aceita um convite e devolve a sessão.

    É a quinta view dispensada de âmbito, e a razão é a do login: corre **antes**
    de existir tenant na sessão. A diferença — e é a decisão da ADR 0010 — é que
    esta view **abre** um âmbito, e o valor que o escolhe vem do **link**:
    `/ativar#<uuid-do-tenant>.<token>`. O uuid é argumento e não credencial, e
    quem concede é a política do `accounts_invitation`, que é uma política normal
    porque o link nomeia o tenant.

    `AllowAny` e não `IsAuthenticated`, e os dois casos são reais: uma conta nova
    chega aqui anónima, e uma conta que já existe tem de chegar aqui **com**
    sessão (`convite_exige_sessao`), porque a activação nunca define password
    numa conta que já tem uma.

    ## `csrf_protect` e `JSONParser`, pela razão do `SECURITY.md` §5

    Esta é exatamente a forma de endpoint que o §5 descreve: **anónimo e de
    escrita**. O `as_view()` do DRF embrulha a view em `csrf_exempt` e o
    `SessionAuthentication` só verifica o token quando **encontra** um utilizador
    na sessão — logo, sem estas duas linhas, um `POST /auth/ativar` anónimo
    nasceria sem protecção de CSRF nenhuma, como o login nasceu. O ataque aqui
    não é só *login CSRF*: é fazer o browser de quem tem o link queimar um token
    de uso único, ou aceitar um convite para um estabelecimento do atacante com a
    conta da vítima. Medido nas duas metades com `enforce_csrf_checks=True`.

    **Um endpoint dispensado de âmbito dispensa-se do âmbito e não do CSRF.**

    ## Códigos que esta view devolve

    * `400 convite_invalido` — expirado, usado, revogado, inexistente, uuid de
      tenant forjado e fragmento mal formado. **O mesmo código e o mesmo corpo**
      nos seis casos: distinguir dizia a quem experimenta um link se aquele
      estabelecimento existe e se aquele convite já foi usado;
    * `409 convite_exige_sessao` — o email convidado já tem conta com password;
    * `403 convite_de_outra_conta` — a sessão é de outra conta;
    * `400` por campo (`{"password": [...]}`) — password em falta ou fraca. É a
      segunda forma do 400 que o docstring deste módulo descreve, e sai assim
      porque é o que um formulário mostra ao lado do input. Uma password fraca
      **não** queima o convite.
    """

    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="auth_ativar",
        summary="Activar um convite",
        request=AtivacaoInSerializer,
        responses={
            status.HTTP_200_OK: SessaoOutSerializer,
            status.HTTP_400_BAD_REQUEST: ErroOutSerializer,
            status.HTTP_403_FORBIDDEN: ErroOutSerializer,
            status.HTTP_409_CONFLICT: ErroOutSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        corpo = AtivacaoInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        try:
            sessao = ativar_convite(
                _pedido_django(request),
                fragmento=corpo.validated_data["fragmento"],
                # `.get` porque o campo é `required=False` **sem** default: é o
                # que faz o `types.ts` dizer `password?: string`, que é a verdade
                # (ver o `AtivacaoInSerializer`). Quem decide se a password é
                # obrigatória é o service, depois de casar o convite.
                password=corpo.validated_data.get("password", ""),
            )
        except RecusaDeConvite as recusa:
            return _resposta_de_recusa(recusa, STATUS_DA_RECUSA_DE_CONVITE)
        except ValidationError as erro:
            return _resposta_de_validacao(erro)
        return _resposta(sessao)


@extend_schema_view(
    # A `list` vem do `ListModelMixin` e não tem docstring própria, pelo que o
    # drf-spectacular usaria a **da classe** como descrição da operação — 40
    # linhas sobre permissões e redes de isolamento dentro do `schema.yaml`
    # commitado, onde o `create` ao lado leva uma linha. A descrição vai
    # explícita para o contrato ficar legível; o porquê continua no docstring da
    # classe, que é onde quem lê o código o procura.
    list=extend_schema(
        operation_id="convites_listar",
        summary="Convites do estabelecimento ativo",
        description=(
            "Os convites do estabelecimento ativo, mais recentes primeiro, "
            "paginados. O `estado` é derivado e diz que acções fazem sentido: "
            "`reenviar` num `pendente` ou `expirado`, `revogar` em tudo o que "
            "não foi aceite. **Nunca** inclui o token — ele sai uma vez, na "
            "resposta do POST que criou o convite."
        ),
        responses={status.HTTP_200_OK: ConviteOutSerializer(many=True)},
    ),
)
class ConviteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """`/api/v1/convites` — criar, listar, reenviar e revogar. Só para o `owner`.

    Ao contrário da activação, estes são endpoints **normais, com âmbito** (ADR
    0010): quem os chama tem sessão e estabelecimento ativo, e o `tenant_id` vem
    do `request.tenant` que o `TenantMiddleware` confirmou. A dispensa de âmbito
    é uma decisão de isolamento e esta superfície não precisa dela.

    ## As duas redes, e porque é que o 404 é a resposta certa

    `get_queryset` filtra por `request.tenant.id` **e** a política filtra por
    `app.tenant_id`: são os dois controlos que o `SECURITY.md` §1 exige lado a
    lado. A consequência visível é que o `id` de um convite de outro
    estabelecimento dá **404 e não 403** — a linha não é legível, logo não há
    objeto sobre o qual negar, e 403 confirmaria que aquele convite existe.

    O `PertenceAoTenant` compara `obj.tenant_id == request.tenant.id` no caminho
    do objeto, que é o que o `SECURITY.md` §5 pede antes de qualquer outra regra.
    É a terceira rede, e chega a correr só se as duas primeiras falharem.

    ## Só `owner`, e o que isso tem a ver com a Q7

    `TemPapel.exige(Papel.OWNER)`: convidar é só do dono no v1. Não é
    conservadorismo — o conjunto de papéis é a Q7 do `SESSION-CONTEXT.md`, está
    marcada como "não inventes default sem falar com um utilizador real", e dar
    a um `manager` o poder de convidar era responder a ela aqui. Como `owner` é
    também o papel mais alto, a regra da ADR 0010 "nenhum convite concede papel
    acima do de quem convida" fica verdadeira sem precisar de uma ordem entre
    papéis — que é precisamente o que a Q7 vai decidir.

    ## Sem `retrieve`, sem `update`, sem `destroy`

    Um convite não se edita: o que muda nele é o token (`reenviar`) e o seu fim
    (`revogar`), e os dois são transições com regras, não um `PATCH`. E não se
    apaga: `revoked_at` guarda que existiu e quem o fez, e `DELETE` sobre um
    convite aceite apagaria o rasto da concessão de acesso. O `detail=True` das
    duas acções é o que faz o `get_object()` correr — e com ele as permissões de
    objeto.

    O `parser_classes` só com JSON não é aqui o controlo que é na activação:
    estes pedidos são autenticados, logo o `SessionAuthentication` do DRF já
    verifica o token de CSRF por si. Está cá para a superfície ser a mesma — o
    `MultiPartParser` do default existe para o upload de faturas, e um corpo
    multipart num endpoint de convites é um engano, não um caso de uso.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant, TemPapel.exige(Papel.OWNER)]
    parser_classes = [JSONParser]
    serializer_class = ConviteOutSerializer
    #: Nunca é usada — o `get_queryset` abaixo substitui-a — e existe por duas
    #: razões: dá ao drf-spectacular o modelo de onde tirar o tipo do `id` no
    #: path, e faz a omissão falhar fechado. Se alguém remover o `get_queryset`,
    #: o endpoint passa a devolver uma lista vazia em vez de os convites de
    #: todos os estabelecimentos.
    queryset = Invitation.objects.none()

    def get_queryset(self) -> QuerySet[Invitation]:
        """A segunda rede, ao lado da política (ver o docstring da classe)."""
        return convites_do_ambito(tenant_id=self.request.tenant.id)

    @extend_schema(
        operation_id="convites_criar",
        summary="Convidar alguém para o estabelecimento",
        request=ConviteInSerializer,
        responses={
            status.HTTP_201_CREATED: ConviteCriadoOutSerializer,
            status.HTTP_400_BAD_REQUEST: ErroOutSerializer,
        },
    )
    def create(self, request: Request) -> Response:
        """O token sai **aqui**, uma vez, e nunca mais (ADR 0010)."""
        corpo = ConviteInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        try:
            criado = criar_convite(
                tenant_id=request.tenant.id,
                email=corpo.validated_data["email"],
                role=corpo.validated_data["role"],
                display_name=corpo.validated_data["display_name"],
                convidado_por=request.user,
            )
        except ValidationError as erro:
            return _resposta_de_validacao(erro)
        return _resposta_de_convite(criado, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="convites_reenviar",
        summary="Reenviar um convite, com um token novo",
        request=None,
        responses={
            status.HTTP_200_OK: ConviteCriadoOutSerializer,
            status.HTTP_409_CONFLICT: ErroOutSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="reenviar")
    def reenviar(self, request: Request, pk: str | None = None) -> Response:
        """Roda o token: o link anterior deixa de casar com alguma coisa."""
        try:
            criado = reenviar_convite(convite=self.get_object())
        except RecusaDeConvite as recusa:
            return _resposta_de_recusa(recusa, STATUS_DA_RECUSA_DE_CONVITE)
        return _resposta_de_convite(criado, status.HTTP_200_OK)

    @extend_schema(
        operation_id="convites_revogar",
        summary="Revogar um convite",
        request=None,
        responses={
            status.HTTP_200_OK: ConviteOutSerializer,
            status.HTTP_409_CONFLICT: ErroOutSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="revogar")
    def revogar(self, request: Request, pk: str | None = None) -> Response:
        """Sem corpo na resposta além do convite: não há token novo a mostrar."""
        try:
            convite = revogar_convite(convite=self.get_object())
        except RecusaDeConvite as recusa:
            return _resposta_de_recusa(recusa, STATUS_DA_RECUSA_DE_CONVITE)
        return Response(ConviteOutSerializer(convite).data)


def _resposta_de_convite(criado: ConviteCriado, codigo: int) -> Response:
    """A resposta de `criar` e de `reenviar`: o convite e o segredo, uma vez."""
    return Response(ConviteCriadoOutSerializer(criado).data, status=codigo)
