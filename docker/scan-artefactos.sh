#!/usr/bin/env bash
# scan-artefactos.sh — procura segredos DENTRO das imagens construídas.
#
# Existe por um incidente: o `backend/.env`, com a password do dono da base de
# dados, esteve dentro da imagem que servia pedidos, e **nenhum** dos outros
# gates o podia ver. O gitleaks olha para o git (e o ficheiro nunca entrou), o
# `trivy config` olha para o texto do Dockerfile, a verificação de
# `COPY .*\.env` não casa com `COPY backend/`, e o `docker history` mostra
# comandos e não conteúdo.
#
# ## Como olha para dentro, e porque não é com um shell
#
# `docker create` + `docker export`, e varre-se o tar **no host**. As duas
# versões anteriores olhavam de *dentro* do artefacto e ambas se declararam
# limpas sobre imagens que nunca abriram:
#
#   - `docker run --entrypoint sh … find /app`: o objecto auditado fornecia o
#     shell, o `USER`, o `WORKDIR` e a disposição de directórios da sua própria
#     auditoria. Medido: `/app` **não existe** no frontend nem no proxy (o que
#     é nosso está em `/srv` e `/etc/caddy`), e o `USER 10001` faz o
#     `find /root` sair em EACCES — engolido pelo `2>/dev/null`. O gate dizia
#     `ok` sobre duas das três imagens que o CI lhe manda varrer sem ter aberto
#     um único ficheiro nelas.
#   - `docker save | tar -tf -`: lista o **invólucro OCI** (`blobs/sha256/…`,
#     `index.json`, `oci-layout`), não os caminhos dos ficheiros, que estão
#     dentro de cada blob. Medido: não podia casar nada, e imprimia
#     "varrido pelo tar — nada encontrado" como se tivesse varrido.
#
# O `docker export` achata o sistema de ficheiros num tar cujos membros **são**
# os caminhos reais. Não precisa de shell, não depende do `USER` da imagem e não
# supõe onde é que a imagem guarda o que é nosso.
#
# ## A decisão de âmbito, que é o que faz este gate útil em vez de ruidoso
#
# Dois tiers, com âmbitos deliberadamente diferentes:
#
#   - **Nomes: a imagem inteira.** Sem âmbito nenhum, porque não é preciso —
#     medido contra as 6 imagens reais, o padrão de nomes dá exactamente um
#     casamento, o `app/.env.example`, que é o template e está excluído. Nomes
#     como `.env`, `.pgpass` ou `id_ed25519` não existem numa imagem base.
#   - **Conteúdo: o que nós pusemos na imagem.** Com âmbito, e por medição:
#     `PRIVATE KEY-----` aparece **1 vez no `stockflow-caddy-bin`**, que tem 13
#     ficheiros — está dentro do binário Go, que traz a etiqueta PEM como
#     literal. No backend aparece 13 vezes, todas na `.venv`. Um tier de
#     conteúdo sem âmbito gritava em todas as imagens a todas as corridas, e um
#     gate que grita sempre é um gate que alguém desliga.
#
# `*.key` e `*.pem` ficam fora do tier de nomes pela mesma razão medida: dariam
# 152 falsos positivos no backend e 123 no proxy. Entram pelo conteúdo, onde o
# cabeçalho PEM distingue uma chave de um certificado.
#
# Um segredo dentro de uma dependência vendorizada é um problema diferente
# (cadeia de fornecimento): é o `pip-audit`, o `pnpm audit` e o `trivy image`.
#
# Não procura por entropia: medido, o `trivy image --scanners secret` devolve
# zero contra uma imagem de sonda com cinco ficheiros de segredo e um `ENV`.
#
# ## O que este gate nunca faz
#
# Dizer "limpa" sem ter varrido. Cada passo que pode falhar — criar o
# contentor, exportar, listar o tar, extrair o âmbito — sai **2**, que o
# `security_check.sh` traduz em INCONCLUSIVO e não em PASS. E cada imagem
# imprime a cobertura que teve (membros totais, ficheiros no âmbito de
# conteúdo), para que zero cobertura seja visível em vez de silenciosa.
#
# Uso: scan-artefactos.sh [imagem...]   (sem argumentos: todas as stockflow-*)
# Saída: exit 0 limpo · 1 achados · 2 não foi possível varrer.
set -uo pipefail

