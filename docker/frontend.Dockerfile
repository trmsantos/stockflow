# syntax=docker/dockerfile:1.7
# frontend.Dockerfile — build do Vite num stage, servido por Caddy no final.
#
# O stage final não tem Node: o que vai para produção são ficheiros estáticos.
# Levar o Node e as 322 dependências de build para a imagem que serve o tráfego
# seria superfície de ataque por nada (SECURITY.md §8, Trivy no CI §9).

# ---------------------------------------------------------------- builder
FROM node@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS builder

# O pnpm vem do corepack, que já vem no Node, e a versão é a do
# `packageManager` do package.json — não uma qualquer do registry.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && corepack install
# `--frozen-lockfile` faz a build falhar se o lockfile não bater com o
# package.json, em vez de resolver versões novas em silêncio.
RUN --mount=type=cache,target=/pnpm-store \
    pnpm config set store-dir /pnpm-store && pnpm install --frozen-lockfile

COPY frontend/ ./
# Sem `VITE_*` nenhuma: tudo o que tem esse prefixo entra no bundle público
# (SECURITY.md §7), por isso a configuração de runtime do cliente não vem daqui.
RUN pnpm build

# ---------------------------------------------------------------- runtime
# O Caddy é construído e não vem da imagem oficial, pela mesma razão do
# `proxy.Dockerfile`: o binário oficial da v2.11.4 traz 17 CVEs HIGH/CRITICAL
# com correção disponível (Go stdlib desactualizado) e o SECURITY.md §9 exige
# zero. Aqui **sem** o plugin de rate limit: este serviço só serve ficheiros
# estáticos na rede interna, o limite por IP é do proxy.
FROM golang@sha256:8ac98ca534ac3f51e1f420a1dd2c15e74c75cfa0f23f3ad27eb5d7236c349a0c AS caddy-builder
# Sem `apk add git`: verificado que o xcaddy resolve os módulos pelo proxy do
# Go e não precisa dele. Menos uma dependência e menos uma versão para fixar.
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@v0.4.7 \
 && xcaddy build v2.11.4

FROM alpine@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

RUN addgroup -g 10001 app \
 && adduser -u 10001 -G app -D -H -s /sbin/nologin app \
 && mkdir -p /data /config /srv \
 && chown -R app:app /data /config /srv

COPY --from=caddy-builder --chown=root:root /go/caddy /usr/local/bin/caddy
COPY --chown=app:app docker/caddy/frontend.Caddyfile /etc/caddy/Caddyfile
COPY --from=builder --chown=app:app /app/dist /srv

# UID numérico: ver DL3066 — o runtime não tem de resolver o nome.
USER 10001:10001
EXPOSE 8080

# `caddy validate` na build apanha um Caddyfile inválido aqui, e não no arranque
# do contentor em produção.
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  # Notação JSON (DL3025) e sem `|| exit 1`: o Docker já trata exit não-zero
  # como unhealthy, e o `wget` devolve não-zero num 4xx/5xx.
  CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/"]

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
