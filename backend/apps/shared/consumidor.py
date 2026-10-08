"""O consumidor da outbox: lê a linha, publica aos handlers, marca-a.

É o passo 10 do `ARCHITECTURE.md` §4, e existe porque a alternativa cobrou o
preço numa máquina real. Medido a 2026-10-08: a receção de mercadoria enfileirava
com `transaction.on_commit` + `.delay()` e um worker de sete dias — imagem
anterior a estas apps — respondeu às duas tarefas com

    Received unregistered task of type 'purchasing.normalizar_pagina'.
    The message has been ignored and discarded.

Fila a zero, **nenhum rasto na aplicação**, e um documento preso em
`a_normalizar` para sempre. A outbox não torna a entrega infalível: torna o
atraso numa **linha de uma tabela que se consulta**, com `attempts`, `last_error`
e um `processed_at` nulo a dizer que ninguém reagiu. É isso, e só isso, que ela
compra — e é a diferença entre um bug que se encontra em dois minutos e um que
não se encontra.

## A latência, e a troca que ela é

O consumidor é uma tarefa agendada pelo `beat` a cada **5 segundos**
(`CELERY_BEAT_SCHEDULE`, em `config/settings/base.py`). O que isso custa está
medido: a rasterização de uma página arrancava em ~0 s com o `.delay()` directo e
passa a arrancar em **0–5 s**. O ecrã de entrada de documento sonda a 2 s com um
orçamento de 3 minutos (ADR 0021), logo cabe com folga — cinco segundos são duas
sondagens, não um timeout. É a troca inteira: cinco segundos de latência por um
facto que fica escrito em vez de desaparecer num broker.

Os 0–5 s têm um limite nomeado: a passagem corre na **mesma fila** (`default`) e
no mesmo worker que as tarefas de trabalho, com `--concurrency=2`. Duas tarefas
longas a ocupar os dois slots — uma chamada a um modelo é segundos, não
milissegundos — atrasam a passagem seguinte, e o `expires` de 60 s da entrada do
`beat` descarta as que entretanto ficaram velhas em vez de as acumular. A saída é
uma fila própria para o consumidor (`task_routes` mais um worker dedicado), e é
uma decisão de operação que não se toma antes de haver uma chamada a um modelo a
sério para medir.

## Os dois âmbitos, nesta ordem e sem os misturar

A tarefa é `tenant_scope_exempt` (a única dispensa legítima a par do cron que
itera tenants — ADR 0005, `apps/shared/tasks.py`): não tem tenant nenhum e tem
de poder reclamar linhas de todos.

1. **`system_scope()`** para ler e reclamar a linha. É o disjunto
   `app.scope = 'system'` da política, que **só** a tabela da outbox tem;
2. o bloco **fecha**;
3. **`tenant_scope(linha.tenant_id)`** para chamar os handlers. Fecha-se o
   primeiro antes de abrir o segundo porque um `set_config` local sobrevive ao
   savepoint e o tenant ficaria colado ao resto da transação de sistema
   (`apps/shared/db.py`, ADR 0005) — e o `tenant_scope` recusa-se a abrir lá
   dentro, de propósito.

Dentro de `system_scope()` o `app.tenant_id` está a NULL, pelo que ler uma tabela
de um tenant a partir de lá devolve **zero linhas sem erro**. Daí a regra do
`ARCHITECTURE.md` §4.9: o consumidor *"reentra em `tenant_scope(row.tenant_id)`
antes de tocar em mais nada"*. O guarda de âmbito de `tests/conftest.py` lê o
predicado de cada política do catálogo e falha se alguém o esquecer.

## `processed_at` commita **com** o handler, e é isso que faz a entrega valer

A marca de processado é escrita dentro da **mesma** transação em que os handlers
correm. Se um deles levantar, a transação desfaz tudo — o que o handler escreveu
e a marca — e a linha volta ao estado pendente. O contrário (marcar numa
transação à parte) tinha uma janela em que o efeito já estava feito e a marca
não, e toda a correção passava a depender da idempotência.

A idempotência continua a ser regra, porque sobra um caso que a transação não
cobre: um evento com **dois** handlers em que o segundo levanta desfaz também o
primeiro, e na passagem seguinte o primeiro volta a correr. É o preço de não ter
estado por handler (uma segunda tabela, com uma linha por par evento/handler), e
está pago pela regra que o `ARCHITECTURE.md` §4 já escrevia: *"handlers são
idempotentes (chave: `event_id`)"*. Cada handler deste projeto diz no seu
docstring como é que o é.

## `attempts`, o teto, e porque é que o teto não é opcional

`attempts` é incrementado **antes** de os handlers correrem, numa transação
própria. Duas consequências, as duas desejadas:

* um handler que mate o worker a meio (SIGKILL, OOM, segfault no rasterizador)
  deixa a tentativa contada. Incrementar no fim deixava esse caso a repetir-se
  para sempre, que é a definição de uma mensagem envenenada;
* a reclamação é também a **exclusão mútua**: o `UPDATE ... WHERE id = %s AND
  processed_at IS NULL AND attempts = %s` serializa-se no lock da linha e a
  segunda passagem concorrente não encontra linha para reclamar. Não substitui a
  idempotência — complementa-a.

Ao chegar a `TETO_DE_TENTATIVAS` a linha **sai do conjunto de candidatas** e fica
lá: `processed_at` nulo, `last_error` com a razão, visível ao tenant pela
política e ao operador pela métrica "tamanho da outbox" (`ARCHITECTURE.md` §8,
*"outbox com itens > 10 min"*). Não se marca como processada — isso era perder o
evento com um nome bonito.

O teto não é só higiene de dead-letter: **sem ele há fome**. As candidatas saem
por `created_at` crescente e em lotes de `LOTE`; `LOTE` linhas envenenadas e mais
antigas ocupavam o lote inteiro em cada passagem, para sempre, e os eventos novos
nunca chegavam a ser lidos. Com teto, uma linha envenenada rouba `TETO_DE_
TENTATIVAS` passagens — ~25 segundos — e sai.

**Repetir uma linha esgotada é uma decisão humana**: põe-se o `attempts` a zero.
Fica nomeado o que falta para isso ser confortável — a outbox não está no admin
(ADR 0007: só lá entram modelos sem política) e não há comando de gestão, logo
hoje é um `UPDATE` em psql. Com um módulo parcialmente deployado — o consumidor a
correr e o `ready()` de um módulo a não ter registado os seus handlers — o teto
gasta-se em 25 segundos e os eventos desse intervalo precisam desse `UPDATE`.

## O que este módulo **não** faz

Não apaga linhas processadas. A retenção é a pergunta que o `apps/shared/
outbox.py` deixou em aberto (*"a limpeza é uma tarefa periódica — que é também
onde se decide quanto tempo é 'curto'"*) e continua em aberto: decidir o prazo é
decidir quanto tempo se consegue responder a "que eventos gerou esta receção?",
e isso é uma decisão do dono. Com o `beat` a existir, passa a ser uma entrada de
configuração e não código novo.
"""

