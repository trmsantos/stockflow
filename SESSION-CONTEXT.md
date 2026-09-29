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

**Estado atual (2026-09-29, sessão 2):** repo `trmsantos/stockflow`, privado, na conta pessoal, em
`main`. **Kickoff: passos 1, 2 e 3 dos 8.** Passos 1-2 fechados e commitados (`9cce291`): `backend/`
com uv, os 9 módulos, 10 contratos de import-linter, e a camada de configuração completa
(`config/settings/{base,dev,prod,test}.py`, urls, wsgi/asgi, celery, logging JSON com allowlist,
lockout de login). 72 testes, ruff limpo sem `# noqa`, `check --deploy` sem warnings, e o gate
`security-check` a dar **PASS** com os sete gates a correr — antes dava PASS com quatro deles nunca
executados. `docker/compose.yml` tem `db` (PostgreSQL 16.15) e `redis` a correr em 5442/6389,
antecipados do passo 6 para a RLS poder nascer provada. Existe um `backend/.env` local (gitignored).

**O `/review` da sessão 2 encontrou quatro bloqueadores que nenhum gate apanhava**, o pior deles uma
recursão infinita no `progressive_cooloff` que punha **todos** os logins a 500, admin incluído.
Passava porque o `test.py` desliga o axes e não havia um único teste de login. Corrigidos e provados
de ponta a ponta contra Postgres. Lição a não perder: um gate verde não é cobertura.

**ADR 0005 fixa a fronteira transacional da RLS**: a transação é o pedido, `tenant_scope()` em
`apps/shared/db.py` entrado pelo `TenantMiddleware`, que é o **último** middleware. Reconciliada com
o `domain-expert`. Decisões de domínio já tomadas: **tenant = NIF** (o dono de três pastelarias é um
tenant com três localizações, porque recebe uma fatura que cobre entregas em duas lojas), o predicado
da RLS é `tenant_id` e só, e dados de referência partilhados não têm `tenant_id`.

**Passo 3 feito** (`apps/shared/`: `db.py` com `tenant_scope`, `TenantModel`, `outbox.py` com RLS,
`events.py`, `TenantTask`, `RequestContextMiddleware`). **ADR 0006 feita e implementada:** três roles
de BD — `stockflow_app` (`NOSUPERUSER NOBYPASSRLS`, sem `CREATE` no esquema, dono de nada, é a única
ligação que serve pedidos), `stockflow_owner` (dono das tabelas, credencial só do `migrate`) e o
superuser de bootstrap (só provisionamento, `docker/db/roles.sql`, idempotente). **A RLS passou a ser
imposta de facto** — antes o role da app era o superuser do cluster e ignorava a política por
completo. `migrate` com a credencial da app morre no primeiro `CREATE TABLE`, de propósito.
**A seguir: passo 4** (`accounts` com `Tenant`/`User`/`Membership`, o `TenantMiddleware` como
**último** middleware, primeira migração RLS de uma tabela de domínio), depois 5 `frontend/`,
6 resto do `docker/`, 7 CI, 8 PASS final.

**Dívida nomeada:** a escada de lockout acima dos 30 min não tem efeito (limitação estrutural do
axes — ver `SECURITY.md` §5); o 429 do lockout não tem corpo JSON útil; sem beat não há quem drene a
outbox; `testpaths` deixa cair testes em `apps/**`; nada corre `lint-imports` fora do gate.

**Sessão 0 (validação com donos de restaurante) continua por confirmar, e agora custa.** O
`domain-expert` marcou seis decisões como "não inventes default sem falar com um utilizador real":
bloquear ou avisar quando falta stock, clientes com várias lojas serem um NIF ou vários, consumo por
talão de POS ou em lote, cozinha central com stock em trânsito, `yield_factor`, e a hora a que
começa o dia de negócio (o desperdício da 01h30 pertence ao serviço anterior). Nenhuma bloqueia o
kickoff; todas bloqueiam o catálogo e o ledger, e são caras de mudar depois de haver migrações
aplicadas — que o CLAUDE.md proíbe editar. A conversa do NIF (sessão 2) acrescentou cinco: o
conjunto de papéis (o segundo sócio é `owner` igual, ou há um papel intermédio? — bloqueia a ADR do
convite); com que frequência acontece ENI → Lda e se esperam que o histórico transite (decide se a
mudança de NIF é self-service ou só suporte); se a contabilista é utilizadora do produto ou só
recebe exports (decide quanto vale o seletor de tenant); se as faturas emitidas ao NIF pessoal do
sócio são frequentes (decide se os "NIFs alternativos" entram no v1); e se grupos com N sociedades
estão no mercado-alvo ao lançamento (decide se `Organization` é fase 2 ou nunca).

**Plano de sessões (README §2):** 0 validação com donos de restaurante · 1 `/kickoff` · 2 catálogo ·
3 ledger de stock · 4 listagem + alertas · 5 contagem em telemóvel · 6–7 receção por fatura · 8 receitas + desperdício.

Antes de fazer qualquer coisa: lê CLAUDE.md, ARCHITECTURE.md, DESIGN.md e SECURITY.md, confirma-me em
5 linhas que percebeste o produto e as regras, e diz-me qual é o próximo passo segundo o estado atual.
