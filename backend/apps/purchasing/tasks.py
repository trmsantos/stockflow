"""As duas tarefas do `purchasing`: normalizar uma página, varrer os slots.

As duas herdam o `TenantTask` por construção — é o `task_cls` do app
(`config/celery.py`), logo não existe outra forma de declarar uma tarefa neste
projecto —, pelo que `tenant_id` é argumento **obrigatório** e o corpo corre
dentro de `tenant_scope(tenant_id)`.

E o `tenant_id` vem **da linha** e nunca de `request.tenant` (ADR 0020): quem
enfileira a `normalizar_pagina` é o `handlers.rasterizar_paginas_pendentes`, a
reagir ao `DocumentoFechado` que o `services.py` escreveu na outbox, e o tenant
que ele passa é o da **coluna** da linha do evento. Uma tarefa que o fosse buscar
ao pedido era uma tarefa a ler um pedido que já acabou.

## Nenhuma delas escreve directamente na base de dados

Chamam `services.py`, que é a única forma de escrever (CLAUDE.md). O que uma
tarefa acrescenta é o **fora** da transação: a chamada à fronteira da
rasterização, que é lenta e nativa e nunca pode correr no processo que serve
pedidos.

## A limpeza continua a não correr, e agora por outra razão

Já há `beat` (`CELERY_BEAT_SCHEDULE`, em `config/settings/base.py`), e a
`limpar_slots_expirados_do_tenant` continua sem agendamento. A razão deixou de
ser a falta do agendador e passou a ser a **forma** da tarefa: ela recebe um
`tenant_id`, logo alguém tem de iterar os estabelecimentos para a enfileirar um
por um — e esse cron teria de ler o `accounts_tenant`, cuja política compara `id`
contra `app.tenant_id` sem o disjunto `app.scope`. Dentro de `system_scope()`
essa leitura devolve **zero linhas sem erro**: o cron corria, dizia que varreu
tudo, e não varria nada.

Alargar aquela política ao âmbito de sistema é uma decisão de ADR — o âmbito de
sistema alcança hoje uma tabela só, de propósito (ADR 0005) — e não se toma ao
lado de uma entrada de `beat`. A alternativa sem RLS nova é dar a esta limpeza um
gatilho por tenant em vez de um cron global (um evento na abertura do slot, com
`countdown`), e é também uma decisão de desenho. Fica escrito nos dois sítios: na
`services.limpar_slots_expirados` e aqui.
"""

from __future__ import annotations

import logging
from uuid import UUID

from celery import shared_task

from apps.purchasing.models import DocumentPage
from apps.purchasing.rasterizacao import (
    PaginaIlegivel,
    RasterizadorIndisponivel,
    rasterizar,
)
from apps.purchasing.services import limpar_slots_expirados, registar_normalizacao

__all__ = ["limpar_slots_expirados_do_tenant", "normalizar_pagina"]

logger = logging.getLogger(__name__)


@shared_task(name="purchasing.normalizar_pagina")
def normalizar_pagina(*, tenant_id: str, pagina_id: str) -> str:
    """Rasteriza uma página e guarda a imagem normalizada.

    **Por página à chegada e não no fecho** (ADR 0020, adenda 2): senão o polling
    do desktop não tem nada para mostrar enquanto a segunda fotografia não chega.

    Quatro saídas, e as quatro são normais:

    * `sem_pagina` — a página já não existe (o documento foi descartado entre o
      enfileiramento e a execução). Uma tarefa a correr tarde não é um erro;
    * `sem_rasterizador` — este ambiente não tem a libvips. Na imagem do worker
      ela vem da camada de apt; numa máquina de desenvolvimento é opcional. A
      página fica sem imagem, o documento fica em `a_normalizar`, e nada mente —
      não há uma coluna `normalized_at` escrita sem imagem por baixo. Não se faz
      `self.retry`: uma dependência não aparece por esperar;
    * `pagina_ilegivel` — a biblioteca **está** lá e recusou este ficheiro: um PDF
      truncado a meio do upload, uma página que o poppler não lê. É um ramo
      próprio porque a acção é outra — não há nada a instalar, há um documento
      que não serve — e também não se repete, porque repetir lê o mesmo ficheiro;
    * `normalizada` — o caminho completo, que é o que um teste exercita
      substituindo a fronteira (e, onde a libvips existe, de verdade).
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
    except PaginaIlegivel:
        # Distinto do de cima, e por isso é um ramo próprio: aqui a biblioteca
        # está lá e **este ficheiro** não serve — um PDF truncado a meio do
        # upload, uma página que o poppler recusa. Sem isto a excepção subia, a
        # tarefa ficava "failed" no Celery e um documento mau parecia uma avaria
        # da infraestrutura. Também não se faz `retry`: repetir lê o mesmo
        # ficheiro.
        logger.warning(
            "página ilegível: a libvips recusou este ficheiro",
            extra={"event": "documento.normalizacao", "outcome": "pagina_ilegivel"},
        )
        return "pagina_ilegivel"
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
