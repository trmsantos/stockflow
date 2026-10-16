"""Os casos de uso da extração. **Única forma de escrever** no `agents`.

Três funções, que são os três momentos de uma chamada ao modelo: abrir a
tentativa, fechá-la com a resposta, fechá-la com uma razão. A tarefa
(`tasks.extrair_documento`) é a orquestração e não escreve nada por si.

## Porque é que abrir e fechar são duas escritas e não uma

Porque a linha é a prova de que a chamada **foi tentada**. Se só se escrevesse no
fim, uma chamada que nunca volta não deixava rasto nenhum — e é exactamente esse
o caso que o relógio dos dez minutos do estado derivado existe para cobrir
(`a_extrair` até lá, `erro` depois). Abrir primeiro é o que torna o `finished_at`
nulo um facto observável em vez de uma ausência.

É também o que faz `started_at`/`finished_at`/`cost_eur` serem `UPDATE`s da mesma
linha, e a razão de a tabela **não** ser append-only (ADR 0021, decisão 4).

## O chat sobre stock (ADR 0027), na segunda metade do ficheiro

Quatro casos de uso de escrita — criar uma conversa com a primeira pergunta,
fazer a pergunta seguinte, apagar a conversa, purgar as expiradas — e o ciclo de
tool-use (`responder`), que é o corpo da tarefa `agents.responder_mensagem`. As
recusas do `POST` são `RecusaDoAssistente` com um `code` da lista fechada, e o
texto sai por `_()` (o `tests/test_i18n.py` mede-o).

O ciclo grava cada tool chamada **à medida** (`status=a_responder`) e verifica o
orçamento diário antes de cada chamada ao modelo. Nunca escreve no ledger: as
tools são a lista fechada de `apps/agents/tools.py`, só de leitura.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.api import MembershipInfo, inicio_do_dia_de_negocio, opcao_de_tenant
from apps.agents import tools
from apps.agents.modelo import (
    VERSAO_DO_PROMPT,
    ErroDoModelo,
    ModeloOcupado,
    RespostaDoModelo,
    RespostaInvalida,
    TempoEsgotado,
    chat_configurado,
    conversar,
    nome_do_modelo_de_chat,
)
from apps.agents.models import (
    TURNOS_POR_CONVERSA,
    ChatMessage,
    CodigoDeErroDaMensagem,
    Conversation,
    EstadoDaExtracao,
    EstadoDaMensagem,
    Extraction,
)
from apps.agents.prompt import VERSAO_DO_PROMPT_DO_CHAT, prompt_de_sistema
from apps.agents.rasto import entrada_de_rasto
from apps.agents.selectors import (
    conversas_expiradas,
    custo_do_dia,
    mensagens_da_conversa,
    perguntas_do_dia,
    turno_em_curso,
    turnos_da_conversa,
)
from apps.agents.serializers import leitura_do_payload
from apps.inventory.api import listar_localizacoes

__all__ = [
    "ASSISTENTE_INDISPONIVEL",
    "CONVERSA_CHEIA",
    "RESPOSTA_PENDENTE",
    "TETO_DIARIO_ATINGIDO",
    "RecusaDoAssistente",
    "abrir_tentativa",
    "apagar_conversa",
    "criar_conversa",
    "fazer_pergunta",
    "fechar_com_erro",
    "fechar_com_resposta",
    "purgar_conversas_do_tenant",
    "responder",
]

logger = logging.getLogger(__name__)


def chave_de_idempotencia(*, documento_id: UUID, tentativa: int) -> str:
    """A chave de uma chamada, derivada de (documento, tentativa).

    Determinística de propósito: uma retentativa da **mesma** tentativa colide na
    unicidade em vez de duplicar a chamada, e o que se paga a um fornecedor de
    modelos é pago uma vez (ARCHITECTURE.md §6). Um valor aleatório dava uma
    chave única e nenhuma idempotência, que é o oposto do que o nome promete.
    """
    return f"extracao:{documento_id}:{tentativa}"


@transaction.atomic
def abrir_tentativa(*, tenant_id: UUID, documento_id: UUID, modelo: str) -> Extraction:
    """Cria a linha da tentativa seguinte deste documento, já começada.

    A tentativa é `max(attempt) + 1` dentro da transação, e a unicidade
    `(tenant, document_id, attempt)` é a rede contra duas tarefas a abrirem a
    mesma: a segunda falha com `IntegrityError` em vez de duplicar a chamada. Não
    se tenta resolver a corrida aqui — uma extração a mais é um custo, e esconder
    a corrida num `get_or_create` escondia também o facto de ela existir.
    """
    maxima = Extraction.objects.filter(
        tenant_id=tenant_id, document_id=documento_id
    ).aggregate(maxima=Max("attempt"))["maxima"]
    tentativa = (maxima or 0) + 1
    return Extraction.objects.create(
        tenant_id=tenant_id,
        document_id=documento_id,
        attempt=tentativa,
        model=modelo,
        prompt_version=VERSAO_DO_PROMPT,
        idempotency_key=chave_de_idempotencia(
            documento_id=documento_id, tentativa=tentativa
        ),
        started_at=timezone.now(),
        status=EstadoDaExtracao.PENDENTE,
    )


@transaction.atomic
def fechar_com_resposta(*, tentativa: Extraction, resposta: RespostaDoModelo) -> Extraction:
    """Guarda a resposta **verbatim** e valida-a. `lido` ou `ilegivel`.

    O `payload` é escrito como veio, sempre — também quando não valida. É o ponto
    inteiro da coluna: *"é prova, texto não confiável guardado para se poder
    voltar a ele"* (ADR 0021, decisão 4). O que a validação decide é o `status`, e
    mais nada.

    A `confidence` sai do payload **só** quando ele valida: um número que vem de
    um payload que não se consegue ler não é uma medida de confiança nenhuma.
    """
    valida = leitura_do_payload(resposta.payload).is_valid()
    tentativa.payload = resposta.payload
    tentativa.input_tokens = resposta.input_tokens
    tentativa.output_tokens = resposta.output_tokens
    tentativa.cost_eur = resposta.cost_eur
    tentativa.finished_at = timezone.now()
    tentativa.status = EstadoDaExtracao.LIDO if valida else EstadoDaExtracao.ILEGIVEL
    tentativa.confidence = _confianca(resposta) if valida else None
    tentativa.save(
        update_fields=[
            "payload",
            "input_tokens",
            "output_tokens",
            "cost_eur",
            "finished_at",
            "status",
            "confidence",
            "updated_at",
        ]
    )
    return tentativa


@transaction.atomic
def fechar_com_erro(*, tentativa: Extraction, razao: str) -> Extraction:
    """Fecha a tentativa com `status=erro` e uma razão legível.

    `razao` é a mensagem da excepção, cortada no que cabe numa frase: **nunca o
    traceback**, pelo precedente do `last_error` da outbox — o `DETAIL` de um erro
    do Postgres leva os valores da linha em conflito (SECURITY.md §1).

    O `payload` fica como está (vazio): não há resposta nenhuma para guardar, e
    escrever a nossa frase lá era corromper a coluna cujo valor inteiro é ser
    verbatim.
    """
    tentativa.finished_at = timezone.now()
    tentativa.status = EstadoDaExtracao.ERRO
    tentativa.error = razao[:1000]
    tentativa.save(update_fields=["finished_at", "status", "error", "updated_at"])
    return tentativa


def _confianca(resposta: RespostaDoModelo) -> Decimal | None:
    """A confiança global do payload, já validado.

    Lê-se do serializer e não do `dict` cru: é a diferença entre um `Decimal` com
    três casas e o que o modelo pôs lá (uma string, um `float`, um `99`).
    """
    serializer = leitura_do_payload(resposta.payload)
    if not serializer.is_valid():
        return None
    return serializer.validated_data["confidence"]


# ===========================================================================
# O chat sobre stock (ADR 0027)
# ===========================================================================
#: Os códigos de recusa do `POST`, lista fechada (ADR 0027, decisão 4). O
#: status HTTP de cada um vive no `views.py`, ao lado da resposta.
ASSISTENTE_INDISPONIVEL = "assistente_indisponivel"
TETO_DIARIO_ATINGIDO = "teto_diario_atingido"
RESPOSTA_PENDENTE = "resposta_pendente"
CONVERSA_CHEIA = "conversa_cheia"

#: O texto de cada recusa, por `_()`, com entrada pt-PT no `django.po`.
_DETALHES = {
    ASSISTENTE_INDISPONIVEL: _("The assistant is not configured on this server."),
    TETO_DIARIO_ATINGIDO: _("The assistant's daily limit has been reached. Try again tomorrow."),
    RESPOSTA_PENDENTE: _(
        "The assistant is still answering the previous question in this conversation."
    ),
    CONVERSA_CHEIA: _("This conversation has reached its limit of questions. Start a new one."),
}

#: Quantas conversas uma purga apaga por instrução.
LOTE_DA_PURGA = 200

#: Quantos caracteres da razão de um erro ficam na linha. Nunca o traceback.
_RAZAO_MAXIMA = 1000


class RecusaDoAssistente(Exception):
    """Uma recusa do `POST`, com o código da lista fechada e o texto traduzido."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.detalhe = _DETALHES[codigo]


