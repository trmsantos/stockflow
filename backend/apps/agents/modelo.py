"""A fronteira do modelo: o único ficheiro deste repositório que fala com um LLM.

Desde 2026-10-15 (ADR 0027) **fala com um**: a fábrica `cliente()` constrói o
`openai.OpenAI` e `conversar()` faz uma chamada de chat com tools. É a única
linha que sabe o fornecedor — trocar de fornecedor é esta fábrica e uma função,
não uma reescrita. E só o **worker** a chama: o processo web recusa 503 antes de
criar linha nenhuma quando falta o modelo ou a chave, e nunca abre socket nenhum.

Desde 2026-10-19 (ADR 0031) `ler_documento` também fala: uma chamada a um modelo
de **visão**, com as páginas todas em base64 inline, em JSON mode e **sem tools
nenhumas**. A ausência de tools não é economia — é a defesa estrutural contra uma
fatura que traga impresso um texto a tentar dar instruções: um modelo convencido
não tem acção nenhuma para desviar.

## As recusas, que são situações diferentes

* `ModeloNaoConfigurado` — não há nome de modelo, ou não há chave. É o estado de
  omissão do projecto, e a frase diz o que configurar;
* `DocumentoGrandeDemais` — o documento tem mais páginas do que
  `AGENTS_EXTRACTION_MAX_PAGES`. **Não se chama**: acima do tecto não há
  chamada, há uma razão legível e uma pessoa a partir o documento em dois;
* `PaginasSemImagem` — nenhuma página tem imagem normalizada para enviar. É o
  caso de uma extração que chegou antes da rasterização, e melhora com o tempo:
  a acção é voltar a tentar;
* `OrcamentoEsgotado` — o tecto diário em euros **deste estabelecimento** já foi
  atingido. Não é um estado novo (ADR 0031, decisão 7): é um `erro` com razão;
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

import base64
import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from django.conf import settings

from apps.agents.prompt_extracao import VERSAO_DO_PROMPT_DA_EXTRACAO, prompt_de_extracao
from apps.purchasing.api import TIPO_DA_IMAGEM_DA_PAGINA, PaginaDoDocumento, bytes_da_pagina

__all__ = [
    "VERSAO_DO_PROMPT",
    "ChamadaATool",
    "DocumentoGrandeDemais",
    "ErroDoModelo",
    "ModeloNaoConfigurado",
    "OrcamentoEsgotado",
    "PaginasSemImagem",
    "RespostaDoModelo",
    "RespostaInvalida",
    "TempoEsgotado",
    "chat_configurado",
    "cliente",
    "conversar",
    "custo_em_euros",
    "extracao_configurada",
    "ler_documento",
    "nome_do_modelo",
    "nome_do_modelo_de_chat",
]

logger = logging.getLogger(__name__)

#: A versão do prompt da **extração**, gravada em cada linha de extração. Vive no
#: `prompt_extracao.py`, ao lado do texto que versiona; reexportada aqui porque é
#: este o nome que o `services.py` grava desde a fatia 1.
VERSAO_DO_PROMPT = VERSAO_DO_PROMPT_DA_EXTRACAO

#: Um milhão: a unidade da tabela de preços.
_MILHAO = Decimal("1000000")
_SEIS_CASAS = Decimal("0.000001")


class ErroDoModelo(RuntimeError):
    """A chamada ao modelo não aconteceu ou não serviu. A tarefa grava a razão."""


class ModeloNaoConfigurado(ErroDoModelo):
    """Não há nome de modelo — ou, no chat, não há chave de API."""


class DocumentoGrandeDemais(ErroDoModelo):
    """Mais páginas do que `AGENTS_EXTRACTION_MAX_PAGES`. Não se chama o modelo."""


class PaginasSemImagem(ErroDoModelo):
    """Nenhuma página tem imagem normalizada para enviar ao modelo.

    A única recusa desta fronteira que melhora com o tempo sem ser do
    fornecedor: a rasterização corre noutra tarefa, e quando acabar o documento
    é relido. Por isso a tarefa **não** abre tentativa quando o vê de antemão —
    esta classe é a rede para a corrida que sobra.
    """


class OrcamentoEsgotado(ErroDoModelo):
    """O tecto diário de euros deste estabelecimento já foi atingido."""


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

    #: O corpo verbatim de uma leitura de documento. **Não é sempre um `dict`**:
    #: um modelo que responda em prosa dá uma string, e uma string é o que vai
    #: para a coluna — guardar o texto tal como veio é o ponto inteiro dela
    #: (ADR 0021, decisão 4), e um não-objecto não valida contra o schema, que é
    #: exactamente a fronteira sintáctica entre `ilegivel` e `lido`.
    payload: Any = field(default_factory=dict)
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


def _chave_de_extracao() -> str:
    """A chave da extração, **com fallback para a do chat** (ADR 0031, decisão 2).

    Uma credencial hoje; duas no dia em que as faturas tiverem de ir para uma
    conta diferente da do chat — e esse dia é uma variável de ambiente, não um
    diff.
    """
    return str(getattr(settings, "AGENTS_EXTRACTION_API_KEY", "") or "") or _chave_de_api()


def _url_de_extracao() -> str:
    """A URL base da extração, com o mesmo fallback para a do chat."""
    return str(getattr(settings, "AGENTS_EXTRACTION_BASE_URL", "") or "") or _url_base()


def extracao_configurada() -> bool:
    """Há modelo de extração, com preço conhecido ou fornecedor gratuito?

    A chave não entra, pela razão do `chat_configurado`: só o worker a tem.
    """
    modelo = nome_do_modelo()
    return bool(modelo) and _modelo_tem_preco(modelo, url_base=_url_de_extracao())


def _limite_de_tokens(max_tokens: int, *, url_base: str | None = None) -> dict[str, int]:
    """O parâmetro que limita a resposta, no nome que o destino conhece.

    A OpenAI retirou `max_tokens` aos modelos recentes a favor de
    `max_completion_tokens`; os fornecedores compatíveis (Gemini, Groq, GitHub
    Models) conhecem `max_tokens` e nem todos aceitam o outro. A URL base decide,
    e a da extração pode não ser a do chat.
    """
    if _url_base() if url_base is None else url_base:
        return {"max_tokens": max_tokens}
    return {"max_completion_tokens": max_tokens}


def _modelo_tem_preco(modelo: str, *, url_base: str | None = None) -> bool:
    """O modelo está na tabela de preços, ou o fornecedor é por URL base (gratuito)?

    Sem URL base o destino é a OpenAI, que cobra: um modelo sem preço custaria
    0 € na tabela e o teto diário em euros nunca disparava (revisão de
    segurança de 2026-10-15). Falha-se fechado. Com URL base aceita-se o 0 €:
    é o nível gratuito que o dono escolheu, e o teto de mensagens por pessoa
    continua a valer.

    `url_base` é argumento porque a extração tem a sua (ADR 0031, decisão 2) e a
    pergunta é a mesma; sem ele vale a do chat, que é o chamador de origem.
    """
    if _url_base() if url_base is None else url_base:
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


def cliente(
    *, chave: str | None = None, url: str | None = None, timeout: int | None = None
) -> Any:
    """A fábrica do cliente: a **única** linha que sabe o fornecedor.

    `max_retries=0` porque nenhuma recusa melhora com o tempo e uma retentativa
    paga duas vezes (ADR 0027, decisão 9); as retentativas de sobrecarga são do
    `conversar`/`ler_documento` e não do SDK. Os testes substituem esta função
    por uma que devolve um cliente falso — nenhum teste fala com a rede.

    Os três argumentos entram com a ADR 0031 (decisão 2) e **continuam a dar uma
    fábrica só**: por omissão são os do chat, e a extração passa os seus. Um
    segundo construtor noutro ficheiro era a propriedade inteira desta fábrica a
    desaparecer.

    Import no corpo: o SDK só é carregado no processo que o usa, que é o worker.
    """
    chave = _chave_de_api() if chave is None else chave
    if not chave:
        raise ModeloNaoConfigurado(
            "não há chave de API: as definições AGENTS_EXTRACTION_API_KEY e "
            "AGENTS_CHAT_API_KEY estão as duas vazias. Só o worker a recebe, "
            "pelo ambiente (ADR 0027)."
        )
    import openai

    return openai.OpenAI(
        api_key=chave,
        base_url=(_url_base() if url is None else url) or None,
        timeout=int(getattr(settings, "AGENTS_CHAT_TIMEOUT_S", 30))
        if timeout is None
        else timeout,
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


def ler_documento(
    *, tenant_id: UUID, paginas: Sequence[PaginaDoDocumento]
) -> RespostaDoModelo:
    """Lê as páginas de um documento com um modelo de visão. Uma chamada só.

    As páginas chegam como DTO congelado do `purchasing.api` (ADR 0020, decisão
    6), já ordenadas, e **sem bytes**: os bytes vêm uma página de cada vez por
    `bytes_da_pagina`, que é a função que impede este módulo de conhecer o
    `MEDIA_ROOT` do `purchasing` (ADR 0031, decisão 1).

    ## Porque é que vão todas numa chamada

    O cabeçalho está na folha 1, as linhas continuam na 2 e os totais estão na
    última. Partir por página obrigava-nos a **fundir** N leituras parciais, e
    fundir é inferência nossa sobre texto não confiável. Dez imagens são ~15 k
    tokens de entrada; acima do tecto não se chama de todo.

    ## JSON mode, e zero tools

    `response_format={"type": "json_object"}` dá JSON válido sem o custo de um
    *"Aqui está o JSON:"*, e quem decide se é **este** JSON é o
    `LeituraDeFaturaSerializer`. Tools nenhumas, e isso é a defesa estrutural
    contra uma fatura com texto a tentar instruir o modelo: não há acção para
    desviar (ADR 0031, decisão 6).

    Devolve o `payload` já desserializado e verbatim — o `dict` tal como o
    modelo o escreveu, sem um campo acrescentado nem retirado. Um corpo que não
    seja JSON válido vai como `{"texto": …}` para a coluna, onde não valida e
    dá `ilegivel`, que é exactamente a fronteira sintáctica da decisão 4.
    """
    modelo = nome_do_modelo()
    if not modelo:
        raise ModeloNaoConfigurado(
            "não há modelo de extração configurado: a definição "
            "AGENTS_EXTRACTION_MODEL está vazia, logo não há a quem pedir a "
            f"leitura destas {len(paginas)} página(s). O documento fica com a "
            "tentativa gravada e à espera de revisão à mão."
        )
    url = _url_de_extracao()
    if not _modelo_tem_preco(modelo, url_base=url):
        raise ModeloNaoConfigurado(
            f"o modelo {modelo!r} não está em AGENTS_MODEL_PRICES_EUR_PER_MTOKEN e "
            "o destino é a OpenAI, que cobra: sem preço na tabela o tecto diário "
            "em euros nunca trava. Falha-se fechado."
        )
    tecto = int(getattr(settings, "AGENTS_EXTRACTION_MAX_PAGES", 10))
    if len(paginas) > tecto:
        raise DocumentoGrandeDemais(
            f"este documento tem {len(paginas)} páginas e lêem-se no máximo "
            f"{tecto} numa leitura. Divide-o em dois documentos."
        )
    imagens = _imagens_das_paginas(tenant_id=tenant_id, paginas=paginas)
    if not imagens:
        raise PaginasSemImagem(
            f"nenhuma das {len(paginas)} página(s) deste documento tem imagem "
            "pronta: a normalização ainda não correu, ou não há rasterizador "
            "neste ambiente. Volta a tentar quando as imagens aparecerem."
        )

    timeout = int(getattr(settings, "AGENTS_EXTRACTION_TIMEOUT_S", 120))
    api = cliente(chave=_chave_de_extracao(), url=url, timeout=timeout)
    mensagens = [
        {"role": "system", "content": prompt_de_extracao()},
        {"role": "user", "content": imagens},
    ]
    ultima: ModeloOcupado | None = None
    for tentativa in range(1, TENTATIVAS_EM_SOBRECARGA + 1):
        try:
            return _ler_documento_uma_vez(
                api=api, modelo=modelo, mensagens=mensagens, url=url, timeout=timeout
            )
        except ModeloOcupado as exc:
            ultima = exc
            logger.warning(
                "modelo sobrecarregado a ler um documento; a repetir",
                extra={"event": "extracao", "outcome": "ocupado", "count": tentativa},
            )
            if tentativa < TENTATIVAS_EM_SOBRECARGA:
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S * tentativa)
    raise ultima if ultima is not None else ErroDoModelo("o modelo não respondeu")


def _imagens_das_paginas(
    *, tenant_id: UUID, paginas: Sequence[PaginaDoDocumento]
) -> list[dict[str, Any]]:
    """As páginas como partes `image_url` em base64 inline, pela ordem do papel.

    **Base64 inline e não upload para o fornecedor** (ADR 0031, decisão 1): uma
    Files API é específica do fornecedor, e a fábrica `cliente()` é a única
    linha deste repositório que o sabe. Um upload partia essa propriedade *e*
    deixava a imagem de uma fatura — com os dois NIF e a morada — no servidor de
    terceiros mais tempo do que a chamada dura.

    Uma página sem bytes é saltada em silêncio e não rebenta a leitura: é melhor
    ler nove folhas de dez do que nenhuma, e quem conta as que faltam é quem
    revê, com a fotografia ao lado.
    """
    partes: list[dict[str, Any]] = []
    for pagina in paginas:
        dados = bytes_da_pagina(tenant_id=tenant_id, pagina_id=pagina.id)
        if not dados:
            continue
        b64 = base64.b64encode(dados).decode("ascii")
        partes.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{TIPO_DA_IMAGEM_DA_PAGINA};base64,{b64}"},
            }
        )
    return partes


def _ler_documento_uma_vez(
    *,
    api: Any,
    modelo: str,
    mensagens: Sequence[Mapping[str, Any]],
    url: str,
    timeout: int,
) -> RespostaDoModelo:
    """Uma chamada só. As retentativas por sobrecarga estão no `ler_documento`."""
    import openai

    comecou = time.monotonic()
    try:
        bruto = api.chat.completions.create(
            model=modelo,
            messages=list(mensagens),
            response_format={"type": "json_object"},
            **_limite_de_tokens(
                int(getattr(settings, "AGENTS_EXTRACTION_MAX_TOKENS", 8000)), url_base=url
            ),
            timeout=timeout,
        )
    except openai.APITimeoutError as exc:
        raise TempoEsgotado(f"o modelo não respondeu em {timeout} s") from exc
    except openai.APIStatusError as exc:
        # Só a classe e o código: a mensagem de um erro do fornecedor pode citar
        # o corpo do pedido, e o corpo tem as imagens de uma fatura.
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
        "documento lido pelo modelo",
        extra={
            "event": "extracao",
            "outcome": resposta.motivo_de_paragem or "sem_motivo",
            "duration_ms": duracao_ms,
            "count": resposta.input_tokens + resposta.output_tokens,
        },
    )
    return _com_payload(resposta)


def _com_payload(resposta: RespostaDoModelo) -> RespostaDoModelo:
    """A mesma resposta com o `payload` desserializado do texto, verbatim.

    Um texto que não é JSON fica na coluna **como texto**; um JSON que não é um
    objecto (uma lista, um número) fica como veio. Nos dois casos não valida
    contra o schema, logo o estado é `ilegivel` e o verbatim está lá para se
    poder voltar a ele (ADR 0021, decisão 4).

    **Nunca** se tenta extrair o JSON de dentro da prosa: adivinhar onde começa
    um objecto é a inferência que o JSON mode existe para tornar desnecessária,
    e a fronteira entre `ilegivel` e `lido` tem de ser da **forma** para ser
    testável.
    """
    try:
        return replace(resposta, payload=json.loads(resposta.texto))
    except (TypeError, ValueError):
        return replace(resposta, payload=resposta.texto)
