"""As únicas escritas do `accounts` (CLAUDE.md: nenhuma escrita fora de services).

Três funções, e o que as junta é **um invariante**, não um caso de uso: o
`User.tenant_ids` espelha as pertenças ativas e é escrito na mesma transação
que qualquer `Membership` (ADR 0007). Um invariante sem um único escritor é um
comentário; com um, é verificável — e está verificado em
`tests/test_rls_isolation.py`.

Os **endpoints** que chamam isto — registo, convite, aceitação de convite,
remoção de um colaborador — entram na sessão da autenticação, com a sua ADR.
Aqui não há views, nem eventos na outbox: nada disto emite um evento de domínio
ainda, porque não há subscritor nenhum e um evento sem consumidor é um contrato
público escrito ao contrário.

## Por que razão o `tenant_ids` não é recalculável

A tentação é `tenant_ids = [m.tenant_id for m in user.memberships.filter(is_active=True)]`.
Não funciona, e falha em silêncio: o `accounts_membership` tem política, logo
dentro de `tenant_scope(A)` essa varredura só vê as pertenças de A e o array
passava a ter **uma** entrada, apagando as outras. A manutenção é incremental
por desenho — junta-se um uuid ao conceder, retira-se ao revogar — e é a razão
pela qual as duas funções que tocam num `Membership` são também as duas que
tocam no array.

## Quem abre a transação

`criar_tenant` **é** a fronteira: abre o `tenant_scope` ele mesmo, porque é
chamado de uma view dispensada de âmbito (o registo) e porque criar um tenant é,
literalmente, gerar o UUID em Python e inserir de dentro do âmbito desse UUID —
a política do `accounts_tenant` compara `id`, não há `WITH CHECK` separado, e
`id = app.tenant_id` é verdade (ADR 0007).

As outras duas correm **dentro** de um âmbito já aberto (o do pedido, ou o que o
registo acabou de abrir) e o seu `transaction.atomic()` é um savepoint, como
manda a ADR 0005. Nenhuma delas abre `tenant_scope`: um `tenant_scope` dentro de
uma transação que não é sua deixa o GUC colado a essa transação depois de
fechar. É também por isso que `criar_tenant` **não** leva um
`transaction.atomic()` por fora — isso punha a transação antes do `set_config`.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import F, Func, Value
from django.utils import timezone

from apps.accounts.models import Membership, Papel, Tenant, User
from apps.shared.db import TenantScopeConflict, current_tenant, tenant_scope

__all__ = ["conceder_pertenca", "criar_tenant", "revogar_pertenca"]


def criar_tenant(*, name: str) -> Tenant:
    """Cria um tenant, abrindo o âmbito dele para o poder inserir.

    O UUID é gerado aqui e não pela base de dados: é preciso conhecê-lo
    **antes** do `INSERT` para o poder pôr no `app.tenant_id`, que é o que faz a
    linha passar a própria política que a vai proteger.
    """
    tenant_id = uuid4()
    with tenant_scope(tenant_id):
        return Tenant.objects.create(id=tenant_id, name=name)


def conceder_pertenca(
    *,
    user: User,
    tenant_id: UUID,
    role: str,
    display_name: str,
) -> Membership:
    """Dá (ou reativa) a pertença de um utilizador a este tenant.

    Idempotente pelo `UniqueConstraint(user, tenant)`: conceder duas vezes
    atualiza o papel e o nome exibido em vez de levantar. É o comportamento que
    um convite reenviado precisa.
    """
    _exigir_ambito(tenant_id)
    if role not in {p.value for p in Papel}:
        raise ValueError(f"papel desconhecido: {role!r}")

    with transaction.atomic():
        membership, _ = Membership.objects.update_or_create(
            user=user,
            tenant_id=tenant_id,
            defaults={"role": role, "display_name": display_name, "is_active": True},
        )
        _espelhar(user, tenant_id, pertence=True)
    return membership


def revogar_pertenca(*, user: User, tenant_id: UUID) -> bool:
    """Desativa a pertença e retira o âmbito da lista de candidatos.

    Devolve se havia alguma coisa para revogar. O array é podado nas duas
    situações: se não há pertença ativa neste tenant, o uuid não pode ficar lá —
    é isso que "espelha as pertenças ativas" quer dizer.

    A sessão de quem for revogado não é tocada: ela guarda um UUID e zero
    autorização, e o pedido seguinte leva 403 do `TenantMiddleware`.
    """
    _exigir_ambito(tenant_id)

    with transaction.atomic():
        revogadas = Membership.objects.filter(
            user=user,
            tenant_id=tenant_id,
            is_active=True,
        ).update(is_active=False, updated_at=timezone.now())
        _espelhar(user, tenant_id, pertence=False)
    return revogadas > 0


def _exigir_ambito(tenant_id: UUID) -> None:
    """O âmbito aberto tem de ser o deste tenant, senão a política recusaria.

    Não é uma verificação defensiva a mais: sem âmbito, o `INSERT` levaria
    `new row violates row-level security policy` e o `UPDATE` afetaria zero
    linhas **sem erro** — que é a forma silenciosa do mesmo bug.
    """
    ativo = current_tenant()
    if ativo != tenant_id:
        raise TenantScopeConflict(
            f"escrita em accounts_membership para {tenant_id} com o âmbito em "
            f"{ativo}: a política filtra por app.tenant_id e o UPDATE afetaria "
            "zero linhas sem erro (ADR 0005, ADR 0007)."
        )


def _espelhar(user: User, tenant_id: UUID, *, pertence: bool) -> None:
    """Junta ou retira o âmbito do `tenant_ids`, na transação da chamada.

    Escreve-se no `accounts_user`, que não tem política: uma escrita de dentro
    de `tenant_scope(A)` numa tabela sem política é normal e não é uma fuga de
    âmbito — o que a coluna diz é "este utilizador pode *tentar* A", e tentar
    não concede nada.

    ## `array_append` no Postgres, e não ler-modificar-escrever em Python

    A versão óbvia — `user.tenant_ids = sorted({*user.tenant_ids, tenant_id})`
    seguido de `save()` — é uma leitura, uma modificação e uma escrita em três
    passos, e a contabilista que é convidada para dois tenants ao mesmo tempo
    perde uma das entradas: a segunda transação escreve por cima do array que
    leu antes de a primeira commitar. É uma atualização perdida clássica, e o
    sintoma é benigno mas confuso — falta um estabelecimento no seletor, sem
    erro nenhum em sítio nenhum.

    Numa instrução só não há janela: o `array_append`/`array_remove` corre
    sobre o valor que a linha tem no momento do `UPDATE`, e o
    `exclude(tenant_ids__contains=...)` (o `@>` do Postgres) é o que torna a
    operação idempotente sem um `SELECT` à frente. O `refresh_from_db` a seguir
    é o que mantém a instância em memória de acordo com a linha — sem ele, o
    chamador ficava com um array velho.

    `updated_at` é `auto_now`, logo **não** é atualizado por
    `QuerySet.update()`: vai à mão, como manda o docstring do `TenantModel`.
    """
    valor = Value(tenant_id, output_field=models.UUIDField())
    campo = ArrayField(models.UUIDField())
    linhas = User.objects.filter(pk=user.pk)
    if pertence:
        linhas = linhas.exclude(tenant_ids__contains=[tenant_id])
        funcao = "array_append"
    else:
        linhas = linhas.filter(tenant_ids__contains=[tenant_id])
        funcao = "array_remove"

    alteradas = linhas.update(
        tenant_ids=Func(F("tenant_ids"), valor, function=funcao, output_field=campo),
        updated_at=timezone.now(),
    )
    if alteradas:
        user.refresh_from_db(fields=["tenant_ids", "updated_at"])
