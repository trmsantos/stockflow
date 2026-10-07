"""Dois endpoints de saúde, que respondem a duas perguntas diferentes.

`/healthz` — **liveness**. "Este processo está a servir HTTP?" É o que o
`HEALTHCHECK` do Docker precisa de saber, e o que decide se o orquestrador
**reinicia** o contentor. Não toca na base de dados, de propósito: se o
Postgres cair, o healthcheck de todos os contentores falha ao mesmo tempo, o
orquestrador reinicia processos que estão bons e o incidente passa de "a base
de dados está em baixo" para "a base de dados está em baixo e a aplicação está
num ciclo de arranques". Reiniciar um processo saudável nunca reparou uma
dependência externa.

`/readyz` — **readiness**. "Este processo consegue servir tráfego real?" Aqui a
base de dados entra, porque a resposta certa quando ela não responde é **tirar
a instância da rotação** do balanceador, não matá-la: ela recupera sozinha
quando a dependência voltar. É o endpoint para o `readinessProbe` de um
orquestrador e **não** para o `HEALTHCHECK` do Docker, que só sabe reiniciar.

Em uma linha: o `/healthz` responde por *este processo*, o `/readyz` responde
pelo processo **e** pelas suas dependências; o primeiro decide reinícios, o
segundo decide encaminhamento de tráfego.

## Porque é que estas views são Django puro e não DRF

Três propriedades que um `APIView` obrigaria a desligar uma a uma:

1. **Fora do throttle.** O `DEFAULT_THROTTLE_CLASSES` do `base.py` aplica-se a
   todas as views do DRF, e o `AnonRateThrottle` conta por IP: um contentor que
   se verifica a si mesmo a cada 10 s partilha o contador com o resto do
   tráfego anónimo que venha do mesmo endereço. Um 429 no healthcheck é um
   contentor reiniciado por excesso de tráfego — exatamente ao contrário do que
   se quer. Numa view do Django, o throttle do DRF não existe;
2. **`AllowAny`.** O `DEFAULT_PERMISSION_CLASSES` é `IsAuthenticated`, e um
   healthcheck corre de dentro do contentor, sem sessão e sem cookies. Numa
   view do Django não há `permission_classes` para esquecer;
3. **Zero queries.** O `AnonRateThrottle` e o `SessionAuthentication` resolvem
   o `request.user`, e o cache do throttle é o Redis. Nada disso corre aqui.

Não entram no `schema.yml`: não são endpoints da API (vivem fora de
`/api/v1/`, que é o `SCHEMA_PATH_PREFIX` do drf-spectacular) e o cliente
gerado pelo `pnpm gen:api` não tem nada que fazer com eles.

## Dispensa de âmbito: nem tenant, nem transação

As duas levam `@tenant_scope_exempt` (ADR 0007). Não é só porque não há tenant
na sessão de um healthcheck — é porque o `tenant_scope` **abre uma transação**
(ADR 0005). Uma verificação a cada 10 s, por contentor, a abrir e fechar uma
transação por cada, é carga inútil no pool e uma linha a mais no
`pg_stat_activity` a competir com pedidos reais. Sem dispensa, a resposta seria
403 `sem_sessao`, que é o default correto — a dispensa é declarada, nunca
inferida.

## O que a resposta não diz

`ok` em `text/plain`, e mais nada: sem versão, sem nome de host, sem lista de
dependências, sem tempo de arranque. Um healthcheck é um endpoint que responde
a quem não está autenticado; tudo o que ele diz é reconhecimento gratuito para
quem procura alvos. O `Cache-Control: no-store` é pela mesma ordem de ideias ao
contrário: uma resposta de saúde guardada em cache é uma resposta que mente.

## O `Host` do pedido, que não se resolve aqui

O pedido chega com o `Host` do contentor (`127.0.0.1:8000`) e o `ALLOWED_HOSTS`
de produção tem o domínio real, logo o Django responde **400 DisallowedHost**
antes de qualquer view — o `CommonMiddleware` chama `request.get_host()` em
todos os pedidos. Isto não se resolve no lado do Django sem pagar mais do que
vale: um `*` no `ALLOWED_HOSTS` é proibido (CLAUDE.md), acrescentar `localhost`
alarga a lista de hosts por que a aplicação responde para servir uma
verificação interna, e um middleware que reconheça o path antes da validação do
`Host` é uma lista de paths nas settings — a forma que a ADR 0007 rejeita — com
o agravante de curto-circuitar o `SecurityMiddleware` e a CSP.

Quem manda o pedido é que escolhe o `Host`, e quem manda o pedido é o
`HEALTHCHECK` do Dockerfile. A via é essa, e o `ALLOWED_HOSTS` fica
exatamente com os domínios de produção. O que este lado garante é que nada
nestas duas views depende do `Host`: não constroem URLs absolutas, não
redirecionam e não variam por host. O modo de falha está fixado em
`tests/test_health.py`, para que ninguém o "corrija" com um `*`.
"""

