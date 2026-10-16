"""A fronteira do modelo: o único ficheiro deste repositório que fala com um LLM.

Desde 2026-10-15 (ADR 0027) **fala com um**: a fábrica `cliente()` constrói o
`openai.OpenAI` e `conversar()` faz uma chamada de chat com tools. É a única
linha que sabe o fornecedor — trocar de fornecedor é esta fábrica e uma função,
não uma reescrita. E só o **worker** a chama: o processo web recusa 503 antes de
criar linha nenhuma quando falta o modelo ou a chave, e nunca abre socket nenhum.

`ler_documento` **não muda de comportamento**: continua a levantar, porque o que
lhe falta não é o cliente — é o prompt e o corpo. A mensagem do
`ClienteDoModeloInexistente` diz-o.

## As recusas, que são situações diferentes

* `ModeloNaoConfigurado` — não há nome de modelo, ou (no chat) não há chave. É
  o estado de omissão do projecto, e a frase diz o que configurar;
* `ClienteDoModeloInexistente` — há nome de modelo de extração e o cliente
  existe, mas a extração não tem prompt nem corpo. Levanta porque é uma
  configuração que promete uma capacidade que o código não tem;
* `TempoEsgotado` — o fornecedor não respondeu dentro de `timeout`;
* `RespostaInvalida` — a resposta não tem a forma que se lê (sem `choices`,
  sem `usage`).

Todas descendem de `ErroDoModelo`, que é o que a tarefa apanha. Um `except`
sobre a base deixa acrescentar uma recusa sem tocar na tarefa.

## O que esta fronteira **nunca** faz

1. **devolver instruções.** O que devolve é dados não confiáveis: texto e
   pedidos de tools, verbatim, que o chamador valida contra um schema antes de
   fazer o que quer que seja (SECURITY.md §6);
2. **escolher um artigo, uma unidade ou uma localização** na extração — isso é a
   revisão humana (CLAUDE.md);
3. **receber conteúdo do tenant sem o marcar como não confiável** no prompt
   (ARCHITECTURE.md §6) — o prompt de sistema é de quem chama, e é ele que o
   diz;
4. **logar a chave, a pergunta ou a resposta.** O que se loga por chamada é
   modelo, tokens, custo, duração e a chave de idempotência (ADR 0027, d7).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings

from apps.purchasing.api import PaginaDoDocumento

__all__ = [
    "VERSAO_DO_PROMPT",
    "ChamadaATool",
    "ClienteDoModeloInexistente",
    "ErroDoModelo",
    "ModeloNaoConfigurado",
    "RespostaDoModelo",
    "RespostaInvalida",
    "TempoEsgotado",
    "chat_configurado",
    "cliente",
    "conversar",
    "custo_em_euros",
    "ler_documento",
    "nome_do_modelo",
    "nome_do_modelo_de_chat",
]

logger = logging.getLogger(__name__)

#: A versão do prompt da **extração**, gravada em cada linha de extração.
#: `0-sem-prompt` porque não há prompt nenhum (ver `ler_documento`).
VERSAO_DO_PROMPT = "0-sem-prompt"

#: Um milhão: a unidade da tabela de preços.
_MILHAO = Decimal("1000000")
_SEIS_CASAS = Decimal("0.000001")


class ErroDoModelo(RuntimeError):
    """A chamada ao modelo não aconteceu ou não serviu. A tarefa grava a razão."""


class ModeloNaoConfigurado(ErroDoModelo):
    """Não há nome de modelo — ou, no chat, não há chave de API."""


class ClienteDoModeloInexistente(ErroDoModelo):
    """Há nome de modelo de extração e não há prompt nem corpo que o chame."""


class TempoEsgotado(ErroDoModelo):
    """O fornecedor não respondeu dentro do `timeout` da chamada."""


class ModeloOcupado(ErroDoModelo):
    """O fornecedor está sobrecarregado e disse para voltar mais tarde.

    Distinta de `ErroDoModelo` porque é a **única** recusa que melhora com o
    tempo: a ADR 0027 d9 pôs `max_retries=0` com o argumento de que "nenhuma
    recusa melhora com o tempo e uma retentativa paga duas vezes", e isso é
    verdade de um 400 ou de um 404 — não de um 503 "high demand", que no nível
    gratuito da Gemini acontece em rajadas de minutos (medido a 2026-10-16).
    Uma retentativa de uma chamada que nunca chegou ao modelo não paga nada:
    não há tokens numa resposta que não existiu.
    """


class RespostaInvalida(ErroDoModelo):
    """A resposta do fornecedor não tem a forma que se lê."""


@dataclass(frozen=True, kw_only=True, slots=True)
class ChamadaATool:
    """Um pedido de tool, verbatim: o id do fornecedor, o nome e os argumentos em JSON.

    Os três são texto não confiável. O nome só vale depois de encontrado no
    registo, e os argumentos só depois de validados pelo schema da tool.
    """

    id: str
    nome: str
    argumentos: str


@dataclass(frozen=True, kw_only=True, slots=True)
class RespostaDoModelo:
    """O que uma chamada devolve: o conteúdo verbatim e o que ela custou.

    Na extração `payload` é o JSON tal como veio. No chat são `texto`, as
    `chamadas` a tools e `mensagem_verbatim` — a mensagem do assistente na forma
    exacta que a chamada seguinte tem de receber de volta, já em `dict` e com
    nomes nossos, para o SDK não atravessar a fronteira. `motivo_de_paragem` é o
    `finish_reason` do fornecedor: `stop`, `tool_calls`, `length`.

    O resto são métricas da chamada, que o `ARCHITECTURE.md` §6 exige.
    """

    payload: dict[str, Any] = field(default_factory=dict)
    texto: str = ""
    chamadas: tuple[ChamadaATool, ...] = ()
    mensagem_verbatim: dict[str, Any] = field(default_factory=dict)
    motivo_de_paragem: str = ""
    modelo: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: Decimal = Decimal("0")
    duracao_ms: int = 0


def nome_do_modelo() -> str:
    """O modelo de extração configurado, ou string vazia. Uma leitura, num sítio."""
    return str(getattr(settings, "AGENTS_EXTRACTION_MODEL", "") or "")


def nome_do_modelo_de_chat() -> str:
    """O modelo do chat configurado, ou string vazia."""
    return str(getattr(settings, "AGENTS_CHAT_MODEL", "") or "")


def _chave_de_api() -> str:
    """A chave, lida no momento da chamada e nunca guardada em módulo nenhum."""
    return str(getattr(settings, "AGENTS_CHAT_API_KEY", "") or "")


def _url_base() -> str:
    """A URL base de um fornecedor OpenAI-compatível, ou vazia (api.openai.com)."""
    return str(getattr(settings, "AGENTS_CHAT_BASE_URL", "") or "")


def _limite_de_tokens(max_tokens: int) -> dict[str, int]:
    """O parâmetro que limita a resposta, no nome que o destino conhece.

    A OpenAI retirou `max_tokens` aos modelos recentes a favor de
    `max_completion_tokens`; os fornecedores compatíveis (Gemini, Groq, GitHub
    Models) conhecem `max_tokens` e nem todos aceitam o outro. A URL base decide.
    """
    if _url_base():
        return {"max_tokens": max_tokens}
    return {"max_completion_tokens": max_tokens}


def _modelo_tem_preco(modelo: str) -> bool:
    """O modelo está na tabela de preços, ou o fornecedor é por URL base (gratuito)?

    Sem URL base o destino é a OpenAI, que cobra: um modelo sem preço custaria
    0 € na tabela e o teto diário em euros nunca disparava (revisão de
    segurança de 2026-10-15). Falha-se fechado. Com URL base aceita-se o 0 €:
    é o nível gratuito que o dono escolheu, e o teto de mensagens por pessoa
    continua a valer.
    """
    if _url_base():
        return True
    tabela: Mapping[str, object] = getattr(settings, "AGENTS_MODEL_PRICES_EUR_PER_MTOKEN", {})
    return modelo in tabela


def chat_configurado() -> bool:
    """Há modelo, com preço conhecido ou fornecedor gratuito? É o 503 `assistente_indisponivel`.

    A chave **não** entra aqui: só o worker a tem (ADR 0027, decisão 7), e o
    processo web não pode exigir um segredo que não deve possuir. Se faltar ao
    worker, `cliente()` levanta `ModeloNaoConfigurado` e o turno fecha com
    `erro_do_modelo`.
    """
    modelo = nome_do_modelo_de_chat()
    return bool(modelo) and _modelo_tem_preco(modelo)


def cliente() -> Any:
    """A fábrica do cliente: a única linha que sabe o fornecedor.

    `max_retries=0` porque nenhuma recusa melhora com o tempo e uma retentativa
    paga duas vezes (ADR 0027, decisão 9); o `timeout` é por chamada e vem das
    settings. Os testes substituem esta função por uma que devolve um cliente
    falso — nenhum teste fala com a rede.

    Import no corpo: o SDK só é carregado no processo que o usa, que é o worker.
    """
    chave = _chave_de_api()
    if not chave:
        raise ModeloNaoConfigurado(
            "não há chave de API para o assistente: a definição AGENTS_CHAT_API_KEY "
            "está vazia. Só o worker a recebe, pelo ambiente (ADR 0027)."
        )
    import openai

    return openai.OpenAI(
        api_key=chave,
        base_url=_url_base() or None,
        timeout=int(getattr(settings, "AGENTS_CHAT_TIMEOUT_S", 30)),
        max_retries=0,
    )


def custo_em_euros(*, modelo: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Os euros de uma chamada, pela tabela de preços. Tokens são a verdade.

    Um modelo fora da tabela custa 0 e deixa um aviso: o teto diário em euros
    não o trava, e é por isso que o aviso existe em vez de um `KeyError`.
    """
    tabela: Mapping[str, Mapping[str, Decimal]] = getattr(
        settings, "AGENTS_MODEL_PRICES_EUR_PER_MTOKEN", {}
    )
    precos = tabela.get(modelo)
    if precos is None:
        logger.warning(
            "modelo sem preço na tabela; custo gravado a zero",
            extra={"event": "chat_custo", "outcome": "sem_preco"},
        )
        return Decimal("0")
    custo = (
        Decimal(input_tokens) * Decimal(precos["input"])
        + Decimal(output_tokens) * Decimal(precos["output"])
    ) / _MILHAO
    return custo.quantize(_SEIS_CASAS, rounding=ROUND_HALF_UP)


