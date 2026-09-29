#!/usr/bin/env bash
#
# gen:api — regenera o cliente TypeScript a partir dos serializers do Django.
#
# Cadeia: serializers -> drf-spectacular -> openapi/schema.yaml ->
# openapi-typescript -> src/lib/api/types.ts. Os dois artefactos ficam
# commitados e o CI corre isto e falha se o diff não estiver vazio: ninguém
# muda a API sem atualizar o cliente (ARCHITECTURE.md §5).
#
# Usa o comando `manage.py spectacular` e não o endpoint `/api/v1/schema/`: o
# endpoint pede autenticação e âmbito de tenant, e não há nenhum num CI.
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$(cd "${FRONTEND_DIR}/../backend" && pwd)"
SCHEMA="${FRONTEND_DIR}/openapi/schema.yaml"
TYPES="${FRONTEND_DIR}/src/lib/api/types.ts"

if ! command -v uv >/dev/null 2>&1; then
  echo "gen:api: 'uv' não está no PATH. O schema vem do Django (CLAUDE.md: nunca pip)." >&2
  exit 1
fi

mkdir -p "$(dirname "${SCHEMA}")" "$(dirname "${TYPES}")"

echo "gen:api: a gerar o schema OpenAPI a partir de ${BACKEND_DIR}"
# `--frozen`: instala o que está no uv.lock e nunca o reescreve — este script
# não é o sítio onde as dependências do backend mudam.
# `--fail-on-warn`: um serializer ambíguo passa a ser um erro aqui, e não um
# `unknown` que só aparece no frontend.
# `--file`: o schema sai para ficheiro, não para o stdout, que também leva as
# linhas de log JSON do Django.
(
  cd "${BACKEND_DIR}"
  uv run --frozen python manage.py spectacular \
    --format openapi \
    --fail-on-warn \
    --file "${SCHEMA}"
)

echo "gen:api: a gerar ${TYPES#"${FRONTEND_DIR}/"}"
# `--alphabetize`: ordem estável, para o diff do CI ser sobre a API e não sobre
# a ordem em que o drf-spectacular emitiu os componentes.
pnpm exec openapi-typescript "${SCHEMA}" \
  --alphabetize \
  --output "${TYPES}"

paths=$(grep -c "^    \"/" "${SCHEMA}" || true)
echo "gen:api: pronto — ${paths} path(s) no schema."
if [ "${paths}" -eq 0 ]; then
  echo "gen:api: o schema não tem paths. É o esperado enquanto nenhum módulo"
  echo "         registar urls em config/urls.py; o cliente gerado fica vazio."
fi