def _verificar_disponibilidade() -> None:
    """503 **antes** de criar linha: há uma pessoa à espera (ADR 0027, decisão 4)."""
    if not chat_configurado():
        raise RecusaDoAssistente(ASSISTENTE_INDISPONIVEL)


def _verificar_tetos(*, tenant_id: UUID, user_id: UUID) -> None:
    """Os dois tetos diários, no `POST` (429). A tarefa volta a verificar o de custo."""
    if perguntas_do_dia(tenant_id=tenant_id, user_id=user_id) >= int(
        settings.AGENTS_CHAT_DAILY_MESSAGES_PER_USER
    ):
        raise RecusaDoAssistente(TETO_DIARIO_ATINGIDO)
    if custo_do_dia(tenant_id=tenant_id) >= Decimal(settings.AGENTS_CHAT_DAILY_BUDGET_EUR):
        raise RecusaDoAssistente(TETO_DIARIO_ATINGIDO)


def _abrir_turno(
    *,
    conversa: Conversation,
    autor: MembershipInfo,
    pergunta: str,
    lingua: str,
    posicao: int,
) -> ChatMessage:
    """A linha `pendente` de um turno. O `idempotency_key` é derivado do id."""
    mensagem = ChatMessage(
        tenant_id=conversa.tenant_id,
        conversation=conversa,
        position=posicao,
        asked_by_id=autor.user_id,
        asked_by_name=autor.display_name,
        role_at_time=autor.role,
        question=pergunta,
        language=lingua,
        status=EstadoDaMensagem.PENDENTE,
    )
    mensagem.idempotency_key = f"chat:{mensagem.id}"
    mensagem.save()
    return mensagem