#: Os estados que querem dizer "volta a tentar", e não "não faço isto". 503 é a
#: sobrecarga que a Gemini devolve em rajadas; 429 do **fornecedor** é a quota
#: dele, não o nosso teto diário, que é verificado antes da chamada.
_ESTADOS_DE_SOBRECARGA = frozenset({429, 503})

#: Quantas vezes uma chamada sobrecarregada se repete, e quanto espera entre
#: tentativas. Curto de propósito: o turno tem um `timeout` por chamada e a
#: pessoa está à espera do lado de lá. Fica no `modelo.py` e não nas settings
#: porque é uma propriedade de como se fala com um fornecedor, não uma escolha
#: de produto.
TENTATIVAS_EM_SOBRECARGA = 3
ESPERA_ENTRE_TENTATIVAS_S = 1.5


def conversar(
    *,
    sistema: str,
    mensagens: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    max_tokens: int,
    timeout: int,
    idempotency_key: str,
) -> RespostaDoModelo:
    """Uma chamada de chat com tools. Devolve texto e/ou pedidos de tools, verbatim.

    `sistema` vai como mensagem `system` e as `mensagens` seguem-se tal como
    vêm — a pergunta é uma mensagem `user` e nunca entra no sistema; os
    resultados das tools são mensagens `tool` com `tool_call_id`, nunca
    concatenados no prompt (ADR 0027, decisão 5). `max_tokens` vai como
    `max_completion_tokens` na OpenAI e como `max_tokens` noutro fornecedor
    (`_limite_de_tokens`). `idempotency_key` é `chat:<mensagem>:<i>`, enviada
    como cabeçalho e logada — é registo nosso.

    O que se loga: modelo, tokens, custo, duração e a chave. O que nunca se
    loga: a chave de API, a pergunta, a resposta.
    """
    ultima: ModeloOcupado | None = None
    for tentativa in range(1, TENTATIVAS_EM_SOBRECARGA + 1):
        try:
            return _conversar_uma_vez(
                sistema=sistema,
                mensagens=mensagens,
                tools=tools,
                max_tokens=max_tokens,
                timeout=timeout,
                idempotency_key=f"{idempotency_key}:{tentativa}",
            )
        except ModeloOcupado as exc:
            ultima = exc
            logger.warning(
                "modelo sobrecarregado; a repetir",
                extra={"event": "chat_chamada", "outcome": "ocupado", "count": tentativa},
            )
            if tentativa < TENTATIVAS_EM_SOBRECARGA:
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S * tentativa)
    raise ultima if ultima is not None else ErroDoModelo("o modelo não respondeu")


