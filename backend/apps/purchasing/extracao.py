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

## O que o evento levou, e o que o porto ficou a fazer

Este ficheiro dizia, até 2026-10-08, que *"o mecanismo certo era o evento"* e que
a condição para trocar o porto por ele era **existir um consumidor da outbox**.
Existe (`apps/shared/consumidor.py`), e a troca está feita na metade em que fazia
sentido:

* **`pedir` saiu.** Era um aviso — *"este documento está pronto, lê-o"* —, e um
  aviso não precisa de saber quem o ouve. O `purchasing` publica
  `DocumentoFechado` (`events.py`) e o `apps/agents/handlers.py` subscreve-o.
  Nenhum dos dois conhece o outro, e a aresta de import que sobra é a mais fraca
  possível: `apps.purchasing.events`, um DTO sem dependências, em vez do `api.py`
  inteiro;
* **`leituras` ficou**, e não é inconsistência. É uma **pergunta** com resposta
  síncrona: o `DocumentoOut` precisa da última leitura de cada documento no
  instante em que serve a resposta HTTP, e um evento não responde a perguntas. É
  aqui que a inversão de dependência continua a ser necessária, e é só por ela
  que este porto continua a existir.

Se nada se registar, o porto é `None` — ver o parágrafo seguinte.

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
    "ConferenciaDeIva",
    "DivergenciaDoCabecalho",
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
    #: Os três campos que a ADR 0031 (decisão 5) acrescentou, cada um com coluna
    #: à espera no `purchasing_receiptline`: sem `supplier_code`/`ean` a memória
    #: do match não existe e cada fatura é a primeira; sem `discount_pct` o custo
    #: derivaria do preço bruto, que é o bug clássico desta família. Com default
    #: porque uma fatura que não os imprime continua a ser uma leitura legítima.
    supplier_code: str = ""
    ean: str = ""
    discount_pct: Decimal | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class DivergenciaDoCabecalho:
    """Um campo em que o papel lido pelo modelo e o QR não dizem o mesmo.

    Guarda-se e mostra-se (*"o papel diz X, o QR diz Y"*), nunca se esconde: o
    QR ganha no valor servido, e a divergência é a prova de que ele ganhou. Uma
    divergência grande é quase sempre a fotografia de **dois** papéis
    diferentes, ou um QR de outro documento — e isso é exactamente o que uma
    pessoa tem de ver antes de dar entrada a mercadoria.

    As três colunas são texto porque isto é para ler: um `Decimal` e uma `date`
    já vêm formatados de quem os compara.
    """

    campo: str
    papel: str
    qr: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ConferenciaDeIva:
    """A soma das linhas lidas numa taxa, contra a base dessa taxa no QR.

    É a melhor validação que esta feature tem de graça (ADR 0031): o QR é gerado
    por software certificado e traz a base tributável por taxa; as linhas são
    leitura de um modelo. Se as duas somas batem, as linhas daquela taxa estão
    quase de certeza bem lidas — e isso vale mais do que qualquer `confidence`
    auto-reportada.

    `base_qr` é `None` quando o QR não tem escalão nenhum com aquela taxa, que é
    o caso de uma taxa que o modelo leu mal (ou de um documento sem QR).
    """

    vat_rate: Decimal
    base_lida: Decimal
    base_qr: Decimal | None
    diferenca: Decimal | None
    bate: bool


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

    ## O cabeçalho pode não ser do modelo, e isso é a decisão com mais valor

    Quando o QR da fatura é legível, **ganha sempre** no cabeçalho (ADR 0031,
    decisão C): é gerado por software certificado e não passa por OCR nenhum.
    Os campos continuam a chamar-se o mesmo — o que muda é a **fonte**, e
    `qr_lido` é como quem lê sabe qual foi. Ao modelo ficam as linhas, o nome e
    a morada do fornecedor, e as referências a guias.

    `tentativa` é o `attempt` da linha de extração: é o que o endpoint de
    re-extração compara com `AGENTS_EXTRACTION_MAX_ATTEMPTS` sem ter de ler uma
    tabela de outro módulo.
    """

    state: str
    confidence: Decimal | None = None
    read_at: datetime | None = None
    desde: datetime | None = None
    motivo: str = ""
    tentativa: int = 0
    supplier_name: str = ""
    supplier_nif: str = ""
    doc_type: str = ""
    doc_number: str = ""
    issued_at: date | None = None
    customer_nif: str = ""
    total: Decimal | None = None
    atcud: str = ""
    fiscal_space: str = ""
    #: O QR desta fatura foi lido e descodificado? É o que distingue um
    #: cabeçalho certificado de um cabeçalho que saiu de uma fotografia.
    qr_lido: bool = False
    #: `E=A` no QR: documento **anulado**. Recusa, não aviso (ADR 0021, adenda).
    anulado: bool = False
    divergencias: tuple[DivergenciaDoCabecalho, ...] = field(default_factory=tuple)
    iva_por_taxa: tuple[ConferenciaDeIva, ...] = field(default_factory=tuple)
    lines: tuple[LinhaLida, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# O porto — ver a secção no topo do ficheiro
# ---------------------------------------------------------------------------
@runtime_checkable
class FronteiraDaExtracao(Protocol):
    """O que o `purchasing` precisa do módulo que fala com o modelo.

    **Uma** operação, desde que o `pedir` saiu para a outbox (ver o topo do
    ficheiro): `leituras` — a última leitura **de cada** documento pedido, em
    lote. Em lote porque a alternativa é uma query por linha na listagem, que é o
    N+1 clássico a atravessar uma fronteira de módulo.

    Um `Protocol` de um método só continua a valer a pena: o que ele compra não é
    a contagem de métodos, é o `purchasing` não importar o `agents` — e a
    substituição por um cliente HTTP no dia em que o `agents` sair para serviço
    próprio (ARCHITECTURE.md §7) fica a ser uma classe, aqui nomeada.
    """

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

    Idempotente **para o mesmo adaptador**: ligar duas vezes o mesmo objecto não
    faz nada, que é o que um `ready()` chamado mais de uma vez (acontece em
    caminhos de teste do Django) tem de fazer sem levantar.

    Ligar um adaptador **diferente** levanta, e isso é deliberado: esta função é
    pública no `api.py`, logo qualquer módulo com aresta para `purchasing.api`
    lhe pode chamar, e uma substituição silenciosa trocava quem lê as faturas sem
    deixar rasto. Para um caso só — o `agents` — o custo de recusar é uma linha.
    """
    global _fronteira
    if _fronteira is not None and _fronteira is not fronteira:
        raise RuntimeError(
            "já há uma fronteira de extração ligada, e esta é outra. Substituir "
            "em silêncio trocaria quem lê as faturas sem deixar rasto."
        )
    _fronteira = fronteira


def fronteira_da_extracao() -> FronteiraDaExtracao | None:
    """O adaptador ligado, ou `None` se nenhum se registou.

    `None` é um caso legítimo e não um erro — ver o topo do ficheiro. Quem chama
    trata o `None`, e trata-o porque o tipo o obriga.
    """
    return _fronteira
