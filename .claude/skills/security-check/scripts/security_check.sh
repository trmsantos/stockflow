#!/usr/bin/env bash
# security_check.sh — verificação de segurança para Django (uv) + React TS (pnpm) + Docker
# Uso: security_check.sh [--fix] [--only backend|frontend|docker|secrets] [--backend-dir DIR] [--frontend-dir DIR]
set -uo pipefail

FIX=0; ONLY=""; BACKEND_DIR="backend"; FRONTEND_DIR="frontend"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix) FIX=1; shift;;
    --only) ONLY="$2"; shift 2;;
    --backend-dir) BACKEND_DIR="$2"; shift 2;;
    --frontend-dir) FRONTEND_DIR="$2"; shift 2;;
    *) echo "arg desconhecido: $1"; exit 2;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
REPORT_DIR="$ROOT/.security-reports"; mkdir -p "$REPORT_DIR"
SUMMARY="$REPORT_DIR/summary.txt"; : > "$SUMMARY"
CRIT=0; HIGH=0; MED=0; LOW=0; SKIPPED=()

log()  { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }
note() { echo "$*" | tee -a "$SUMMARY"; }
skip() { SKIPPED+=("$1"); note "  [skip] $1 — $2"; }
have() { command -v "$1" >/dev/null 2>&1; }
run_if() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

# Instalação best-effort de ferramentas (não altera o projeto)
ensure_uv_tool() { have "$1" || (have uv && uv tool install -q "$2" >/dev/null 2>&1) || true; }
ensure_uv_tool gitleaks gitleaks 2>/dev/null   # gitleaks não é pip; fica aqui só por simetria
ensure_uv_tool bandit bandit
ensure_uv_tool semgrep semgrep
ensure_uv_tool pip-audit pip-audit
ensure_uv_tool lint-imports import-linter

count_sev() { # $1=critical $2=high $3=medium $4=low
  CRIT=$((CRIT+$1)); HIGH=$((HIGH+$2)); MED=$((MED+$3)); LOW=$((LOW+$4))
}

# ---------------------------------------------------------------- secrets
if run_if secrets; then
  log "Segredos (gitleaks)"
  if have gitleaks; then
    gitleaks detect --source . --no-banner --redact -r "$REPORT_DIR/gitleaks.json" >/dev/null 2>&1
    n=$(python3 -c "import json,sys;print(len(json.load(open('$REPORT_DIR/gitleaks.json'))))" 2>/dev/null || echo 0)
    note "  gitleaks: $n segredo(s) potenciais"; count_sev "$n" 0 0 0
  else skip gitleaks "instala: https://github.com/gitleaks/gitleaks#installing"; fi

  log "Ficheiros sensíveis no git"
  bad=$(git ls-files 2>/dev/null | grep -E '(^|/)(\.env|\.env\..*|.*\.pem|.*\.key|db\.sqlite3|id_rsa.*)$' || true)
  if [[ -n "$bad" ]]; then note "  CRITICAL ficheiros sensíveis commitados:"; echo "$bad" | sed 's/^/    /' | tee -a "$SUMMARY"; count_sev "$(echo "$bad" | wc -l)" 0 0 0; else note "  ok"; fi
fi

