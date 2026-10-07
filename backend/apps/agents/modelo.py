"""A fronteira do modelo: a única função deste repositório que falaria com um LLM.

E hoje não fala com nenhum. **Zero chaves de API, zero rede, zero cliente HTTP** —
ligar a extração a sério é configuração (um nome de modelo, uma credencial) mais
um prompt, e nenhuma das duas coisas existe. Em vez de fingir, esta fronteira
levanta uma excepção que diz exactamente o que falta, e a tarefa grava a tentativa
com `status=erro` e a razão legível.

É isso que torna a fatia 1 completa e testável: todo o resto do caminho — o
documento, as páginas, a linha da tentativa, o custo, o estado derivado, o painel
só de leitura — corre de ponta a ponta, e o que fica em aberto é uma função com
um nome.

## As duas recusas, que são situações diferentes

* `ModeloNaoConfigurado` — `settings.AGENTS_EXTRACTION_MODEL` está vazio. É o
  estado de omissão do projecto, e a frase diz o que configurar;
* `ClienteDoModeloInexistente` — há nome de modelo mas não há cliente que o
  chame. Levanta porque é uma configuração que promete uma capacidade que o
  código não tem, e falhar com uma frase é melhor do que devolver um documento
  vazio que parece uma fatura ilegível.

As duas descendem de `ErroDoModelo`, que é o que a tarefa apanha — um `except`
sobre a base deixa acrescentar uma terceira recusa sem tocar na tarefa.

## O que esta função **nunca** pode fazer, no dia em que falar com um modelo

1. **devolver instruções.** O que ela devolve é dados não confiáveis, e o chamador
   grava-os verbatim num `JSONField` que nunca é comparado num `if` (SECURITY.md
   §6);
2. **escolher um artigo, uma unidade ou uma localização.** Nada de extraído
   escolhe uma entidade do catálogo — isso é a revisão humana, que é obrigatória
   (CLAUDE.md);
3. **receber o conteúdo da página sem o marcar como não confiável** no prompt
   (ARCHITECTURE.md §6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.purchasing.api import PaginaDoDocumento

__all__ = [
    "VERSAO_DO_PROMPT",
    "ClienteDoModeloInexistente",
    "ErroDoModelo",
    "ModeloNaoConfigurado",
    "RespostaDoModelo",
    "ler_documento",
    "nome_do_modelo",
]

#: A versão do prompt que produziu uma resposta, gravada em cada linha de
#: extração. `0-sem-prompt` porque não há prompt nenhum: a coluna existe para o
#: dia em que a resposta de um modelo tiver de ser atribuída a uma versão, e um
#: valor vazio tornava indistinguível "não havia prompt" de "ninguém preencheu".
VERSAO_DO_PROMPT = "0-sem-prompt"


class ErroDoModelo(RuntimeError):
    """A chamada ao modelo não aconteceu. A tarefa grava a razão e não rebenta."""


class ModeloNaoConfigurado(ErroDoModelo):
    """Não há nome de modelo em `settings.AGENTS_EXTRACTION_MODEL`."""


class ClienteDoModeloInexistente(ErroDoModelo):
    """Há nome de modelo e não há cliente que o chame."""


@dataclass(frozen=True, kw_only=True, slots=True)
class RespostaDoModelo:
    """O que uma chamada devolve: o payload verbatim e o que ela custou.

    `payload` é um `dict` tal como veio, e é a única coisa deste repositório que
    se guarda sem a ter lido. O resto são métricas da chamada, que o
    `ARCHITECTURE.md` §6 exige ("custo em tokens logado").
    """

    payload: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: Decimal = Decimal("0")


def nome_do_modelo() -> str:
    """O modelo configurado, ou string vazia. Uma leitura, num sítio."""
    return str(getattr(settings, "AGENTS_EXTRACTION_MODEL", "") or "")


def ler_documento(*, paginas: Sequence[PaginaDoDocumento]) -> RespostaDoModelo:
    """Lê as páginas de um documento. **Levanta sempre, hoje.**

    As páginas chegam como DTO congelado do `purchasing.api` (ADR 0020, decisão
    6), já ordenadas. A assinatura é a que um cliente a sério usaria, e é
    deliberado: no dia em que houver modelo, o que muda é o corpo desta função e
    mais nada — nem a tarefa, nem os serviços, nem o contrato.
    """
    modelo = nome_do_modelo()
    if not modelo:
        raise ModeloNaoConfigurado(
            "não há modelo de extração configurado: a definição "
            "AGENTS_EXTRACTION_MODEL está vazia, logo não há a quem pedir a "
            f"leitura destas {len(paginas)} página(s). O documento fica com a "
            "tentativa gravada e à espera de revisão à mão."
        )
    raise ClienteDoModeloInexistente(
        f"o modelo {modelo!r} está configurado mas este projecto não tem "
        "cliente nenhum que o chame: a extração a sério é uma credencial, um "
        "prompt e o corpo desta função — ver o docstring de "
        "apps/agents/modelo.py."
    )
