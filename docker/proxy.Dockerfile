# syntax=docker/dockerfile:1.7
# proxy.Dockerfile — o único serviço que expõe portas ao exterior.
#
# Existe por uma razão só: a imagem oficial do Caddy corre como root e o binário
# traz `cap_net_bind_service` nas capabilities de ficheiro. Com
# `cap_drop: [ALL]` (SECURITY.md §8) o `execve` desse binário falha com
# `operation not permitted`, e o contentor entra em ciclo de reinícios com um
# sintoma que não aponta para a causa. Aqui a cópia do binário perde as
# capabilities (um `cp` simples não copia extended attributes) e o processo ouve
# em 8080, onde não precisa delas — o mapeamento para a porta de fora é do
# compose, e em produção é do orquestrador.
FROM caddy@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b

RUN addgroup -g 10001 app && adduser -u 10001 -G app -D -H -s /sbin/nologin app \
 && cp /usr/bin/caddy /usr/local/bin/caddy \
 && rm /usr/bin/caddy \
 && mkdir -p /data /config \
 && chown -R app:app /data /config

COPY --chown=app:app docker/caddy/proxy.Caddyfile /etc/caddy/Caddyfile

USER app
EXPOSE 8080

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
