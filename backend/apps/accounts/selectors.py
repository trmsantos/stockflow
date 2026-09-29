"""Queries de leitura do `accounts`. Uma só, e é a do caminho crítico.

O `TenantMiddleware` corre esta query **uma vez por pedido**, como primeira e
única instrução dentro do âmbito antes de entregar o pedido (ADR 0007). Vive
aqui e não no middleware porque o caminho do login e o da troca de tenant fazem
exatamente a mesma pergunta, e duas escritas da mesma query são duas
oportunidades de uma delas se esquecer do `is_active`.
"""

from __future__ import annotations

from uuid import UUID

from apps.accounts.models import Membership

__all__ = ["membership_no_ambito"]


def membership_no_ambito(*, user_id: UUID, tenant_id: UUID) -> Membership | None:
    """A pertença ativa de (utilizador, âmbito), ou `None` se a política não a der.

    ## Porque é que `None` não distingue "não existe" de "não é meu"

    Não pode distinguir, e é essa a propriedade que fecha o caminho de leitura
    entre tenants. A query leva `user_id = <o do pedido>` no `WHERE` e corre
    dentro de `tenant_scope(tenant_id)`, onde as políticas do
    `accounts_membership` e do `accounts_tenant` filtram por `app.tenant_id`.
    Um `tenant_id` forjado na sessão escolhe um âmbito onde esta query não
    devolve nada — e **nenhuma linha do tenant alheio é lida** no caminho, nem
    para ser descartada depois em Python.

    ## `select_related("tenant")` não é só performance

    É o que traz o `name` do tenant para o `TenantContext` sem uma segunda
    query, mas é também uma segunda verificação de graça: o FK não é nulável,
    logo o Django emite um `INNER JOIN` e a linha só aparece se as **duas**
    políticas casarem. Um `Membership` que aponte para um tenant que o âmbito
    não mostra desaparece, em vez de produzir um contexto com o nome a `None`.

    ## `get()` e não `first()`

    `first()` numa queryset sem `order_by` acrescenta `ORDER BY id`, que troca
    a leitura direta pelo índice único `(user_id, tenant_id)` por uma ordenação
    de um resultado de uma linha. `get()` não ordena.
    """
    try:
        return Membership.objects.select_related("tenant").get(
            user_id=user_id,
            tenant_id=tenant_id,
            is_active=True,
        )
    except Membership.DoesNotExist:
        return None
