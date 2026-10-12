"""O NIF de um fornecedor: forma canónica e dígito de controlo (ADR 0022, §4.4).

Dois usos, e são diferentes de propósito:

* **o NIF do catálogo** (`catalog_supplier.nif`) é **validado**: nove dígitos,
  primeiro diferente de zero, dígito de controlo módulo 11. É o que esta fatia
  escreve a partir de um formulário ou do `apps/demo`;
* **o NIF como impresso** numa receção (`purchasing_receipt.supplier_nif`) só é
  **normalizado** — é o que foi lido, e uma fatura espanhola não tem nove dígitos.
  O `purchasing` usa `normalizar_nif` daqui para guardar e `nif_valido` para
  decidir se vale a pena procurar o fornecedor (`fornecedor_por_nif`).

**Sem lista de prefixos.** O primeiro dígito diz o tipo de contribuinte (1 e 2
pessoa singular, 5 pessoa colectiva, 6 Estado, ...), e a lista oficial muda — um
prefixo novo recusado por uma lista velha era um fornecedor real a não entrar.
O que o algoritmo garante chega: `999999990` e `000000000` passam o dígito de
controlo e são recusados **explicitamente**, porque são os dois valores que
aparecem numa fatura quando o emissor não pôs NIF nenhum.
"""

from __future__ import annotations

__all__ = ["NIF_RECUSADOS", "nif_valido", "normalizar_nif"]

#: Os dois NIF com dígito de controlo certo que nunca são de ninguém: o
#: "consumidor final" (`999999990`) e o vazio. Recusados por nome, não por regra.
NIF_RECUSADOS: frozenset[str] = frozenset({"999999990", "000000000"})

#: Os pesos do módulo 11, do primeiro ao oitavo dígito.
_PESOS = (9, 8, 7, 6, 5, 4, 3, 2)


def normalizar_nif(texto: str | None) -> str:
    """Maiúsculas, só alfanuméricos ASCII, e sem o `PT` à frente de nove dígitos.

    Não valida: `"ES B12345678"` sai `"ESB12345678"` e é assim que uma receção o
    guarda, como impresso (§4.4). O `PT` só cai quando o que resta são nove
    dígitos — `"PT"` sozinho, ou `"PT12"`, ficam como estão.
    """
    limpo = "".join(ch for ch in (texto or "").upper() if ch.isascii() and ch.isalnum())
    if limpo.startswith("PT") and len(limpo) == 11 and limpo[2:].isdigit():
        return limpo[2:]
    return limpo


def nif_valido(texto: str | None) -> bool:
    """Nove dígitos, primeiro diferente de zero, dígito de controlo certo.

    Normaliza primeiro, para `"PT 503 214 787"` ser aceite como `"503214787"`:
    quem valida é quem vai guardar, e guarda a forma canónica.
    """
    nif = normalizar_nif(texto)
    if len(nif) != 9 or not nif.isdigit() or nif[0] == "0" or nif in NIF_RECUSADOS:
        return False
    return _digito_de_controlo(nif[:8]) == int(nif[8])


def _digito_de_controlo(oito_digitos: str) -> int:
    """Módulo 11 com pesos 9..2; resto; 11 − resto; 10 ou 11 → 0."""
    soma = sum(int(digito) * peso for digito, peso in zip(oito_digitos, _PESOS, strict=True))
    digito = 11 - (soma % 11)
    return 0 if digito >= 10 else digito
