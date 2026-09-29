"""Contexto de correlação de um pedido: `request_id`, `tenant_id`, `user_id`.

`RequestContextMiddleware` é o **primeiro** da lista (ARCHITECTURE.md §4): o
`request_id` existe antes de qualquer coisa poder falhar. Um middleware de
segurança que rejeita o pedido, um 404 antes da view, uma exceção na resolução
da URL — tudo isso é logado, e sem um id gerado no topo essas linhas ficavam sem
nada que as ligue ao resto. É o oposto da posição do `TenantMiddleware`, que é o
último porque precisa do `request.user` e porque é ele que abre a transação do
pedido (ADR 0005).

Os três campos chegam ao log por `ContextVar`, não por argumento: são lidos pelo
`RequestContextFilter` de `config/log.py`, que corre em cada registo e não tem
acesso ao `request`.

## O `request_id` é gerado, nunca aceite do cliente

Não se lê `X-Request-ID` do pedido. Um id vindo de fora é texto não confiável a
entrar no sistema de logs: bastava repetir o mesmo valor em mil pedidos para
tornar a correlação inútil, ou enviar algo com 4 KB. Vai na resposta, para o
cliente e o proxy poderem citá-lo num relatório de erro.

## O `user_id` vai em hash, e chega no fim do pedido

ARCHITECTURE.md §8 pede `user_id (hash)` e "nunca PII". O hash é um HMAC com a
`SECRET_KEY` (`salted_hmac`), não um digest do pk: o espaço de chaves primárias
é pequeno e um sha256 de um inteiro enumera-se em segundos, o que devolveria a
identidade que o hash devia esconder. Consequência aceite: rodar a
`SECRET_KEY` muda o pseudónimo, logo a correlação por utilizador é válida dentro
de uma janela de retenção, não para sempre.

O campo é preenchido **depois** de `get_response()`, na linha de acesso. Na
entrada não dá: este middleware corre antes do `AuthenticationMiddleware` e
`request.user` ainda não existe. Forçá-lo mais tarde na fase de pedido punha uma
leitura da sessão à frente de todos os pedidos anónimos — incluindo o
healthcheck. As linhas emitidas *durante* o pedido levam `request_id` e
`tenant_id`, que é o que as correlaciona; a linha de acesso leva os três.

## A linha de acesso não leva o path

Leva a `route` — o padrão de URL, `produtos/<uuid:pk>/` — e não `request.path`.
O path de um pedido pode conter identificadores e, em alguns desenhos, dados
pessoais em query string; a `route` responde à mesma pergunta ("que endpoint?")
sem transportar nada do utilizador.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.crypto import salted_hmac

from apps.shared.db import current_tenant

__all__ = ["REQUEST_ID_HEADER", "RequestContextMiddleware", "request_log_context"]

logger = logging.getLogger(__name__)

#: Onde o `request_id` sai na resposta. O cliente cita-o num relatório de erro.
REQUEST_ID_HEADER = "X-Request-ID"

#: Domínio do HMAC do `user_id`. Fixo: mudá-lo é o mesmo que rodar a chave.
_USER_ID_SALT = "apps.shared.middleware.user_id"

#: Quantos hexadecimais do HMAC vão para o log. 16 (64 bits) bastam para não
#: colidir dentro de uma janela de retenção e não ocupam uma linha inteira.
_USER_ID_LENGTH = 16

_request_id: ContextVar[str | None] = ContextVar("stockflow_request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("stockflow_user_id", default=None)


def request_log_context() -> dict[str, str | None]:
    """Os campos de correlação do pedido em curso, para o filtro de logs.

    As chaves são exatamente as de `config.log.CONTEXT_FIELDS` — há um teste que
    o fixa, senão um campo renomeado num dos lados passava a sair sempre a
    `None` sem ninguém dar por isso.

    Fora de um pedido (Celery, `manage.py`, shell) o `request_id` e o `user_id`
    são `None` e o `tenant_id` continua a vir do âmbito, que é o que faz uma
    tarefa aparecer no log com o seu tenant.
    """
    tenant = current_tenant()
    return {
        "request_id": _request_id.get(),
        "tenant_id": str(tenant) if tenant is not None else None,
        "user_id": _user_id.get(),
    }


class RequestContextMiddleware:
    """Gera o `request_id`, publica-o e escreve uma linha por pedido."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = uuid4().hex
        request.request_id = request_id
        token_request = _request_id.set(request_id)
        token_user = _user_id.set(None)
        comecou = time.monotonic()
        try:
            response = self.get_response(request)
            _user_id.set(_pseudonimo(request))
            response[REQUEST_ID_HEADER] = request_id
            self._registar(request, response, comecou)
            return response
        finally:
            # `reset` devolve o valor que a variável tinha quando o token foi
            # criado, mesmo que tenha havido um `set` no meio.
            _user_id.reset(token_user)
            _request_id.reset(token_request)

    def _registar(
        self,
        request: HttpRequest,
        response: HttpResponse,
        comecou: float,
    ) -> None:
        """Uma linha por pedido. Mensagem constante, dados em `extra`.

        É a convenção do `config/log.py`: interpolar valores na mensagem
        escreve-os em claro, fora da allowlist de campos.
        """
        logger.info(
            "pedido servido",
            extra={
                "event": "http_request",
                "method": request.method,
                "route": getattr(request.resolver_match, "route", None),
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - comecou) * 1000, 1),
            },
        )


def _pseudonimo(request: HttpRequest) -> str | None:
    """HMAC estável da identidade do utilizador, ou `None` se não houver.

    A guarda do cookie evita resolver `request.user` — que é lazy e custa uma
    leitura da sessão — em pedidos que não podem ter utilizador. A única
    autenticação do projeto é por sessão (SECURITY.md §2); se um dia houver
    outra, esta guarda tem de a conhecer.
    """
    if settings.SESSION_COOKIE_NAME not in request.COOKIES:
        return None
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    assinatura = salted_hmac(_USER_ID_SALT, str(user.pk), algorithm="sha256")
    return assinatura.hexdigest()[:_USER_ID_LENGTH]
