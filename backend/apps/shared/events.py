"""Classe base dos eventos de domínio.

Um evento é um **DTO**: uma dataclass imutável com os dados que outro módulo
precisa para reagir, e nada mais. Não conhece `models`, `services` nem a base de
dados. É o que torna `apps.<m>.events` importável por qualquer módulo sem abrir
o grafo de dependências do `api.py` (ADR 0003, ARCHITECTURE.md §3).

Este ficheiro não importa nenhum módulo do projeto e é o único com essa
restrição sem exceção no import-linter — nem sequer os eventos de quem está
acima. Também não importa Django: só stdlib.

## Como se declara um evento

    @dataclass(frozen=True, kw_only=True, slots=True)
    class StockReceived(DomainEvent):
        movement_ids: tuple[UUID, ...]
        total_cost: Decimal

`frozen` porque um evento é um facto passado; `kw_only` porque acrescentar um
campo no meio não pode mudar o significado de uma chamada posicional; `slots`
porque são muitos e pequenos.

## Contrato público

Um evento importado por outro módulo é contrato público (ADR 0003): mudar-lhe os
campos é breaking, tal como em `api.py`. Renomear a classe muda o `event_type()`
e as linhas já escritas na outbox continuam com o nome antigo — o consumidor
tem de saber tratar os dois durante a transição.

## Dinheiro e quantidades

`payload()` recusa `float`. As quantidades e o dinheiro do StockFlow são
`Decimal` (CLAUDE.md) e um `Decimal` que passe por `float` a caminho do JSON
perde exatidão em silêncio — 0.1 + 0.2 num inventário valorizado é uma
diferença de cêntimos que ninguém consegue explicar depois. `Decimal` é
serializado como **string**, nunca como número JSON, para atravessar a outbox e
voltar sem perder casas decimais.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

__all__ = ["DomainEvent"]


def _agora() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


@dataclass(frozen=True, kw_only=True, slots=True)
class DomainEvent:
    """Envelope comum a todos os eventos de domínio.

    * `event_id` é a chave de idempotência dos handlers (ARCHITECTURE.md §4) e
      é também a chave primária da linha da outbox: escrever o mesmo evento
      duas vezes na mesma transação dá violação de unicidade, não duplicado.
    * `tenant_id` está no envelope e não no payload de cada evento porque é o
      predicado da política RLS e a coluna da outbox.
    * `occurred_at` é o instante em que o facto aconteceu, em UTC. Não se
      confunde com o `created_at` da linha da outbox (esse é do lado da BD) nem
      com a hora a que o consumidor o processou.
    """

    tenant_id: UUID
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: dt.datetime = field(default_factory=_agora)

    @classmethod
    def event_type(cls) -> str:
        """Nome do tipo, em caminho pontuado completo.

        `apps.inventory.events.StockReceived`. É importável, logo o consumidor
        pode resolvê-lo para a classe sem manter uma tabela de nomes a par.
        """
        return f"{cls.__module__}.{cls.__qualname__}"

    def payload(self) -> dict[str, Any]:
        """O evento inteiro, pronto para o `JSONField` da outbox.

        Inclui o envelope: a linha é auto-suficiente, o que é o que permite
        publicá-la num broker externo se um módulo for extraído (ARCHITECTURE.md
        §7) sem reconstruir o evento a partir de três colunas.
        """
        return {
            campo.name: _jsonavel(getattr(self, campo.name))
            for campo in dataclasses.fields(self)
        }


def _jsonavel(valor: Any) -> Any:
    """Converte para tipos que o `json` sabe escrever, sem perder exatidão.

    Recusa `float` em vez de o aceitar: ver o docstring do módulo.
    """
    if valor is None or isinstance(valor, str | bool | int):
        return valor
    if isinstance(valor, float):
        raise TypeError(
            "float num payload de evento. Quantidades e dinheiro são Decimal "
            "(CLAUDE.md); se é mesmo um número aproximado, converte-o para "
            "string antes de o pôr no evento."
        )
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, dt.datetime | dt.date | dt.time):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return _jsonavel(valor.value)
    if isinstance(valor, dict):
        return {str(chave): _jsonavel(item) for chave, item in valor.items()}
    if isinstance(valor, list | tuple):
        return [_jsonavel(item) for item in valor]
    raise TypeError(
        f"{type(valor).__name__} não tem representação JSON definida para um "
        "evento. Põe no evento um tipo simples (UUID, Decimal, str, int, bool, "
        "datetime) ou um `tuple` deles — `set` não serve, porque a ordem do "
        "JSON deixava de ser reproduzível."
    )
