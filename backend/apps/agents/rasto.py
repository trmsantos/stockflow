"""O rasto das tools de um turno: a forma de cada entrada, e a validação à leitura.

É o `tool_calls` do `ChatMessage` (ADR 0027, decisão 1): JSON verbatim com nome,
argumentos, número de linhas, truncado, milissegundos e `ok` de cada tool que o
modelo chamou. Guarda-se à medida que acontece e lê-se **validado**, como o
`payload` da extração — uma entrada que não tenha esta forma é descartada na
leitura e nunca chega ao cliente, e nenhum `if` do produto ramifica no conteúdo.

Puro de propósito: é importado pelo `models.py` (a propriedade
`chamadas_validadas`) e pelo `services.py` (que escreve as entradas), e um módulo
que os dois importam não pode importar nenhum deles.
"""

from __future__ import annotations

from typing import Any

__all__ = ["chamadas_validas", "entrada_de_rasto"]

#: O tamanho máximo do nome de uma tool e de uma string dentro dos argumentos
#: no rasto. Os argumentos vêm do modelo e são texto não confiável; cortá-los é
#: o que impede uma resposta de carregar um `args` de um megabyte para o ecrã.
_NOME_MAXIMO = 60
_TEXTO_MAXIMO = 200


def entrada_de_rasto(
    *, nome: str, args: dict[str, Any], rows: int, truncated: bool, ms: int, ok: bool
) -> dict[str, Any]:
    """Uma entrada do rasto, já na forma que a leitura aceita."""
    return {
        "name": nome[:_NOME_MAXIMO],
        "args": _args_limpos(args),
        "rows": int(rows),
        "truncated": bool(truncated),
        "ms": int(ms),
        "ok": bool(ok),
    }


def chamadas_validas(valor: Any) -> list[dict[str, Any]]:
    """As entradas de um `tool_calls` que têm a forma certa, pela ordem gravada.

    Uma lista que não seja lista é zero entradas; uma entrada que não seja um
    objecto com os seis campos tipados é descartada. Devolve sempre uma lista
    nova, para quem lê não conseguir alterar o que está na linha.
    """
    if not isinstance(valor, list):
        return []
    validas: list[dict[str, Any]] = []
    for entrada in valor:
        if not isinstance(entrada, dict):
            continue
        nome = entrada.get("name")
        args = entrada.get("args")
        rows = entrada.get("rows")
        truncated = entrada.get("truncated")
        ms = entrada.get("ms")
        ok = entrada.get("ok")
        if not (isinstance(nome, str) and nome and isinstance(args, dict)):
            continue
        if not (isinstance(rows, int) and isinstance(ms, int)):
            continue
        if isinstance(rows, bool) or isinstance(ms, bool):
            continue
        if not (isinstance(truncated, bool) and isinstance(ok, bool)):
            continue
        validas.append(
            entrada_de_rasto(
                nome=nome, args=args, rows=rows, truncated=truncated, ms=ms, ok=ok
            )
        )
    return validas


def _args_limpos(args: dict[str, Any]) -> dict[str, Any]:
    """Os argumentos com as strings cortadas e só valores JSON simples."""
    limpos: dict[str, Any] = {}
    for chave, valor in args.items():
        if not isinstance(chave, str):
            continue
        if isinstance(valor, str):
            limpos[chave[:_NOME_MAXIMO]] = valor[:_TEXTO_MAXIMO]
        elif isinstance(valor, bool | int | float) or valor is None:
            limpos[chave[:_NOME_MAXIMO]] = valor
        elif isinstance(valor, list):
            limpos[chave[:_NOME_MAXIMO]] = [
                item[:_TEXTO_MAXIMO] if isinstance(item, str) else str(item)[:_TEXTO_MAXIMO]
                for item in valor[:20]
            ]
        else:
            limpos[chave[:_NOME_MAXIMO]] = str(valor)[:_TEXTO_MAXIMO]
    return limpos
