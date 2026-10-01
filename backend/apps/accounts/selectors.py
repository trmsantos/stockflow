"""Queries de leitura do `accounts`. Três, e cada uma corre dentro de um âmbito.

A primeira é a do caminho crítico: o `TenantMiddleware` corre o
`membership_no_ambito` **uma vez por pedido**, como primeira e única instrução
dentro do âmbito antes de entregar o pedido (ADR 0007). Vive aqui e não no
middleware porque o caminho do login e o da troca de tenant fazem exatamente a
mesma pergunta, e duas escritas da mesma query são duas oportunidades de uma
delas se esquecer do `is_active`.

As outras duas são dos convites (ADR 0010), e a diferença entre elas vale ser
dita: a da listagem corre no âmbito que a **sessão** escolheu, e a da activação
corre no âmbito que o **link** escolheu. A política é a mesma nos dois casos, e é
ela que concede — nenhuma destas funções filtra por tenant em Python.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from apps.accounts.models import Invitation, Membership

__all__ = [
    "convite_por_token_hash",
    "convites_do_ambito",
    "membership_no_ambito",
]


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


def convite_por_token_hash(token_hash: str) -> Invitation | None:
    """O convite deste token **dentro do âmbito aberto**, ou `None`.

    É a leitura que a ADR 0010 põe no centro: corre dentro do
    `tenant_scope(uuid que vem do link)`, onde a política do
    `accounts_invitation` filtra por `app.tenant_id`. Um uuid forjado escolhe um
    âmbito onde este `token_hash` não existe — zero linhas, sem erro, e nenhuma
    linha de outro estabelecimento é lida no caminho, nem para ser descartada
    depois em Python.

    ## Sem `select_related("tenant")`, e é a parte que não é performance

    O `membership_no_ambito` abaixo usa-o, e aqui a ausência é deliberada. A
    ordem das leituras é parte da decisão: casa-se o convite **primeiro** e o
    nome do estabelecimento só se lê depois de a pertença existir, pelo caminho
    normal da sessão. Trazer o `Tenant` no mesmo `JOIN` punha o nome à mão de
    quem escrevesse a mensagem de erro seguinte — e "foste convidado para a
    Pastelaria Aurora" sobre um uuid adivinhado é um oráculo de enumeração de
    clientes.

    ## `filter().first()` e não `get()`

    Ao contrário do `membership_no_ambito`, aqui a ausência de linha é o caminho
    **esperado** e não a excepção: qualquer link velho, revogado ou forjado passa
    por ela. Um `try/except DoesNotExist` em volta do caminho normal lê pior, e o
    `first()` ordena por uma chave única de uma linha — o `ORDER BY` que ele
    acrescenta é sobre um resultado de uma linha encontrado pelo índice
    `invitation_token_hash_uniq`.
    """
    return Invitation.objects.filter(token_hash=token_hash).first()


def convites_do_ambito(*, tenant_id: UUID) -> QuerySet[Invitation]:
    """Os convites deste estabelecimento, mais recentes primeiro.

    O filtro por `tenant_id` é o segundo controlo e não o primeiro: quem isola é
    a política, e isto é o `get_queryset` filtrado que o CLAUDE.md e o
    `SECURITY.md` §1 exigem **ao lado** dela. Com os dois, uma política desligada
    por acidente não é travessia de tenant, e um filtro esquecido também não.

    A ordem é a do índice `(tenant_id, -created_at)` que o `TenantModel` dá a
    todas as tabelas de tenant, pelo que a listagem paginada não ordena nada em
    memória.

    Sem `select_related`: nada do que o `ConviteOutSerializer` emite atravessa
    uma relação. O `invited_by` existe na tabela e **não** está no contrato
    (ver o modelo), e é essa ausência que faz com que uma lista de 50 convites
    seja uma query e não 51.
    """
    return Invitation.objects.filter(tenant_id=tenant_id).order_by("-created_at")
