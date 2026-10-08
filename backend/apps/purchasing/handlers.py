"""O que o `purchasing` faz quando um documento fecha: rasterizar as páginas.

Um `handlers.py` é o sítio que o `ARCHITECTURE.md` §3 nomeia para as subscrições
a eventos, e nada aqui é importável de fora do módulo — quem reage a um evento do
`purchasing` de **outro** módulo tem o seu próprio `handlers.py` (é o caso do
`apps/agents/handlers.py`, que subscreve o mesmo evento para pedir a extração).

As subscrições registam-se no `ready()` do `PurchasingConfig`, e é de lá que vem
a única razão para este ficheiro ter uma função `registar_handlers()` em vez de
chamadas no corpo do módulo: um `apps.py` não pode importar models no topo, logo
importa este ficheiro dentro do `ready()`, e um efeito no corpo do módulo
tornava o registo dependente de **quando** alguém o importa. Com a função, o
registo acontece onde está escrito que acontece.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.purchasing.events import DocumentoFechado
from apps.purchasing.models import DocumentPage
from apps.shared.handlers import EventoEntregue, subscrever

__all__ = ["rasterizar_paginas_pendentes", "registar_handlers"]

logger = logging.getLogger(__name__)


def registar_handlers() -> None:
    """Liga os handlers deste módulo. Chamado no `ready()` do `AppConfig`.

    Idempotente, porque o `subscrever` o é para o mesmo par: um `ready()` corre
    mais de uma vez em caminhos de teste do Django, e um registo duplicado fazia
    a rasterização ser enfileirada duas vezes por documento.
    """
    subscrever(DocumentoFechado, rasterizar_paginas_pendentes)


def rasterizar_paginas_pendentes(evento: EventoEntregue) -> None:
    """Enfileira uma `normalizar_pagina` por página sem imagem.

    ## Como é idempotente

    Pelo filtro, e não por uma marca: o que ele devolve são as páginas com
    `normalized_at IS NULL`. Uma segunda entrega do mesmo evento — depois de um
    handler irmão levantar, ou de uma passagem interrompida — vê só o que ainda
    falta, e se não faltar nada não enfileira nada. A `event_id` é a chave de
    idempotência do contrato (ARCHITECTURE.md §4) e aqui ela não precisa de ser
    guardada: o estado da própria página é a marca, e é uma marca que não pode
    dessincronizar-se do trabalho feito.

    E a tarefa é idempotente pelo mesmo mecanismo um nível abaixo: rasterizar
    duas vezes a mesma página escreve os mesmos bytes no mesmo caminho.

    ## Corre dentro do âmbito, e é isso que o torna simples

    O consumidor abriu `tenant_scope(evento.tenant_id)` antes de chamar isto,
    pelo que esta leitura é feita com a política a alcançá-la. A versão anterior
    deste código — um `transaction.on_commit` dentro do serviço — tinha de ler as
    páginas **antes** do `on_commit` porque a closure corria fora do âmbito, onde
    a política devolve zero linhas sem erro. Era um defeito a sério e apareceu em
    produção como *"a imagem nunca fica pronta"*, sem uma linha de log. A outbox
    desfaz a armadilha em vez de a contornar.

    O `on_commit` do enfileiramento **continua a ser obrigatório**, e por isso
    está aqui: o que o consumidor abriu é uma transação, e enfileirar antes de
    ela commitar é publicar um facto que pode desaparecer — a tarefa correria
    contra páginas que não existem. Com o `on_commit`, as tarefas saem depois de
    a transação do handler (e a marca `processed_at`, que commita com ela) estar
    escrita.
    """
    tenant_id = evento.tenant_id
    documento_id = evento.uuid_do_payload("documento_id")
    paginas = list(
        DocumentPage.objects.filter(
            tenant_id=tenant_id, document_id=documento_id, normalized_at__isnull=True
        ).values_list("id", flat=True)
    )
    if not paginas:
        return

    # Import no corpo e não no topo: o `tasks.py` importa o `services.py`, que
    # importa o `models.py` — e este ficheiro é importado pelo `ready()` do
    # `AppConfig`. É o mesmo padrão do `semear_demonstracao` no
    # `accounts/api.py`, e sem supressão de lint nenhuma.
    from apps.purchasing.tasks import normalizar_pagina

    def _enfileirar() -> None:
        for pagina_id in paginas:
            normalizar_pagina.delay(tenant_id=str(tenant_id), pagina_id=str(pagina_id))

    transaction.on_commit(_enfileirar)
    logger.info(
        "rasterização pedida para as páginas de um documento",
        extra={
            "event": "documento.normalizacao",
            "outcome": "enfileirada",
            "event_id": str(evento.event_id),
            "count": len(paginas),
        },
    )
