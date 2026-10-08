"""Queries de leitura das extrações. Nenhuma escreve.

Duas. A primeira serve o porto: **a última tentativa de cada documento**, em
lote. Em lote porque a alternativa é uma query por linha na listagem de
documentos — o N+1 clássico, aqui a atravessar uma fronteira de módulo, que é
onde é mais difícil de ver. A segunda serve o handler do `DocumentoFechado`, e é
a pergunta de que depende não se pagar uma leitura duas vezes.

Todas recebem `tenant_id` e filtram por ele, ao lado da política (SECURITY.md §1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from apps.agents.models import Extraction

__all__ = ["ja_houve_tentativa", "ultimas_tentativas"]


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