# Nomes que não têm razão de existir numa imagem. Calibrado contra as 6 imagens
# reais: um único casamento, o `.env.example`, excluído à parte.
readonly RE_NOMES='(^|/)(\.env|\.env\..+|[^/]+\.env|\.netrc|\.pgpass|\.git-credentials|\.npmrc|\.yarnrc(\.yml)?|\.pypirc|\.dockercfg|id_rsa|id_dsa|id_ecdsa|id_ed25519|secrets\.(json|ya?ml)|credentials\.(json|ya?ml|ini)|service-account[^/]*\.json|terraform\.tfvars|[^/]+\.(p12|pfx|jks|keystore|kdbx)|settings\.local[^/]*|config_local[^/]*|[^/]*local_settings[^/]*)$'
readonly RE_NOMES_PATH='(^|/)(\.aws/credentials|\.aws/config|\.docker/config\.json|\.kube/config|\.config/gcloud/.+|\.ssh/id_[^/]+)$'

# O âmbito do tier de conteúdo: o que nós copiámos para a imagem, onde cada
# imagem o guarda de facto. `/app` é o backend; `/srv` e `/etc/caddy` são o
# frontend e o proxy; `/root` e `/home` nunca são nossos mas são onde as
# ferramentas deixam credenciais.
readonly RE_AMBITO='^(app|srv|etc/caddy|root|home)/'
readonly RE_PODA='^app/(\.venv|staticfiles)/|/__pycache__/|^app/node_modules/'

# Placeholders excluídos: a diferença entre "há uma credencial aqui" e "há um
# exemplo de formato numa docstring". O `config/env.py` tem
# `postgres://utilizador:password@host` numa mensagem de erro, e o
# `.env.example` tem os `muda-me-*` — eram os únicos falsos positivos que
# sobravam.
readonly RE_DSN='[a-z][a-z0-9+.-]*://[^:/@[:space:]]+:[^@[:space:]/]{6,}@'
readonly RE_PLACEHOLDER=':(password|passwd|senha|muda-me[a-z-]*|changeme|secret|placeholder|exemplo|example|xxx+|[*]+|your[-_]?password|<[^>]*>)@'

