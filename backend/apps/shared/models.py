"""Infraestrutura de persistência partilhada: o mixin `TenantModel`.

Também é aqui que a tabela da outbox entra no registo de modelos do Django. O
Django só importa `<app>/models.py`, logo um modelo definido em
`apps/shared/outbox.py` não seria descoberto sem o reexport no fim deste
ficheiro. O `__all__` é o que o torna um reexport explícito, sem `# noqa`.
"""

from __future__ import annotations

from uuid import uuid4

from django.db import models

from apps.shared.outbox import OutboxEvent

__all__ = ["OutboxEvent", "TenantModel"]


class TenantModel(models.Model):
    """Base abstrata de tudo o que pertence a um tenant.

    Herdar daqui é o que torna uma tabela elegível para a política RLS: dá-lhe
    a coluna `tenant_id` que o predicado compara (ADR 0005). A migração que
    cria a tabela tem de acrescentar `ENABLE` + `FORCE ROW LEVEL SECURITY` e a
    política — o mixin não o pode fazer por ela, e é a regra do CLAUDE.md que
    não se discute.

    ## Detalhes que não são estilo

    **A chave é UUID e não sequencial** (SECURITY.md §4): um id inteiro exposto
    numa API multi-tenant conta quantos documentos existem e convida a
    enumerar. `default=uuid4` (v4, aleatório) e não uma versão ordenada por
    tempo — a ordenação faz-se por `created_at`, que é indexado.

    **O tenant é referenciado por string.** `ForeignKey("accounts.Tenant")` não
    gera import, e é o que mantém `apps.shared` como camada de base do grafo,
    sem depender de `accounts` (ADR 0003). O import-linter impõe-no: o contrato
    do `shared` é o único sem exceção nenhuma.

    **`related_name="+"`**, ou seja, sem acessor inverso. Não é avareza: o
    caminho de acesso suportado é filtrar por `tenant_id` dentro do âmbito, e
    `tenant.stockmovement_set.all()` daria ao objeto `Tenant` uma vintena de
    acessores que atravessam o domínio todo a partir do módulo de identidade.

    **`on_delete=CASCADE`**: apagar um tenant apaga os seus dados, que é o que o
    direito ao esquecimento do RGPD exige. Em contrapartida é uma operação
    grande e não é para correr dentro de um pedido.

    ## Índices

    O `Meta.indexes` traz o índice composto `(tenant_id, -created_at)`, que é a
    forma de **todas** as listagens: filtro por tenant, mais recentes primeiro.
    Por isso o FK leva `db_index=False` — o índice de coluna única que o Django
    criaria por omissão seria um prefixo redundante deste, pago em cada escrita.

    O índice **não tem nome**. É deliberado e é a forma suportada pelo Django
    para índices declarados numa base abstrata: `ModelBase._prepare` chama
    `set_name_with_model` em cada modelo concreto e gera um nome único a partir
    da tabela. Dar-lhe um nome fixo daria colisão entre subclasses, e um nome
    com `%(app_label)s`/`%(class)s` não é interpolado em índices (só em
    `related_name`) — ficava literal, e o limite de 30 caracteres do
    `models.E034` estoura com nomes como `purchasereceiptdraftline`.

    ## Ao herdar

    Uma subclasse que declare `Meta` tem de estender a deste mixin, senão perde
    o índice do tenant:

        class StockMovement(TenantModel):
            class Meta(TenantModel.Meta):
                ordering = ["-created_at"]

    E `updated_at` é `auto_now`, logo **não** é atualizado por
    `QuerySet.update()`. Um service que escreva por `update()` põe
    `updated_at=timezone.now()` à mão.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=False,
        verbose_name="tenant",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["tenant", "-created_at"])]
