# syntax=docker/dockerfile:1.7
# proxy.Dockerfile — o único serviço que expõe portas ao exterior.
#
# O Caddy é construído aqui e não vem da imagem oficial, por duas razões
# medidas e não por gosto:
#
#   1. **CVEs.** O binário das imagens oficiais (todas as tags, v2.11.4) traz
#      17 CVEs HIGH/CRITICAL **com correção disponível**: Go stdlib 1.26.3
#      quando a correção está na 1.26.4, mais grpc, x/crypto, x/net e x/text.
#      O upstream ainda não reconstruiu. Com um Go recente ficam zero, e o
#      SECURITY.md §9 exige zero. **A versão exacta lê-se no digest abaixo**,
#      não aqui: um número escrito num comentário apodrece e já apodreceu.
#   2. **Rate limit por IP.** O SECURITY.md §1 e §5 delegam-no ao proxy, porque
#      o django-axes cobre a conta e o par IP+conta mas não o IP puro. Não é
#      directiva do Caddy oficial: é o plugin `caddy-ratelimit`, e só entra com
#      uma build própria.
#
# Tudo fixado por versão exacta, incluindo o plugin — este binário está no
# caminho de todo o tráfego, e um `xcaddy build` sem versões é o oposto de
# reproduzível. O módulo de terceiros é uma dependência nova e deliberada.
FROM golang@sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca AS caddy-builder
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

# As quatro dependências transitivas que trazem CVEs, fixadas nas versões que o
# grafo de facto resolve — e não nas versões mínimas corrigidas, que era o meu
# erro: cada mínima puxava outra para cima em cascata (`crypto@0.55` exige
# `net@0.57`, `grpc@1.83.2` exige `text@0.41`). Estes números vieram de deixar o
# Go resolver com `-u` e **ler** o resultado, e estão fixados para a build ser
# reproduzível. O `go mod tidy` é obrigatório depois do upgrade: sem ele faltam
# entradas no `go.sum` dos módulos `standard` e a build morre.
#
# **2026-10-19 — segunda ronda.** Quatro CVEs HIGH no binário, todos de negação
# de serviço e todos já corrigidos a montante: CVE-2026-78669 (excesso de
# SETTINGS em HTTP/2), CVE-2026-78667 (cabeçalhos `Range`) e CVE-2026-97031
# (`crypto/tls`, ECH). Duas lições que a primeira ronda não deu:
#
#   1. **Três dos quatro eram da `stdlib` 1.26.8, e a `stdlib` não se fixa
#      aqui.** Com `GOTOOLCHAIN=local` a stdlib do binário é a da imagem do
#      builder e mais nada — nenhum `go get` lhe toca. A correcção foi subir o
#      digest do `golang` — primeiro para `1.26.9-alpine3.24`, e a
#      2026-10-21 para `1.26.10-alpine3.24` (CVE-2026-111943, em
#      `crypto/x509`), na mesma altura em que o `klauspost/compress`
#      subiu para `v1.18.7` (CVE-2026-63209). Um CVE de `stdlib`
#      lê-se sempre como "o digest do builder está velho", nunca como uma
#      dependência a acrescentar à lista abaixo.
#   2. O método do `-u` voltou a pagar-se. O mínimo corrigido do `x/net` era o
#      0.60.0, mas o grafo resolveu **0.61.0** e levou atrás o `crypto`
#      (0.57→0.58) e o `text` (0.42→0.43); o `grpc` ficou no 1.84.0, que já era
#      o que o `-u` queria. Ter fixado o 0.60.0 à mão recomeçava a cascata.
#
# O andar `caddy-builder` é **igual** no `proxy.Dockerfile` e no
# `frontend.Dockerfile` (só o `main.go` difere, pelo plugin). Subir um e
# esquecer o outro deixa o `trivy` a falhar numa das imagens.
RUN go mod init stockflow/caddy \
 && go get github.com/caddyserver/caddy/v2@v2.11.4 \
 && go get github.com/mholt/caddy-ratelimit@v0.1.0 \
 && go get golang.org/x/crypto@v0.58.0 \
            golang.org/x/net@v0.61.0 \
            golang.org/x/text@v0.43.0 \
            google.golang.org/grpc@v1.84.0 \
            github.com/klauspost/compress@v1.18.7 \
 && go mod tidy \
 && go build -trimpath -ldflags="-s -w" -o /caddy . \
 && /caddy version

# ---------------------------------------------------------------- runtime
# Alpine e não a imagem do Caddy: o binário dela é o que estamos a substituir, e
# deixá-lo na imagem punha os 17 CVEs de volta no relatório do Trivy, que analisa
# o sistema de ficheiros e não o processo. O `wget` do busybox serve o
# healthcheck.
#
# **Sem `apk add`, e isso é a correcção de 2026-10-21.** Havia aqui um
# `ca-certificates` fixado em `=20260909-r0`, e o CI ficou vermelho sozinho, em
# todos os PR, sem ninguém ter tocado em nada: o `apk` resolve contra o
# repositório **vivo** do Alpine, que só guarda o último patch de cada pacote —
# a imagem base está fixada por digest, o repositório de pacotes não. Um pin de
# versão de apk contra um repositório que roda apodrece por construção.
#
# O pacote era para o ACME *"quando o TLS passar a ser terminado aqui"*, e esse
# dia não chegou: o Caddyfile tem `auto_https off` e os dois `reverse_proxy` vão
# para HTTP dentro da rede do compose. Não se carrega uma dependência que
# apodrece por uma necessidade que ainda não existe. Quando o TLS vier mesmo
# para aqui, o pacote volta — a float e com a razão escrita, porque um ficheiro
# de certificados é dos poucos que se quer sempre fresco.
FROM alpine@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

RUN addgroup -g 10001 app \
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
