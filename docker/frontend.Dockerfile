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
FROM caddy@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b AS runtime

# A imagem do Caddy corre como root por omissão. Ouvimos em 8080 (>1024), logo
# não é preciso.
#
# E há uma armadilha: o binário do Caddy vem com `cap_net_bind_service` nas
# **capabilities de ficheiro**, para se poder ligar à porta 80 sem ser root. Com
# `cap_drop: [ALL]` no compose o bounding set fica vazio, e o `execve` de um
# binário com capabilities que não podem ser concedidas falha com
# `operation not permitted` — o contentor entra em ciclo de reinícios e o
# sintoma não aponta para aqui. Um `cp` simples não copia extended attributes,
# logo a cópia fica sem as capabilities, que é o que queremos: em 8080 não
# servem para nada e a alternativa era não retirar as capabilities.
RUN addgroup -g 10001 app && adduser -u 10001 -G app -D -H -s /sbin/nologin app \
 && cp /usr/bin/caddy /usr/local/bin/caddy \
 && rm /usr/bin/caddy \
 && mkdir -p /data /config /srv \
 && chown -R app:app /data /config /srv

COPY --chown=app:app docker/caddy/frontend.Caddyfile /etc/caddy/Caddyfile
COPY --from=builder --chown=app:app /app/dist /srv

USER app
EXPOSE 8080

# `caddy validate` na build apanha um Caddyfile inválido aqui, e não no arranque
# do contentor em produção.
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/ || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