def _enfileirar(mensagem: ChatMessage, *, request_id: str | None) -> None:
    """`.delay()` em `on_commit`, com o `tenant_id` **da linha** (ADR 0027, decisão 8).

    Import no corpo: o `tasks.py` importa este módulo. É o padrão do
    `handlers.pedir_extracao`.
    """
    from apps.agents.tasks import responder_mensagem

    tenant_id = str(mensagem.tenant_id)
    mensagem_id = str(mensagem.id)
    transaction.on_commit(
        lambda: responder_mensagem.delay(
            tenant_id=tenant_id, mensagem_id=mensagem_id, request_id=request_id
        )
    )


@transaction.atomic
def criar_conversa(
    *,
    tenant_id: UUID,
    autor: MembershipInfo,
    pergunta: str,
    lingua: str,
    request_id: str | None = None,
) -> Conversation:
    """Cria a conversa **e** faz a primeira pergunta: não existe conversa vazia.

    As três recusas acontecem antes de qualquer escrita, por ordem: sem modelo
    ou chave (503), teto diário de perguntas ou de euros (429). O título é a
    pergunta cortada a 120.
    """
    _verificar_disponibilidade()
    _verificar_tetos(tenant_id=tenant_id, user_id=autor.user_id)
    agora = timezone.now()
    conversa = Conversation.objects.create(
        tenant_id=tenant_id,
        created_by_id=autor.user_id,
        created_by_name=autor.display_name,
        title=pergunta[:120],
        last_message_at=agora,
    )
    mensagem = _abrir_turno(
        conversa=conversa, autor=autor, pergunta=pergunta, lingua=lingua, posicao=1
    )
    _enfileirar(mensagem, request_id=request_id)
    return conversa


