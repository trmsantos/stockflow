---
name: security-check
description: Corre uma verificação de segurança completa ao código (Django + React TS + Docker) e produz um relatório de findings por severidade com correções concretas. Usa esta skill sempre que o utilizador pedir para "verificar a segurança", "auditar", "fazer security check/review/scan", antes de fechar qualquer tarefa que toque em autenticação, permissões, uploads, queries, variáveis de ambiente, Dockerfiles ou dependências, e sempre que o CLAUDE.md o exigir no fim de uma feature — mesmo que o utilizador não o peça explicitamente.
---

# Security Check

Verificação em duas partes: (1) ferramentas automáticas via `scripts/security_check.sh`,
(2) revisão manual guiada por `references/checklist.md`. As duas são obrigatórias; a
automática apanha padrões conhecidos, a manual apanha lógica (autorização, tenancy, agentes).

## Passo 1 — Correr o script

```bash
bash .claude/skills/security-check/scripts/security_check.sh [--fix] [--only backend|frontend|docker|secrets]
```

O script:
- Instala as ferramentas em falta com `uv tool install` / `pnpm dlx` (não polui o projeto).
- Corre gitleaks, bandit, semgrep (python e react), pip-audit, `manage.py check --deploy`,
  import-linter, pnpm audit, um grep de padrões perigosos e, se houver Dockerfiles, hadolint,
  `trivy config` e `docker/scan-artefactos.sh`.
- **Não** corre `eslint-plugin-security` nem `trivy image`, apesar de as duas coisas existirem no
  projeto: o eslint corre pelo `pnpm lint` (com `--max-warnings 0`) e o `trivy image` corre no job
  `docker` do CI. Quem lê esta lista tem de poder confiar nela — uma regressão de CVE numa imagem é
  invisível a este script, e o `CLAUDE.md` faz dele o critério de PASS.
- Escreve relatórios em `.security-reports/` (JSON + resumo) e imprime um sumário por severidade.
- Sai com código ≠ 0 se houver findings HIGH ou CRITICAL.

Se uma ferramenta não estiver disponível e não for instalável (sem rede), o script diz qual
e continua. Regista isso no relatório final — não finjas que correu.

## Passo 2 — Revisão manual

Lê `references/checklist.md` e percorre-o **apenas nas secções relevantes para os ficheiros
alterados** (usa `git diff --name-only main...HEAD` para os identificar). Para cada item,
abre o código e verifica; não assumas pelo nome do ficheiro.

Foco obrigatório, porque as ferramentas não apanham:
- Autorização por objeto em cada view que recebe um `pk` (IDOR).
- Filtragem por tenant em cada queryset.
- Output de LLM a chegar a shell/SQL/HTML.
- Segredos em `VITE_*`.
- `dangerouslySetInnerHTML`.

## Passo 3 — Relatório

Devolve ao utilizador, nesta ordem:

1. **Resumo**: N findings (X critical, Y high, Z medium, W low). Ferramentas que não correram.
2. **Tabela de findings** — colunas: Severidade · Ficheiro:linha · Regra/Origem · Descrição · Correção.
   Ordenada por severidade. Máximo 25 linhas; agrupa repetições ("12 ocorrências de X em `apps/core/`").
3. **Correções aplicadas** (se `--fix` ou se o utilizador pediu para corrigir): diff resumido.
4. **Falsos positivos** identificados, com justificação de uma linha cada. Não os escondas —
   lista-os para o utilizador poder discordar.
5. **Veredicto**: `PASS` (zero high/critical) ou `FAIL` com o que bloqueia.

Não aumentes a severidade para parecer diligente nem a reduzas para o PASS. Se tiveres dúvida
sobre a severidade, usa a da ferramenta e comenta.

## Quando o utilizador pede para corrigir

- Corrige uma classe de problema de cada vez e volta a correr o script entre correções.
- Nunca corrijas suprimindo (`# nosec`, `// eslint-disable`, `.gitleaksignore`) sem um
  comentário na mesma linha que explique porquê e sem o dizer no relatório.
- Correções em `settings/prod.py` seguem exatamente o bloco em `SECURITY.md §2`.
- Se a correção exigir uma decisão de produto (ex.: "isto expõe emails de outros utilizadores —
  é intencional?"), pergunta antes de alterar.

## Ficheiros

- `scripts/security_check.sh` — orquestrador das ferramentas.
- `references/checklist.md` — checklist manual por área (backend, BD, frontend, agentes, docker).
