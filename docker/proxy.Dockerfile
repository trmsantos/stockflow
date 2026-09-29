# syntax=docker/dockerfile:1.7
# proxy.Dockerfile — o único serviço que expõe portas ao exterior.
#
# O Caddy é construído aqui e não vem da imagem oficial, por duas razões
# medidas e não por gosto:
#
#   1. **CVEs.** O binário das imagens oficiais (todas as tags, v2.11.4) traz
#      17 CVEs HIGH/CRITICAL **com correção disponível**: Go stdlib 1.26.3
#      quando a correção está na 1.26.4, mais grpc, x/crypto, x/net e x/text.
#      O upstream ainda não reconstruiu. Com Go 1.26.8 ficam zero, e o
#      SECURITY.md §9 exige zero.
#   2. **Rate limit por IP.** O SECURITY.md §1 e §5 delegam-no ao proxy, porque
#      o django-axes cobre a conta e o par IP+conta mas não o IP puro. Não é
#      directiva do Caddy oficial: é o plugin `caddy-ratelimit`, e só entra com
#      uma build própria.
#
# Tudo fixado por versão exacta, incluindo o plugin — este binário está no
# caminho de todo o tráfego, e um `xcaddy build` sem versões é o oposto de
# reproduzível. O módulo de terceiros é uma dependência nova e deliberada.
FROM golang@sha256:8ac98ca534ac3f51e1f420a1dd2c15e74c75cfa0f23f3ad27eb5d7236c349a0c AS caddy-builder
# Sem `apk add git`: verificado que o xcaddy resolve os módulos pelo proxy do
# Go e não precisa dele. Menos uma dependência e menos uma versão para fixar.
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
# v2.11.4 é a mesma versão da imagem oficial que isto substitui: a única
# diferença é o toolchain e o plugin, e não um salto de versão do servidor.
RUN go install github.com/caddyserver/xcaddy/cmd/xcaddy@v0.4.7 \
 && xcaddy build v2.11.4 --with github.com/mholt/caddy-ratelimit@v0.1.0

# ---------------------------------------------------------------- runtime
# Alpine e não a imagem do Caddy: o binário dela é o que estamos a substituir, e
# deixá-lo na imagem punha os 17 CVEs de volta no relatório do Trivy, que analisa
# o sistema de ficheiros e não o processo. O `wget` do busybox serve o
# healthcheck, e o `ca-certificates` é para o ACME quando o TLS passar a ser
# terminado aqui.
FROM alpine@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

RUN apk add --no-cache "ca-certificates=20260909-r0" \
 && addgroup -g 10001 app \
 && adduser -u 10001 -G app -D -H -s /sbin/nologin app \
 && mkdir -p /data /config \
 && chown -R app:app /data /config

COPY --from=caddy-builder --chown=root:root /go/caddy /usr/local/bin/caddy
COPY --chown=app:app docker/caddy/proxy.Caddyfile /etc/caddy/Caddyfile

# UID numérico: ver DL3066 — o runtime não tem de resolver o nome.
USER 10001:10001
EXPOSE 8080

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