# ---------------------------------------------------------------- backend
if run_if backend && [[ -d "$BACKEND_DIR" ]]; then
  pushd "$BACKEND_DIR" >/dev/null

  log "bandit"
  if have bandit; then
    bandit -r . -x './.venv,./tests,./*/migrations' -f json -o "$REPORT_DIR/bandit.json" -q >/dev/null 2>&1
    read h m l < <(python3 - <<'PY'
import json;d=json.load(open(__import__('os').environ['REPORT_DIR']+'/bandit.json'))
r=d.get('results',[]);c=lambda s:sum(1 for x in r if x['issue_severity']==s)
print(c('HIGH'),c('MEDIUM'),c('LOW'))
PY
)
    note "  bandit: high=$h medium=$m low=$l"; count_sev 0 "$h" "$m" "$l"
  else skip bandit "uv tool install bandit"; fi

  log "semgrep (django, python, owasp-top-ten)"
  if have semgrep; then
    semgrep --config p/django --config p/python --config p/owasp-top-ten \
      --exclude .venv --exclude migrations --json -o "$REPORT_DIR/semgrep-backend.json" -q . >/dev/null 2>&1
    read h m l < <(python3 - <<'PY'
import json,os;d=json.load(open(os.environ['REPORT_DIR']+'/semgrep-backend.json'))
r=d.get('results',[]);c=lambda s:sum(1 for x in r if x['extra']['severity']==s)
print(c('ERROR'),c('WARNING'),c('INFO'))
PY
)
    note "  semgrep: error=$h warning=$m info=$l"; count_sev 0 "$h" "$m" "$l"
  else skip semgrep "uv tool install semgrep"; fi

  log "pip-audit (dependências)"
  if have pip-audit && have uv; then
    uv export --frozen --no-dev -o "$REPORT_DIR/requirements.txt" >/dev/null 2>&1
    pip-audit -r "$REPORT_DIR/requirements.txt" -f json -o "$REPORT_DIR/pip-audit.json" >/dev/null 2>&1
    n=$(python3 -c "import json,os;d=json.load(open(os.environ['REPORT_DIR']+'/pip-audit.json'));print(sum(len(x.get('vulns',[])) for x in d.get('dependencies',[])))" 2>/dev/null || echo 0)
    note "  pip-audit: $n vulnerabilidade(s)"; count_sev 0 "$n" 0 0
  else skip pip-audit "uv tool install pip-audit"; fi

  log "Django check --deploy"
  if have uv && [[ -f manage.py ]]; then
    out=$(DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}" uv run manage.py check --deploy 2>&1 || true)
    echo "$out" > "$REPORT_DIR/django-check.txt"
    w=$(echo "$out" | grep -cE '^\?: \(security\.W|^\(security' || true)
    e=$(echo "$out" | grep -cE 'ERRORS|\(security\.E' || true)
    note "  check --deploy: warnings=$w errors=$e"; count_sev 0 "$e" "$w" 0
  else skip "check --deploy" "manage.py não encontrado ou uv ausente"; fi

  log "import-linter (fronteiras entre módulos)"
  if have lint-imports && grep -q "importlinter" pyproject.toml 2>/dev/null; then
    if lint-imports > "$REPORT_DIR/import-linter.txt" 2>&1; then note "  fronteiras ok"; else note "  HIGH fronteiras violadas (ver import-linter.txt)"; count_sev 0 1 0 0; fi
  else skip import-linter "configura [tool.importlinter] em pyproject.toml"; fi

  popd >/dev/null
fi

# ---------------------------------------------------------------- frontend
if run_if frontend && [[ -d "$FRONTEND_DIR" ]]; then
  pushd "$FRONTEND_DIR" >/dev/null

  log "pnpm audit"
  if have pnpm; then
    pnpm audit --json > "$REPORT_DIR/pnpm-audit.json" 2>/dev/null || true
    read c h m l < <(python3 - <<'PY'
import json,os
try: v=json.load(open(os.environ['REPORT_DIR']+'/pnpm-audit.json')).get('metadata',{}).get('vulnerabilities',{})
except Exception: v={}
print(v.get('critical',0),v.get('high',0),v.get('moderate',0),v.get('low',0))
PY
)
    note "  pnpm audit: critical=$c high=$h moderate=$m low=$l"; count_sev "$c" "$h" "$m" "$l"
  else skip pnpm-audit "pnpm não encontrado"; fi

  log "semgrep (react, typescript)"
  if have semgrep; then
    semgrep --config p/react --config p/typescript --exclude node_modules --exclude dist \
      --json -o "$REPORT_DIR/semgrep-frontend.json" -q . >/dev/null 2>&1
    read h m l < <(python3 - <<'PY'
import json,os;d=json.load(open(os.environ['REPORT_DIR']+'/semgrep-frontend.json'))
r=d.get('results',[]);c=lambda s:sum(1 for x in r if x['extra']['severity']==s)
print(c('ERROR'),c('WARNING'),c('INFO'))
PY
)
    note "  semgrep: error=$h warning=$m info=$l"; count_sev 0 "$h" "$m" "$l"
  fi

  log "Padrões perigosos (grep)"
  danger=$(grep -rnE "dangerouslySetInnerHTML|localStorage\.(set|get)Item\(['\"](token|jwt|access|refresh)|VITE_[A-Z_]*(SECRET|KEY|TOKEN|PASSWORD)" src 2>/dev/null || true)
  if [[ -n "$danger" ]]; then note "  HIGH padrões perigosos:"; echo "$danger" | head -20 | sed 's/^/    /' | tee -a "$SUMMARY"; count_sev 0 "$(echo "$danger" | wc -l)" 0 0; else note "  ok"; fi

  popd >/dev/null
