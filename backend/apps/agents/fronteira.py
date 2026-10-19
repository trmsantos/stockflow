"""O adaptador do porto da extração: a única aresta `agents -> purchasing`.

Implementa o `FronteiraDaExtracao` que o `apps/purchasing/extracao.py` define, e é
ligado uma vez no `ready()` do `AgentsConfig`. A razão de haver um porto em vez de
um import está escrita no topo desse ficheiro, e é onde deve ser lida — em duas
linhas: o `purchasing` não pode importar o `agents` (import-linter), o `agents`
pode importar o `purchasing.api`, logo a dependência inverte-se.

Uma metade só, desde que o `pedir` saiu para a outbox: `leituras` traduz a última
tentativa de cada documento no DTO do porto. Quem enfileira a extração é agora o
`apps/agents/handlers.py`, subscrito ao `DocumentoFechado` — e a razão da troca
está no topo do `apps/purchasing/extracao.py`.

A tradução é a única coisa com substância, e tem um porquê em cada ramo: o
cabeçalho e as linhas só saem quando o `status` é `lido`, e saem já **revalidados
à leitura** (ADR 0021, decisão 4). Um `ilegivel` ou um `erro` chegam ao cliente
com estado e razão e mais nada — é o que torna impossível servir um número que o
modelo não disse.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from uuid import UUID

from apps.agents.models import EstadoDaExtracao, Extraction
from apps.agents.serializers import leitura_validada
from apps.purchasing.api import EstadoDaLeitura, FronteiraDaExtracao, LeituraDeDocumento

__all__ = ["FronteiraLocalDaExtracao"]


class FronteiraLocalDaExtracao(FronteiraDaExtracao):
    """O porto servido pelo `agents` deste mesmo processo.

    "Local" no nome porque é a implementação de monólito. No dia em que o
    `agents` sair para serviço próprio (ARCHITECTURE.md §7), o que muda é esta
    classe — passa a cliente HTTP — e nada mais do lado do `purchasing`, que é a
    propriedade que o porto compra.

    Herda o `Protocol` **explicitamente** em vez de o satisfazer por pato. Não é
    cerimónia: é o que faz o contrato ser verificável por um verificador de
    tipos e o que dá ao `FronteiraDaExtracao` o consumidor que justifica ele ser
    público.
    """

    def leituras(
        self, *, tenant_id: UUID, documento_ids: Sequence[UUID]
    ) -> Mapping[UUID, LeituraDeDocumento]:
        """A última leitura de cada documento, traduzida para o DTO do porto."""
        from apps.agents.selectors import ultimas_tentativas

        tentativas = ultimas_tentativas(
            tenant_id=tenant_id, documento_ids=documento_ids
        )
        return {
            documento_id: _traduzir(tentativa)
            for documento_id, tentativa in tentativas.items()
        }


def _traduzir(tentativa: Extraction) -> LeituraDeDocumento:
    """Uma linha de extração no vocabulário do `purchasing`.

    O `desde` é `started_at` ou, se não houver, o `created_at` da linha: é o
    instante a partir do qual o relógio dos dez minutos conta do outro lado. Sem
    ele, uma tarefa morta deixava o documento em `a_extrair` para sempre.
    """
    estado = EstadoDaLeitura(tentativa.status)
    base = LeituraDeDocumento(
        state=estado.value,
        read_at=tentativa.finished_at,
        desde=tentativa.started_at or tentativa.created_at,
        motivo=tentativa.error,
        confidence=tentativa.confidence,
        # O número da tentativa atravessa a fronteira porque o `purchasing` tem
        # de o comparar com `AGENTS_EXTRACTION_MAX_ATTEMPTS` no endpoint de
        # re-extração (ADR 0031, E) — e ler a tabela do `agents` para o saber é
        # exactamente o que o porto existe para evitar.
        tentativa=tentativa.attempt,
    )
    if tentativa.status != EstadoDaExtracao.LIDO:
        return base
    validada = leitura_validada(tentativa.payload)
    if validada is None:
        # Gravada como `lido` e já não valida: o schema mudou, ou alguém mexeu na
        # linha. O que se serve é `ilegivel` — a validação à leitura existe
        # exactamente para este caso, e confiar no `status` gravado era ter feito
        # a validação uma vez só.
        return replace(base, state=EstadoDaLeitura.ILEGIVEL.value)
    return replace(
        validada,
        state=estado.value,
        read_at=base.read_at,
        desde=base.desde,
        motivo=base.motivo,
        tentativa=base.tentativa,
        confidence=tentativa.confidence or validada.confidence,
    )
