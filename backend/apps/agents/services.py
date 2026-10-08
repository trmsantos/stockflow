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
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.agents.modelo import VERSAO_DO_PROMPT, RespostaDoModelo
from apps.agents.models import EstadoDaExtracao, Extraction
from apps.agents.serializers import leitura_do_payload

__all__ = ["abrir_tentativa", "fechar_com_erro", "fechar_com_resposta"]


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
