"""Outbox transacional: a única forma de um evento sair de uma transação.

Um efeito secundário — email de alerta, extração de fatura, previsão — não corre
no ciclo do pedido (CLAUDE.md, ARCHITECTURE.md §4). Mas publicá-lo diretamente
no broker a partir de um service tem dois modos de falha simétricos e ambos
acontecem: se o broker aceita e a transação faz rollback, o consumidor reage a
um facto que não existe; se a transação commita e o broker está em baixo, o
facto existe e ninguém reage. A linha desta tabela é escrita **na mesma
transação** que o resto, logo commita ou desaparece com ela, e um worker
publica-a depois.

## A política RLS desta tabela é a única com `app.scope = 'system'`

O consumidor não é um pedido: não tem tenant nenhum e tem de conseguir reclamar
linhas de todos. Daí o disjunto de sistema na política (ADR 0005), que existe
**só** aqui. Ele lê a linha sob `system_scope()`, fecha o bloco, e só depois
abre `tenant_scope(row.tenant_id)` para tratar o evento.

## Por que razão o `tenant_id` não é ForeignKey

Decisão tomada no passo 3, e deliberada: é um `UUIDField` simples.

1. `apps.shared` é a camada de base do grafo e não depende de `accounts` — nem
   ao nível do import (ADR 0003) nem ao nível da base de dados. Uma FK é uma
   dependência de esquema tão real como um import.
2. Uma FK obrigaria `shared/migrations/0001` a depender de
   `accounts/migrations/0001`, que só nasce no passo 4. O passo 3 deixava de
   poder migrar e a política RLS ficava sem prova de funcionar.
3. A política só precisa da **coluna**. `tenant_id = NULLIF(current_setting(...
   ), '')::uuid` não consulta a tabela de tenants.
4. E há uma razão de operação: um evento é um registo histórico. Com
   `on_delete=CASCADE`, apagar um tenant apagaria também os eventos ainda não
   processados que descrevem o que lhe aconteceu; com `PROTECT`, o apagar
   falhava por causa da outbox. Sem FK, a limpeza das duas tabelas é uma
   decisão explícita de quem apaga o tenant.

O preço é nomeável: nada impede uma linha com um `tenant_id` que já não existe.
Para uma tabela de eventos com retenção curta, é o preço certo.

## Retenção

As linhas processadas não são apagadas aqui. `processed_at` marca-as, e a
limpeza é uma tarefa periódica — que é também onde se decide quanto tempo é
"curto". Fica para o passo que escrever o consumidor.
"""

from __future__ import annotations

from uuid import uuid4

from django.db import models
from django.db.models import Q

from apps.shared.db import TenantScopeConflict, current_tenant
from apps.shared.events import DomainEvent

__all__ = ["OutboxEvent", "publish"]


class OutboxEvent(models.Model):
    """Um evento de domínio à espera de ser publicado aos handlers.

    A chave primária **é** o `event_id` do evento. Não é atalho: dá de graça a
    unicidade que torna `publish()` idempotente dentro da transação (escrever o
    mesmo evento duas vezes é violação de unicidade, não duplicado) e é a mesma
    chave por que os handlers são idempotentes (ARCHITECTURE.md §4).
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant_id = models.UUIDField(verbose_name="tenant")
    event_type = models.CharField(max_length=200, verbose_name="tipo de evento")
    payload = models.JSONField(default=dict, verbose_name="conteúdo")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="escrito em")
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="processado em",
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name="tentativas")
    #: Só a classe e a mensagem da exceção, nunca o traceback: o `DETAIL` de um
    #: erro do Postgres leva os valores da linha em conflito, e esta coluna é
    #: lida no admin (SECURITY.md §1, "Exposição de dados em logs").
    last_error = models.TextField(blank=True, default="", verbose_name="último erro")

    class Meta:
        verbose_name = "evento na outbox"
        verbose_name_plural = "eventos na outbox"
        indexes = [
            # A query do consumidor: as pendentes, mais antigas primeiro. É
            # parcial porque o que interessa é sempre a minoria — as
            # processadas acumulam até à limpeza e não têm de entrar no índice.
            models.Index(
                fields=["created_at"],
                condition=Q(processed_at__isnull=True),
                name="outbox_pendentes_idx",
            ),
            # Diagnóstico por tenant ("que eventos gerou esta receção?"), que é
            # o que a política RLS deixa um pedido ver.
            models.Index(fields=["tenant_id", "created_at"], name="outbox_tenant_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.pk})"


def publish(event: DomainEvent) -> OutboxEvent:
    """Escreve o evento na outbox, na transação de quem o produziu.

    Chama-se de dentro de um `services.py` — é a escrita que a regra "nenhuma
    escrita na BD fora de services" pressupõe, não uma exceção a ela.

    Verifica o âmbito antes de escrever. Sem esta verificação o erro aparecia
    como `new row violates row-level security policy` vindo do Postgres, que
    diz o que aconteceu mas não onde: a política é a rede, não a regra
    (SECURITY.md §1).
    """
    tenant = current_tenant()
    if tenant is None:
        raise TenantScopeConflict(
            f"{event.event_type()} publicado fora de um tenant_scope. Um "
            "evento pertence sempre a um tenant e a linha é escrita na "
            "transação do pedido ou da tarefa (ADR 0005)."
        )
    if tenant != event.tenant_id:
        raise TenantScopeConflict(
            f"{event.event_type()} é do tenant {event.tenant_id} mas o âmbito "
            f"aberto é o de {tenant}."
        )
    return OutboxEvent.objects.create(
        id=event.event_id,
        tenant_id=event.tenant_id,
        event_type=event.event_type(),
        payload=event.payload(),
    )