@transaction.atomic
def fazer_pergunta(
    *,
    tenant_id: UUID,
    conversa: Conversation,
    autor: MembershipInfo,
    pergunta: str,
    lingua: str,
    request_id: str | None = None,
) -> ChatMessage:
    """O turno seguinte de uma conversa que já existe.

    Além das recusas do `criar_conversa`: um turno em curso (409
    `resposta_pendente`) e o teto de turnos (409 `conversa_cheia`). A conversa é
    trancada (`select_for_update`) para duas perguntas em paralelo não abrirem
    dois turnos com a mesma posição — a unicidade apanhava a segunda com um 500.
    """
    _verificar_disponibilidade()
    _verificar_tetos(tenant_id=tenant_id, user_id=autor.user_id)
    trancada = Conversation.objects.select_for_update().get(tenant_id=tenant_id, pk=conversa.pk)
    if turno_em_curso(tenant_id=tenant_id, conversa_id=trancada.pk) is not None:
        raise RecusaDoAssistente(RESPOSTA_PENDENTE)
    if turnos_da_conversa(tenant_id=tenant_id, conversa_id=trancada.pk) >= TURNOS_POR_CONVERSA:
        raise RecusaDoAssistente(CONVERSA_CHEIA)
    maxima = mensagens_da_conversa(tenant_id=tenant_id, conversa_id=trancada.pk).aggregate(
        maxima=Max("position")
    )["maxima"]
    mensagem = _abrir_turno(
        conversa=trancada, autor=autor, pergunta=pergunta, lingua=lingua, posicao=(maxima or 0) + 1
    )
    trancada.last_message_at = timezone.now()
    trancada.save(update_fields=["last_message_at", "updated_at"])
    _enfileirar(mensagem, request_id=request_id)
    return mensagem


@transaction.atomic
def apagar_conversa(*, conversa: Conversation) -> None:
    """Apaga a conversa; o `CASCADE` leva os turnos. Não é append-only (decisão 2)."""
    conversa.delete()


@transaction.atomic
def purgar_conversas_do_tenant(
    *, tenant_id: UUID, limite: datetime, lote: int = LOTE_DA_PURGA
) -> int:
    """Apaga, em lotes, as conversas com `last_message_at` anterior a `limite`.

    Corre dentro de `tenant_scope(tenant_id)` (é o corpo de uma `TenantTask`):
    a política só deixa ver — e apagar — as deste tenant. Devolve quantas
    conversas apagou.
    """
    apagadas = 0
    while True:
        ids = conversas_expiradas(tenant_id=tenant_id, limite=limite, lote=lote)
        if not ids:
            return apagadas
        Conversation.objects.filter(tenant_id=tenant_id, pk__in=ids).delete()
        apagadas += len(ids)


