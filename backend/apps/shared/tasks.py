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
uma exceção a uma regra de isolamento. Para não andar copiada, tem uma base
própria, a `SystemTask`, e declara-se assim:

    @shared_task(name="…", base=SystemTask)
    def ...

A ADR 0005 nomeia **duas** coisas que a podem ter, e desde 2026-10-15 existem as
duas:

* **o consumidor da outbox** (`shared.consumir_outbox`, aqui em baixo), que lê a
  linha sob `system_scope()` e reentra em `tenant_scope(row.tenant_id)` antes de
  tocar em mais nada;
* **o cron que itera tenants** (`agents.purgar_conversas_expiradas`, ADR 0027),
  que **não lê o `accounts_tenant`** — e não por esquecimento. A política dessa
  tabela compara `id` contra `app.tenant_id` sem o disjunto `app.scope`: dentro de
  `system_scope()` essa leitura devolve **zero linhas sem erro**, que é o defeito
  silencioso que a ADR 0007 existe para evitar. Dar-lhe o disjunto de sistema
  alargava o alcance do âmbito de sistema, que continua a ser uma tabela só, e o
  dono recusou-o. O cron descobre os tenants pelo `accounts_user.tenant_ids` (a
  tabela sem política, o único bit legível fora de âmbito — ADR 0007), fecha o
  bloco e enfileira uma `TenantTask` por tenant.

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

from celery import Task, shared_task

from apps.shared.db import tenant_scope

__all__ = ["SystemTask", "TenantIdRequired", "TenantTask", "consumir_outbox"]

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


class SystemTask(TenantTask):
    """Tarefa **dispensada** do âmbito do tenant. Ver "A dispensa", no topo.

    Uma classe e não um `tenant_scope_exempt=True` solto em cada decorador: o
    Celery aceita opções arbitrárias no decorador e põe-nas no dicionário da
    classe que cria, logo as duas formas funcionam — mas uma delas é um atributo
    com nome, tipado e greppável, e a outra é um `kwargs` que ninguém verifica.
    Uma dispensa a uma regra de isolamento tem de ser do primeiro tipo.

    Quem a herda **não tem âmbito nenhum**: abre `tenant_scope` ou
    `system_scope` ela mesma, e sem isso lê zero linhas de tudo, em silêncio.
    """

    tenant_scope_exempt = True


@shared_task(name="shared.consumir_outbox", base=SystemTask)
def consumir_outbox() -> dict[str, int]:
    """Uma passagem pela outbox. Agendada pelo `beat` a cada 5 segundos.

    Sem argumentos — nem `tenant_id`, que é o ponto da `SystemTask`: esta é a
    tarefa que atravessa tenants para reclamar linhas de todos, e o âmbito de
    cada linha abre-se lá dentro, a partir da coluna `tenant_id` dela.

    O corpo inteiro vive em `apps/shared/consumidor.py`, que é onde está escrito
    o porquê de cada decisão: a ordem dos dois âmbitos, o `processed_at` a
    commitar com os handlers, o teto de tentativas e a latência de 0–5 s que a
    passagem periódica custa.

    Idempotente por construção, e tem de ser: com `task_acks_late` uma passagem
    interrompida é reentregue, e duas passagens em paralelo não tratam a mesma
    linha (a reclamação é um `UPDATE` condicional no `attempts`).

    Import no corpo e não no topo do ficheiro: este módulo é o `task_cls` do app
    Celery (`config/celery.py`) e é por isso o primeiro a ser importado quando a
    primeira tarefa do processo é criada. O `consumidor.py` puxa o `models.py` do
    `shared`, e um import de models no topo deste ficheiro era um
    `AppRegistryNotReady` à espera de um caminho de arranque que o alcançasse. É
    o mesmo padrão do `semear_demonstracao` no `accounts/api.py`, e sem supressão
    de lint nenhuma.
    """
    from apps.shared.consumidor import consumir_outbox as passagem

    return passagem()
