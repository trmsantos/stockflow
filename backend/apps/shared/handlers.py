"""O registo de handlers: `event_type` → quem reage a ele.

Um mapa, duas funções e nada mais. Esta é a metade do consumidor da outbox que
o `apps.shared` **pode** ter: a que não conhece nenhum módulo.

## Porque é que o registo é por inversão e não por import

O `apps.shared` é infraestrutura e não importa módulos — é um contrato do
import-linter (`shared não depende de nenhum outro módulo`) e a ADR 0003.
Logo o consumidor não pode conhecer o `handlers.py` de ninguém: se quisesse
descobrir handlers por si, tinha de importar `apps.purchasing.handlers`, e a
aresta que isso abria era a pior do grafo — a camada de base a depender de
todas as outras.

A dependência inverte-se, como no porto da extração
(`apps/purchasing/extracao.py`): **cada módulo registra os seus handlers no
`ready()` do seu `AppConfig`**, que é o sítio que o `ARCHITECTURE.md` §3 nomeia
para subscrições, e o `shared` só conhece strings e funções. É a mesma forma, e
é de propósito que é a mesma: um leitor que entendeu o porto não tem de
entender um segundo mecanismo.

## O que um handler recebe, e por que razão não é o evento

Recebe um `EventoEntregue`: o envelope da linha da outbox mais o `payload` como
`dict`. **Não** recebe a instância da classe de evento, e a escolha tem três
razões:

1. reconstruir a dataclass obrigava a desserializar os campos a partir das
   strings do JSON (`Decimal`, `UUID`, `datetime` saem todos como texto — ver o
   `payload()` do `apps/shared/events.py`), e isso é um mecanismo de tipos que
   ninguém pediu e que falha de formas novas;
2. o `apps/shared/events.py` escreve por extenso o caso que a reconstrução não
   sobrevive: *"renomear a classe muda o `event_type()` e as linhas já escritas
   na outbox continuam com o nome antigo — o consumidor tem de saber tratar os
   dois durante a transição"*. Um registo por string trata-os: subscreve-se o
   mesmo handler duas vezes, uma por nome. Um registo que importasse a classe
   não encontrava o nome antigo e a linha ficava pendente para sempre;
3. a aresta `shared -> apps.<m>.events` não existe no grafo (é o único contrato
   sem a exceção `.events`), logo o `shared` não pode sequer resolver o nome
   para a classe.

O preço é nomeável: o handler lê `payload["documento_id"]` e converte-o ele
mesmo. É uma linha por campo, à vista, no módulo que conhece o evento.

## O tempo de vida das subscrições

`subscrever()` é para sempre — chama-se uma vez, no `ready()`. O
`subscricao()` é um gestor de contexto que a retira à saída, e existe **para os
testes**: a alternativa era um teste a escrever no dicionário privado deste
módulo, que é pior em todos os sentidos (não restaura nada se o teste falhar, e
congela um detalhe interno num ficheiro de testes).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apps.shared.events import DomainEvent

__all__ = [
    "EventoEntregue",
    "Handler",
    "handlers_de",
    "subscrever",
    "subscricao",
    "tipos_subscritos",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class EventoEntregue:
    """Uma linha da outbox a caminho dos handlers.

    Congelado e com `slots`, como os DTO que atravessam fronteiras de módulo:
    um handler não muta o que recebe, e o que ele escreve escreve-o pelo
    `services.py` do seu módulo.

    `event_id` é a **chave de idempotência** (ARCHITECTURE.md §4, passo 10): o
    mesmo evento pode ser entregue mais de uma vez — numa retentativa depois de
    um handler irmão levantar, ou numa passagem que apanhou a linha antes de o
    `processed_at` commitar — e é por este id que um handler reconhece trabalho
    que já fez.

    `tenant_id` vem da **coluna** da linha e não do payload: é o predicado da
    política RLS, é o âmbito que o consumidor abre antes de chamar o handler, e
    é o valor em que o handler pode confiar sem olhar para o JSON.

    `attempts` é informativo e vem já incrementado pela reclamação desta
    passagem — um handler que queira ramificar na última tentativa compara-o
    com o `TETO_DE_TENTATIVAS` do consumidor.
    """

    event_id: UUID
    tenant_id: UUID
    event_type: str
    payload: Mapping[str, Any]
    attempts: int

    def uuid_do_payload(self, campo: str) -> UUID:
        """Um campo do payload como `UUID`.

        Existe porque **o payload é JSON**: o `payload()` do `DomainEvent`
        serializa um `UUID` como texto, e o que sai do `JSONField` é esse texto.
        Cada handler que precise de um id fazia `UUID(payload["x"])`, e a versão
        ingénua disso rebenta quando o evento é construído à mão num teste, com
        um `UUID` a sério lá dentro.

        Levanta `KeyError` se o campo não existe e `ValueError` se não é um UUID
        — as duas corretas: o consumidor apanha-as, grava a razão na linha e
        tenta outra vez. Um evento com um payload que o handler não entende é um
        defeito de contrato, e tem de ficar escrito em vez de ser ignorado.
        """
        valor = self.payload[campo]
        return valor if isinstance(valor, UUID) else UUID(str(valor))


#: O que um handler é: uma função que recebe o evento entregue e não devolve
#: nada. Síncrona e curta — corre dentro da transação do `tenant_scope` que o
#: consumidor abriu, logo o que ela demorar é tempo com um lock aberto. Trabalho
#: lento enfileira-se numa tarefa, que é precisamente o que os handlers deste
#: projeto fazem.
Handler = Callable[[EventoEntregue], None]

#: `event_type` → handlers, na ordem em que foram subscritos. Dicionário de
#: módulo, como o `_fronteira` do porto da extração, e pela mesma razão: o
#: registo é estado de processo, populado no arranque e lido pelo worker.
_subscricoes: dict[str, tuple[Handler, ...]] = {}


def subscrever(evento: type[DomainEvent] | str, handler: Handler) -> None:
    """Liga um handler a um tipo de evento. Chama-se no `ready()` do módulo.

    `evento` é normalmente a **classe** do evento — o nome sai do
    `event_type()` dela, logo não há strings mágicas a divergir do código. A
    forma em string existe para um caso só, e é o que o `apps/shared/events.py`
    descreve: uma classe renomeada deixa linhas na outbox com o nome antigo, e
    durante a transição o mesmo handler subscreve-se duas vezes, uma por nome.

    **Idempotente para o mesmo handler**: subscrever o mesmo par duas vezes não
    faz nada. Não é zelo — o `ready()` de uma `AppConfig` corre mais de uma vez
    em caminhos de teste do Django, e um registo que duplicasse fazia o handler
    correr duas vezes por evento. A comparação é por identidade de função, que é
    o que um `ready()` repetido reapresenta.
    """
    event_type = evento if isinstance(evento, str) else evento.event_type()
    registados = _subscricoes.get(event_type, ())
    if handler in registados:
        return
    _subscricoes[event_type] = (*registados, handler)


def handlers_de(event_type: str) -> tuple[Handler, ...]:
    """Os handlers subscritos a este tipo, ou um tuplo vazio.

    **Vazio não é erro**, e é o que o consumidor tem de tratar com mais cuidado:
    uma linha cujo tipo ninguém subscreve não se marca como processada e não
    desaparece. Ver o `apps/shared/consumidor.py`.
    """
    return _subscricoes.get(event_type, ())


def tipos_subscritos() -> tuple[str, ...]:
    """Os tipos com handler, ordenados. Para diagnóstico e para os testes.

    Serve a pergunta "este processo sabe reagir a quê?", que é a primeira que se
    faz quando um evento fica pendente — e é a pergunta que o worker de sete
    dias do defeito que originou esta feature respondia com um silêncio.
    """
    return tuple(sorted(_subscricoes))


@contextmanager
def subscricao(evento: type[DomainEvent] | str, handler: Handler) -> Iterator[None]:
    """Subscrição com o tempo de vida de um bloco. **Para os testes.**

    Retira o handler à saída, mesmo que o bloco levante. O registo é estado de
    módulo e sobrevive a um teste: sem isto, um handler encenado num teste corria
    em todos os seguintes.

    Restaura o estado anterior em vez de apagar a entrada: assim um bloco aberto
    sobre um tipo que já tinha handlers de produção não os leva com ele.
    """
    event_type = evento if isinstance(evento, str) else evento.event_type()
    antes = _subscricoes.get(event_type)
    subscrever(event_type, handler)
    try:
        yield
    finally:
        if antes is None:
            _subscricoes.pop(event_type, None)
        else:
            _subscricoes[event_type] = antes
