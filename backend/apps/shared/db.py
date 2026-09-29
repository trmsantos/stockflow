"""Âmbito transacional da RLS multi-tenant (ADR 0005).

Este módulo é a fronteira de isolamento do StockFlow. Expõe quatro nomes e mais
nada — `tenant_scope`, `system_scope`, `current_tenant` e `TenantScopeConflict`:
o resto do repositório não conhece o nome do GUC nem o SQL que o escreve.

## Como funciona

`tenant_scope(tenant_id)` abre `transaction.atomic()` e corre, como primeira
instrução dessa transação, `SELECT set_config('app.tenant_id', %s, true)`:

* **parametrizado**, nunca interpolado. `SET` não aceita parâmetro e formatar o
  UUID numa string de SQL é injeção num valor que vem da sessão (CLAUDE.md,
  SECURITY.md §3). `set_config` é uma função: aceita os dois argumentos como
  parâmetros, incluindo o nome do GUC;
* o terceiro argumento `true` é o que lhe dá **âmbito de transação**. É o ponto
  inteiro da ADR 0005: um GUC de sessão sobrevive à resposta e, com
  `CONN_MAX_AGE = 60`, o pedido seguinte servido pela mesma ligação herda o
  tenant do anterior.

O tenant ativo é publicado num `ContextVar`, que `current_tenant()` lê. É a
origem do campo `tenant_id` dos logs (`config/log.py`) e o que permite detetar
conflitos sem ir à base de dados.

## Reentrância, e por que razão trocar de tenant levanta

Um `set_config(..., true)` dentro de um savepoint **vive até ao fim da
transação de topo**: ao sair do bloco interior o valor não se restaura. Medido
contra o Postgres 16.15 do compose:

    BEGIN;
      set_config('app.tenant_id', 'aaaa', true);
      SAVEPOINT s1;
        set_config('app.tenant_id', 'bbbb', true);
      RELEASE SAVEPOINT s1;
      current_setting('app.tenant_id') -> 'bbbb'   <-- contaminado

Logo `tenant_scope` é reentrante para o **mesmo** tenant (dá um savepoint, como
qualquer `@transaction.atomic` de um service) e levanta `TenantScopeConflict`
para um tenant diferente. Pela mesma razão são proibidas as duas misturas de
âmbito: `system_scope()` dentro de `tenant_scope()` seria escalada de
privilégio a meio de um pedido, e `tenant_scope()` dentro de `system_scope()`
deixaria o tenant colado ao resto da transação de sistema. O consumidor da
outbox lê a linha sob `system_scope()`, **fecha** o bloco, e só depois abre
`tenant_scope(row.tenant_id)`.

## O que o Postgres faz à saída do bloco, exatamente

Medido, não deduzido: no fim da transação o GUC **não volta a NULL** — volta a
`''`, porque `app.tenant_id` é um placeholder e o valor de arranque de um
placeholder é a string vazia. A consequência é a política, não este módulo:
`current_setting('app.tenant_id', true)::uuid` levanta
`invalid input syntax for type uuid: ""` na segunda transação de uma ligação
persistente, pelo que a política tem de comparar contra
`NULLIF(current_setting('app.tenant_id', true), '')::uuid` — aí o predicado é
NULL, a linha não casa, zero linhas, sem erro. Está fixado em
`tests/test_tenant_scope.py` e escrito na migração que cria a primeira tabela
com política.

## Fronteira, e o que fica de fora dela

Quem abre o âmbito num pedido é o `TenantMiddleware` do `apps/accounts/`, que é
o **último** da lista de middleware (ADR 0005, ARCHITECTURE.md §4). No Celery é
o `TenantTask` de `apps/shared/tasks.py`. Um `tenant_scope` aberto dentro de uma
transação que não é sua deixa o GUC colado a essa transação depois de fechar —
é por isso que ele tem de ser a fronteira exterior, e é por isso que os testes
deste mecanismo precisam de `django_db(transaction=True)`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.db import connection, transaction

__all__ = ["TenantScopeConflict", "current_tenant", "system_scope", "tenant_scope"]

#: Nome do GUC que a política RLS lê. Privado de propósito: o único sítio fora
#: deste módulo que o pode escrever é o SQL de uma política, numa migração.
_TENANT_SETTING = "app.tenant_id"

#: GUC do âmbito de sistema. Só a tabela da outbox o tem como disjunto na sua
#: política (ADR 0005): o consumidor precisa de reclamar linhas de qualquer
#: tenant. Nenhuma outra política o menciona.
_SCOPE_SETTING = "app.scope"
_SYSTEM_SCOPE = "system"

#: `true` = âmbito de transação. Ver o docstring do módulo.
_SET_CONFIG_LOCAL = "SELECT set_config(%s, %s, true)"

_current_tenant: ContextVar[UUID | None] = ContextVar("stockflow_tenant", default=None)
_system: ContextVar[bool] = ContextVar("stockflow_system_scope", default=False)


class TenantScopeConflict(RuntimeError):
    """Tentativa de mudar de âmbito dentro de um âmbito já aberto.

    Nunca é uma condição recuperável: significa que o código tentou mudar de
    tenant (ou escalar para sistema) a meio de uma transação, onde o
    `set_config` local do bloco interior sobrevive ao bloco e contaminaria o
    resto da transação.
    """


def current_tenant() -> UUID | None:
    """Tenant do âmbito ativo, ou `None` fora de qualquer âmbito.

    `None` é o caso normal em muitos sítios: login, healthcheck, admin, pedido
    anónimo, cron que itera tenants. Não é erro — é a política a devolver zero
    linhas.
    """
    return _current_tenant.get()


@contextmanager
def tenant_scope(tenant_id: UUID | str) -> Iterator[UUID]:
    """Transação com `app.tenant_id` definido, que é a fronteira da RLS.

    Reentrante para o mesmo tenant (o bloco interior é um savepoint). Levanta
    `TenantScopeConflict` para um tenant diferente ou dentro de `system_scope`.
    """
    tenant = _as_uuid(tenant_id)

    if _system.get():
        raise TenantScopeConflict(
            "tenant_scope() dentro de system_scope(): o set_config do bloco "
            "interior sobrevive-lhe e o tenant ficava colado ao resto da "
            "transação de sistema. Fecha o system_scope antes de abrir o "
            "âmbito do tenant (ADR 0005)."
        )

    ativo = _current_tenant.get()
    if ativo is not None:
        if ativo != tenant:
            raise TenantScopeConflict(
                f"âmbito de {ativo} já aberto; pedido para {tenant}. Um "
                "set_config local dentro de um savepoint vive até ao fim da "
                "transação de topo, logo trocar de tenant a meio contaminaria "
                "o resto do pedido (ADR 0005)."
            )
        with transaction.atomic():
            yield tenant
        return

    with transaction.atomic():
        _set_local(_TENANT_SETTING, str(tenant))
        token = _current_tenant.set(tenant)
        try:
            yield tenant
        finally:
            _current_tenant.reset(token)


@contextmanager
def system_scope() -> Iterator[None]:
    """Transação com `app.scope = 'system'`, para o consumidor da outbox.

    É o único disjunto que dispensa `app.tenant_id`, e só a tabela da outbox o
    tem na sua política. Reentrante; levanta `TenantScopeConflict` dentro de um
    `tenant_scope` — um service a correr num pedido não escala para sistema.
    """
    if _current_tenant.get() is not None:
        raise TenantScopeConflict(
            "system_scope() dentro de tenant_scope(): seria escalada de "
            "privilégio a meio de um pedido, e o app.scope ficava definido "
            "até ao fim da transação (ADR 0005)."
        )

    if _system.get():
        with transaction.atomic():
            yield
        return

    with transaction.atomic():
        _set_local(_SCOPE_SETTING, _SYSTEM_SCOPE)
        token = _system.set(True)
        try:
            yield
        finally:
            _system.reset(token)


def _set_local(nome: str, valor: str) -> None:
    """Corre o `set_config` com âmbito de transação, com os dois argumentos
    parametrizados."""
    with connection.cursor() as cursor:
        cursor.execute(_SET_CONFIG_LOCAL, [nome, valor])


def _as_uuid(valor: UUID | str) -> UUID:
    """Normaliza o tenant para `UUID`.

    Aceita string porque o Celery serializa os argumentos em JSON: uma tarefa
    recebe o tenant como texto. A conversão é também validação — uma string que
    não seja um UUID nunca chega ao `set_config`.
    """
    if isinstance(valor, UUID):
        return valor
    try:
        return UUID(valor)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"tenant_id não é um UUID: {valor!r}") from exc
