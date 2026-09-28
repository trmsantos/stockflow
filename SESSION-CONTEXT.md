# Contexto de sessão — colar como primeira mensagem no Claude Code

> Cola tudo abaixo desta linha na primeira mensagem de cada sessão nova (ou pelo menos na primeira de todas).
> O CLAUDE.md já dá as regras; isto dá o *porquê* e o estado atual.

---

Estou a construir o **StockFlow**: um SaaS multi-tenant de gestão de stock para restauração e negócios
alimentares em Portugal (restaurantes, pastelarias, cafés). O diferenciador é IA aplicada aos dados do
cliente — entrada de mercadoria por foto/PDF da fatura do fornecedor, alertas de validade e rutura,
relatório de desperdício em euros — e não um chatbot de suporte.

**Decisões já tomadas (não reabrir sem motivo forte):**
- Stack: Django 5 + DRF com uv · PostgreSQL 16 com Row-Level Security por tenant · Celery + Redis ·
  React 18 + TypeScript strict + Vite + Tailwind v4 + shadcn/ui · OpenAPI → tipos TS · Docker multi-stage · pnpm.
- Arquitetura: monólito modular (`accounts, catalog, inventory, purchasing, recipes, agents, billing,
  notifications, shared`), módulos só se importam via `api.py`, outbox para eventos. Ver ARCHITECTURE.md e ADR 0001.
- Stock é um **ledger** append-only de `StockMovement`; quantidades são projeções. Nunca editáveis.
- A IA só produz **drafts**; um humano confirma antes de qualquer escrita no ledger.
- Sem estética genérica de IA: DESIGN.md define IBM Plex, um único acento verde-azulado, densidade
  compacta, tab bar mobile (Stock · Receber · Contar · Alertas).
- Segurança e encriptação conforme SECURITY.md; `security-reviewer` tem de dar PASS no fim de cada feature.

**Como trabalhamos:**
- Uma feature por sessão, sempre via `/feature <descrição>`. O pipeline é
  architect → domain-expert → backend → frontend → security-reviewer, e pára para eu aprovar o contrato.
- Tu (agente principal) coordenas; delegas nos subagents de `.claude/agents/`; não implementas diretamente.
- Se eu decidir algo relevante nesta conversa, regista-o em `docs/decisions/` antes de terminar.
- Não instales dependências fora do lockfile, não desligues segurança "para testar", não suprimas lint.

**Estado atual:** `[ATUALIZAR]` — ex.: "repo vazio, vou correr `/kickoff`" ou
"catalog feito (sessão 2); hoje: `/feature localizações e movimentos de stock com lotes e validade`".

**Plano de sessões (README §2):** 0 validação com donos de restaurante · 1 `/kickoff` · 2 catálogo ·
3 ledger de stock · 4 listagem + alertas · 5 contagem em telemóvel · 6–7 receção por fatura · 8 receitas + desperdício.

Antes de fazer qualquer coisa: lê CLAUDE.md, ARCHITECTURE.md, DESIGN.md e SECURITY.md, confirma-me em
5 linhas que percebeste o produto e as regras, e diz-me qual é o próximo passo segundo o estado atual.
