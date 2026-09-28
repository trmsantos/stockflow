# ADR 0001 — Monólito modular com ledger de stock

**Contexto.** Produto novo, uma pessoa, 1–2 h/dia. Precisa de multi-tenant seguro desde o dia 1 e de espaço para IA sem contaminar o domínio.

**Decisão.** Um Django modular (ver ARCHITECTURE.md) com fronteiras por `api.py` impostas por import-linter; stock modelado como ledger append-only; IA isolada em `agents/` a produzir só drafts.

**Alternativas.** Microserviços (custo operacional injustificado); Next.js full-stack (perde Django admin, ORM, RLS madura); stock como quantidade editável (perde auditoria e origina inconsistências).

**Consequências.** Mais código inicial (services, outbox); em troca, extração de `agents/` para serviço próprio é mecânica quando fizer sentido, e cada número no ecrã tem origem rastreável.
