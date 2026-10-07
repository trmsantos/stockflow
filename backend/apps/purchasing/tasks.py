"""As duas tarefas do `purchasing`: normalizar uma página, varrer os slots.

As duas herdam o `TenantTask` por construção — é o `task_cls` do app
(`config/celery.py`), logo não existe outra forma de declarar uma tarefa neste
projecto —, pelo que `tenant_id` é argumento **obrigatório** e o corpo corre
dentro de `tenant_scope(tenant_id)`.

E o `tenant_id` vem **da linha do documento** e nunca de `request.tenant` (ADR
0020): quem enfileira é o `services.enfileirar_trabalho_do_documento`, que já
está dentro do âmbito e o passa como argumento. Uma tarefa que o fosse buscar ao
pedido era uma tarefa a ler um pedido que já acabou.

## Nenhuma delas escreve directamente na base de dados

Chamam `services.py`, que é a única forma de escrever (CLAUDE.md). O que uma
tarefa acrescenta é o **fora** da transação: a chamada à fronteira da
rasterização, que é lenta e nativa e nunca pode correr no processo que serve
pedidos.

## A limpeza não corre

`limpar_slots_expirados` não tem agendamento: **não há `beat`** neste projecto, e
esta feature é a primeira a precisar dele (dívida nomeada no `SESSION-CONTEXT.md`
e repetida na ADR 0021). A tarefa existe, tem teste, e o dia em que o `beat`
existir é uma entrada de configuração — mais o cron que itera tenants, que é a
única coisa deste repositório que pode ter `tenant_scope_exempt` e que também não
existe.
"""

from __future__ import annotations

import logging
from uuid import UUID

from celery import shared_task

from apps.purchasing.models import DocumentPage
from apps.purchasing.rasterizacao import RasterizadorIndisponivel, rasterizar
from apps.purchasing.services import limpar_slots_expirados, registar_normalizacao

__all__ = ["limpar_slots_expirados_do_tenant", "normalizar_pagina"]

logger = logging.getLogger(__name__)


@shared_task(name="purchasing.normalizar_pagina")
def normalizar_pagina(*, tenant_id: str, pagina_id: str) -> str:
    """Rasteriza uma página e guarda a imagem normalizada.

    **Por página à chegada e não no fecho** (ADR 0020, adenda 2): senão o polling
    do desktop não tem nada para mostrar enquanto a segunda fotografia não chega.

    Três saídas, e as três são normais:

    * `sem_pagina` — a página já não existe (o documento foi descartado entre o
      enfileiramento e a execução). Uma tarefa a correr tarde não é um erro;
    * `sem_rasterizador` — a fronteira levantou. **É a saída de hoje**: não há
      rasterizador nas dependências deste projecto (ver
      `apps/purchasing/rasterizacao.py`). A página fica sem imagem, o documento
      fica em `a_normalizar`, e nada mente — não há uma coluna `normalized_at`
      escrita sem imagem por baixo. Não se faz `self.retry`: a dependência não
      aparece por esperar;
    * `normalizada` — o caminho completo, que é o que um teste exercita
      substituindo a fronteira.
    """
    pagina = DocumentPage.objects.filter(
        tenant_id=UUID(tenant_id), pk=UUID(pagina_id)
    ).select_related("file").first()
    if pagina is None:
        return "sem_pagina"
    try:
        imagem = rasterizar(
            caminho=pagina.file.path, numero_da_pagina=pagina.file_page_number
        )
    except RasterizadorIndisponivel:
        logger.warning(
            "página sem imagem: não há rasterizador neste ambiente",
            extra={"event": "documento.normalizacao", "outcome": "sem_rasterizador"},
        )
        return "sem_rasterizador"
    registar_normalizacao(
        tenant_id=UUID(tenant_id), pagina_id=UUID(pagina_id), imagem=imagem
    )
    return "normalizada"


@shared_task(name="purchasing.limpar_slots_expirados")
def limpar_slots_expirados_do_tenant(*, tenant_id: str) -> int:
    """Apaga os slots deste estabelecimento que expiraram sem página nenhuma.

    O nome da tarefa (`purchasing.limpar_slots_expirados`) é o da ADR; o nome da
    função leva o sufixo `_do_tenant` porque o serviço que ela chama já se chama
    `limpar_slots_expirados` e dois nomes iguais no mesmo import eram um erro à
    espera de acontecer.
    """
    return limpar_slots_expirados(tenant_id=UUID(tenant_id))