def _conversar_uma_vez(
    *,
    sistema: str,
    mensagens: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    max_tokens: int,
    timeout: int,
    idempotency_key: str,
) -> RespostaDoModelo:
    """Uma chamada só. As retentativas por sobrecarga estão no `conversar`."""
    modelo = nome_do_modelo_de_chat()
    if not modelo:
        raise ModeloNaoConfigurado(
            "não há modelo de chat configurado: a definição AGENTS_CHAT_MODEL está vazia."
        )
    if not _modelo_tem_preco(modelo):
        raise ModeloNaoConfigurado(
            f"o modelo {modelo!r} não está em AGENTS_MODEL_PRICES_EUR_PER_MTOKEN e o "
            "destino é a OpenAI, que cobra: sem preço o teto diário não trava."
        )
    api = cliente()
    import openai

    comecou = time.monotonic()
    try:
        bruto = api.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": sistema}, *mensagens],
            tools=list(tools) if tools else openai.NOT_GIVEN,
            **_limite_de_tokens(max_tokens),
            timeout=timeout,
            extra_headers={"Idempotency-Key": idempotency_key},
        )
    except openai.APITimeoutError as exc:
        raise TempoEsgotado(f"o modelo não respondeu em {timeout} s") from exc
    except openai.APIStatusError as exc:
        # Só a classe e o código: a mensagem de um erro do fornecedor pode citar
        # o corpo do pedido, e o corpo tem a pergunta.
        if exc.status_code in _ESTADOS_DE_SOBRECARGA:
            raise ModeloOcupado(
                f"o fornecedor respondeu {exc.status_code} e pediu para esperar"
            ) from exc
        raise ErroDoModelo(f"{type(exc).__name__} ao chamar o modelo") from exc
    except openai.OpenAIError as exc:
        raise ErroDoModelo(f"{type(exc).__name__} ao chamar o modelo") from exc
    duracao_ms = int((time.monotonic() - comecou) * 1000)

    resposta = _ler(bruto, modelo=modelo, duracao_ms=duracao_ms)
    logger.info(
        "chamada ao modelo de chat",
        extra={
            "event": "chat_chamada",
            "outcome": resposta.motivo_de_paragem or "sem_motivo",
            "duration_ms": duracao_ms,
            "count": resposta.input_tokens + resposta.output_tokens,
            "event_id": idempotency_key,
        },
    )
    return resposta


