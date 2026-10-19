"""Queries de leitura das extrações. Nenhuma escreve.

Duas. A primeira serve o porto: **a última tentativa de cada documento**, em
lote. Em lote porque a alternativa é uma query por linha na listagem de
documentos — o N+1 clássico, aqui a atravessar uma fronteira de módulo, que é
onde é mais difícil de ver. A segunda serve o handler do `DocumentoFechado`, e é
a pergunta de que depende não se pagar uma leitura duas vezes.

Todas recebem `tenant_id` e filtram por ele, ao lado da política (SECURITY.md §1).

## As do chat (ADR 0027)

Filtram **também** por `created_by`/`asked_by`: a conversa é da pessoa, e a
política só sabe de tenants. É a segunda rede ao lado da primeira, e é o que faz
a conversa de outro utilizador do mesmo estabelecimento dar 404 e não 403.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db.models import Prefetch, QuerySet, Sum
from django.utils import timezone

from apps.agents.models import ChatMessage, Conversation, EstadoDaMensagem, Extraction

__all__ = [
    "conversa_do_utilizador",
    "conversas_do_utilizador",
    "conversas_expiradas",
    "custo_de_extracao_do_dia",
    "custo_do_dia",
    "ja_houve_tentativa",
    "mensagens_da_conversa",
    "perguntas_do_dia",
    "turno_em_curso",
    "turnos_da_conversa",
    "ultimas_tentativas",
]


def ja_houve_tentativa(*, tenant_id: UUID, documento_id: UUID) -> bool:
    """Este documento já teve alguma chamada ao modelo?

    É a idempotência do `handlers.pedir_extracao`, e vive aqui em vez de lá por
    ser uma leitura com nome: o que o handler pergunta não é "quantas tentativas
    há" nem "qual foi a última", é só se já se gastou dinheiro neste documento.

    `exists()` e não `count()`: o índice `(tenant, document_id, -attempt)` serve
    o primeiro com um `LIMIT 1` e o segundo obrigava a varrer as linhas todas
    para devolver um número que ninguém lê.
    """
    return Extraction.objects.filter(
        tenant_id=tenant_id, document_id=documento_id
    ).exists()


def custo_de_extracao_do_dia(
    *, tenant_id: UUID, agora: datetime | None = None
) -> Decimal:
    """`SUM(cost_eur)` das extrações deste tenant desde a meia-noite local.

    **Por tenant e não por utilizador** (ADR 0031, resposta 2 do dono): receber
    mercadoria não é um acto pessoal, logo não há tecto por pessoa. E separado da
    soma do chat de propósito: são dois orçamentos com dois números e duas
    tabelas, e somá-los fazia uma tarde de perguntas ao assistente travar a
    entrada de uma fatura.
    """
    desde = _inicio_do_dia_civil(agora or timezone.now())
    total = Extraction.objects.filter(
        tenant_id=tenant_id, created_at__gte=desde
    ).aggregate(total=Sum("cost_eur"))["total"]
    return total or Decimal("0")


def ultimas_tentativas(
    *, tenant_id: UUID, documento_ids: Sequence[UUID]
) -> Mapping[UUID, Extraction]:
    """A tentativa de `attempt` mais alto de cada documento pedido.

    Uma query e um `dict`, em vez de um `DISTINCT ON` por documento: a lista de
    ids tem no máximo o tamanho de uma página de resultados (50, pelo
    `PAGE_SIZE`), e o índice `(tenant, document_id, -attempt)` serve a ordenação
    sem ficheiro temporário. A última a ser escrita no `dict` ganha, e é por isso
    que a ordenação é **ascendente** — invertê-la daria a primeira tentativa e o
    erro passava despercebido, porque na maioria dos documentos só há uma.
    """
    if not documento_ids:
        return {}
    linhas = Extraction.objects.filter(
        tenant_id=tenant_id, document_id__in=list(documento_ids)
    ).order_by("document_id", "attempt")
    return {linha.document_id: linha for linha in linhas}


# ---------------------------------------------------------------------------
# O chat (ADR 0027)
# ---------------------------------------------------------------------------
def conversas_do_utilizador(*, tenant_id: UUID, user_id: UUID) -> QuerySet[Conversation]:
    """As conversas **desta pessoa** neste estabelecimento, mais recentes primeiro.

    É a base do `get_queryset()` da view: o `created_by` ao lado do `tenant_id`
    é o que torna a conversa de outra pessoa ilegível (404), e o `id` a
    desempatar é o que faz a paginação não repetir linhas.
    """
    return Conversation.objects.filter(tenant_id=tenant_id, created_by_id=user_id).order_by(
        "-last_message_at", "-id"
    )


def mensagens_da_conversa(*, tenant_id: UUID, conversa_id: UUID) -> QuerySet[ChatMessage]:
    """Os turnos de uma conversa, por posição."""
    return ChatMessage.objects.filter(tenant_id=tenant_id, conversation_id=conversa_id).order_by(
        "position"
    )


def conversa_do_utilizador(
    *, tenant_id: UUID, user_id: UUID, conversa_id: UUID
) -> Conversation | None:
    """Uma conversa desta pessoa com os turnos carregados, ou `None`.

    O `Prefetch` com a ordenação por posição é o que faz o `GET` de detalhe —
    o alvo do polling a 2 s — custar duas queries e não uma por turno.
    """
    return (
        conversas_do_utilizador(tenant_id=tenant_id, user_id=user_id)
        .filter(pk=conversa_id)
        .prefetch_related(
            Prefetch(
                "messages",
                queryset=mensagens_da_conversa(tenant_id=tenant_id, conversa_id=conversa_id),
            )
        )
        .first()
    )


def turnos_da_conversa(*, tenant_id: UUID, conversa_id: UUID) -> int:
    """Quantos turnos a conversa tem — o teto `conversa_cheia` compara com isto."""
    return mensagens_da_conversa(tenant_id=tenant_id, conversa_id=conversa_id).count()


def turno_em_curso(*, tenant_id: UUID, conversa_id: UUID) -> ChatMessage | None:
    """O turno `pendente`/`a_responder` que ainda não esgotou o relógio, se houver.

    Um turno que já passou a `JANELA_DA_RESPOSTA` lê-se `erro/tempo_esgotado`
    e **não** bloqueia a pergunta seguinte — senão um worker morto trancava a
    conversa para sempre.
    """
    for turno in mensagens_da_conversa(tenant_id=tenant_id, conversa_id=conversa_id).filter(
        status__in=[EstadoDaMensagem.PENDENTE, EstadoDaMensagem.A_RESPONDER]
    ):
        if not turno.esgotou_o_tempo:
            return turno
    return None


def _inicio_do_dia_civil(agora: datetime) -> datetime:
    """A meia-noite local de `agora`. Os tetos diários contam no calendário civil."""
    local = timezone.localtime(agora)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def custo_do_dia(*, tenant_id: UUID, agora: datetime | None = None) -> Decimal:
    """`SUM(cost_eur)` do tenant desde a meia-noite local (ADR 0027, decisão 9).

    É a mesma query da métrica "custo LLM/dia" do `ARCHITECTURE.md` §8: o teto e
    a métrica não podem divergir porque são a mesma soma.
    """
    desde = _inicio_do_dia_civil(agora or timezone.now())
    total = ChatMessage.objects.filter(tenant_id=tenant_id, created_at__gte=desde).aggregate(
        total=Sum("cost_eur")
    )["total"]
    return total or Decimal("0")


def perguntas_do_dia(*, tenant_id: UUID, user_id: UUID, agora: datetime | None = None) -> int:
    """Quantas perguntas esta pessoa fez hoje neste estabelecimento."""
    desde = _inicio_do_dia_civil(agora or timezone.now())
    return ChatMessage.objects.filter(
        tenant_id=tenant_id, asked_by_id=user_id, created_at__gte=desde
    ).count()


def conversas_expiradas(*, tenant_id: UUID, limite: datetime, lote: int) -> list[UUID]:
    """Até `lote` ids de conversas com `last_message_at` anterior a `limite`.

    Em lotes porque a purga apaga em `CASCADE` e um `DELETE` de um ano de
    conversas numa instrução seguraria os locks durante o tempo todo.
    """
    return list(
        Conversation.objects.filter(tenant_id=tenant_id, last_message_at__lt=limite)
        .order_by("last_message_at", "id")
        .values_list("id", flat=True)[:lote]
    )