imagens=("$@")
if [[ ${#imagens[@]} -eq 0 ]]; then
    # Sem `mapfile`: é do bash 4 e o macOS traz o 3.2. Este ficheiro corre na
    # máquina de quem desenvolve e no runner do CI.
    while IFS= read -r linha; do
        [[ -n "$linha" ]] && imagens+=("$linha")
    done < <(docker images --format '{{.Repository}}' 2>/dev/null | grep -E '^stockflow-' | sort -u)
fi
if [[ ${#imagens[@]} -eq 0 ]]; then
    echo "nenhuma imagem para analisar" >&2
    exit 2
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/scan-artefactos.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT

achados=0
inconclusivos=0

for img in "${imagens[@]}"; do
    linhas=""
    tar_img="$tmp/img.tar"
    lista="$tmp/lista.txt"
    rm -rf "$tmp/ex" "$tar_img" "$lista"

    # O comando fictício é para as imagens sem `CMD` nem `ENTRYPOINT` — um stage
    # que é só um binário. Sem ele, `docker create` sai com "no command
    # specified" e o contentor nunca existe. Nada é executado: `create` não
    # arranca nada, e o `export` lê o sistema de ficheiros do contentor parado.
    cid=$(docker create "$img" /nao-executado 2>/dev/null) \
        || cid=$(docker create "$img" 2>/dev/null)
    if [[ -z "$cid" ]]; then
        echo "$img: NÃO VARRIDA — docker create falhou" >&2
        inconclusivos=$((inconclusivos + 1))
        continue
    fi
    docker export "$cid" -o "$tar_img" 2>/dev/null; estado_export=$?
    docker rm -f "$cid" >/dev/null 2>&1
    if (( estado_export != 0 )) || [[ ! -s "$tar_img" ]]; then
        echo "$img: NÃO VARRIDA — docker export falhou" >&2
        inconclusivos=$((inconclusivos + 1))
        continue
    fi
    if ! tar -tf "$tar_img" > "$lista" 2>/dev/null || [[ ! -s "$lista" ]]; then
        echo "$img: NÃO VARRIDA — a listagem do tar saiu vazia" >&2
        inconclusivos=$((inconclusivos + 1))
        continue
    fi
    # Um nome de ficheiro com carácter de controlo partiria a lista que
    # alimenta a extracção, e o membro escapava sem rasto. Recusa-se em voz
    # alta em vez de se varrer por alto.
    #
    # `[[:cntrl:]]` e não `grep -P`: o `-P` é do GNU grep, o macOS traz o BSD
    # que não o tem, e a forma como isto falharia lá era a pior possível — o
    # `grep` sai 2, a condição dá falso, e a verificação nunca corre sem o
    # dizer. (O meu grep local é o ugrep, que aceita `-P`: medi a portabilidade
    # onde ela não se via.)
    if LC_ALL=C grep -q '[[:cntrl:]]' "$lista"; then
        echo "$img: NÃO VARRIDA — membro com carácter de controlo no nome" >&2
        inconclusivos=$((inconclusivos + 1))
        continue
    fi

    membros=$(wc -l < "$lista" | tr -d ' ')

    # (1) Nomes, na imagem inteira.
    nomes=$(grep -E "$RE_NOMES" "$lista" | grep -vE '(^|/)\.env\.example$' || true)
    nomes_path=$(grep -E "$RE_NOMES_PATH" "$lista" | grep -vE '\.pub$' || true)

    # (2) Conteúdo, no que é nosso. A extracção é para um directório descartável
    #     e só dos membros do âmbito; o `find -type f` a seguir é o que dá o
    #     número honesto de ficheiros varridos (um symlink não tem conteúdo).
    grep -E "$RE_AMBITO" "$lista" | grep -vE "$RE_PODA" | grep -vE '/$' > "$tmp/escopo.txt" || true
    no_ambito=0
    conteudo=""
    if [[ -s "$tmp/escopo.txt" ]]; then
        mkdir -p "$tmp/ex"
        if ! tar -xf "$tar_img" -C "$tmp/ex" -T "$tmp/escopo.txt" 2>/dev/null; then
            echo "$img: NÃO VARRIDA — a extracção do âmbito falhou" >&2
            inconclusivos=$((inconclusivos + 1))
            continue
        fi
        chmod -R u+rwX "$tmp/ex" 2>/dev/null || true
        no_ambito=$(find "$tmp/ex" -type f 2>/dev/null | wc -l | tr -d ' ')
        while IFS= read -r f; do
            rel=${f#"$tmp/ex/"}
            if head -c 400 "$f" 2>/dev/null | grep -qa 'PRIVATE KEY-----'; then
                conteudo="$conteudo/$rel (chave privada)"$'\n'
            fi
            if grep -qa '_authToken' "$f" 2>/dev/null; then
                conteudo="$conteudo/$rel (token de registry)"$'\n'
            fi
            if grep -haoE "$RE_DSN" "$f" 2>/dev/null | grep -qvE "$RE_PLACEHOLDER"; then
                conteudo="$conteudo/$rel (credencial em DSN)"$'\n'
            fi
        done < <(find "$tmp/ex" -type f 2>/dev/null)
    fi

    for bloco in "$nomes" "$nomes_path"; do
        [[ -n "$bloco" ]] && linhas=$(printf '%s\n%s' "$linhas" \
            "$(printf '%s\n' "$bloco" | sed 's|^|  ficheiro: /|')")
    done
    [[ -n "$conteudo" ]] && linhas=$(printf '%s\n%s' "$linhas" \
        "$(printf '%s' "$conteudo" | sed 's|^|  conteúdo: |')")

    # O ambiente gravado na imagem: sai num `docker inspect` a quem a puxar, sem
    # precisar de ficheiro nenhum. Três passagens, porque o nome não basta — o
    # `MIGRATION_DATABASE_URL` com a password do dono, que foi o que esteve
    # dentro da imagem, não tem `SECRET` nem `PASSWORD` no nome, e nem o
    # `FIELD_ENCRYPTION_KEY` nem o `STOCKFLOW_NIF_PEPPER` casavam o padrão
    # antigo — são os dois segredos cuja rotação é mais cara de todas.
    env_bruto=$(docker inspect "$img" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)
    ambiente=$(printf '%s\n' "$env_bruto" \
        | grep -iE '^[A-Z0-9_]*(SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE_KEY|API_KEY|ENCRYPTION_KEY|PEPPER|SALT|BASIC_AUTH|_KEY|DSN)[A-Z0-9_]*=.+' \
        | grep -viE '^(GPG_KEY|PYTHON_GPG_KEY|SSL_CERT_(FILE|DIR))=' || true)
    dsn=$(printf '%s\n' "$env_bruto" | grep -E "=$RE_DSN" | grep -vE "$RE_PLACEHOLDER" || true)
    for bloco in "$ambiente" "$dsn"; do
        [[ -n "$bloco" ]] && linhas=$(printf '%s\n%s' "$linhas" \
            "$(printf '%s\n' "$bloco" | sed -E 's/=.*/=<omitido>/; s/^/  ENV: /')")
    done

    linhas=$(printf '%s' "$linhas" | grep -v '^$' | sort -u || true)
    cobertura="$membros membros, $no_ambito no âmbito de conteúdo"
    if [[ -n "$linhas" ]]; then
        echo "$img: $cobertura — ACHADOS"
        echo "$linhas"
        achados=$((achados + $(printf '%s\n' "$linhas" | wc -l | tr -d ' ')))
    else
        echo "$img: $cobertura — limpa"
    fi
done

if (( inconclusivos > 0 )); then
    echo "$inconclusivos imagem(ns) não foi possível varrer" >&2
    exit 2
fi
if (( achados > 0 )); then
    echo "$achados achado(s) de segredo em imagens" >&2
    exit 1
fi
echo "ok (${#imagens[@]} imagens varridas)"
