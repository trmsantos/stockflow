"""A fronteira da extração: os DTO que a atravessam e o porto que a liga.

Este ficheiro não fala com a base de dados e não importa `selectors.py` nem
`services.py` — é a camada mais baixa deste módulo depois do `models.py`, e é
isso que lhe permite ser importado pelos dois. O `api.py` reexporta tudo o que
está aqui; quem está **fora** do `purchasing` importa de lá e não daqui.

## Porque é que existe um porto, e não um import

O `DocumentoOut` da decisão 9 da ADR 0021 leva `state` e `extraction`, e os dois
dependem da **última chamada ao modelo** — que vive no `agents_extraction`, uma
tabela do `agents`. E o `purchasing` **não pode ler o `agents`**: o contrato
`purchasing só depende de inventory e catalog` do import-linter proíbe
`apps.purchasing -> apps.agents`, inclusive o `api.py`. A ADR é silenciosa sobre
isto — afirma "zero contratos novos no import-linter" e, na mesma página, um DTO
que precisa de uma aresta que não existe. O `CLAUDE.md` ganha (*"módulos só se
importam via `apps/<m>/api.py`"*), logo a aresta não se abre.

A aresta que **existe** é a contrária: `agents -> purchasing.api`. Logo a
dependência inverte-se — o `agents` registra-se aqui no arranque
(`AgentsConfig.ready()`) e o `purchasing` lê a extração por uma chamada a um
objecto cujo tipo conhece e cuja classe não importa. É a forma do adaptador, com
o grafo de imports a apontar para o lado que já estava declarado.

**O mecanismo certo era o evento.** Um `DocumentoFechado` na outbox resolvia isto
sem porto nenhum: o `purchasing` publicava, o `handlers.py` do `agents`
subscrevia, e nenhum dos dois conhecia o outro. Não há consumidor da outbox (ADR
0010, ADR 0020), logo um evento hoje significa que a extração **nunca corre**. A
condição para trocar o porto pelo evento é exactamente essa: **existir um
consumidor da outbox**. Enquanto não existir, é isto — um slot, com um nome, num
sítio.

Se nada se registar, o porto é `None`: o `purchasing` serve `extraction: null` e
um estado sem a metade da extração. Falha fechado e não levanta — um
estabelecimento não deve perder o ecrã dos documentos porque o módulo da extração
não arrancou.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "FronteiraDaExtracao",
    "LeituraDeDocumento",
    "LinhaLida",
    "PaginaDoDocumento",
    "fronteira_da_extracao",
    "ligar_fronteira_da_extracao",
]


# ---------------------------------------------------------------------------
# DTOs. Congelados e com `slots`, como os do `accounts.api`: o que atravessa a
# fronteira de um módulo não se muta do outro lado.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class PaginaDoDocumento:
    """Uma página, como quem está fora do `purchasing` a vê.

    `imagem` é o caminho relativo ao `MEDIA_ROOT` e está vazio enquanto não
    houver rasterização. `qr_payload` é o que o QR da fatura diz — a verdade do
    cabeçalho (ADR 0021, adenda) — e está vazio porque não há descodificador.

    Não leva bytes: quem precisar deles abre o caminho, e hoje ninguém precisa
    porque não há imagem nenhuma. No dia em que o `agents` chamar um modelo a
    sério, é aqui que se decide se ele recebe bytes ou um caminho — e a resposta
    certa é bytes, para o `agents` não ter de conhecer o armazenamento do
    `purchasing`.
    """

    id: UUID
    position: int
    file_page_number: int
    imagem: str
    qr_payload: str
    normalized: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class LinhaLida:
    """Uma linha **como o modelo a leu**, nunca como uma pessoa a confirmou.

    É a "zona do documento" da decisão 3 da ADR 0021 — `description` como vem
    impressa, a unidade impressa, a quantidade faturada, o preço, a taxa — e não
    tem um único campo que a revisão escreva. Na fatia 2 estes valores passam a
    ser colunas do `purchasing_receiptline` e este DTO deixa de ser preenchido
    pelo `agents`; a forma não muda, e é essa continuidade que justifica ele
    viver aqui e não lá.

    Dinheiro e quantidades são `Decimal`, nunca `float` (CLAUDE.md).
    """

    position: int
    description: str
    quantity: Decimal | None
    unit: str
    unit_price: Decimal | None
    vat_rate: Decimal | None
    line_total: Decimal | None
    confidence: Decimal | None


@dataclass(frozen=True, kw_only=True, slots=True)
class LeituraDeDocumento:
    """O resultado da última chamada ao modelo, para um documento.

    `state` é um `EstadoDaLeitura` (`apps/purchasing/models.py`) e é a metade que
    falta ao estado do documento. `desde` é o instante a partir do qual o relógio
    dos dez minutos conta — sem ele, uma tarefa morta deixava o documento em
    `a_extrair` para sempre.

    `motivo` é a razão legível de um `erro`, e existe porque um estado sem
    explicação manda alguém ler logs: *"não há modelo configurado"* responde à
    pergunta e `erro` sozinho não.

    O cabeçalho e as linhas ficam **vazios** quando o estado não é `lido`: é o
    que torna impossível servir um número que o modelo não disse.
    """

    state: str
    confidence: Decimal | None = None
    read_at: datetime | None = None
    desde: datetime | None = None
    motivo: str = ""
    supplier_name: str = ""
    supplier_nif: str = ""
    doc_type: str = ""
    doc_number: str = ""
    issued_at: date | None = None
    customer_nif: str = ""
    total: Decimal | None = None
    lines: tuple[LinhaLida, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# O porto — ver a secção no topo do ficheiro
# ---------------------------------------------------------------------------
@runtime_checkable
class FronteiraDaExtracao(Protocol):
    """O que o `purchasing` precisa do módulo que fala com o modelo.

    Duas operações, as duas direcções do mesmo trabalho:

    * `pedir` — enfileira a extração de um documento. É chamada de dentro de um
      serviço, e a implementação tem de usar `transaction.on_commit`: enfileirar
      antes do commit é publicar um facto que pode desaparecer;
    * `leituras` — a última leitura **de cada** documento pedido, em lote. Em
      lote porque a alternativa é uma query por linha na listagem, que é o N+1
      clássico a atravessar uma fronteira de módulo.
    """

    def pedir(self, *, tenant_id: UUID, documento_id: UUID) -> None:
        """Enfileira a extração deste documento, depois do commit."""
        ...

    def leituras(
        self, *, tenant_id: UUID, documento_ids: Sequence[UUID]
    ) -> Mapping[UUID, LeituraDeDocumento]:
        """A última leitura de cada documento que tenha alguma."""
        ...


#: O slot. Privado, e com um nome que se encontra num `grep`: é a única variável
#: mutável de módulo deste pacote, e a alternativa (um registo de N adaptadores)
#: era um mecanismo de plugins para um caso só.
_fronteira: FronteiraDaExtracao | None = None


def ligar_fronteira_da_extracao(fronteira: FronteiraDaExtracao) -> None:
    """Liga o adaptador da extração. Chamado uma vez, no `ready()` do `agents`.

    Idempotente por substituição: ligar duas vezes deixa o último, que é o que um
    `ready()` chamado mais de uma vez (acontece em caminhos de teste do Django)
    tem de fazer sem levantar.
    """
    global _fronteira
    _fronteira = fronteira


def fronteira_da_extracao() -> FronteiraDaExtracao | None:
    """O adaptador ligado, ou `None` se nenhum se registou.

    `None` é um caso legítimo e não um erro — ver o topo do ficheiro. Quem chama
    trata o `None`, e trata-o porque o tipo o obriga.
    """
    return _fronteira