from __future__ import annotations

import logging

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_safe

from apps.accounts.api import tenant_scope_exempt

__all__ = ["CORPO_INDISPONIVEL", "CORPO_OK", "healthz", "readyz"]

logger = logging.getLogger(__name__)

#: Corpos das respostas. Constantes para não haver duas grafias e para o teste
#: poder afirmar igualdade exata — é assim que "não revela nada" se mede.
CORPO_OK = b"ok\n"
CORPO_INDISPONIVEL = b"unavailable\n"


@tenant_scope_exempt
@require_safe
def healthz(request: HttpRequest) -> HttpResponse:
    """200 se o processo está a servir HTTP. Não toca na base de dados.

    O `@require_safe` recusa tudo o que não seja GET ou HEAD com 405: um
    endpoint sem autenticação não tem razão para aceitar um corpo de pedido.
    Na prática um POST leva 403 antes disto — o `CsrfViewMiddleware` corre
    antes da resolução da view (medido com o gunicorn e o `settings.prod`) —, e
    o 405 é a segunda recusa, a que sobra se alguém puser um `@csrf_exempt`
    aqui. As duas estão fixadas em `tests/test_health.py`.

    A ordem dos decoradores importa: o `@tenant_scope_exempt` é o de fora, logo
    a marca fica no objeto que o resolver devolve ao `TenantMiddleware` — e um
    POST leva 405 sem abrir transação nenhuma.
    """
    return _resposta(CORPO_OK, 200)


@tenant_scope_exempt
@require_safe
def readyz(request: HttpRequest) -> HttpResponse:
    """200 se o processo consegue falar com a base de dados, 503 se não.

    Não é para o `HEALTHCHECK` do Docker (ver o docstring do módulo): 503 aqui
    quer dizer "não me mandes tráfego", e quem responde a isso é um
    balanceador, não um `docker restart`.

    O `SELECT 1` corre em autocommit — esta view é dispensada de âmbito, logo
    não há transação de pedido — e não menciona tabela nenhuma, pelo que não
    depende de RLS nem de `app.tenant_id`.

    Nota operacional que não é deste ficheiro: o proxy não deve encaminhar
    `/readyz` para a Internet. Um 503 diz a quem pergunta que a base de dados
    está em baixo, e essa informação não é para o público.
    """
    if not _a_base_de_dados_responde():
        return _resposta(CORPO_INDISPONIVEL, 503)
    return _resposta(CORPO_OK, 200)


def _a_base_de_dados_responde() -> bool:
    """Uma ida e volta real ao Postgres, e nunca uma exceção para fora.

    `SELECT 1` e não `ensure_connection()`: com `CONN_MAX_AGE = 60` a ligação é
    persistente e o `ensure_connection` de uma ligação já aberta não fala com o
    servidor nenhum — devolvia 200 sobre uma ligação morta. O `fetchone` é o
    que prova que a resposta voltou.

    A exceção é logada e o corpo da resposta não a leva: a mensagem de um erro
    de ligação transporta host, porta e nome da base de dados.
    """
    try:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except DatabaseError:
        logger.warning(
            "readiness: a base de dados não respondeu",
            extra={"event": "readiness_db_indisponivel", "outcome": "indisponivel"},
            exc_info=True,
        )
        return False


def _resposta(corpo: bytes, status: int) -> HttpResponse:
    """Corpo mínimo, `text/plain`, e sem cache em sítio nenhum."""
    resposta = HttpResponse(corpo, status=status, content_type="text/plain; charset=utf-8")
    resposta["Cache-Control"] = "no-store"
    return resposta
