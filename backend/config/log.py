"""Logging estruturado em JSON (ARCHITECTURE.md §8).

Uma linha JSON por registo, com `request_id`, `tenant_id` e `user_id`.

## Onde a allowlist protege, e onde não

Os logs são um destino de fuga de dados (SECURITY.md §1, "Exposição de dados em
logs"). A defesa aqui é uma *allowlist*, mas **o seu alcance é exatamente um
campo**: os `extra=`. Dito por inteiro, porque a diferença importa:

* **Protegido.** `extra={...}`: só as chaves de `CONTEXT_FIELDS` e
  `EXTRA_ALLOWLIST` chegam ao output. Qualquer outra é descartada em silêncio —
  falha fechada, em vez de deixar PII passar por omissão.
* **Não protegido: a `message`.** `record.getMessage()` inclui a string e os
  `%`-args formatados. `logger.info("fatura de %s", email)` escreve o email em
  claro. Verificado por execução; há um teste que fixa este comportamento.
* **Não protegido: a `exception`.** `formatException` escreve o traceback como
  vem, e o `DETAIL` de um `IntegrityError` do Postgres leva os valores da linha
  em conflito (um NIF, um email). Também fixado em teste.

Não há aqui nenhum scrubber de regex, de propósito: um filtro por padrões dá
uma sensação de segurança que não se verifica (não apanha nomes, endereços nem
NIFs escritos de outra forma) e, ao correr em cada linha de log, custa
latência. A garantia fica onde é verificável.

## Convenção (é ela que faz a diferença na prática)

1. PII vai em `extra=`, com uma chave que esteja na allowlist — nunca no texto
   da mensagem nem nos `%`-args.
2. A mensagem é uma constante: `logger.info("fatura recebida", extra={...})`.
   Não interpola valores vindos do utilizador, da BD ou de um LLM.
3. Identificadores em vez de pessoas: `tenant_id`, `user_id` (hash),
   `event_id`, `count`. Nunca nome, email, NIF, IBAN ou telefone.
4. `exc_info=True` em erros de BD sobre tabelas com PII: usa `logger.error` com
   uma mensagem própria e o `event`, sem `exc_info`, ou trata a exceção onde
   ela nasce.

Alargar a `EXTRA_ALLOWLIST` é uma decisão de segurança — passa pelo
`security-reviewer`.

Quem preenche `request_id`/`tenant_id`/`user_id` é o middleware de logging, que
nasce no passo 3 do kickoff. Até lá o filtro garante que as chaves existem com
valor `None`, para o formato da linha ser estável desde o primeiro dia.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

#: Campos de correlação presentes em todas as linhas de log.
CONTEXT_FIELDS: tuple[str, ...] = ("request_id", "tenant_id", "user_id")

#: Únicos `extra=` que chegam ao output. Nada aqui é PII: são identificadores
#: opacos, nomes de operação e métricas. Alargar esta lista é uma decisão de
#: segurança — passa pelo `security-reviewer`.
EXTRA_ALLOWLIST: frozenset[str] = frozenset(
    {
        "event",
        "duration_ms",
        "status_code",
        "method",
        "route",
        "outcome",
        "task_name",
        "task_id",
        "event_id",
        "count",
    }
)


class RequestContextFilter(logging.Filter):
    """Garante que os campos de correlação existem em todos os registos."""

    def filter(self, record: logging.LogRecord) -> bool:
        for field in CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, None)
        return True


class JsonFormatter(logging.Formatter):
    """Serializa o registo numa linha JSON com uma allowlist de campos."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            payload[field] = getattr(record, field, None)
        for key, value in record.__dict__.items():
            if key in EXTRA_ALLOWLIST:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)
