"""`TenantMiddleware`: a sessão escolhe o âmbito, a política concede-o.

É o **último** middleware da lista (ADR 0005, ARCHITECTURE.md §4): precisa do
`request.user`, e é ele que abre a transação do pedido — ser o último deixa a
escrita da sessão (`SESSION_SAVE_EVERY_REQUEST`) e o `AccessAttempt` do axes
fora dela, em autocommit, que é onde têm de estar.

## A inversão que resolve a circularidade

Resolver o tenant é ler o `Membership`; o `Membership` tem política; uma
leitura sem âmbito devolve zero linhas; e o âmbito não pode abrir antes de se
saber o tenant. Não se resolve com ordem de middleware nem com disciplina,
porque é circular. Este middleware parte o ciclo assim:

1. **Não consulta a base de dados antes do âmbito** — não poderia. Lê o
   `request.session["tenant_id"]` e o `request.user`: `django_session` e
   `accounts_user` não têm política, logo isto funciona sem âmbito. O
   `request.user` é resolvido **aqui**, de propósito, para a query da sessão e
   a do utilizador ficarem fora do âmbito e a promessa do ponto 3 ser literal.
2. Abre `tenant_scope(esse id)` a envolver o `get_response()` inteiro.
3. A **primeira e única** instrução dentro do âmbito antes de entregar o pedido
   é uma query: o `Membership` de (utilizador autenticado, âmbito), por um
   índice único. Zero linhas → 403 com `transaction.set_rollback(True)`.

O valor que vem da sessão não é uma credencial, é um **argumento**: forjá-lo
escolhe um âmbito onde a query — que leva `user_id = <o meu>` no `WHERE` — não
devolve nada, e nenhuma linha do tenant alheio é lida no caminho.

## Por pedido, não por sessão

A verificação repete-se em cada pedido e não há cache: revogar um `Membership`
corta o acesso no pedido **seguinte**, sem ninguém tocar em sessões. O custo é
uma query por pedido, por índice único, e não há sinal nenhum da secção 7 do
ARCHITECTURE.md que justifique cache.

## Os códigos da resposta, e porque é que o status não basta

O corpo do 403 leva um `code` estável, porque o `SessionAuthentication` do DRF
também responde 403 a anónimos e o frontend tem de ramificar pelo **código** e
não pelo status:

* `sem_sessao` — não há utilizador autenticado, ou a sessão não nomeia tenant
  nenhum. O cliente manda o utilizador para o login ou para o seletor de
  estabelecimento;
* `tenant_desconhecido` — a sessão nomeia um tenant onde a política não devolve
  pertença ativa (revogada, inexistente, ou um uuid forjado). O cliente limpa o
  tenant ativo e volta ao seletor;
* `tenant_divergente` — 409, e só o pode causar o header `X-Tenant-ID`.

## O header `X-Tenant-ID` nunca escolhe âmbito

Um cookie de sessão por browser significa que a contabilista não tem o tenant A
e o B abertos em dois separadores: trocar num muda o outro no fetch seguinte. A
correção barata é o cliente mandar em cada pedido o tenant que acha ativo, e o
middleware responder 409 se divergir da sessão. O header **só** pode causar um
409 — nunca seleciona nada — e é essa assimetria que o torna inofensivo.

## A dispensa é declarada na view

`tenant_scope_exempt`, de `apps/accounts/api.py`, e o default é ter âmbito: uma
view que não declare nada é servida com âmbito, uma que não o consiga obter leva
403 **antes** de o `get_response()` correr. O path é resolvido uma vez, só para
ler a declaração. O esquecimento falha fechado.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import Resolver404, ResolverMatch, resolve

from apps.accounts.api import (
    ATRIBUTO_MEMBERSHIP,
    ATRIBUTO_TENANT,
    MembershipInfo,
    TenantContext,
    dispensa_declarada,
)
from apps.accounts.selectors import membership_no_ambito
from apps.shared.db import tenant_scope

__all__ = [
    "CODIGO_DIVERGENTE",
    "CODIGO_DESCONHECIDO",
    "CODIGO_SEM_SESSAO",
    "SESSION_TENANT_KEY",
    "TENANT_HEADER",
    "TenantMiddleware",
]

logger = logging.getLogger(__name__)

#: A chave da sessão onde o tenant ativo é guardado. O login e a troca de tenant
#: escrevem-na; ninguém mais. Constante para os três sítios não divergirem.
SESSION_TENANT_KEY = "tenant_id"

#: O header com que o cliente declara o tenant que **acha** que está ativo.
TENANT_HEADER = "X-Tenant-ID"

CODIGO_SEM_SESSAO = "sem_sessao"
CODIGO_DESCONHECIDO = "tenant_desconhecido"
CODIGO_DIVERGENTE = "tenant_divergente"

_DETALHES = {
    CODIGO_SEM_SESSAO: "Não há estabelecimento ativo nesta sessão.",
    CODIGO_DESCONHECIDO: "Não tem acesso ativo a este estabelecimento.",
    CODIGO_DIVERGENTE: (
        "O estabelecimento deste pedido não é o da sessão. "
        "Recarregue antes de continuar."
    ),
}


class TenantMiddleware:
    """Abre a transação do pedido com `app.tenant_id` definido, ou nega."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # O path é resolvido uma vez, e só para ler a declaração da view. A
        # `route` que vem daqui é também o que a linha de log da recusa leva:
        # o `request.resolver_match` do Django só existe depois de toda a
        # cadeia de middleware, logo não serve neste ponto.
        match = self._resolver(request)
        if match is None or dispensa_declarada(match.func):
            return self.get_response(request)
        rota = match.route

        tenant_id = self._tenant_da_sessao(request)
        if tenant_id is None:
            return self._negar(rota, CODIGO_SEM_SESSAO, 403)

        # Antes do âmbito, e sem tocar em tabela com política: um header que
        # divirja não escolhe nada, só recusa.
        if self._header_divergente(request, tenant_id):
            return self._negar(rota, CODIGO_DIVERGENTE, 409)

        # Resolver o utilizador **aqui** é o que mantém a promessa de que a
        # query ao Membership é a primeira instrução dentro do âmbito: o
        # `request.user` é lazy e custa uma leitura da sessão e uma do
        # `accounts_user`, nenhuma delas com política.
        user = request.user
        if not user.is_authenticated:
            return self._negar(rota, CODIGO_SEM_SESSAO, 403)

        with tenant_scope(tenant_id):
            membership = membership_no_ambito(user_id=user.pk, tenant_id=tenant_id)
            if membership is None:
                # A política não devolveu linha nenhuma: nada do tenant alheio
                # foi lido. O rollback é por higiene — não há escritas neste
                # caminho, mas fechar a transação com `set_rollback` é o que
                # impede que uma futura escrita antes daqui commite por engano.
                transaction.set_rollback(True)
                return self._negar(rota, CODIGO_DESCONHECIDO, 403)

            setattr(
                request,
                ATRIBUTO_TENANT,
                TenantContext(
                    id=membership.tenant_id,
                    name=membership.tenant.name,
                    role=membership.role,
                ),
            )
            setattr(
                request,
                ATRIBUTO_MEMBERSHIP,
                MembershipInfo(
                    user_id=membership.user_id,
                    tenant_id=membership.tenant_id,
                    role=membership.role,
                    display_name=membership.display_name,
                ),
            )

            response = self.get_response(request)

            if response.status_code >= 500:
                # O DRF trata a exceção dentro da view: sem isto, um 500
                # commitava o que a view já tinha escrito (ADR 0005).
                transaction.set_rollback(True)
            return response

    # ------------------------------------------------------------------
    def _resolver(self, request: HttpRequest) -> ResolverMatch | None:
        """A view que vai servir este pedido, ou `None` se não houver nenhuma.

        `None` é um 404 antes da view: não há nada que possa ler dados de um
        tenant, e abrir uma transação para o servir seria uma transação por
        cada pedido a um endpoint que não existe.
        """
        try:
            return resolve(request.path_info, urlconf=getattr(request, "urlconf", None))
        except Resolver404:
            return None

    def _tenant_da_sessao(self, request: HttpRequest) -> UUID | None:
        """O tenant da sessão, já validado como UUID.

        Um valor que não seja um UUID nunca chega ao `set_config` — o
        `tenant_scope` também o recusaria, mas com uma exceção, e uma sessão
        adulterada tem de dar 403 e não 500.
        """
        valor = request.session.get(SESSION_TENANT_KEY)
        if not valor:
            return None
        return _como_uuid(valor)

    def _header_divergente(self, request: HttpRequest, tenant_id: UUID) -> bool:
        """O cliente declarou um tenant diferente do da sessão?

        Um header ilegível conta como divergente: não é um âmbito que se possa
        confirmar, e a resposta certa continua a ser "recarregue".
        """
        declarado = request.headers.get(TENANT_HEADER)
        if not declarado:
            return False
        return _como_uuid(declarado) != tenant_id

    def _negar(self, rota: str, codigo: str, status: int) -> JsonResponse:
        """Resposta com `code` estável, e uma linha de log sem PII.

        Leva a `route` — o padrão de URL — e não o path: é a convenção do
        `config/log.py`, porque o path de um pedido pode transportar
        identificadores e a `route` responde à mesma pergunta sem os levar.
        """
        logger.warning(
            "pedido recusado por âmbito de tenant",
            extra={
                "event": "tenant_scope_denied",
                "outcome": codigo,
                "status_code": status,
                "route": rota,
            },
        )
        return JsonResponse({"code": codigo, "detail": _DETALHES[codigo]}, status=status)


def _como_uuid(valor: object) -> UUID | None:
    if isinstance(valor, UUID):
        return valor
    try:
        return UUID(str(valor))
    except (AttributeError, TypeError, ValueError):
        return None
