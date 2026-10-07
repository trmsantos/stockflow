# ADR 0003 — Fronteiras de `shared/` e importação de eventos

**Contexto.** Dois problemas no ARCHITECTURE.md. (1) O §2 punha o `TenantMiddleware` em `shared/`,
mas ele resolve o tenant do utilizador autenticado (precisa de `accounts.api`) e o `accounts` importa
`shared` para o `TenantModel` — ciclo ao nível do pacote. (2) O §3 diz `events.py` importável entre
módulos e o §6b fecha o grafo com "Nada mais": à letra, `notifications` não pode tipar eventos de
`inventory`.

**Decisão.** (1) O `TenantMiddleware` passa para `apps/accounts/`. O `apps/shared/` fica como
infraestrutura pura — `TenantModel`, `events.py`, `outbox.py` — e não depende de nenhum outro módulo,
incluindo `accounts`: é a camada de base do grafo. O `TenantModel` aponta para o tenant por string
(`ForeignKey("accounts.Tenant", ...)`). (2) Resolve-se a contradição a favor do §3: qualquer módulo
pode importar `apps.<m>.events`. Uma classe de evento é um DTO, não implementação — não acopla aos
`models` nem aos `services` do emissor e dá verificação estática na fronteira onde os erros custam
mais. O grafo restritivo do §6b continua a valer para tudo o resto, incluindo `api.py`.

**Alternativas.** Manter o middleware em `shared/` com o ciclo estreito (depende de disciplina e de
uma exceção no import-linter que tende a crescer); despacho por nome de evento com payload
serializado não tipado (perde o typing na fronteira mais cara); concentrar os eventos partilhados em
`apps/shared/events.py` (torna esse ficheiro um ponto de conflito que todas as features editam).

**Consequências.** A regra "todos → `accounts.api`" ganha uma exceção explícita: o `shared` não
importa `accounts.api`. É deliberado — o ciclo fica estruturalmente impossível em vez de evitado por
disciplina. O import-linter ganha `shared` como camada de base e uma permissão transversal para
`apps.*.events`; um evento importado por outro módulo é contrato público, mudar-lhe os campos é
breaking, tal como em `api.py`.
