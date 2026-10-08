"""Os eventos que o `purchasing` emite. Contrato público (ADR 0003).

Um `events.py` é importável por **qualquer** módulo — é a exceção transversal do
import-linter, e existe porque um handler precisa do tipo para subscrever
(ARCHITECTURE.md §3). O preço é o de qualquer contrato público: mudar-lhe os
campos é breaking, e renomear a classe muda o `event_type()` enquanto as linhas
já escritas na outbox continuam com o nome antigo (ver `apps/shared/events.py`).

Um evento só, por agora, e é o do fluxo da receção: `ARCHITECTURE.md` §6b abre
com *"`purchasing.upload_invoice` → evento `InvoiceUploaded` → ..."*. O nome
daqui é `DocumentoFechado` e não `InvoiceUploaded`, por duas razões que a fatia 1
tornou medíveis:

* **um documento não é uma fatura.** O que entrou é um papel fotografado; se o
  que está no papel é uma fatura, uma guia ou um gato, é o que a extração vai
  tentar dizer (ADR 0020, decisão 8). Chamar `Invoice` ao evento era afirmar o
  conteúdo antes de alguém o ler;
* **o momento não é o upload, é o fecho.** Um `upload` nasce fechado (um PDF de
  dez páginas é um documento completo), mas uma captura de telemóvel recebe
  páginas durante minutos e só está pronta quando uma pessoa diz que está (ADR
  0021, decisão 9). O facto que interessa aos dois lados — rasterizar e extrair —
  é *"não vêm mais páginas"*, e esse chama-se fecho.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apps.shared.events import DomainEvent

__all__ = ["DocumentoFechado"]


@dataclass(frozen=True, kw_only=True, slots=True)
class DocumentoFechado(DomainEvent):
    """Um documento de fornecedor deixou de aceitar páginas.

    Publicado por `purchasing.services.enfileirar_trabalho_do_documento`, na
    transação do pedido que o fechou. Dois handlers reagem hoje, e é por
    publicar isto em vez de chamar `.delay()` que nenhum dos dois módulos
    conhece o outro:

    * `apps.purchasing.handlers` enfileira a rasterização das páginas que ainda
      não têm imagem;
    * `apps.agents.handlers` enfileira a leitura do documento pelo modelo.

    **Leva o id e mais nada.** Não leva a lista de páginas, e isso é a correção
    de um defeito a sério que a versão `on_commit` deste fluxo teve de resolver
    de outra forma: um `on_commit` corre fora do `tenant_scope`, onde a política
    devolve zero linhas, logo a lista tinha de ser lida **antes** e viajar na
    closure. Um handler da outbox não tem esse problema — corre dentro de
    `tenant_scope(tenant_id)` — e por isso lê as páginas ele mesmo, no instante
    em que vai agir. Uma lista dentro do evento era uma fotografia do estado,
    tirada antes do commit e já velha quando o handler a lesse.
    """

    documento_id: UUID
