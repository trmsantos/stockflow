# CLAUDE.md — StockFlow (gestão de stock para restauração)

Lido em todas as sessões. Ganha a qualquer instinto teu.

## Produto (uma frase)
SaaS multi-tenant para restaurantes, pastelarias e cafés gerirem stock, validades, receitas e
compras, com entrada de mercadoria por fatura do fornecedor (foto/PDF → linhas de stock) via IA.

## Stack (não negociável)
Python 3.12 · Django 5 · DRF · **uv** · PostgreSQL 16 (RLS por tenant) · Celery + Redis ·
React 18 · TypeScript strict · Vite · Tailwind v4 · shadcn/ui · TanStack Query ·
TanStack **Router** (árvore em código, search params validados por Zod — ADR 0008) · Zod ·
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

Skills locais: **lê `.claude/skills/`** — hoje são a `security-check`, a `inventory-domain`, a
`invoice-extraction`, as quatro de Django e a `web-design-guidelines`.
Skills externas esperadas (ver README): frontend-design, react-best-practices, shadcn, grill-me.

## Ordem de trabalho (o `/feature` impõe isto)
1. `architect` lê `ARCHITECTURE.md`, decide módulo e contrato, escreve uma ADR curta.
2. `domain-expert` valida regras se a feature tocar em stock/compras/receitas/contagens/faturas.
3. `backend`: model → migração (RLS se tiver `tenant_id`) → serializers read/write separados
   → `services.py` → view → testes → `spectacular` → `pnpm gen:api`.
4. `frontend`: lê `DESIGN.md`; compõe shadcn; estados loading/empty/error; a11y; mobile primeiro.
5. `pnpm typecheck && pnpm lint && uv run pytest` — e a suite **também sem a influência do `.env`**,
   senão o verde local não diz nada sobre o CI. Ecrã novo ou alterado: fotografar com **cada papel**.
6. `security-reviewer` corre a skill `security-check` + checklist. Sem PASS não está feito.
7. PR. **O CI só corre em PR** — um push sem PR aberto não dispara nada, e os 4 testes que precisam
   de libvips só correm lá.

## Regras que não se discutem
- **Stock é um ledger.** Nunca se altera `quantity` de um `StockLevel`; cria-se um `StockMovement`.
- **A sessão escolhe o âmbito, a política concede-o.** Nada que venha da sessão ou de um header é
  credencial: é argumento, verificado dentro do âmbito (ADR 0007).
- **Toda a tabela de dados de um tenant tem política RLS na migração que a cria**, e o predicado
  compara a coluna que identifica o tenant contra `NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
  Essa coluna é `tenant_id` em toda a parte exceto em `accounts_tenant`, onde é `id` — a tabela *é* o
  tenant (ADR 0007). Sem o `NULLIF` a política levanta erro em vez de devolver zero linhas, porque
  fora do âmbito o GUC é a string vazia e não NULL. As únicas famílias sem política são os dados de
  referência partilhados (ADR 0005) e `accounts_user`, que tem de ser lido antes de existir âmbito
  para o login funcionar (ADR 0007); as duas vivem numa lista fechada em `tests/test_db_roles.py`,
  que falha nos dois sentidos.
- Onde append-only é regra de negócio, a mesma migração revoga a escrita destrutiva ao role da
  aplicação: `REVOKE UPDATE, DELETE ON <tabela> FROM stockflow_app` (ADR 0006). **Quais são as tabelas
  não se escreve aqui**: a lista fechada vive no `APPEND_ONLY` de `tests/test_db_roles.py` e o teste
  falha nos dois sentidos se ela e a base de dados divergirem. Esta linha já afirmou o contrário da
  verdade **duas vezes** — primeiro que a regra se aplicava quando não se aplicava, depois que o
  conjunto estava vazio quando o ledger já lá estava. Um inventário do que está feito, num ficheiro
  que ninguém regenera, apodrece; a lista fechada existe para não ser copiada para aqui.
- Lógica em `services.py`; módulos só se importam via `apps/<m>/api.py` (import-linter).
- Serializers de escrita listam `fields`; sem `__all__`. IDs são UUID. Quantidades e dinheiro são `Decimal`.
- Efeitos secundários (email, extração de faturas, previsões) em Celery via outbox.
- Output de LLM é texto não confiável: nunca vai para SQL, shell, `eval` ou HTML sem escape.
  Toda a extração de fatura passa por revisão humana antes de gerar movimentos.
- **Dinheiro e nomes de pessoas saem por papel.** Onde a ADR o disser, os euros são de
  `owner|manager` e a chave fica **ausente** do JSON — nunca `0` (afirmação falsa sobre o preço) nem
  `null` (que o ecrã imprime como "—", e isso é outro facto: *não há valor*). O nome de quem agiu é o
  `display_name` da pertença, **nunca o email**, e sem o email como recurso quando o nome está vazio.
  Quando um caminho novo passa a servir dinheiro, procura o **caminho irmão**: esta fuga aparece aos
  pares (a receção e o documento serviam a mesma fatura por portas diferentes).
- **Os schemas Zod são escritos à mão** e não se geram do `types.ts`. Um campo que passe a opcional no
  contrato tem de ganhar `.optional()` no Zod — `.nullable()` sozinho exige a chave presente, e o ecrã
  **rebenta** em vez de degradar, com o `pnpm typecheck` verde. Nenhum gate atravessa esta fronteira:
  só fotografar o ecrã autenticado com cada papel (`frontend/scripts/ver-ecra.py`) a apanha.
- **Testes não herdam configuração do ambiente.** O Django lê o `backend/.env`, que é da máquina de
  quem desenvolve e não está no repositório: um teste que dependa de settings fixa-as com
  `override_settings`. Caso contrário afirma coisas diferentes em máquinas diferentes, e "a suite
  passou" deixa de ser prova de nada.
- Frontend: só tokens de `DESIGN.md`; sem `bg-[#…]`; sem Inter/Roboto; sem tokens em localStorage.
- Docker: multi-stage, `USER app`, `HEALTHCHECK`, imagens fixadas por digest, zero segredos.
- Nunca: `DEBUG=True` fora de dev, desligar CSRF/CORS, editar migração aplicada, `# noqa` no código.
- Exceção de lint só em `[tool.ruff.lint.per-file-ignores]`, **com um comentário por cima que a
  justifique**. Quantas são e quais lê-se no `pyproject.toml` — contá-las aqui era outro inventário a
  apodrecer, e já apodreceu. O que se discute é cada exceção **nova**: se a justificação não couber
  num comentário curto, o problema não é o lint.

## Ficheiros
`DESIGN.md` · `ARCHITECTURE.md` · `SECURITY.md` · `docs/decisions/` (ADRs) · `.claude/`
