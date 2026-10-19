"""O QR da fatura portuguesa: o que ele diz, e porque é que ganha ao modelo.

Desde 1/1/2023 toda a fatura emitida em Portugal imprime um código QR gerado
pelo **software certificado** que a emitiu. O que ele traz, legível por máquina e
**sem erro de OCR**: os dois NIF, o tipo de documento, o estado (normal ou
anulado), a data, a identificação do documento, o ATCUD, o espaço fiscal
(`PT` · `PT-AC` · `PT-MA`), as bases e o IVA por taxa, e o total. O que ele
**não** traz são as linhas.

Logo a divisão do trabalho é esta, e é a decisão com mais valor desta fatia
(ADR 0021 adenda; ADR 0031, C): **o QR é a verdade do cabeçalho e o modelo só
serve para as linhas** — mais o nome e a morada do fornecedor e as referências a
guias, que o QR não tem.

## Três consequências, e nenhuma é um aviso

1. **O QR ganha sempre.** Um NIF lido por um modelo a partir de uma fotografia
   tremida contra um NIF assinado por software certificado não é uma comparação
   entre iguais. O valor servido é o do QR;
2. **a divergência guarda-se e mostra-se.** "O papel diz X, o QR diz Y" é
   informação, não ruído: uma divergência grande quer dizer que a fotografia tem
   dois papéis, ou que o QR é de outro documento, e isso descobre-se **antes** de
   dar entrada a mercadoria e não numa contagem três semanas depois;
3. **`E=A` é recusa.** Um documento anulado não dá entrada a nada. Não é um
   aviso com um botão por baixo — é uma recusa.

E a validação que isto compra de graça: **Σ das linhas lidas por taxa contra a
base por taxa do QR**. Vale mais do que a `confidence` que o modelo reporta de si
próprio, porque é uma comparação entre duas fontes independentes.

## O formato, e o que este ficheiro não faz

O payload é uma lista de `chave:valor` separada por `*`, com as chaves da
especificação da AT (`A` emitente, `B` adquirente, `D` tipo, `E` estado, `F`
data, `G` nº do documento, `H` ATCUD, `I1` espaço fiscal, `I2..I8`/`J*`/`K*` as
bases e o IVA por escalão, `N` total de impostos, `O` total). Chaves que não
conhecemos são **ignoradas em silêncio**: a especificação cresce e um campo novo
não pode partir a leitura de uma fatura.

Este ficheiro **não descodifica a imagem do QR** — isso é uma dependência que
ainda não está escolhida (ADR 0021, adenda), e a coluna
`purchasing_documentpage.qr_payload` fica vazia até lá. O que está aqui é a
leitura do texto já descodificado, que é pura, determinística e testável sem
imagem nenhuma.

Puro: não toca na base de dados e não importa `models.py`. É isso que lhe permite
ser usado pelos selectors **e** pelos serviços sem inverter nada.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.purchasing.extracao import (
    ConferenciaDeIva,
    DivergenciaDoCabecalho,
    LeituraDeDocumento,
)

__all__ = [
    "ESTADO_ANULADO",
    "TAXAS_POR_ESPACO",
    "TOLERANCIA_POR_TAXA",
    "CabecalhoDoQR",
    "aplicar_qr",
    "bases_por_taxa",
    "ler_qr",
]

#: O valor do campo `E` que diz que o documento foi **anulado**. Os outros
#: estados da especificação (`N` normal, `F` facturado, `R` autofacturação) não
#: recusam nada.
ESTADO_ANULADO = "A"

#: As taxas de cada escalão por espaço fiscal. **Não é um conjunto fixo de
#: taxas** (ADR 0021, adenda): o Continente é 6/13/23, a Madeira 5/12/22 e os
#: Açores 4/9/16, e é o campo `I1` do QR que decide qual. Sem QR não se sabe o
#: espaço, e aí a verificação por taxa simplesmente não acontece.
TAXAS_POR_ESPACO: dict[str, dict[str, Decimal]] = {
    "PT": {"reduzida": Decimal("6"), "intermedia": Decimal("13"), "normal": Decimal("23")},
    "PT-AC": {"reduzida": Decimal("4"), "intermedia": Decimal("9"), "normal": Decimal("16")},
    "PT-MA": {"reduzida": Decimal("5"), "intermedia": Decimal("12"), "normal": Decimal("22")},
}

#: A tolerância de base por taxa, em euros. ±0,02 € fixos **mais** um cêntimo por
#: linha daquela taxa: um rolo de trinta linhas do Makro acumula arredondamentos
#: e falharia sempre por um cêntimo com uma tolerância constante (ADR 0021,
#: adenda: *"algo que escale no total"*).
TOLERANCIA_POR_TAXA = Decimal("0.02")
TOLERANCIA_POR_LINHA = Decimal("0.01")

#: Os prefixos das bases/IVA por espaço fiscal, e o escalão de cada par.
#: `I2`/`J2`/`K2` é a base isenta (taxa 0), e os pares seguintes são
#: (base, IVA) de cada escalão. Fechado: uma chave nova da AT é um diff.
_PREFIXO_DO_ESPACO = {"PT": "I", "PT-AC": "J", "PT-MA": "K"}
_ESCALOES = (("reduzida", "3", "4"), ("intermedia", "5", "6"), ("normal", "7", "8"))


@dataclass(frozen=True, kw_only=True, slots=True)
class CabecalhoDoQR:
    """O cabeçalho de uma fatura, tal como o software certificado o assinou.

    Todos os campos são opcionais na forma (string vazia, `None`): um QR
    truncado por uma dobra no papel lê-se até onde dá, e o que falta cai para o
    que o modelo leu. O que **nunca** acontece é inventar-se um valor.
    """

    supplier_nif: str = ""
    customer_nif: str = ""
    doc_type: str = ""
    estado: str = ""
    issued_at: date | None = None
    doc_number: str = ""
    atcud: str = ""
    fiscal_space: str = ""
    total: Decimal | None = None
    total_iva: Decimal | None = None
    #: Base tributável por taxa, já resolvida pelo espaço fiscal. A taxa 0 é a
    #: base isenta, que é o que uma aquisição intracomunitária com
    #: autoliquidação imprime.
    bases: tuple[tuple[Decimal, Decimal], ...] = ()

    @property
    def anulado(self) -> bool:
        """`E=A`: o documento foi anulado. Recusa, não aviso."""
        return self.estado == ESTADO_ANULADO


#: O maior valor que cabe nas colunas de dinheiro (`Decimal(12,2)`). Um QR é
#: texto de fora: um número maior do que isto não é um total, é lixo — e seria
#: um `DataError` do Postgres no momento de criar a receção.
_DINHEIRO_MAXIMO = Decimal("9999999999.99")

#: O comprimento de cada campo, igual ao da coluna que o vai receber. Cortar
#: aqui, na fronteira, é o que impede um QR dobrado ou forjado de rebentar uma
#: escrita três ficheiros à frente.
_LIMITES = {
    "A": 20,
    "B": 20,
    "D": 20,
    "E": 1,
    "G": 100,
    "H": 50,
    "I1": 5,
}


def _decimal(texto: str) -> Decimal | None:
    """Um número do QR como `Decimal`, ou `None` se não for um número plausível.

    A especificação manda ponto decimal; aceita-se a vírgula porque um emissor
    distraído a põe e o valor continua a ser legível. Nunca `float`: isto é
    dinheiro (CLAUDE.md). Um valor fora do que cabe numa coluna de dinheiro é
    `None` — não há total nenhum, que é melhor do que um total absurdo.
    """
    try:
        valor = Decimal(texto.strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not valor.is_finite() or abs(valor) > _DINHEIRO_MAXIMO:
        return None
    return valor.quantize(Decimal("0.01"))


def _data(texto: str) -> date | None:
    """`AAAAMMDD` como `date`, ou `None`. Formato único e sem ambiguidade."""
    try:
        return datetime.strptime(texto.strip(), "%Y%m%d").date()
    except ValueError:
        return None


def ler_qr(payload: str | None) -> CabecalhoDoQR | None:
    """O cabeçalho que o QR diz, ou `None` se não houver QR que se leia.

    `None` em três casos que de fora são o mesmo — *não há cabeçalho
    certificado*: a coluna está vazia, o texto não tem a forma `chave:valor*…`,
    ou não traz nenhum dos campos que interessam. Quem chama trata o `None`
    servindo o que o modelo leu, que é o caminho de hoje.
    """
    if not payload:
        return None
    campos: dict[str, str] = {}
    for parte in payload.split("*"):
        chave, separador, valor = parte.partition(":")
        if not separador:
            continue
        nome = chave.strip().upper()
        campos[nome] = valor.strip()[: _LIMITES.get(nome, 200)]
    if not campos:
        return None

    espaco = campos.get("I1", "")
    cabecalho = CabecalhoDoQR(
        supplier_nif=campos.get("A", ""),
        customer_nif=campos.get("B", ""),
        doc_type=campos.get("D", ""),
        estado=campos.get("E", ""),
        issued_at=_data(campos.get("F", "")),
        doc_number=campos.get("G", ""),
        atcud=campos.get("H", ""),
        fiscal_space=espaco,
        total=_decimal(campos.get("O", "")),
        total_iva=_decimal(campos.get("N", "")),
        bases=_bases(campos, espaco),
    )
    # Um texto qualquer com dois pontos lá dentro não é um QR de fatura. O que
    # torna isto um cabeçalho é ter pelo menos o NIF do emitente ou o ATCUD —
    # os dois campos que nenhum outro texto traz por acaso.
    if not cabecalho.supplier_nif and not cabecalho.atcud:
        return None
    return cabecalho


def _bases(campos: dict[str, str], espaco: str) -> tuple[tuple[Decimal, Decimal], ...]:
    """As bases tributáveis por taxa, resolvidas pelo espaço fiscal do QR."""
    prefixo = _PREFIXO_DO_ESPACO.get(espaco)
    taxas = TAXAS_POR_ESPACO.get(espaco)
    if prefixo is None or taxas is None:
        return ()
    bases: list[tuple[Decimal, Decimal]] = []
    isenta = _decimal(campos.get(f"{prefixo}2", ""))
    if isenta is not None:
        bases.append((Decimal("0"), isenta))
    for escalao, sufixo_base, _sufixo_iva in _ESCALOES:
        base = _decimal(campos.get(f"{prefixo}{sufixo_base}", ""))
        if base is not None:
            bases.append((taxas[escalao], base))
    return tuple(bases)


def bases_por_taxa(cabecalho: CabecalhoDoQR) -> dict[Decimal, Decimal]:
    """As bases do QR num mapa taxa → base, para comparar com as linhas."""
    return dict(cabecalho.bases)


def _divergencia(campo: str, papel: object, qr: object) -> DivergenciaDoCabecalho | None:
    """Uma divergência, ou `None` se os dois dizem o mesmo (ou o papel cala-se).

    Um campo que o modelo não leu **não é** uma divergência: é uma ausência que
    o QR preenche, e enchê-la de avisos faz quem revê deixar de os ler.
    """
    if papel in (None, ""):
        return None
    if qr in (None, ""):
        return None
    if str(papel).strip() == str(qr).strip():
        return None
    return DivergenciaDoCabecalho(campo=campo, papel=str(papel), qr=str(qr))


def _conferencia(
    leitura: LeituraDeDocumento, cabecalho: CabecalhoDoQR
) -> tuple[ConferenciaDeIva, ...]:
    """Σ das linhas lidas por taxa contra a base por taxa do QR.

    As linhas sem taxa lida ficam de fora da soma — somá-las numa taxa qualquer
    era inventar o facto que falta. As taxas que o QR tem e as linhas não
    aparecem na mesma, com `base_lida` a zero: é esse o caso que diz "faltam
    linhas", que é o erro mais caro de uma extração.
    """
    do_qr = bases_por_taxa(cabecalho)
    somas: dict[Decimal, Decimal] = {}
    quantas: dict[Decimal, int] = {}
    for linha in leitura.lines:
        if linha.vat_rate is None or linha.line_total is None:
            continue
        taxa = Decimal(linha.vat_rate)
        somas[taxa] = somas.get(taxa, Decimal("0")) + Decimal(linha.line_total)
        quantas[taxa] = quantas.get(taxa, 0) + 1
    if not do_qr:
        return ()
    conferencias: list[ConferenciaDeIva] = []
    for taxa in sorted(set(somas) | set(do_qr)):
        lida = somas.get(taxa, Decimal("0"))
        base = do_qr.get(taxa)
        if base is None:
            conferencias.append(
                ConferenciaDeIva(
                    vat_rate=taxa,
                    base_lida=lida,
                    base_qr=None,
                    diferenca=None,
                    bate=False,
                )
            )
            continue
        diferenca = lida - base
        tolerancia = TOLERANCIA_POR_TAXA + TOLERANCIA_POR_LINHA * quantas.get(taxa, 0)
        conferencias.append(
            ConferenciaDeIva(
                vat_rate=taxa,
                base_lida=lida,
                base_qr=base,
                diferenca=diferenca,
                bate=abs(diferenca) <= tolerancia,
            )
        )
    return tuple(conferencias)


def aplicar_qr(leitura: LeituraDeDocumento, payload: str | None) -> LeituraDeDocumento:
    """A leitura com o cabeçalho do QR por cima, e as divergências à vista.

    Sem QR legível devolve a leitura **tal como está** — é o caminho de hoje,
    enquanto a biblioteca que descodifica a imagem não for escolhida. Com QR, os
    campos do cabeçalho passam a ser os dele; o que o modelo tinha lá e não bate
    fica em `divergencias`, e as linhas **nunca** se tocam: o QR não as tem.
    """
    cabecalho = ler_qr(payload)
    if cabecalho is None:
        return leitura

    divergencias = [
        divergencia
        for divergencia in (
            _divergencia("supplier_nif", leitura.supplier_nif, cabecalho.supplier_nif),
            _divergencia("customer_nif", leitura.customer_nif, cabecalho.customer_nif),
            _divergencia("doc_type", leitura.doc_type, cabecalho.doc_type),
            _divergencia("doc_number", leitura.doc_number, cabecalho.doc_number),
            _divergencia("issued_at", leitura.issued_at, cabecalho.issued_at),
            _divergencia("total", leitura.total, cabecalho.total),
        )
        if divergencia is not None
    ]
    return replace(
        leitura,
        supplier_nif=cabecalho.supplier_nif or leitura.supplier_nif,
        customer_nif=cabecalho.customer_nif or leitura.customer_nif,
        doc_type=cabecalho.doc_type or leitura.doc_type,
        doc_number=cabecalho.doc_number or leitura.doc_number,
        issued_at=cabecalho.issued_at or leitura.issued_at,
        total=cabecalho.total if cabecalho.total is not None else leitura.total,
        atcud=cabecalho.atcud,
        fiscal_space=cabecalho.fiscal_space,
        qr_lido=True,
        anulado=cabecalho.anulado,
        divergencias=tuple(divergencias),
        iva_por_taxa=_conferencia(leitura, cabecalho),
    )
