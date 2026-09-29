"""`TenantTask`: o âmbito do tenant por construção, no Celery.

O Celery não tem middleware. Se o âmbito da RLS fosse um decorador ou uma linha
no corpo de cada tarefa, dependia de disciplina — e a tarefa esquecida corre com
`app.tenant_id` a NULL, onde as políticas devolvem zero linhas e o bug aparece
como "não encontrei nada" em vez de como erro.

Por isso `TenantTask` é o `task_cls` do **app** (ligado em `config/celery.py`):
toda a tarefa criada por `@app.task` — e por `@shared_task`, que usa o app atual
— herda-o, logo não existe outra forma de declarar uma tarefa neste projeto
(ADR 0005, ARCHITECTURE.md §4.8).

## O que isso impõe

* `tenant_id` é argumento **obrigatório** da tarefa, e a recusa é no
  `apply_async`: quem enfileira fica com o erro, no sítio onde o erro foi
  cometido. Recusar só na execução punia o worker por um bug de quem publicou, e
  o rasto ficava num log em vez de numa exceção.
* O corpo corre dentro de `tenant_scope(tenant_id)` — uma transação por tarefa,
  com o `set_config` como primeira instrução.
* Passa-se o `tenant_id`, não um objeto `Tenant`: os argumentos vão em JSON
  pelo broker e um modelo serializado é um modelo velho quando a tarefa corre.

## A dispensa

`tenant_scope_exempt = True` é um atributo de classe, visível na declaração da
tarefa e greppável em todo o repositório — que é precisamente o que se quer de
uma exceção a uma regra de isolamento. Hoje só a devem ter duas coisas
(ADR 0005):

    @app.task(base=TenantTask)          # ou uma subclasse
    class ...  # o cron que itera tenants e enfileira uma tarefa por cada
               # e o consumidor da outbox, que lê a linha sob system_scope()

Uma tarefa dispensada **não** tem âmbito nenhum: se toca em dados de um tenant,
abre `tenant_scope` ela mesma.

## Retries

O `tenant_id` vai nos argumentos, logo um `self.retry()` reenfileira a tarefa
com ele e o âmbito reabre-se na tentativa seguinte. Não há estado de âmbito a
sobreviver entre tentativas, o que é o comportamento certo: cada tentativa é uma
transação nova.
"""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID

from celery import Task

from apps.shared.db import tenant_scope

__all__ = ["TenantIdRequired", "TenantTask"]

#: Nome do argumento que transporta o tenant. Um só nome, em todas as tarefas.
TENANT_ID_ARG = "tenant_id"


class TenantIdRequired(TypeError):
    """Tarefa enfileirada sem `tenant_id` e sem dispensa explícita."""


class TenantTask(Task):
    """Base de todas as tarefas: `tenant_id` obrigatório, corpo com âmbito."""

    #: Dispensa do âmbito de tenant. Ver o docstring do módulo antes de a pôr a
    #: `True` — e ver a ADR 0005, que enumera quem a pode ter.
    tenant_scope_exempt = False

    def apply_async(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        **options: Any,
    ) -> Any:
        """Recusa enfileirar sem `tenant_id`."""
        if not self.tenant_scope_exempt:
            self._tenant_id(args, kwargs)
        return super().apply_async(args=args, kwargs=kwargs, **options)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Corre o corpo da tarefa dentro do âmbito do tenant.

        O Celery usa o `__call__` quando a tarefa o redefine
        (`celery.app.trace.build_tracer`), pelo que este é o ponto de entrada
        real do worker — e também do modo eager dos testes.
        """
        if self.tenant_scope_exempt:
            return super().__call__(*args, **kwargs)
        with tenant_scope(self._tenant_id(args, kwargs)):
            return super().__call__(*args, **kwargs)

    def _tenant_id(self, args: tuple[Any, ...] | None, kwargs: dict[str, Any] | None) -> UUID:
        """Extrai e valida o `tenant_id` dos argumentos da chamada."""
        if kwargs and TENANT_ID_ARG in kwargs:
            valor = kwargs[TENANT_ID_ARG]
        else:
            valor = self._posicional(args)
        if valor is None:
            raise TenantIdRequired(
                f"{self.name}: tenant_id é None. É o predicado da política "
                "RLS: sem ele a tarefa corria a ver zero linhas de todas as "
                "tabelas, em silêncio (ADR 0005)."
            )
        if isinstance(valor, UUID):
            return valor
        try:
            return UUID(valor)
        except (AttributeError, TypeError, ValueError) as exc:
            raise TenantIdRequired(
                f"{self.name}: tenant_id={valor!r} não é um UUID."
            ) from exc

    def _posicional(self, args: tuple[Any, ...] | None) -> Any:
        """O `tenant_id` passado por posição, se a assinatura o declarar.

        Precisa da assinatura do `run` para saber a que posição corresponde o
        nome. Uma tarefa com assinatura só de `*args` não pode ser resolvida
        por posição — e é bom que não possa: passa a ter de nomear o argumento.
        """
        try:
            ligados = inspect.signature(self.run).bind_partial(*(args or ()))
        except TypeError as exc:
            raise TenantIdRequired(
                f"{self.name}: os argumentos não batem com a assinatura da "
                f"tarefa, logo não é possível encontrar o {TENANT_ID_ARG}."
            ) from exc
        if TENANT_ID_ARG not in ligados.arguments:
            raise TenantIdRequired(
                f"{self.name}: falta o argumento obrigatório {TENANT_ID_ARG}. "
                "Toda a tarefa corre dentro do âmbito de um tenant; se esta é "
                "uma das que não pode (cron que itera tenants, consumidor da "
                "outbox), declara `tenant_scope_exempt = True` na classe da "
                "tarefa (ADR 0005)."
            )
        return ligados.arguments[TENANT_ID_ARG]
