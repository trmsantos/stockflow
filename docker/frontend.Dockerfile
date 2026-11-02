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

# **Os três ficheiros de instalação, e o terceiro entrou a 2026-10-06.** O
# `pnpm-workspace.yaml` é a casa dos `overrides` desde o pnpm v10 — deixou de ser
# o `package.json` — e sem ele aqui o `--frozen-lockfile` falha com
# `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`: dentro da imagem o pnpm não vê override
# nenhum e o lockfile diz que há um. Foi exactamente o que aconteceu, e o
# diagnóstico só é óbvio depois de se saber que a configuração mudou de ficheiro.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
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
)

func main() { caddycmd.Main() }
GO

# As dependências transitivas que trazem CVEs, fixadas nas versões que o
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
# **2026-11-02 — terceira ronda.** Uma CVE HIGH, outra vez negação de serviço:
# CVE-2026-116587 no `github.com/go-jose/go-jose/v4` (v4.1.4), por parâmetros
# RSA forjados num JWK. Não é `stdlib`, logo a lição 1 acima lê-se ao contrário:
# o digest do builder está bom — zero no resto do binário e zero no Alpine — e o
# que faltava era uma linha nesta lista. Entra por `modules/standard`, via
# `caddypki/acmeserver` -> `smallstep/certificates` -> `go-oidc`; é código que
# não usamos, mas está ligado no binário, e o Trivy analisa o binário.
#
# O `-u` resolveu **v4.1.7** (o mínimo corrigido era o 4.1.6) e desta vez não
# levou nada atrás: `crypto`, `net`, `text`, `grpc` e `compress` ficaram onde
# estavam, e as duas imagens resolveram a mesma versão, com e sem o plugin de
# rate limit. Uma cascata vazia também é um resultado medido — o método é que
# não muda: fixa-se o que o `-u` resolveu, não o mínimo corrigido.
#
# **O irmão `go-jose/v3` fica, e convém saber porquê.** O mesmo CVE afecta o
# `v3.0.5` que o `caddypki` arrasta por `go.step.sm/crypto`, e a montante não há
# correcção publicada para o ramo v3: o Trivy marca-o `affected` **sem** versão
# de correcção, e o gate só fica verde porque corre com `--ignore-unfixed`.
# Medido: nem com `go.step.sm/crypto` no v0.91.1, o mais recente, o v3 sai do
# grafo — e esse upgrade arrastava `api`, `protobuf`, `tools` e `genproto` por
# nada. Não há aqui número para fixar; no dia em que o ramo v3 for corrigido a
# montante, entra nesta lista como qualquer outro.
#
# O andar `caddy-builder` é **igual** no `proxy.Dockerfile` e no
# `frontend.Dockerfile` (só o `main.go` difere, pelo plugin). Subir um e
# esquecer o outro deixa o `trivy` a falhar numa das imagens.
RUN go mod init stockflow/caddy \
 && go get github.com/caddyserver/caddy/v2@v2.11.4 \
 && go get golang.org/x/crypto@v0.58.0 \
            golang.org/x/net@v0.61.0 \
            golang.org/x/text@v0.43.0 \
            google.golang.org/grpc@v1.84.0 \
            github.com/klauspost/compress@v1.18.7 \
            github.com/go-jose/go-jose/v4@v4.1.7 \
 && go mod tidy \
 && go build -trimpath -ldflags="-s -w" -o /caddy . \
 && /caddy version

FROM alpine@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

RUN addgroup -g 10001 app \
 && adduser -u 10001 -G app -D -H -s /sbin/nologin app \
 && mkdir -p /data /config /srv \
 && chown -R app:app /data /config /srv

COPY --from=caddy-builder --chown=root:root /caddy /usr/local/bin/caddy
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