# ---------------------------------------------------------------------------
# O ciclo de tool-use: o corpo de `agents.responder_mensagem`
# ---------------------------------------------------------------------------
def responder(*, tenant_id: UUID, mensagem_id: UUID, request_id: str | None = None) -> str:
    """Responde a um turno `pendente`. Devolve o estado em que o turno ficou.

    Idempotente pela linha: um turno que já não está `pendente` devolve
    `ja_tratada` sem chamar o modelo — uma segunda entrega da tarefa não paga
    duas vezes. Reconfirma a pertença no arranque (`pertenca_revogada` se a
    política já não devolver linha), verifica o orçamento antes de **cada**
    chamada, grava cada tool à medida, e fecha com um dos códigos da lista.
    Nunca levanta por causa do modelo: o que levanta é bug nosso.
    """
    mensagem = (
        ChatMessage.objects.select_related("conversation")
        .filter(tenant_id=tenant_id, pk=mensagem_id)
        .first()
    )
    if mensagem is None:
        logger.warning(
            "turno não encontrado no âmbito", extra={"event": "chat", "outcome": "nao_encontrada"}
        )
        return "nao_encontrada"
    if mensagem.status != EstadoDaMensagem.PENDENTE:
        return "ja_tratada"

    opcao = (
        opcao_de_tenant(mensagem.asked_by_id, tenant_id) if mensagem.asked_by_id else None
    )
    if opcao is None:
        _fechar_turno_com_erro(
            mensagem,
            codigo=CodigoDeErroDaMensagem.PERTENCA_REVOGADA,
            razao="quem perguntou já não tem pertença activa neste estabelecimento",
        )
        return _registar(mensagem, request_id, "erro")

    _comecar_turno(mensagem)
    agora = timezone.now()
    inicio_do_dia = inicio_do_dia_de_negocio(tenant_id=tenant_id)
    contexto = tools.contexto_para(
        tenant_id=tenant_id,
        papel=mensagem.role_at_time,
        agora=agora,
        inicio_do_dia=inicio_do_dia,
        # A língua do turno decide que manual a `ajuda_sobre` lê, e quem
        # pergunta decide o "és tu" da equipa (ADR 0028).
        lingua=mensagem.language,
        user_id=mensagem.asked_by_id,
    )
    sistema = prompt_de_sistema(
        estabelecimento=opcao.name,
        papel=mensagem.role_at_time,
        localizacoes=listar_localizacoes(tenant_id=tenant_id),
        agora=agora,
        hoje=contexto.hoje,
        inicio_do_dia=inicio_do_dia,
        lingua=mensagem.language,
    )
    mensagens = [*_historico(mensagem), {"role": "user", "content": mensagem.question}]
    definicoes = tools.definicoes_para(mensagem.role_at_time)
    teto = int(settings.AGENTS_CHAT_MAX_TOOL_ITERATIONS)
    orcamento = Decimal(settings.AGENTS_CHAT_DAILY_BUDGET_EUR)

    for iteracao in range(1, teto + 1):
        if custo_do_dia(tenant_id=tenant_id) >= orcamento:
            _fechar_turno_com_erro(
                mensagem,
                codigo=CodigoDeErroDaMensagem.TETO_DE_CUSTO,
                razao="o orçamento diário do estabelecimento esgotou-se",
            )
            return _registar(mensagem, request_id, "erro")
        try:
            resposta = conversar(
                sistema=sistema,
                mensagens=mensagens,
                tools=definicoes,
                max_tokens=int(settings.AGENTS_CHAT_MAX_TOKENS),
                timeout=int(settings.AGENTS_CHAT_TIMEOUT_S),
                idempotency_key=f"chat:{mensagem.id}:{iteracao}",
            )
        except TempoEsgotado as erro:
            _fechar_turno_com_erro(
                mensagem, codigo=CodigoDeErroDaMensagem.TEMPO_ESGOTADO, razao=str(erro)
            )
            return _registar(mensagem, request_id, "erro")
        except RespostaInvalida as erro:
            _fechar_turno_com_erro(
                mensagem, codigo=CodigoDeErroDaMensagem.RESPOSTA_INVALIDA, razao=str(erro)
            )
            return _registar(mensagem, request_id, "erro")
        except ModeloOcupado as erro:
            # Sobrecarga do fornecedor: as retentativas do `modelo.py` já
            # falharam. O código é próprio porque a frase que a pessoa lê é
            # "está ocupado, tenta outra vez" e não "falhou".
            _fechar_turno_com_erro(
                mensagem, codigo=CodigoDeErroDaMensagem.MODELO_OCUPADO, razao=str(erro)
            )
            return _registar(mensagem, request_id, "erro")
        except ErroDoModelo as erro:
            _fechar_turno_com_erro(
                mensagem, codigo=CodigoDeErroDaMensagem.ERRO_DO_MODELO, razao=str(erro)
            )
            return _registar(mensagem, request_id, "erro")

        _acumular(mensagem, resposta, iteracao=iteracao)
        if resposta.chamadas:
            mensagens.append(resposta.mensagem_verbatim)
            for chamada in resposta.chamadas:
                try:
                    resultado = tools.executar(
                        nome=chamada.nome, argumentos=chamada.argumentos, contexto=contexto
                    )
                except Exception:
                    # Sem isto o turno ficava `a_responder` até ao tempo esgotado
                    # derivado. O traceback vai para o log do worker; a linha
                    # leva só o nome da tool, nunca os argumentos.
                    logger.exception(
                        "tool do assistente levantou",
                        extra={"event": "chat_tool", "outcome": "excecao", "tool": chamada.nome},
                    )
                    _fechar_turno_com_erro(
                        mensagem,
                        codigo=CodigoDeErroDaMensagem.ERRO_DO_MODELO,
                        razao=f"a ferramenta {chamada.nome} falhou",
                    )
                    return _registar(mensagem, request_id, "erro")
                _gravar_tool(mensagem, resultado)
                mensagens.append(
                    {"role": "tool", "tool_call_id": chamada.id, "content": resultado.conteudo}
                )
            continue

        texto = resposta.texto.strip()
        if not texto:
            _fechar_turno_com_erro(
                mensagem,
                codigo=CodigoDeErroDaMensagem.RESPOSTA_INVALIDA,
                razao=f"o modelo parou sem texto ({resposta.motivo_de_paragem or 'sem motivo'})",
            )
            return _registar(mensagem, request_id, "erro")
        _fechar_turno_com_resposta(mensagem, texto)
        return _registar(mensagem, request_id, "respondida")

    _fechar_turno_com_erro(
        mensagem,
        codigo=CodigoDeErroDaMensagem.TETO_DE_ITERACOES,
        razao=f"o modelo pediu tools em {teto} chamadas seguidas sem responder",
    )
    return _registar(mensagem, request_id, "erro")