fi

# ---------------------------------------------------------------- docker
if run_if docker; then
  dfs=$(git ls-files 2>/dev/null | grep -iE '(^|/)(Dockerfile.*|.*\.Dockerfile)$' || find . -name 'Dockerfile*' -not -path '*/node_modules/*' 2>/dev/null)
  if [[ -n "$dfs" ]]; then
    log "hadolint"
    if have hadolint; then
      n=0; for f in $dfs; do n=$((n + $(hadolint -f json "$f" 2>/dev/null | python3 -c "import json,sys;print(sum(1 for x in json.load(sys.stdin) if x['level'] in ('error','warning')))" 2>/dev/null || echo 0))); done
      note "  hadolint: $n problema(s)"; count_sev 0 0 "$n" 0
    else skip hadolint "https://github.com/hadolint/hadolint"; fi

    log "Verificações rápidas de Dockerfile"
    for f in $dfs; do
      grep -qE '^\s*USER\s+' "$f" || { note "  HIGH $f: sem USER não-root"; count_sev 0 1 0 0; }
      grep -qE '^\s*HEALTHCHECK' "$f" || { note "  MEDIUM $f: sem HEALTHCHECK"; count_sev 0 0 1 0; }
      grep -nE '^\s*(ENV|ARG)\s+\w*(SECRET|PASSWORD|TOKEN|KEY)\w*=' "$f" && { note "  CRITICAL $f: segredo em ENV/ARG"; count_sev 1 0 0 0; }
      grep -nE '^\s*COPY\s+.*\.env' "$f" && { note "  CRITICAL $f: COPY de .env"; count_sev 1 0 0 0; }
      grep -qE '^\s*FROM\s+\S+:latest' "$f" && { note "  MEDIUM $f: imagem base :latest"; count_sev 0 0 1 0; }
    done

    log "trivy (config + imagens locais)"
    if have trivy; then
      trivy config --severity HIGH,CRITICAL -f json -o "$REPORT_DIR/trivy-config.json" . >/dev/null 2>&1
      n=$(python3 -c "import json,os;d=json.load(open(os.environ['REPORT_DIR']+'/trivy-config.json'));print(sum(len(r.get('Misconfigurations',[])) for r in d.get('Results',[])))" 2>/dev/null || echo 0)
      note "  trivy config: $n misconfig HIGH/CRITICAL"; count_sev 0 "$n" 0 0
    else skip trivy "https://aquasecurity.github.io/trivy"; fi
  fi
fi

# ---------------------------------------------------------------- resumo
log "RESUMO"
note "critical=$CRIT high=$HIGH medium=$MED low=$LOW"
[[ ${#SKIPPED[@]} -gt 0 ]] && note "ferramentas não corridas: ${SKIPPED[*]}"
note "relatórios em $REPORT_DIR/"
if (( CRIT > 0 || HIGH > 0 )); then note "VEREDICTO: FAIL"; exit 1; else note "VEREDICTO: PASS"; exit 0; fi