from __future__ import annotations

import logging
from collections import Counter
from uuid import UUID

from django.utils import timezone

from apps.shared.db import system_scope, tenant_scope
from apps.shared.handlers import EventoEntregue, handlers_de
from apps.shared.outbox import OutboxEvent

__all__ = [
    "ENTREGUE",
    "FALHOU",
    "JA_RECLAMADA",
    "LIMITE_DO_ERRO",
    "LOTE",
    "SEM_HANDLER",
    "TETO_DE_TENTATIVAS",
    "consumir_outbox",
]

logger = logging.getLogger(__name__)

#: Quantas linhas uma passagem trata, no máximo. Com uma passagem a cada 5 s dá
#: 600 eventos/minuto de capacidade, muito acima do que um estabelecimento
#: produz (um documento de fornecedor gera um evento). O teto existe pelo lado
#: oposto: uma passagem que tratasse a outbox inteira depois de uma paragem longa
#: ficava minutos a correr, passava o `task_soft_time_limit` e era morta a meio —
#: e o `beat` tinha empilhado passagens novas entretanto.
LOTE = 50

#: Quantas entregas falhadas uma linha suporta antes de deixar de ser candidata.
#: Cinco, que a 5 s de intervalo são ~25 segundos: tempo para um pico de carga ou
#: um reinício de base de dados passarem, e pouco o suficiente para uma linha
#: envenenada não roubar o lote a ninguém. Ver a secção do teto, no topo.
TETO_DE_TENTATIVAS = 5

#: Quantos caracteres da mensagem de erro cabem no `last_error`. A coluna é
#: `TextField` e sem limite uma mensagem de megabytes ficava lá — o `last_error`
#: é para ser lido por uma pessoa, não arquivado.
LIMITE_DO_ERRO = 1000

