"""A tabela fechada de unidades, e a conversão para a unidade base (ADR 0022, §4.3).

Três dimensões e três unidades base — massa em `g`, volume em `ml`, contagem em
`un` — e uma lista **fechada** de sinónimos por dimensão, tal como o
`domain-expert` a emendou: KG→g ×1000, CL→ml ×10, DZ→un ×12. O que não está na
lista **não é unidade**: `CX`, `SC`, `SACO`, `EMB`, `PCT`, `GRD`, `BLOCO`, `ROLO`
são embalagens (`ProductPackaging`) ou unidades de apresentação de um artigo, e
nunca um factor implícito. *"Nunca 1 por omissão"* — a conversão em falta é uma
recusa, não um palpite.

Sem remoção genérica de plurais: cada forma aceite está escrita. É o que torna a
lista auditável — e é por isso que ela vive numa constante de módulo e não numa
tabela, porque um sinónimo novo é um diff visível e não uma linha que alguém
inseriu num `admin`.

## Normalizar, e depois procurar

`normalizar_unidade` é a única forma canónica: NFKD sem acentos, maiúsculas, sem
espaços, sem ponto final. É o que faz `"Pç"`, `"PÇ."` e `"pc"` serem a mesma
chave, e é também a chave com que o `catalog_supplierproductcode.invoice_unit`
é guardado e comparado ao semear uma receção (§4.1).

Nenhuma destas funções toca na base de dados: são puras, e é por isso que o
`api.py` as reexporta sem invólucro para o `purchasing` as usar em `rever_linha`.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from types import MappingProxyType

from django.utils.translation import gettext_lazy as _

__all__ = [
    "DIMENSAO_DA_BASE",
    "FACTORES",
    "ApresentacaoIncoerente",
    "dimensao_da_unidade",
    "factor_para_base",
    "normalizar_unidade",
    "verificar_apresentacao",
]

#: A dimensão de cada unidade base. As chaves são os valores de
#: `models.UnidadeBase`; estão aqui em literal para este módulo não importar o
#: `models.py` — é puro de propósito.
DIMENSAO_DA_BASE: MappingProxyType[str, str] = MappingProxyType(
    {"g": "massa", "ml": "volume", "un": "contagem"}
)

#: A tabela fechada: dimensão → {sinónimo normalizado → factor para a base}.
#: As formas com acento e cedilha (`PÇ`, `PEÇA`, `DÚZIA`) **não** estão aqui
#: porque a normalização as reduz a estas; o teste exaustivo afirma que chegam
#: cá. Os factores são `Decimal` porque é `Decimal` que sai daqui para uma
#: quantidade de stock, e um `int` multiplicado por um `Decimal` dá `Decimal`,
#: mas um `float` nunca entra nesta cadeia (CLAUDE.md).
FACTORES: MappingProxyType[str, MappingProxyType[str, Decimal]] = MappingProxyType(
    {
        "massa": MappingProxyType(
            {
                "G": Decimal(1),
                "GR": Decimal(1),
                "GRS": Decimal(1),
                "GRAMA": Decimal(1),
                "GRAMAS": Decimal(1),
                "KG": Decimal(1000),
                "KGS": Decimal(1000),
                "KILO": Decimal(1000),
                "QUILO": Decimal(1000),
                "QUILOS": Decimal(1000),
            }
        ),
        "volume": MappingProxyType(
            {
                "ML": Decimal(1),
                "CL": Decimal(10),
                "L": Decimal(1000),
                "LT": Decimal(1000),
                "LTR": Decimal(1000),
                "LITRO": Decimal(1000),
                "LITROS": Decimal(1000),
            }
        ),
        "contagem": MappingProxyType(
            {
                "UN": Decimal(1),
                "UNI": Decimal(1),
                "UND": Decimal(1),
                "UNID": Decimal(1),
                "UNIDADE": Decimal(1),
                "UNIDADES": Decimal(1),
                "PC": Decimal(1),
                "PCS": Decimal(1),
                "PECA": Decimal(1),
                "PECAS": Decimal(1),
                "DZ": Decimal(12),
                "DUZIA": Decimal(12),
            }
        ),
    }
)

#: O índice inverso, construído uma vez: sinónimo normalizado → (dimensão, factor).
_POR_SINONIMO: MappingProxyType[str, tuple[str, Decimal]] = MappingProxyType(
    {
        sinonimo: (dimensao, factor)
        for dimensao, tabela in FACTORES.items()
        for sinonimo, factor in tabela.items()
    }
)


class ApresentacaoIncoerente(ValueError):
    """`display_unit` e `display_factor` não se podem contradizer, nem contradizer a base.

    Leva o `campo` a que a recusa pertence (`display_unit` ou `display_factor`)
    para o serializer a pôr debaixo do campo certo, e a `mensagem` já traduzível.
    """

    def __init__(self, campo: str, mensagem: object) -> None:
        super().__init__(str(mensagem))
        self.campo = campo
        self.mensagem = mensagem


def normalizar_unidade(texto: str | None) -> str:
    """A forma canónica de uma unidade como vem impressa numa fatura.

    NFKD e remoção das marcas combinadas (acentos, cedilha), maiúsculas, sem
    espaços nenhuns, e sem ponto final — `"kg."`, `" Kg "` e `"KG"` são a mesma
    coisa. Não valida: `"CX"` sai `"CX"` na mesma, e é `factor_para_base` que
    diz que não é unidade.
    """
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acentos = "".join(ch for ch in decomposto if not unicodedata.combining(ch))
    sem_espacos = "".join(sem_acentos.split())
    return sem_espacos.upper().rstrip(".")


def dimensao_da_unidade(texto: str | None) -> str | None:
    """`"massa"`, `"volume"`, `"contagem"` — ou `None` se não é unidade da tabela."""
    entrada = _POR_SINONIMO.get(normalizar_unidade(texto))
    return None if entrada is None else entrada[0]


def factor_para_base(invoice_unit: str | None, base_unit: str) -> Decimal | None:
    """Quantas unidades base vale **uma** `invoice_unit`, ou `None`.

    `None` em dois casos que de fora são o mesmo — *não há conversão possível*:
    a unidade não está na tabela (`"CX"`), ou está mas noutra dimensão (`"KG"`
    para um artigo em `ml`). Quem chama decide o que fazer com o `None`; o que
    nunca acontece é sair `1` por omissão.
    """
    entrada = _POR_SINONIMO.get(normalizar_unidade(invoice_unit))
    if entrada is None:
        return None
    dimensao, factor = entrada
    if DIMENSAO_DA_BASE.get(base_unit) != dimensao:
        return None
    return factor


def verificar_apresentacao(
    *, base_unit: str, display_unit: str | None, display_factor: Decimal
) -> None:
    """A validação complementar do §4.3: a apresentação não pode mentir sobre a tabela.

    Se `display_unit` normaliza para um sinónimo da tabela, o `display_factor`
    **tem** de ser o da tabela — `"kg"` com factor 500 é uma mentira que
    multiplicava cada contagem por dois. E se normaliza para outra dimensão que
    a `base_unit` (`"L"` num artigo em gramas), é recusa no `display_unit`.

    Um `display_unit` fora da tabela (`"saco"`, `"bloco"`) aceita qualquer
    factor positivo: é exactamente para isso que ele existe.
    """
    entrada = _POR_SINONIMO.get(normalizar_unidade(display_unit))
    if entrada is None:
        return
    dimensao, factor = entrada
    if DIMENSAO_DA_BASE.get(base_unit) != dimensao:
        raise ApresentacaoIncoerente(
            "display_unit",
            _(
                "{unidade} is a unit of {dimensao} and the base unit of this item "
                "is {base}. Choose a display unit of the same dimension."
            ).format(unidade=display_unit, dimensao=dimensao, base=base_unit),
        )
    if display_factor != factor:
        raise ApresentacaoIncoerente(
            "display_factor",
            _(
                "One {unidade} is {factor} {base}, and the factor is fixed by the "
                "unit table. Use {factor}, or a display unit that is not a known unit."
            ).format(unidade=display_unit, factor=factor, base=base_unit),
        )
