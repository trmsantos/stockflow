---
description: Bootstrap inicial do repositório (só na primeira sessão)
---
Faz o bootstrap do StockFlow a partir de zero, nesta ordem, parando após cada passo para eu confirmar:

1. Estrutura de pastas de ARCHITECTURE.md §2. `backend/` com `uv init`; `pyproject.toml` com Django 5, DRF, drf-spectacular, django-environ, psycopg[binary], celery, redis, argon2-cffi, django-axes, django-csp, import-linter (contrato de independência entre `apps.*`), ruff, pytest-django. `uv.lock` gerado.
2. `config/settings/{base,dev,prod,test}.py` — `prod.py` exatamente como SECURITY.md §2.
3. `apps/shared/` com `outbox.py`, `events.py`, mixin `TenantModel` (UUID pk, tenant FK, timestamps).
   O `TenantMiddleware` **não** vive aqui: vai para `apps/accounts/` no passo 4 (ADR 0003), e o contrato
   do import-linter proíbe `shared` de importar `accounts`. Decide também aqui a fronteira transacional
   da RLS (onde corre o `set_config('app.tenant_id', ...)`) e regista-a numa ADR — ver ARCHITECTURE.md §4.
4. `apps/accounts/` com `Tenant`, `User` custom, `Membership` com papéis `owner|manager|staff`. Migração com RLS.
5. `frontend/` com Vite + React TS strict + Tailwind v4 + shadcn init + TanStack Query + Zod + openapi-typescript (`pnpm gen:api`). `src/styles/tokens.css` com os tokens de DESIGN.md.
6. `docker/` — `backend.Dockerfile`, `frontend.Dockerfile`, `compose.yml` (backend, worker, frontend, db, redis, proxy). Não-root, healthchecks, digests.
7. `.github/workflows/ci.yml` com os gates de SECURITY.md §9.
8. `security-reviewer` corre e tem de dar PASS num repo vazio.

Não implementes nenhuma feature de negócio no kickoff.