#: Os resultados de uma passagem, que são as chaves do resumo que a tarefa
#: devolve. Lista fechada e com nome: é o que um teste afirma e o que aparece no
#: `outcome` dos logs.
ENTREGUE = "entregue"
SEM_HANDLER = "sem_handler"
FALHOU = "falhou"
JA_RECLAMADA = "ja_reclamada"

#: Nome da operação nos logs (`config/log.py`, convenção 2: a mensagem é uma
#: constante e o que varia vai em `extra=`).
EVENTO_DE_LOG = "outbox.consumo"


def consumir_outbox(*, lote: int = LOTE) -> dict[str, int]:
    """Uma passagem pela outbox. Devolve o resumo por resultado.

    Chamada pela tarefa `shared.consumir_outbox`, que o `beat` agenda. Corre
    **fora** de qualquer âmbito: abre os seus, nesta ordem e sem os misturar.

    O resumo (`{"entregue": 3, "sem_handler": 1}`) é o valor de retorno da tarefa
    e o que o log da passagem conta. Uma passagem sem nada para fazer — que é a
    esmagadora maioria delas, uma a cada 5 segundos — devolve `{}` e **não escreve
    log nenhum**: a alternativa eram 17 mil linhas por dia a dizer que não havia
    nada a dizer.
    """
    resumo: Counter[str] = Counter()
    for event_id in _candidatas(lote):
        resumo[_tratar(event_id)] += 1
    if resumo:
        logger.info(
            "passagem pela outbox",
            extra={
                "event": EVENTO_DE_LOG,
                "outcome": "passagem",
                "count": sum(resumo.values()),
            },
        )
    return dict(resumo)


def _candidatas(lote: int) -> list[UUID]:
    """Os ids das linhas pendentes que ainda têm tentativas, mais antigas primeiro.

    Só os ids, e numa transação que fecha antes de a primeira ser tratada: a
    alternativa — manter a lista trancada com `FOR UPDATE` enquanto os handlers
    correm — é impossível por construção, porque o `system_scope` tem de fechar
    antes de o `tenant_scope` abrir.

    A ordem é `created_at` e o índice que a serve é o parcial
    `outbox_pendentes_idx`, que existe desde a migração que criou a tabela
    exactamente para esta query.
    """
    with system_scope():
        return list(
            OutboxEvent.objects.filter(
                processed_at__isnull=True, attempts__lt=TETO_DE_TENTATIVAS
            )
            .order_by("created_at")
            .values_list("id", flat=True)[:lote]
        )


def _tratar(event_id: UUID) -> str:
    """Reclama uma linha e entrega-a aos handlers. Devolve o resultado."""
    linha = _reclamar(event_id)
    if linha is None:
        # Outra passagem chegou primeiro (ou a linha foi processada entre a
        # listagem e agora). Não é erro e não se loga: é o mecanismo a funcionar.
        return JA_RECLAMADA

    handlers = handlers_de(linha.event_type)
    if not handlers:
        # **O defeito de 2026-10-08, na forma em que esta feature o resolve.** O
        # Celery, no lugar dele, escrevia `ignored and discarded` e a mensagem
        # desaparecia. Aqui a linha fica, com `processed_at` nulo e com a razão
        # na coluna — e o `event_type` vai para o `last_error` e não para a
        # mensagem de log porque a mensagem é uma constante (`config/log.py`).
        _anotar(
            linha,
            f"nenhum handler subscrito a {linha.event_type} neste processo. "
            "Um módulo registra os seus handlers no ready() do AppConfig "
            "(apps/shared/handlers.py); se este processo é anterior ao módulo "
            "que reage a este evento, a linha fica à espera dele.",
            SEM_HANDLER,
        )
        return SEM_HANDLER

    evento = EventoEntregue(
        event_id=linha.id,
        tenant_id=linha.tenant_id,
        event_type=linha.event_type,
        payload=linha.payload,
        attempts=linha.attempts,
    )
    try:
        with tenant_scope(linha.tenant_id):
            for handler in handlers:
                handler(evento)
            _marcar_processada(linha)
    except Exception as erro:
        # Largo de propósito, e a razão está no docstring de `_anotar`: um
        # handler é código de outro módulo e pode levantar o que quiser.
        _anotar(linha, _razao(erro), FALHOU)
        return FALHOU
    return ENTREGUE


