"""As tarefas do `agents`: a extração de um documento e as três do chat (ADR 0027).

Herda o `TenantTask` por construção (é o `task_cls` do app), logo `tenant_id` é
argumento obrigatório e o corpo corre dentro de `tenant_scope(tenant_id)`. O
`tenant_id` vem **da linha do documento** e nunca de `request.tenant` (ADR 0020):
quem a enfileira é o adaptador do porto, chamado de dentro do âmbito do pedido, e
o valor viaja como argumento.

## A tarefa orquestra; a chamada vive atrás do `modelo.py`

A chamada ao modelo vive atrás de `apps/agents/modelo.py`, que levanta uma
excepção clara por cada razão de não ter lido — sem modelo, documento grande
demais, orçamento esgotado, tempo esgotado. Aqui apanha-se a base dessas
excepções, grava-se a tentativa com `status=erro` e uma razão legível, e **não
se rebenta a tarefa**: um worker a falhar em retentativas por uma configuração
que não existe é ruído, e a informação útil (que o documento não foi lido, e
porquê) tem de estar na base de dados e não num log.

O que esta tarefa **não** faz, e tem de continuar a não fazer: escrever linhas de
receção. Quem semeia é o `purchasing.services.criar_rececao`, quando uma pessoa
cria a receção (ADR 0031, decisão 5) — nenhuma fotografia cria um rascunho
sozinha, e o `agents` continua a ter uma aresta só, de leitura.

## As três do chat

* `agents.responder_mensagem(tenant_id, mensagem_id, request_id)` — `TenantTask`
  com o `tenant_id` **da linha**, enfileirada pelo `POST` em `on_commit` com
  `.delay()` e não pela outbox: a pergunta tem um consumidor só e os 0–5 s do
  `beat` seriam latência visível (ADR 0027, decisão 3). Sem `self.retry`:
  nenhuma recusa melhora com o tempo e uma retentativa paga duas vezes;
* `agents.purgar_conversas_expiradas` — `SystemTask` do `beat`, uma vez por dia.
  É **o cron que itera tenants** que a ADR 0005 nomeou e que não existia, e
  descobre-os pelo `accounts_user.tenant_ids` — sem tocar na política do
  `accounts_tenant`, que o dono recusou alargar (ADR 0027, decisão 2);
* `agents.purgar_conversas(tenant_id)` — `TenantTask`, uma por tenant, apaga em
  `tenant_scope` e em lotes as conversas com mais de `AGENTS_CHAT_RETENTION_DAYS`.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.accounts.api import tenants_dos_utilizadores_ativos
from apps.agents.modelo import ErroDoModelo, ler_documento, nome_do_modelo
from apps.agents.services import (
    abrir_tentativa,
    fechar_com_erro,
    fechar_com_resposta,
    purgar_conversas_do_tenant,
    responder,
    verificar_orcamento_de_extracao,
)
from apps.purchasing.api import paginas_do_documento
from apps.shared.db import system_scope
from apps.shared.tasks import SystemTask

__all__ = [
    "extrair_documento",
    "purgar_conversas",
    "purgar_conversas_expiradas",
    "responder_mensagem",
]

logger = logging.getLogger(__name__)


@shared_task(name="agents.extrair_documento")
def extrair_documento(*, tenant_id: str, documento_id: str) -> str:
    """Lê um documento e grava a tentativa. Devolve o estado em que ela ficou.

    Cinco saídas, e as cinco são normais:

    * `sem_paginas` — o documento não tem páginas (foi descartado, ou o slot
      expirou entre o fecho e a execução). **Não** se abre tentativa nenhuma:
      uma linha de extração de um documento sem páginas era um custo a fingir;
    * `paginas_por_normalizar` — há páginas e nenhuma tem imagem ainda. Também
      **não** abre tentativa, e é isso que faz o documento continuar em
      `a_normalizar` em vez de cair num `erro` que só diz "chegaste cedo": a
      rasterização corre noutra tarefa, e quando a última página ficar pronta o
      `registar_normalizacao` volta a publicar `DocumentoFechado` e esta tarefa
      corre outra vez — desta vez com imagens;
    * `erro` — a fronteira do modelo levantou (sem modelo, documento grande
      demais, orçamento esgotado, tempo esgotado). A razão fica na coluna
      `error`, legível, ao lado do `status`;
    * `ilegivel` — houve resposta e ela não valida contra o schema;
    * `lido` — houve resposta e ela valida.

    As páginas vêm pelo `purchasing.api`, como DTO congelado, e os **bytes** de
    cada imagem vêm um de cada vez por `bytes_da_pagina`: esta tarefa nunca abre
    um PDF e nunca conhece o armazenamento do `purchasing`.
    """
    tenant = UUID(tenant_id)
    documento = UUID(documento_id)
    paginas = paginas_do_documento(tenant_id=tenant, documento_id=documento)
    if not paginas:
        logger.info(
            "extração sem páginas para ler",
            extra={"event": "extracao", "outcome": "sem_paginas"},
        )
        return "sem_paginas"
    if not any(pagina.normalized for pagina in paginas):
        logger.info(
            "extração à espera da imagem das páginas",
            extra={"event": "extracao", "outcome": "paginas_por_normalizar"},
        )
        return "paginas_por_normalizar"

    tentativa = abrir_tentativa(
        tenant_id=tenant, documento_id=documento, modelo=nome_do_modelo()
    )
    try:
        # O tecto diário é verificado **depois** de a tentativa existir e antes
        # de qualquer byte sair: a linha é a prova de que se tentou, e a razão
        # fica legível ao lado dela (ADR 0031, decisão 7).
        verificar_orcamento_de_extracao(tenant_id=tenant)
        resposta = ler_documento(tenant_id=tenant, paginas=paginas)
    except ErroDoModelo as erro:
        # Só a mensagem, nunca o traceback (SECURITY.md §1). E sem `self.retry`:
        # nenhuma das recusas desta fronteira melhora com o tempo.
        fechar_com_erro(tentativa=tentativa, razao=str(erro))
        logger.warning(
            "extração fechada com erro",
            extra={"event": "extracao", "outcome": type(erro).__name__},
        )
        return "erro"
    fechada = fechar_com_resposta(tentativa=tentativa, resposta=resposta)
    logger.info(
        "extração concluída",
        extra={"event": "extracao", "outcome": fechada.status},
    )
    return str(fechada.status)


# ---------------------------------------------------------------------------
# O chat (ADR 0027)
# ---------------------------------------------------------------------------
@shared_task(name="agents.responder_mensagem")
def responder_mensagem(
    *, tenant_id: str, mensagem_id: str, request_id: str | None = None
) -> str:
    """Responde a um turno. Devolve o estado em que ele ficou.

    O corpo inteiro está em `services.responder`, que é idempotente pela linha:
    uma segunda entrega encontra o turno fora de `pendente` e devolve
    `ja_tratada` sem chamar o modelo. O `request_id` do pedido que enfileirou
    viaja como argumento e vai para o log do turno (ADR 0027, decisão 7).
    """
    return responder(
        tenant_id=UUID(tenant_id), mensagem_id=UUID(mensagem_id), request_id=request_id
    )


@shared_task(name="agents.purgar_conversas_expiradas", base=SystemTask)
def purgar_conversas_expiradas() -> dict[str, int]:
    """Enfileira uma purga por tenant. Uma vez por dia, pelo `beat`.

    Lê os ids sob `system_scope()` — a leitura é ao `accounts_user`, que não tem
    política, logo o âmbito aqui é a forma do consumidor da outbox e não uma
    necessidade —, **fecha o bloco** e só depois enfileira: um `tenant_scope`
    dentro de `system_scope` levanta (ADR 0005), e é a tarefa filha que o abre.
    Um tenant sem utilizador activo não é purgado — e não tem conversas de
    ninguém.
    """
    with system_scope():
        tenants = tenants_dos_utilizadores_ativos()
    for tenant_id in tenants:
        purgar_conversas.delay(tenant_id=str(tenant_id))
    logger.info(
        "purga de conversas enfileirada",
        extra={"event": "chat_purga", "outcome": "enfileirada", "count": len(tenants)},
    )
    return {"tenants": len(tenants)}


@shared_task(name="agents.purgar_conversas")
def purgar_conversas(*, tenant_id: str) -> int:
    """Apaga as conversas de um tenant com mais de `AGENTS_CHAT_RETENTION_DAYS`.

    `TenantTask`: corre em `tenant_scope(tenant_id)`, onde a política só deixa
    ver — e apagar — as deste tenant. Em lotes, dentro do serviço.
    """
    limite = timezone.now() - timedelta(days=int(settings.AGENTS_CHAT_RETENTION_DAYS))
    apagadas = purgar_conversas_do_tenant(tenant_id=UUID(tenant_id), limite=limite)
    logger.info(
        "conversas expiradas apagadas",
        extra={"event": "chat_purga", "outcome": "apagadas", "count": apagadas},
    )
    return apagadas
