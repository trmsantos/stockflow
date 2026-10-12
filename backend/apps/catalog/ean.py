"""O código de barras de uma embalagem: GTIN-8, -12, -13 e -14 (ADR 0022, §4.1).

Quatro comprimentos e não só os dois do contrato original, por uma razão que o
`domain-expert` nomeou: o **ITF-14 é o código da caixa**, e a caixa é
precisamente a embalagem que uma fatura de distribuidor imprime. O dígito de
controlo é o mesmo algoritmo nos quatro (pesos 3 e 1 alternados a partir da
direita), e a coluna já tinha catorze posições.

É a **segunda chave de match** ao semear uma receção (§4.7): quando o par
`(fornecedor, código)` não casa, o EAN da linha casa com o da embalagem — entre
fornecedores, porque o EAN é do fabricante e não de quem vende.
"""

from __future__ import annotations

__all__ = ["COMPRIMENTOS_GTIN", "ean_valido", "normalizar_ean"]

#: GTIN-8, UPC-A (GTIN-12), EAN-13 e ITF-14.
COMPRIMENTOS_GTIN: frozenset[int] = frozenset({8, 12, 13, 14})


def normalizar_ean(texto: str | None) -> str:
    """Só os dígitos: `"4006 381 333 931"` e `"4006381333931"` são o mesmo código."""
    return "".join(ch for ch in (texto or "") if ch.isascii() and ch.isdigit())


def ean_valido(texto: str | None) -> bool:
    """Um dos quatro comprimentos, só dígitos, e dígito de controlo GTIN certo."""
    ean = normalizar_ean(texto)
    if len(ean) not in COMPRIMENTOS_GTIN or len(ean) != len(texto or ""):
        return False
    return _digito_gtin(ean[:-1]) == int(ean[-1])


def _digito_gtin(corpo: str) -> int:
    """A partir da direita, ×3, ×1, ×3, ...; o dígito completa a dezena."""
    soma = sum(
        int(digito) * (3 if posicao % 2 == 0 else 1)
        for posicao, digito in enumerate(reversed(corpo))
    )
    return (10 - soma % 10) % 10