def _reclamar(event_id: UUID) -> OutboxEvent | None:
    """Incrementa o `attempts` da linha e devolve-a. `None` se já não é nossa.

    O `UPDATE` condicional é a **reclamação**: `attempts` faz de coluna de versão
    e duas passagens concorrentes serializam-se no lock da linha — a segunda vê
    um `attempts` diferente, não actualiza nada, e desiste desta linha.

    Numa transação própria, e **antes** dos handlers, para a tentativa ficar
    contada mesmo que o processo morra a meio da entrega. Ver a secção do teto.
    """
    with system_scope():
        linha = OutboxEvent.objects.filter(
            pk=event_id, processed_at__isnull=True
        ).first()
        if linha is None:
            return None
        reclamadas = OutboxEvent.objects.filter(
            pk=event_id, processed_at__isnull=True, attempts=linha.attempts
        ).update(attempts=linha.attempts + 1)
        if not reclamadas:
            return None
        linha.attempts += 1
        return linha


def _marcar_processada(linha: OutboxEvent) -> None:
    """Escreve o `processed_at`. **Dentro da transação dos handlers.**

    Corre sob `tenant_scope(linha.tenant_id)`, onde a política da outbox deixa
    ver e escrever esta linha pelo disjunto normal (`tenant_id = app.tenant_id`)
    e não pelo de sistema.

    Limpa o `last_error`: a linha passou, e uma razão de erro antiga ao lado de
    um `processed_at` preenchido mandava alguém investigar um problema resolvido.
    """
    OutboxEvent.objects.filter(pk=linha.id, processed_at__isnull=True).update(
        processed_at=timezone.now(), last_error=""
    )


def _anotar(linha: OutboxEvent, razao: str, resultado: str) -> None:
    """Grava a razão na linha e **deixa o `processed_at` nulo**.

    O `attempts` já foi incrementado pela reclamação, logo aqui só se escreve o
    texto. A escrita é sob `system_scope()` e não sob o âmbito do tenant: é
    contabilidade do consumidor sobre uma entrega que não aconteceu, e a
    transação do tenant acabou de ser desfeita.

    `except Exception` largo em quem chama, e é deliberado: um handler é código de
    outro módulo e pode levantar o que quiser. Uma lista de exceções esperadas
    aqui deixava passar a excepção não prevista — que é precisamente a que não
    pode derrubar a passagem inteira e fazer as outras linhas perderem a vez.
    """
    with system_scope():
        OutboxEvent.objects.filter(pk=linha.id, processed_at__isnull=True).update(
            last_error=razao[:LIMITE_DO_ERRO]
        )
    contexto = {
        "event": EVENTO_DE_LOG,
        "outcome": resultado,
        "event_id": str(linha.id),
        # Explícito, porque fora do `tenant_scope` o contexto de log não o tem:
        # quem loga em nome de outro tenant diz qual (`config/log.py`).
        "tenant_id": str(linha.tenant_id),
        "count": linha.attempts,
    }
    if linha.attempts >= TETO_DE_TENTATIVAS:
        logger.error(
            "evento na outbox sem entrega e sem mais tentativas",
            extra={**contexto, "outcome": "esgotado"},
        )
        return
    logger.warning("evento na outbox não entregue", extra=contexto)


def _razao(erro: BaseException) -> str:
    """A classe e a **primeira linha** da mensagem. Nunca o traceback.

    O corte na primeira linha não é cosmética: é onde o psycopg põe a fronteira
    entre o que aconteceu e os valores da linha em conflito. Um
    `UniqueViolation` traz `DETAIL: Key (tenant_id, sha256)=(…) already exists.`
    na linha seguinte, e esta coluna é lida no admin (`apps/shared/outbox.py`,
    `SECURITY.md` §1). É um corte **estrutural** e não um scrubber de padrões —
    o `config/log.py` argumenta por extenso contra os segundos.

    O que isto não alcança: a mensagem que o próprio handler escreve. Um
    `ValueError(f"o produto {nome} não existe")` põe o nome na primeira linha, e
    a responsabilidade é de quem o escreveu — como em qualquer log deste projeto.
    """
    mensagem = str(erro).strip().splitlines()
    primeira = mensagem[0] if mensagem else ""
    return f"{type(erro).__name__}: {primeira}".strip()
