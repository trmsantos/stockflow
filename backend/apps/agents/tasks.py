"""`agents.tasks.extrair_documento`: a tarefa que lê um documento.

Herda o `TenantTask` por construção (é o `task_cls` do app), logo `tenant_id` é
argumento obrigatório e o corpo corre dentro de `tenant_scope(tenant_id)`. O
`tenant_id` vem **da linha do documento** e nunca de `request.tenant` (ADR 0020):
quem a enfileira é o adaptador do porto, chamado de dentro do âmbito do pedido, e
o valor viaja como argumento.

## A tarefa faz tudo menos a chamada ao modelo

E isso é deliberado, não incompleto: a chamada vive atrás de
`apps/agents/modelo.py`, que levanta uma excepção clara quando não há modelo
configurado. Aqui apanha-se essa excepção, grava-se a tentativa com `status=erro`
e uma razão legível, e **não se rebenta a tarefa** — um worker a falhar em
retentativas por uma configuração que não existe é ruído, e a informação útil
(que o documento não foi lido, e porquê) tem de estar na base de dados e não num
log.

O que esta tarefa **não** faz, e tem de continuar a não fazer: escrever linhas de
receção. Isso é da fatia 2 e entra pelo `purchasing.api` (ADR 0020, decisão 6) —
nunca pelos models do `purchasing`, que o import-linter já proíbe.
"""

from __future__ import annotations

import logging
from uuid import UUID

from celery import shared_task

from apps.agents.modelo import ErroDoModelo, ler_documento, nome_do_modelo
from apps.agents.services import abrir_tentativa, fechar_com_erro, fechar_com_resposta
from apps.purchasing.api import paginas_do_documento

__all__ = ["extrair_documento"]

logger = logging.getLogger(__name__)


@shared_task(name="agents.extrair_documento")
def extrair_documento(*, tenant_id: str, documento_id: str) -> str:
    """Lê um documento e grava a tentativa. Devolve o estado em que ela ficou.

    Quatro saídas, e as quatro são normais:

    * `sem_paginas` — o documento não tem páginas (foi descartado, ou o slot
      expirou entre o fecho e a execução). **Não** se abre tentativa nenhuma:
      uma linha de extração de um documento sem páginas era um custo a fingir;
    * `erro` — a fronteira do modelo levantou. **É a saída de hoje**, e a razão
      fica na coluna `error`, legível, ao lado do `status`;
    * `ilegivel` — houve resposta e ela não valida contra o schema;
    * `lido` — houve resposta e ela valida.

    As páginas vêm pelo `purchasing.api`, como DTO congelado: esta tarefa nunca
    abre um PDF e nunca conhece o armazenamento do `purchasing`.
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

    tentativa = abrir_tentativa(
        tenant_id=tenant, documento_id=documento, modelo=nome_do_modelo()
    )
    try:
        resposta = ler_documento(paginas=paginas)
    except ErroDoModelo as erro:
        # Só a mensagem, nunca o traceback (SECURITY.md §1). E sem `self.retry`:
        # nenhuma das recusas desta fronteira melhora com o tempo.
        fechar_com_erro(tentativa=tentativa, razao=str(erro))
        logger.warning(
            "extração sem modelo para chamar",
            extra={"event": "extracao", "outcome": "erro"},
        )
        return "erro"
    fechada = fechar_com_resposta(tentativa=tentativa, resposta=resposta)
    logger.info(
        "extração concluída",
        extra={"event": "extracao", "outcome": fechada.status},
    )
    return str(fechada.status)
