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
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /build

# O `xcaddy` não serve para isto: o `--with` dele trata cada argumento como um
# **plugin a importar**, e `golang.org/x/net` não é um pacote importável na raiz.
# Com o `go.mod` nosso controlamos as versões das dependências transitivas, que
# é precisamente o que falta.
COPY <<'GO' main.go
package main

import (
	caddycmd "github.com/caddyserver/caddy/v2/cmd"
	_ "github.com/caddyserver/caddy/v2/modules/standard"
	_ "github.com/mholt/caddy-ratelimit"
)

func main() { caddycmd.Main() }
GO

# As quatro dependências que trazem os 6 CVEs, fixadas nas versões que o grafo
# de facto resolve — e não nas versões mínimas corrigidas, que era o meu erro:
# cada mínima puxava outra para cima em cascata (`crypto@0.55` exige
# `net@0.57`, `grpc@1.83.2` exige `text@0.41`). Estes números vieram de deixar o
# Go resolver com `-u` e **ler** o resultado, e estão fixados para a build ser
# reproduzível. O `go mod tidy` é obrigatório depois do upgrade: sem ele faltam
# entradas no `go.sum` dos módulos `standard` e a build morre.
RUN go mod init stockflow/caddy \
 && go get github.com/caddyserver/caddy/v2@v2.11.4 \
 && go get github.com/mholt/caddy-ratelimit@v0.1.0 \
 && go get golang.org/x/crypto@v0.57.0 \
            golang.org/x/net@v0.59.0 \
            golang.org/x/text@v0.42.0 \
            google.golang.org/grpc@v1.84.0 \
 && go mod tidy \
 && go build -trimpath -ldflags="-s -w" -o /caddy . \
 && /caddy version

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

COPY --from=caddy-builder --chown=root:root /caddy /usr/local/bin/caddy
COPY --chown=app:app docker/caddy/proxy.Caddyfile /etc/caddy/Caddyfile

# UID numérico: ver DL3066 — o runtime não tem de resolver o nome.
USER 10001:10001
EXPOSE 8080

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
