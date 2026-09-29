# CLAUDE.md — StockFlow (gestão de stock para restauração)

Lido em todas as sessões. Ganha a qualquer instinto teu.

## Produto (uma frase)
SaaS multi-tenant para restaurantes, pastelarias e cafés gerirem stock, validades, receitas e
compras, com entrada de mercadoria por fatura do fornecedor (foto/PDF → linhas de stock) via IA.

## Stack (não negociável)
Python 3.12 · Django 5 · DRF · **uv** · PostgreSQL 16 (RLS por tenant) · Celery + Redis ·
React 18 · TypeScript strict · Vite · Tailwind v4 · shadcn/ui · TanStack Query · Zod ·
OpenAPI (drf-spectacular → openapi-typescript) · Docker multi-stage · pnpm.

Comandos: `uv sync` · `uv run manage.py <cmd>` · `uv run pytest` · `uv run ruff check .` ·
`pnpm dev|build|lint|typecheck|gen:api` · `docker compose up --build` ·
`bash .claude/skills/security-check/scripts/security_check.sh`

Nunca `pip install`. Nunca `npm`/`yarn`.

## Quem faz o quê (subagents em `.claude/agents/`)
| Fase | Agente | Escreve em |
|---|---|---|
| Decidir onde/como | `architect` | `docs/decisions/` |
| API e domínio | `backend` | `backend/**` |
| UI | `frontend` | `frontend/**` |
| Regras do negócio (stock, validades, faturas PT) | `domain-expert` | nada — só responde |
| Verificação final | `security-reviewer` | nada — só reporta |

Slash commands: `/feature <descrição>` corre o pipeline completo · `/review` revê o diff atual ·
`/kickoff` só na primeira sessão.

Skills locais: `security-check` · `inventory-domain` · `invoice-extraction` · `django-expert` ·
`django-safe-migration` · `django-celery-expert` · `django-reviewer`.
Skills externas esperadas (ver README): frontend-design, web-design-guidelines, react-best-practices, shadcn, grill-me.

## Ordem de trabalho (o `/feature` impõe isto)
1. `architect` lê `ARCHITECTURE.md`, decide módulo e contrato, escreve uma ADR curta.
2. `domain-expert` valida regras se a feature tocar em stock/compras/receitas/contagens/faturas.
3. `backend`: model → migração (RLS se tiver `tenant_id`) → serializers read/write separados
   → `services.py` → view → testes → `spectacular` → `pnpm gen:api`.
4. `frontend`: lê `DESIGN.md`; compõe shadcn; estados loading/empty/error; a11y; mobile primeiro.
5. `pnpm typecheck && pnpm lint && uv run pytest`.
6. `security-reviewer` corre a skill `security-check` + checklist. Sem PASS não está feito.

## Regras que não se discutem
- **Stock é um ledger.** Nunca se altera `quantity` de um `StockLevel`; cria-se um `StockMovement`.
- Toda a tabela com `tenant_id` tem política RLS na migração que a cria.
- Onde append-only é regra de negócio, a mesma migração revoga a escrita destrutiva ao role da
  aplicação: `REVOKE UPDATE, DELETE ON <tabela> FROM stockflow_app` (ADR 0006). Hoje aplica-se a
  `inventory_stockmovement` e a mais nada; a lista fechada vive no `APPEND_ONLY` de
  `tests/test_db_roles.py` e o teste falha se a lista e a base de dados divergirem.
- Lógica em `services.py`; módulos só se importam via `apps/<m>/api.py` (import-linter).
- Serializers de escrita listam `fields`; sem `__all__`. IDs são UUID. Quantidades e dinheiro são `Decimal`.
- Efeitos secundários (email, extração de faturas, previsões) em Celery via outbox.
- Output de LLM é texto não confiável: nunca vai para SQL, shell, `eval` ou HTML sem escape.
  Toda a extração de fatura passa por revisão humana antes de gerar movimentos.
- Frontend: só tokens de `DESIGN.md`; sem `bg-[#…]`; sem Inter/Roboto; sem tokens em localStorage.
- Docker: multi-stage, `USER app`, `HEALTHCHECK`, imagens fixadas por digest, zero segredos.
- Nunca: `DEBUG=True` fora de dev, desligar CSRF/CORS, editar migração aplicada, `# noqa` no código.
- Exceção de lint só em `[tool.ruff.lint.per-file-ignores]`, com comentário e ADR. Hoje são duas:
  `S101` nos testes e `F403` na camada de settings (ADR 0004). Uma terceira é sinal de que algo está errado.

## Ficheiros
`DESIGN.md` · `ARCHITECTURE.md` · `SECURITY.md` · `docs/decisions/` (ADRs) · `.claude/`