def _historico(mensagem: ChatMessage) -> list[dict[str, str]]:
    """Os turnos respondidos anteriores, como pares `user`/`assistant`.

    Só os `respondida`: um turno com erro não ensina nada ao modelo, e um
    `tool_calls` antigo não se repete — o que fica é a pergunta e a resposta.
    """
    historico: list[dict[str, str]] = []
    anteriores = mensagens_da_conversa(
        tenant_id=mensagem.tenant_id, conversa_id=mensagem.conversation_id
    ).filter(position__lt=mensagem.position, status=EstadoDaMensagem.RESPONDIDA)
    for turno in anteriores:
        historico.append({"role": "user", "content": turno.question})
        historico.append({"role": "assistant", "content": turno.answer})
    return historico


@transaction.atomic
def _comecar_turno(mensagem: ChatMessage) -> None:
    mensagem.status = EstadoDaMensagem.A_RESPONDER
    mensagem.started_at = timezone.now()
    mensagem.model = nome_do_modelo_de_chat()
    mensagem.prompt_version = VERSAO_DO_PROMPT_DO_CHAT
    mensagem.save(update_fields=["status", "started_at", "model", "prompt_version", "updated_at"])


@transaction.atomic
def _acumular(mensagem: ChatMessage, resposta: RespostaDoModelo, *, iteracao: int) -> None:
    """Tokens, custo e iteração de uma chamada, gravados logo: é o que o teto lê."""
    mensagem.input_tokens += resposta.input_tokens
    mensagem.output_tokens += resposta.output_tokens
    mensagem.cost_eur = Decimal(mensagem.cost_eur) + resposta.cost_eur
    mensagem.iterations = iteracao
    mensagem.save(
        update_fields=["input_tokens", "output_tokens", "cost_eur", "iterations", "updated_at"]
    )


@transaction.atomic
def _gravar_tool(mensagem: ChatMessage, resultado: tools.ResultadoDaTool) -> None:
    """Uma entrada do rasto, gravada **à medida** — é o que o ecrã lê em `a_responder`."""
    mensagem.tool_calls = [
        *mensagem.tool_calls,
        entrada_de_rasto(
            nome=resultado.nome,
            args=resultado.args,
            rows=resultado.linhas,
            truncated=resultado.truncado,
            ms=resultado.ms,
            ok=resultado.ok,
        ),
    ]
    mensagem.save(update_fields=["tool_calls", "updated_at"])
    # Uma linha por tool: o nome é nosso (não é PII) e vai em `outcome`; os
    # argumentos — texto do modelo — nunca vão para o log.
    logger.info(
        "tool do assistente executada",
        extra={
            "event": "chat_tool",
            "outcome": resultado.nome if resultado.ok else f"{resultado.nome}:recusada",
            "duration_ms": resultado.ms,
            "count": resultado.linhas,
        },
    )


@transaction.atomic
def _fechar_turno_com_resposta(mensagem: ChatMessage, texto: str) -> None:
    mensagem.answer = texto
    mensagem.status = EstadoDaMensagem.RESPONDIDA
    mensagem.finished_at = timezone.now()
    mensagem.save(update_fields=["answer", "status", "finished_at", "updated_at"])
    Conversation.objects.filter(tenant_id=mensagem.tenant_id, pk=mensagem.conversation_id).update(
        last_message_at=mensagem.finished_at, updated_at=mensagem.finished_at
    )


@transaction.atomic
def _fechar_turno_com_erro(mensagem: ChatMessage, *, codigo: str, razao: str) -> None:
    """`erro` com código e razão legível — classe e mensagem, nunca traceback."""
    mensagem.status = EstadoDaMensagem.ERRO
    mensagem.error_code = codigo
    mensagem.error = razao[:_RAZAO_MAXIMA]
    mensagem.finished_at = timezone.now()
    if mensagem.started_at is None:
        mensagem.started_at = mensagem.finished_at
    mensagem.save(
        update_fields=["status", "error_code", "error", "finished_at", "started_at", "updated_at"]
    )


def _registar(mensagem: ChatMessage, request_id: str | None, estado: str) -> str:
    """Uma linha de log por turno: modelo, tokens, custo, iterações, tools — nunca o texto."""
    duracao = 0
    if mensagem.started_at and mensagem.finished_at:
        duracao = int((mensagem.finished_at - mensagem.started_at).total_seconds() * 1000)
    logger.info(
        "turno do assistente fechado",
        extra={
            "event": "chat_turno",
            "outcome": mensagem.error_code or estado,
            "duration_ms": duracao,
            "count": mensagem.iterations,
            "event_id": request_id,
        },
    )
    return estado
