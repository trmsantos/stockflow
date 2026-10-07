"""Defesa do login: os três ganchos que o `django-axes` nos deixa (SECURITY.md §5).

1. `progressive_cooloff` — `AXES_COOLOFF_TIME`: quanto tempo dura o bloqueio.
2. `axes_username` — `AXES_USERNAME_CALLABLE`: **qual é a conta** a que uma
   tentativa pertence. Sem ele o contador por conta fragmenta-se pela caixa do
   email e o lockout deixa de trancar; a segunda metade deste docstring explica
   o que o axes faz de facto.
3. `lockout_response` — `AXES_LOCKOUT_CALLABLE`: **o corpo do 429**. Fecha o
   item de dívida que o `SECURITY.md` §5 nomeava e que a ADR 0010 fechou com um
   código estável; a terceira metade deste docstring explica o que o axes
   responderia sem ele.

## 1. `progressive_cooloff`

O `django-axes` aceita em `AXES_COOLOFF_TIME` um callable que recebe o request e
devolve um `timedelta`. É esse o gancho que a escada de SECURITY.md §5 usa.

Duas restrições mandam no desenho desta função, e nenhuma é óbvia a partir da
documentação do axes — vêm de ler o pacote instalado (django-axes 8.3.1). A
segunda limita o que esta função pode prometer: **lê o parágrafo
"Consequência" antes de assumires que o bloqueio cresce.**

**1. Não pode perguntar nada ao axes.** O valor devolvido aqui é usado *para
construir* a query das tentativas:

    axes/helpers.py get_cool_off        ← chama esta função
      ↑
    axes/attempts.py get_cool_off_threshold
      ↑
    axes/handlers/database.py get_user_attempts (:389)
      ↑
    axes/handlers/database.py get_failures (:111)

Ou seja, chamar `AxesProxyHandler.get_failures(request)` (ou `is_locked`,
`is_allowed`, `get_user_attempts`, `get_cool_off_threshold`) daqui fecha o ciclo
e dá `RecursionError` — com o `AxesStandaloneBackend` à cabeça dos
`AUTHENTICATION_BACKENDS`, isso significa **todos** os logins a 500, incluindo o
do admin. Por isso esta função lê o request e mais nada. Não faz uma única query
à base de dados: corre no caminho crítico do login, de dentro da construção de
uma query.

**2. O número de falhas nem sempre está disponível.** O axes guarda-o em
`request.axes_failures_since_start`, e o valor depende do caminho:

* *decisão* de lockout — `AxesProxyHandler.update_request`
  (`handlers/proxy.py:96`) põe o atributo a `None` no início de cada pedido, e
  o `user_login_failed` só lhe atribui o número real em
  `handlers/database.py:247`, **depois** de já ter chamado `get_failures` (:246)
  e `get_attempt_expiration` (:236). Nos dois casos esta função é chamada com o
  atributo a `None`;
* *resposta* de lockout — o `AxesMiddleware` chama `get_lockout_response`
  (`helpers.py:496`) já depois do :247, e aí o atributo tem o número real.

Consequência, dita por inteiro para não haver ilusões: **hoje o bloqueio
aplicado é sempre `COOLOFF_STEPS[0]`, 30 minutos, a contar da última falha.**
Os degraus acima do primeiro não chegam a ter efeito nenhum:

* na decisão de lockout, o número de falhas não está disponível (acima), logo o
  degrau é o primeiro;
* na resposta de lockout, o número está disponível e o degrau é calculado, mas
  o `get_lockout_response` só o põe no corpo da resposta quando o pedido traz
  `X-Requested-With: XMLHttpRequest` (JSON), ou quando há um
  `AXES_LOCKOUT_TEMPLATE`/`AXES_LOCKOUT_URL` configurado. Não temos nenhum dos
  dois, e o `fetch` do cliente React não manda esse header: a resposta é o
  `AXES_COOLOFF_MESSAGE`, uma string fixa que não fala de tempo. O valor é
  calculado e descartado.

Ou seja, a escada de SECURITY.md §5 está aqui como política e como estrutura
de dados, não como comportamento observável. Torná-la real exige contar as
falhas **fora** do axes — uma tabela ou um contador em Redis, com TTL próprio,
independente da janela de contagem —, porque a limitação é estrutural: um único
valor não pode ser ao mesmo tempo uma janela curta de contagem e um bloqueio
longo. Fica para quando houver requisito, e passa por ADR.

O que este desenho garante desde já: o login funciona, o lockout dispara às 5
falhas e dura 30 minutos deslizantes, e a janela de contagem tem um piso que
não se contorna a espaçar as tentativas. O `getattr` com default mantém a
função correta se um dia o axes passar a preencher o atributo mais cedo.

## 2. `axes_username`, e o que o axes faz de facto com a caixa do email

**Nada.** Lido no pacote instalado (django-axes 8.3.1), não presumido: não há um
`lower()`, um `casefold()` ou um `normalize` em ficheiro nenhum do pacote. O
`get_client_username` (`helpers.py:134`) devolve o valor cru de
`credentials[AXES_USERNAME_FORM_FIELD]` ou de `request.data`/`request.POST`, e
esse valor entra tal e qual nos dois lados do contador:

* na escrita — `AccessAttempt.objects.get_or_create(username=username, ...)`
  (`handlers/database.py:181`);
* na leitura — `AccessAttempt.objects.filter(**filter_kwargs)`
  (`handlers/database.py:369`), com `username=` exato.

Consequência, e é a que interessa: com a unicidade do email insensível à caixa,
`ana@x.pt` e `Ana@x.pt` são **uma** conta no `accounts_user` e **duas** chaves no
contador do axes. Cinco tentativas repartidas entre as duas grafias dão duas
linhas de três e de duas, o `max()` do `get_failures` devolve 3, e o limite de 5
nunca é atingido: o lockout deixa de existir para quem varie a caixa entre
tentativas — de graça, sem proxies e sem esperar. O eixo `(ip_address, username)`
fragmenta-se exatamente da mesma forma.

`AXES_USERNAME_CALLABLE` é o gancho que resolve isso, e resolve-o nos dois lados
de uma vez: é a **primeira** coisa que o `get_client_username` consulta, logo
todos os caminhos que perguntam "de quem é esta tentativa?" passam por aqui — a
decisão de lockout, o registo da falha, as chaves de cache e a resposta 429.

## 3. `lockout_response`, e o que o axes responderia sem ele

O `AxesMiddleware` não recusa o pedido: deixa a view responder e, se o axes
marcou o pedido (`request.axes_locked_out`), **substitui** a resposta pelo
`get_lockout_response`. Sem `AXES_LOCKOUT_CALLABLE`, esse helper responde o
`AXES_COOLOFF_MESSAGE` — uma string de texto, em `text/plain`, com o status 429.
Um corpo JSON só sairia dele com `X-Requested-With: XMLHttpRequest` no pedido
(que o `fetch` do cliente React não manda) ou com um `AXES_LOCKOUT_TEMPLATE`
configurado. Resultado: o cliente recebia um 429 que não sabia distinguir do 429
do throttle do DRF, e o `errors.ts` ficava sem `code` para ramificar.

Com este gancho o corpo é `{"code": "conta_bloqueada", "detail": ...}`, a mesma
forma do `TenantMiddleware`, e o status continua a vir do
`AXES_HTTP_RESPONSE_CODE` — a setting mantém-se a fonte de verdade em vez de
aparecer aqui um 429 literal.

**Armadilha a conhecer antes de mexer nesta função:** o `get_lockout_response`
chama-a com três argumentos e, se isso levantar `TypeError`, **volta a chamá-la
com dois** (compatibilidade com assinaturas antigas, `axes/helpers.py:476`). Um
`TypeError` levantado *dentro* do corpo é, para o axes, indistinguível de uma
assinatura errada: a função é chamada duas vezes e o erro que aparece é o
segundo. Daí o corpo não construir nada que possa levantar.

**O que o corpo não diz: quanto tempo falta.** A única duração disponível neste
caminho é a da escada (`progressive_cooloff`), e aqui ela está calculada com o
número real de falhas — mas o bloqueio **aplicado** é sempre o primeiro degrau,
porque na decisão de lockout o número de falhas ainda não existe (ver a parte 1).
Pôr o valor da escada no corpo era anunciar "4 horas" sobre um bloqueio de 30
minutos; escrever "30 minutos" à mão era uma segunda fonte de verdade para o
`COOLOFF_STEPS[0]`. Fica sem número, e é dívida que se paga com a escada.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from axes.helpers import get_failure_limit
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _

from apps.accounts.api import normalizar_email

#: Código estável do 429 do lockout (ADR 0010). Vive aqui e não no `accounts`
#: porque quem o devolve é o `AxesMiddleware` através de uma setting do axes, e
#: esta é a configuração do axes — mas é contrato público, como os códigos do
#: `TenantMiddleware`, e o frontend ramifica por ele.
CODIGO_CONTA_BLOQUEADA = "conta_bloqueada"

#: A frase que acompanha o código. Sem número: ver a parte 3 do docstring.
DETALHE_CONTA_BLOQUEADA = _(
    "Too many failed sign-in attempts. "
    "This account is temporarily locked; try again later."
)

#: Escada de espera, a partir do momento em que `AXES_FAILURE_LIMIT` é atingido.
#: A última entrada é o teto: a partir daí não cresce mais.
#:
#: **O primeiro degrau é também o piso da janela de contagem das falhas** e não
#: pode ser curto. O valor devolvido por esta função serve as duas coisas ao
#: mesmo tempo: o `get_cool_off_threshold` usa-o como `attempt_time__gte` ao
#: contar as tentativas (`axes/attempts.py:17` + `handlers/database.py:389`).
#: Com um primeiro degrau de 1 minuto, um atacante a tentar uma password a cada
#: 70 s nunca tranca — cada linha sai da janela antes de a quinta falha existir.
#: Baixar `COOLOFF_STEPS[0]` desliga o lockout sem tocar em mais nada
#: (SECURITY.md §5). Há um teste que fixa o piso.
COOLOFF_STEPS: tuple[timedelta, ...] = (
    timedelta(minutes=30),
    timedelta(hours=1),
    timedelta(hours=4),
    timedelta(hours=12),
    timedelta(hours=24),
)


def progressive_cooloff(request: HttpRequest | None = None) -> timedelta:
    """Devolve quanto tempo falta esperar, em função das falhas acumuladas.

    Sem request (comandos de gestão do axes, que só querem o teto de expiração
    das tentativas) devolve o passo máximo — a opção conservadora.

    Zero queries à BD e zero chamadas a APIs do axes que voltem a
    `get_cool_off`. Ver o docstring do módulo para o porquê de cada uma.
    """
    if request is None:
        return COOLOFF_STEPS[-1]

    # O atributo existe mas vale `None` no caminho da decisão de lockout, e não
    # existe em requests que nunca passaram pelo axes (testes, outro
    # middleware). Os dois casos caem no primeiro degrau.
    failures = getattr(request, "axes_failures_since_start", None) or 0

    # Pelo helper, não por `settings.AXES_FAILURE_LIMIT`: a setting pode ser um
    # callable ou um path para um callable (`axes/helpers.py:446`), e aí a
    # aritmética direta sobre a setting dava `TypeError`. O helper não volta a
    # `get_cool_off`, só resolve a setting. As credenciais não estão
    # disponíveis nesta chamada — o axes não as passa ao `get_cool_off` —, daí
    # o `None`: um `AXES_FAILURE_LIMIT` que dependa do utilizador tem de saber
    # lidar com isso.
    limit = get_failure_limit(request, None)

    excess = max(failures - limit, 0)
    return COOLOFF_STEPS[min(excess, len(COOLOFF_STEPS) - 1)]


def axes_username(
    request: HttpRequest | None,
    credentials: dict[str, Any] | None = None,
) -> str | None:
    """A conta a que esta tentativa de login pertence, na forma canónica.

    É o `AXES_USERNAME_CALLABLE`. Faz duas coisas: acha o valor da conta no
    pedido (`_valor_da_conta`, que segue a precedência do axes e conserta um
    caso em que ele desiste) e normaliza-o com o `normalizar_email` do
    `accounts` — a **mesma** função que decide se duas grafias são a mesma conta
    na base de dados. Duas definições de "a mesma conta" davam um contador que
    não fecha com a tabela que protege.

    Lê `AXES_USERNAME_FORM_FIELD` em vez de fixar `"email"`: a setting continua
    a ser o sítio onde se declara o campo que transporta a conta, e assim
    apagá-la volta a dar o defeito visível que `tests/test_lockout.py` fixa, em
    vez de um contador que parece funcionar.

    Zero queries e zero chamadas a APIs do axes, pela razão do
    `progressive_cooloff`: isto corre no caminho crítico do login, de dentro da
    construção da query das tentativas.

    Devolve `None` quando não há campo nenhum, que é exatamente o que o axes já
    devolvia: um pedido de login sem o campo da conta não identifica conta
    nenhuma e as suas tentativas agrupam-se todas sob a mesma chave. Um valor
    que **não seja texto** — `{"email": [...]}` num corpo JSON — cai no mesmo
    sítio, e aí é uma melhoria de propósito: hoje esse valor atravessa o axes
    até ao `filter(username=[...])` e rebenta a query do login.
    """
    valor = _valor_da_conta(request, credentials)
    if not isinstance(valor, str):
        return None
    return normalizar_email(valor)


#: A chave por que o `authenticate()` do Django transporta a conta. Não é a
#: nossa (`AXES_USERNAME_FORM_FIELD = "email"`) e é procurada logo depois dela —
#: ver o docstring de `_valor_da_conta` para o caso concreto que a exige.
CAMPO_DO_DJANGO = "username"


def _valor_da_conta(request: HttpRequest | None, credentials: dict[str, Any] | None) -> Any:
    """O valor cru da conta: credenciais primeiro, corpo do pedido depois.

    A precedência entre as duas **fontes** é a do `get_client_username`
    (`axes/helpers.py:134`) e não uma escolha nossa: as credenciais mandam
    quando trazem resposta, porque são o que o backend de autenticação recebeu;
    senão lê-se o corpo do pedido — `request.data` num pedido DRF,
    `request.POST` num pedido Django.

    ## Porque é que se procuram duas chaves, e não só a nossa

    O axes procura só `AXES_USERNAME_FORM_FIELD` e desiste. Isso tem um modo de
    falha silencioso que não é sobre caixa nenhuma e é pior do que ela: o
    `django.contrib.auth.authenticate()` emite o sinal `user_login_failed` com
    os **kwargs que o chamador lhe passou** (`django/contrib/auth/__init__.py`),
    e a forma canónica é `authenticate(request, username=..., password=...)` —
    é assim que o `AuthenticationForm` do admin o chama. Nesse caminho as
    credenciais são `{"username": ..., "password": "***"}`, o
    `credentials.get("email")` do axes devolve `None` e, porque o dicionário das
    credenciais não está vazio, ele **não** desce ao corpo do pedido: todas as
    falhas ficam registadas com `username = NULL`.

    A consequência não é um contador a menos, é um contador global: o eixo
    `"username"` do `AXES_LOCKOUT_PARAMETERS` passa a casar
    `filter(username=None)`, que são as tentativas de *todas* as contas juntas —
    cinco falhas de cinco pessoas diferentes trancavam o login a todas. Procurar
    também o `username` resolve-o no único sítio onde a pergunta "de quem é esta
    tentativa?" é respondida.

    Um valor que não seja `None` é resposta, mesmo vazio: só a **ausência** da
    chave faz descer à fonte seguinte.
    """
    campos = tuple(dict.fromkeys((settings.AXES_USERNAME_FORM_FIELD, CAMPO_DO_DJANGO)))
    for fonte in (credentials, _corpo(request)):
        for campo in campos:
            valor = fonte.get(campo) if hasattr(fonte, "get") else None
            if valor is not None:
                return valor
    return None


def _corpo(request: HttpRequest | None) -> Any:
    """O corpo do pedido: `request.data` num pedido DRF, `request.POST` no do
    Django. Pode não ter `get` — um corpo JSON pode ser uma lista."""
    if request is None:
        return None
    dados = getattr(request, "data", None)
    return getattr(request, "POST", None) if dados is None else dados


def lockout_response(
    request: HttpRequest | None = None,
    original_response: HttpResponse | None = None,
    credentials: dict[str, Any] | None = None,
) -> JsonResponse:
    """O 429 do lockout, com corpo JSON e `code` estável (ADR 0010).

    É o `AXES_LOCKOUT_CALLABLE`. A assinatura tem de aceitar os **três**
    argumentos positionais com que o `get_lockout_response` chama primeiro: com
    dois, a primeira chamada levanta `TypeError`, o axes engole-o e repete com
    dois — funciona, mas por acidente, e o `TypeError` do meio esconde qualquer
    outro.

    Não lê o request e não faz query nenhuma. Em particular **não** põe o nome
    da conta no corpo (o `get_lockout_response` do axes põe-no no seu contexto):
    quem recebe esta resposta acabou de escrever o email, logo não ganha
    informação, e um email no corpo de uma resposta a um pedido não autenticado
    é um oráculo gratuito para quem está a varrer contas.

    O status vem do `AXES_HTTP_RESPONSE_CODE` para a setting continuar a ser a
    fonte de verdade: com o callable configurado, o ramo do axes que a lê deixa
    de correr, e um 429 literal aqui fazia a setting passar a não ter efeito
    nenhum sem deixar rasto.
    """
    return JsonResponse(
        {"code": CODIGO_CONTA_BLOQUEADA, "detail": DETALHE_CONTA_BLOQUEADA},
        status=settings.AXES_HTTP_RESPONSE_CODE,
    )
