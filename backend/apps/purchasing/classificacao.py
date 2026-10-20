"""O que é cada linha lida, e o que nela merece um olhar. **Puro e nosso.**

Duas derivações, nenhuma delas pedida ao modelo e nenhuma delas guardada numa
coluna nova:

1. **a espécie da linha** (`goods` · `deposit` · `charge` · `document_ref`) —
   derivada por palavras na descrição. O `kind` **não entra no schema** da
   extração (ADR 0031, B) de propósito: pedi-lo ao modelo era deixá-lo
   classificar, e uma classificação errada muda o sinal do dinheiro no painel
   (ADR 0014). Portes e vasilhame **copiam-se como linhas normais** porque são
   faturados; o que decide o que eles são somos nós;
2. **os avisos da linha** — marcação, nunca correcção. Cada um é uma
   desconfiança sobre um número que **não se altera**: `quantity × unit_price`
   fora de `line_total ± 0,02 €`, uma taxa fora do conjunto conhecido, um campo
   em falta, um preço desviado do último do mesmo (fornecedor, código), uma
   confiança baixa. A linha fica como o papel a imprimiu e a pessoa decide.

Puro: nem base de dados, nem settings, nem relógio. É isso que faz os avisos
serem **derivados à leitura** em vez de uma coluna — a ADR 0031 não traz
migração nenhuma, e um aviso guardado era um valor a envelhecer mal (o preço de
referência muda com a fatura seguinte).

## Porque é que a confiança é só mais um aviso

Porque é um número auto-reportado por um modelo, calibrado por nada. **Nunca
bloqueia nada** (ADR 0031, decisão 4): não auto-confirma, não se soma, não se
medeia, não sai como métrica. Marca e ordena atenção, e o limiar é uma hipótese
configurável (`AGENTS_EXTRACTION_CONFIDENCE_THRESHOLD`). `None` e `0.000` são
estados distintos e o código trata-os como tal: `None` é "o modelo não disse" e
`0.000` é "o modelo disse que não confia nada".
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal

__all__ = [
    "AVISO_CONFIANCA_BAIXA",
    "AVISO_PRECO_DESVIADO",
    "AVISO_SEM_CONVERSAO",
    "AVISO_SEM_QUANTIDADE",
    "AVISO_SEM_TAXA",
    "AVISO_TAXA_DESCONHECIDA",
    "AVISO_TOTAL_NAO_BATE",
    "AVISOS",
    "DESVIO_DE_PRECO",
    "ESPECIE_CHARGE",
    "ESPECIE_DEPOSIT",
    "ESPECIE_DOCUMENT_REF",
    "ESPECIE_GOODS",
    "TAXAS_CONHECIDAS",
    "TOLERANCIA_DA_LINHA",
    "avisos_da_linha",
    "e_linha_de_continuacao",
    "especie_da_linha",
]

ESPECIE_GOODS = "goods"
ESPECIE_DEPOSIT = "deposit"
ESPECIE_CHARGE = "charge"
ESPECIE_DOCUMENT_REF = "document_ref"

#: Vasilhame: embalagem retornável cuja devolução foi convencionada. **Não é
#: custo e não é compra** (ADR 0021, adenda: está fora da base tributável, que é
#: a razão de a linha de tara vir sem IVA), e não gera movimento nenhum.
_PALAVRAS_DE_DEPOSITO = (
    "vasilhame",
    "tara",
    "casco",
    "grade",
    "grades",
    "caixa retornavel",
    "caixas retornaveis",
    "palete retornavel",
    "barril",
)

#: Encargos: faturados, sem mercadoria por trás. O desconto de rodapé entra aqui
#: com `line_total` negativo e **não se rateia** pelas linhas (ADR 0031, D) — a
#: consequência, dita e não escondida, é o custo médio ficar ligeiramente acima
#: do real.
_PALAVRAS_DE_ENCARGO = (
    "portes",
    "porte",
    "transporte",
    "frete",
    "taxa de servico",
    "despesas",
    "desconto",
    "descontos",
    "arredondamento",
    "eco taxa",
    "ecotaxa",
    "taxa ambiental",
)

#: Referência a outro documento: a fatura de fim de mês que liquida guias não
#: repete as linhas — imprime `"GUIA 4471 DE 06/10/2026"`, quantidade 1, com um
#: valor. Isso não é uma linha de produto (ADR 0021, adenda).
_PALAVRAS_DE_REFERENCIA = (
    "guia de remessa",
    "guia nr",
    "guia n",
    "guia ",
    "n/ guia",
    "v/ guia",
    "nossa guia",
    "vossa guia",
)

#: As taxas de IVA em vigor nos três espaços fiscais portugueses, mais o zero da
#: isenção e da autoliquidação. **Não é validação**: uma taxa fora desta lista
#: valida na mesma e sai **marcada** — o papel ganha sempre (ADR 0021, adenda), e
#: recusar uma taxa que não antecipámos era recusar uma fatura verdadeira.
TAXAS_CONHECIDAS: frozenset[Decimal] = frozenset(
    Decimal(valor) for valor in (0, 4, 5, 6, 9, 12, 13, 16, 22, 23)
)

#: A tolerância de `quantity × unit_price` contra `line_total`. Dois cêntimos: é
#: o arredondamento legítimo de uma linha, e a adenda da ADR 0021 usa o mesmo
#: número para o IVA por taxa.
TOLERANCIA_DA_LINHA = Decimal("0.02")

#: Quanto um preço pode desviar-se do último do mesmo (fornecedor, código) antes
#: de ser marcado. 30 % é **hipótese** e não medição: é largo o suficiente para
#: não marcar a inflação de um trimestre e apertado o suficiente para apanhar um
#: dígito a mais.
DESVIO_DE_PRECO = Decimal("0.30")

AVISO_TOTAL_NAO_BATE = "total_nao_bate"
AVISO_TAXA_DESCONHECIDA = "taxa_desconhecida"
AVISO_SEM_TAXA = "sem_taxa"
AVISO_SEM_QUANTIDADE = "sem_quantidade"
AVISO_SEM_CONVERSAO = "sem_conversao"
AVISO_PRECO_DESVIADO = "preco_desviado"
AVISO_CONFIANCA_BAIXA = "confianca_baixa"

#: A lista fechada, para o `ChoiceField` do serializer e para o `types.ts` sair
#: como união: um aviso novo é um diff no contrato, não uma string solta.
AVISOS: tuple[str, ...] = (
    AVISO_TOTAL_NAO_BATE,
    AVISO_TAXA_DESCONHECIDA,
    AVISO_SEM_TAXA,
    AVISO_SEM_QUANTIDADE,
    AVISO_SEM_CONVERSAO,
    AVISO_PRECO_DESVIADO,
    AVISO_CONFIANCA_BAIXA,
)


#: As linhas que **não** são linhas: o arrasto de uma fatura de várias folhas.
#: O prompt manda deitá-las fora (ADR 0031, B) e esta lista é a segunda rede —
#: copiá-las duplica o documento, e um documento duplicado duplica o stock e
#: duplica as compras, e descobre-se semanas depois numa contagem.
_PALAVRAS_DE_CONTINUACAO = (
    "a transportar",
    "transporte da pagina",
    "transporte de pagina",
    "transporte anterior",
    "da pagina anterior",
    "subtotal",
    "sub-total",
    "sub total",
    "continua",
    "total da pagina",
    "soma a transportar",
)


def e_linha_de_continuacao(
    descricao: str, *, quantity: Decimal | None, unit_price: Decimal | None
) -> bool:
    """Isto é um arrasto de folha e não mercadoria?

    **As duas condições juntas**, nunca só a palavra: a descrição tem de ser uma
    das formas conhecidas **e** a linha não pode ter quantidade nem preço
    unitário — é essa a assinatura de um subtotal, e é o que impede um artigo
    chamado "TRANSPORTE ESCOLAR 1L" de desaparecer de uma fatura.

    O `transporte` que **é** faturado (portes) tem preço unitário, logo cai do
    lado certo e entra como linha `charge`.
    """
    if quantity is not None or unit_price is not None:
        return False
    texto = _sem_acentos(descricao).strip()
    return any(palavra in texto for palavra in _PALAVRAS_DE_CONTINUACAO)


def _sem_acentos(texto: str) -> str:
    """Minúsculas e sem acentos: `"Descontos"`, `"DESCONTO"` e `"desconto"` são um."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in decomposto if not unicodedata.combining(ch)).lower()


