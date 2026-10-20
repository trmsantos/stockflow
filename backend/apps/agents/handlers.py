"""O que o `agents` faz quando um documento fecha: pedir a leitura ao modelo.

Este ficheiro é o que o topo do `apps/purchasing/extracao.py` prometia:

> **O mecanismo certo era o evento.** Um `DocumentoFechado` na outbox resolvia
> isto sem porto nenhum: o `purchasing` publicava, o `handlers.py` do `agents`
> subscrevia, e nenhum dos dois conhecia o outro. Não há consumidor da outbox
> (ADR 0010, ADR 0020), logo um evento hoje significa que a extração **nunca
> corre**. A condição para trocar o porto pelo evento é exactamente essa:
> **existir um consumidor da outbox**.

A condição cumpriu-se, e por isso a metade `pedir` do porto deixou de existir: o
`purchasing` publica `DocumentoFechado` e não conhece quem o lê. A outra metade
(`leituras`) **fica**, porque é uma pergunta e não um aviso — o `DocumentoOut`
precisa da última leitura de cada documento no instante em que serve a resposta,
e isso é uma chamada, não um evento.

A aresta de import é a mesma que já estava declarada (`agents -> purchasing`), e
agora é mais fraca: `apps.purchasing.events` em vez de `apps.purchasing.api`. Um
`events.py` é um DTO sem dependências (ADR 0003), o que é exactamente o que se
quer de uma subscrição.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.agents.selectors import ja_houve_tentativa
from apps.purchasing.events import DocumentoFechado, ReleituraPedida
from apps.shared.handlers import EventoEntregue, subscrever

__all__ = ["pedir_extracao", "registar_handlers", "releitura_pedida"]

logger = logging.getLogger(__name__)


def registar_handlers() -> None:
    """Liga os handlers deste módulo. Chamado no `ready()` do `AgentsConfig`."""
    subscrever(DocumentoFechado, pedir_extracao)
    subscrever(ReleituraPedida, releitura_pedida)


def pedir_extracao(evento: EventoEntregue) -> None:
    """Enfileira a leitura do documento pelo modelo, uma vez por documento.

    ## Como é idempotente

    Pela existência de uma tentativa: se o documento já tem uma linha em
    `agents_extraction`, este evento já foi tratado e não se pede nada. É a
    verificação que falta aqui ser feita e não poder ser delegada à tabela, e a
    razão é dinheiro — `abrir_tentativa` é `max(attempt) + 1` de propósito (ADR
    0021, decisão 4: cada abertura é uma tentativa nova, não uma sobreposição),
    logo uma segunda entrega do mesmo evento **pagaria** uma segunda leitura ao
    fornecedor do modelo. A `idempotency_key` única da tabela é meia garantia:
    impede repetir a *mesma* tentativa, não impede abrir a seguinte.

    O que esta verificação deliberadamente **não** impede é uma re-extração
    pedida por uma pessoa. Isso não passa por aqui: entra pelo `ReleituraPedida`
    e pelo `releitura_pedida` lá em baixo, onde a intenção é explícita e o custo
    é de quem carregou no botão (ADR 0031, E).

    ## O `on_commit`, e a janela que ele deixa aberta

    O consumidor chamou isto dentro de `tenant_scope(evento.tenant_id)`, que é
    uma transação — e é nela que o `processed_at` da linha da outbox é escrito.
    Enfileirar antes do commit publicava um facto que pode desaparecer, logo o
    `on_commit` não é opcional.

    Fica nomeada a janela que sobra, porque é pequena e não é zero: se o processo
    morrer **entre** o commit e a publicação no broker, a linha da outbox fica
    marcada como processada e a tarefa nunca foi enfileirada. A outbox garante
    que o *evento* não se perde, não que a mensagem do broker não se perca —
    fechar isso pedia uma segunda outbox, para as mensagens. O sintoma é o mesmo
    do defeito que originou esta feature (um documento preso em `a_extrair`), mas
    agora com um relógio: o estado derivado lê-se `erro` ao fim de dez minutos
    (`JANELA_DA_EXTRACAO`) em vez de ficar preso para sempre.
    """
    tenant_id = evento.tenant_id
    documento_id = evento.uuid_do_payload("documento_id")
    if ja_houve_tentativa(tenant_id=tenant_id, documento_id=documento_id):
        return

    # Import no corpo e não no topo: o `tasks.py` importa o `modelo.py` e os
    # serviços, e este ficheiro é importado pelo `ready()` do `AppConfig`. É o
    # mesmo padrão do `semear_demonstracao` no `accounts/api.py`.
    from apps.agents.tasks import extrair_documento

    transaction.on_commit(
        lambda: extrair_documento.delay(
            tenant_id=str(tenant_id), documento_id=str(documento_id)
        )
    )
    logger.info(
        "extração pedida para um documento",
        extra={
            "event": "extracao",
            "outcome": "enfileirada",
            "event_id": str(evento.event_id),
        },
    )


def releitura_pedida(evento: EventoEntregue) -> None:
    """Enfileira **outra** leitura deste documento, porque uma pessoa a pediu.

    O contrário do `pedir_extracao`: aqui não há verificação de "já houve
    tentativa", e é esse o ponto. As três recusas (receção confirmada, leitura
    em curso, tecto de tentativas) foram feitas no `purchasing.services`, onde a
    intenção é explícita e o custo é de quem carregou no botão — e o tecto
    diário em euros é verificado outra vez dentro da tarefa, imediatamente antes
    da chamada.

    O `on_commit` é obrigatório pela mesma razão do irmão: o consumidor abriu uma
    transação, e enfileirar antes do commit é publicar um facto que pode
    desaparecer.
    """
    tenant_id = evento.tenant_id
    documento_id = evento.uuid_do_payload("documento_id")

    from apps.agents.tasks import extrair_documento

    transaction.on_commit(
        lambda: extrair_documento.delay(
            tenant_id=str(tenant_id), documento_id=str(documento_id)
        )
    )
    logger.info(
        "releitura pedida para um documento",
        extra={
            "event": "extracao",
            "outcome": "releitura_enfileirada",
            "event_id": str(evento.event_id),
        },
    )
