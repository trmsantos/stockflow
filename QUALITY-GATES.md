# Quality Gates — Prevenção de Erros

Este documento lista as **barreiras automáticas** que impedem regressões técnicas. Nenhuma mudança merga sem passar em TODOS estes gates.

## 1. Segurança (Security Check)

```bash
bash .claude/skills/security-check/scripts/security_check.sh
```

**Must-pass:**
- ✅ Gitleaks: 0 segredos
- ✅ Bandit: 0 HIGH/CRITICAL
- ✅ Semgrep: 0 findings
- ✅ Pip-audit: 0 vulnerabilidades
- ✅ Pnpm audit: 0 vulnerabilidades
- ✅ Docker security: limpo

**Veredicto:** `PASS` (zero HIGH/CRITICAL) ou `FAIL`

## 2. Fronteiras de Módulos (Import-linter)

```bash
cd backend && uv run lint-imports
```

**Regra:** Entre módulos, só se importa via `api.py`, `events.py` e `apps.shared`

**Enforcement:** Viola automaticamente o build

**Common mistakes:**
- ❌ `from apps.accounts.models import User` (direto em services)
- ✅ `from apps.accounts.api import TenantContext` (via api)
- ❌ `from apps.catalog.models import Product`
- ✅ Usar UUID + lookup, ou receber como argumento

## 3. Testes (pytest)

```bash
cd backend && uv run pytest
```

**Must-pass:**
- ✅ 533 testes (cobertura mínima)
- ✅ RLS isolation test: verifica que cada tenant vê só seus dados
- ✅ DB roles test: verifica que tables estão em lista `APPEND_ONLY` se read-only

**Veredicto:** 0 failures, 0 errors

## 4. Código-style (ruff + pnpm lint)

```bash
cd backend && uv run ruff check . --fix  # auto-fix imports, formatting
cd backend && uv run ruff format .       # auto-format
cd frontend && pnpm lint --fix           # auto-fix JS/TS
cd frontend && pnpm typecheck            # strict TypeScript
```

**Must-pass:**
- ✅ Ruff format (imports, 88-char lines)
- ✅ Ruff check (linting rules)
- ✅ Pnpm lint (ESLint + security plugins)
- ✅ Pnpm typecheck (strict mode, no `any`)

## 5. Django Checks (production mode)

```bash
cd backend && python manage.py check --deploy
```

**Status:** 15 warnings (type hints in drf-spectacular — cosmetic, não bloqueador)

**Must-pass:** 0 HIGH/CRITICAL

## 6. Database Migrations

**Rules that prevent repeating past errors:**

### a) Permissions + RLS (ADR 0006, ADR 0007)
Every table needs:
- ✅ RLS enabled with FORCE (two separate SQL statements)
- ✅ Policy checking `tenant_id = NULLIF(current_setting('app.tenant_id'), '')::uuid`
- ✅ GRANT to `stockflow_app` role

**Checklist before merging:**
```sql
-- 1. Verify RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' AND tablename NOT IN (...)
ORDER BY tablename;

-- 2. Verify policies exist
SELECT schemaname, tablename, policyname, qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;

-- 3. Verify grants
SELECT table_name, privilege_type
FROM role_table_grants 
WHERE grantee = 'stockflow_app'
ORDER BY table_name;
```

### b) Owner Role (Prevent RLS permission conflicts)

**Rule:** Tables are owned by `stockflow_owner`, not `stockflow_app`

```bash
# After migration, verify:
sudo -u postgres psql -c "
  SELECT tablename, tableowner 
  FROM pg_tables 
  WHERE schemaname = 'public' AND tableowner != 'stockflow_owner';"
# Must return empty
```

### c) Stock Ledger (ADR 0006)

**Rule:** `StockMovement` table is append-only for `stockflow_app`

```bash
# After migration, verify:
sudo -u postgres psql -c "
  SELECT tablename FROM pg_tables 
  WHERE schemaname = 'public' AND tablename IN (SELECT * FROM APPEND_ONLY);"
# Should include 'inventory_stockmovement' (when implemented)
```

## 7. Docker Security

```bash
bash .claude/skills/security-check/scripts/security_check.sh
```

**Must-pass:**
- ✅ Hadolint: 0 warnings
- ✅ Trivy config: 0 misconfigurations
- ✅ No secrets in images
- ✅ All base images pinned by digest

## 8. TypeScript Strict Mode

```bash
cd frontend && pnpm typecheck
```

**Rule:** `strict: true` in tsconfig.json

**No exceptions:** No `any`, `@ts-ignore`, `// @ts-expect-error`

**Veredicto:** 0 errors

## 9. Frontend Fixtures (Prevent production leaks)

**Rule:** Fake-data server (`frontend/fixtures/`) is dev-only

**Enforcement:**
- ✅ `src/` has gate: `no imports from fixtures/`
- ✅ Build output has sentinel check: fails if fixtures are bundled
- ✅ CI runs: `grep -r "servidor de fixtures" dist/` must return empty

## How to Use This Document

**Before committing:**
```bash
# Run all gates locally
bash .claude/skills/security-check/scripts/security-check.sh
cd backend && uv run ruff check . --fix && uv run pytest
cd frontend && pnpm lint && pnpm typecheck
```

**If a gate fails:**
1. Read the error carefully — it's designed to explain what's wrong
2. Check this document for the rule
3. Fix the code
4. Re-run the gate

**If a gate blocks correctly but you believe the code is safe:**
- Don't bypass with `# noqa` or suppressions
- Document the exception in `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]`
- Add a 2-line comment explaining WHY (e.g., "S101: assert is idiomatic in pytest")
- Update this document
- Get code-review approval

---

**Last updated:** 2026-10-14
**Errors prevented by these gates:** 7+ (migrations, RLS, permissions, imports, secrets, types)