def especie_da_linha(descricao: str, *, line_total: Decimal | None = None) -> str:
    """A espécie de uma linha lida, derivada da descrição. `goods` por omissão.

    A ordem das perguntas é a precedência, e `goods` é o fim da linha: na dúvida
    é mercadoria, porque é a espécie que a revisão humana olha com mais atenção
    e a única que pode gerar movimento.

    Um `line_total` **negativo** numa linha que daria `goods` passa a `charge`:
    quantidades e dinheiro guardam-se positivos em todos os tipos e o sinal é do
    `doc_type` (ADR 0022), logo uma mercadoria negativa não existe — o que
    existe é um desconto que veio no meio das linhas.
    """
    texto = _sem_acentos(descricao)
    if any(palavra in texto for palavra in _PALAVRAS_DE_REFERENCIA):
        return ESPECIE_DOCUMENT_REF
    if any(palavra in texto for palavra in _PALAVRAS_DE_DEPOSITO):
        return ESPECIE_DEPOSIT
    if any(palavra in texto for palavra in _PALAVRAS_DE_ENCARGO):
        return ESPECIE_CHARGE
    if line_total is not None and line_total < 0:
        return ESPECIE_CHARGE
    return ESPECIE_GOODS


def avisos_da_linha(
    *,
    kind: str,
    quantity_invoiced: Decimal | None,
    unit_price: Decimal | None,
    line_total: Decimal | None,
    vat_rate: Decimal | None,
    base_per_invoice_unit: Decimal | None,
    extraction_confidence: Decimal | None,
    limiar_de_confianca: Decimal,
    preco_de_referencia: Decimal | None = None,
) -> tuple[str, ...]:
    """O que nesta linha merece um olhar. **Nunca altera nada.**

    Devolve códigos de uma lista fechada, pela ordem em que importam. Um aviso
    não impede a confirmação de coisa nenhuma — o portão é humano e já existe —,
    e nenhum deles corrige um número: a aritmética do papel é a do papel, e um
    total que não bate é informação sobre a leitura, não um erro a emendar.
    """
    avisos: list[str] = []

    if (
        quantity_invoiced is not None
        and unit_price is not None
        and line_total is not None
        and abs(quantity_invoiced * unit_price - line_total) > TOLERANCIA_DA_LINHA
    ):
        avisos.append(AVISO_TOTAL_NAO_BATE)

    if vat_rate is None:
        avisos.append(AVISO_SEM_TAXA)
    elif vat_rate not in TAXAS_CONHECIDAS:
        avisos.append(AVISO_TAXA_DESCONHECIDA)

    if kind == ESPECIE_GOODS:
        if quantity_invoiced is None:
            avisos.append(AVISO_SEM_QUANTIDADE)
        if base_per_invoice_unit is None:
            avisos.append(AVISO_SEM_CONVERSAO)

    if (
        preco_de_referencia is not None
        and preco_de_referencia > 0
        and unit_price is not None
        and abs(unit_price - preco_de_referencia) / preco_de_referencia > DESVIO_DE_PRECO
    ):
        avisos.append(AVISO_PRECO_DESVIADO)

    # `None` e `0.000` são estados distintos: o primeiro é "o modelo não disse"
    # e não se marca (marcá-lo enchia de avisos uma leitura inteira sem
    # confiança), o segundo é uma confiança a sério, e baixa.
    if extraction_confidence is not None and extraction_confidence < limiar_de_confianca:
        avisos.append(AVISO_CONFIANCA_BAIXA)

    return tuple(avisos)
