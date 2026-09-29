"""Bloqueio progressivo de login (SECURITY.md §5).

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
"""

from __future__ import annotations

from datetime import timedelta

from axes.helpers import get_failure_limit
from django.http import HttpRequest

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