def _ler(bruto: Any, *, modelo: str, duracao_ms: int) -> RespostaDoModelo:
    """A resposta do SDK em nomes nossos. Lê atributos, não tipos.

    Por atributos e não por `isinstance` do SDK: é o que deixa um cliente falso
    devolver objectos simples nos testes, e é o que faz esta função ser a única
    que muda se o SDK mudar a forma.
    """
    try:
        escolha = bruto.choices[0]
        mensagem = escolha.message
        motivo = str(escolha.finish_reason or "")
        texto = str(mensagem.content or "")
        chamadas = tuple(
            ChamadaATool(
                id=str(chamada.id),
                nome=str(chamada.function.name),
                argumentos=str(chamada.function.arguments or "{}"),
            )
            for chamada in (mensagem.tool_calls or ())
        )
        uso = bruto.usage
        input_tokens = int(uso.prompt_tokens or 0) if uso is not None else 0
        output_tokens = int(uso.completion_tokens or 0) if uso is not None else 0
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise RespostaInvalida(f"{type(exc).__name__} ao ler a resposta do modelo") from exc

    # Verbatim a sério: o `model_dump` do SDK guarda campos extra do fornecedor
    # (a Gemini põe um `thought_signature` em cada tool_call e recusa a volta
    # sem ele, com 400). A reconstrução por campos fica para os clientes falsos.
    dump = getattr(mensagem, "model_dump", None)
    if callable(dump):
        verbatim: dict[str, Any] = dict(dump(exclude_none=True))
        verbatim.setdefault("role", "assistant")
    else:
        verbatim = {"role": "assistant", "content": texto or None}
        if chamadas:
            verbatim["tool_calls"] = [
                {
                    "id": chamada.id,
                    "type": "function",
                    "function": {"name": chamada.nome, "arguments": chamada.argumentos},
                }
                for chamada in chamadas
            ]
    return RespostaDoModelo(
        texto=texto,
        chamadas=chamadas,
        mensagem_verbatim=verbatim,
        motivo_de_paragem=motivo,
        modelo=modelo,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_eur=custo_em_euros(
            modelo=modelo, input_tokens=input_tokens, output_tokens=output_tokens
        ),
        duracao_ms=duracao_ms,
    )


def ler_documento(*, paginas: Sequence[PaginaDoDocumento]) -> RespostaDoModelo:
    """Lê as páginas de um documento. **Levanta sempre, hoje.**

    As páginas chegam como DTO congelado do `purchasing.api` (ADR 0020, decisão
    6), já ordenadas. A assinatura é a que um cliente a sério usaria, e é
    deliberado: no dia em que houver prompt, o que muda é o corpo desta função e
    mais nada — nem a tarefa, nem os serviços, nem o contrato. O cliente já
    existe (`cliente()`, ADR 0027); o que falta é o prompt e a leitura da
    resposta, e ligar a extração ao modelo está fora de âmbito dessa ADR.
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
        f"o modelo {modelo!r} está configurado mas a extração não tem cliente "
        "nenhum ligado: a fábrica `cliente()` existe desde a ADR 0027 e serve o "
        "chat; ligar a extração a sério é um prompt e o corpo desta função — "
        "ver o docstring de apps/agents/modelo.py."
    )
