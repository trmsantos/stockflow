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
# primeiras versões olhavam de *dentro* do artefacto e ambas se declararam
# limpas sobre imagens que nunca abriram:
#
#   - `docker run --entrypoint sh … find /app`: o objecto auditado fornecia o
#     shell, o `USER`, o `WORKDIR` e a disposição de directórios da sua própria
#     auditoria. Medido: `/app` **não existe** no frontend nem no proxy, e o
#     `USER 10001` faz o `find /root` sair em EACCES, engolido pelo
#     `2>/dev/null`. O gate dizia `ok` sobre duas das três imagens do CI sem ter
#     aberto um ficheiro nelas.
#   - `docker save | tar -tf -`: lista o **invólucro OCI** (`blobs/sha256/…`,
#     `index.json`), não os caminhos dos ficheiros, que estão dentro de cada
#     blob. Não podia casar nada, e imprimia "varrido pelo tar — nada
#     encontrado" como se tivesse varrido.
#
# O `docker export` achata o sistema de ficheiros num tar cujos membros *são*
# os caminhos reais. Sem shell, sem depender do `USER`, sem supor a disposição.
#
# ## O âmbito, e porque deixou de ser uma lista de caminhos
#
# **Nomes: a imagem inteira. Conteúdo: a imagem inteira menos o que é
# vendorizado** (`.venv`, `site-packages`, `node_modules`, `__pycache__`,
# `staticfiles`). Não há lista de inclusão.
#
# A terceira versão tinha uma (`app`, `srv`, `etc/caddy`, `root`, `home`) e foi
# ela a causa de três evasões, todas com `exit 0` e a palavra `limpa`:
#
#   - segredo em `/opt`, `/var/lib` ou `/usr/local/etc` — fora da lista;
#   - ficheiro no âmbito com nome neutro que era **symlink** para fora dele: o
#     `find -type f` não segue links e o alvo não era extraído. A pior das três,
#     porque a linha de cobertura saía normal (62 ficheiros) e não deixava rasto;
#   - o próprio `/app` ser symlink para `/opt/app`, anulando o âmbito inteiro.
#
# Uma lista de inclusão falha **cega**: o que não está nela não é varrido, em
# silêncio. Uma de exclusão falha **ruidosa**, e ruído mede-se. Medido no
# backend: 62 ficheiros no âmbito antigo com 0 falsos positivos, contra **5 958
# no âmbito novo, também com 0** — sobre a stdlib inteira do Python e as
# bibliotecas do Debian 12.
#
# O que tornou isso possível foi apertar os **padrões** em vez de estreitar o
# âmbito:
#
#   - a chave privada é um **bloco PEM ancorado à linha** e não a substring
#     `PRIVATE KEY-----`. Medido no binário do Caddy, 52 MB do nosso Go: a
#     substring casa (` denied: %v PRIVATE KEY-----no SNI`, tabela de strings),
#     o bloco ancorado dá 0, e numa chave verdadeira dá 1. O falso positivo que
#     justificava o âmbito estreito não era da chave — era do padrão;
#   - `AKIA` exige fronteira à esquerda: sem ela casava
#     `ISAKIAISLANDISSHARITALICI…`, uma lista de palavras Unicode do
#     `libunistring`;
#   - a poda é por **componente de caminho** (`/.venv/`) e não ancorada em
#     `^app/`. Com a ancoragem, uma imagem em que `/app` era symlink para
#     `/opt/app` devolvia 13 falsos positivos de docstrings do `kombu` e do
#     `redis` — a poda deixava de casar ao mesmo tempo que o âmbito se abria;
#   - lê-se o ficheiro **inteiro** e não os primeiros 400 bytes. Uma chave ao
#     byte 601 passava, e a cobertura dizia "3 no âmbito — limpa" sobre três
#     ficheiros todos com segredo: contava ficheiros **abertos**, não varridos.
#
# Os 60 falsos positivos da primeira tentativa vinham da `.venv` e do `/etc`
# com padrões largos. Um segredo dentro de uma dependência vendorizada é cadeia
# de fornecimento: é o `pip-audit`, o `pnpm audit` e o `trivy image`.
#
# Custo medido: ~3 s a extrair e ~1 s a varrer a imagem do backend. Os greps são
# em lote — cinco padrões num ciclo por ficheiro davam 30 000 processos por
# imagem e não acabavam em dez minutos.
#
# Não procura por entropia: medido, o `trivy image --scanners secret` devolve
# zero contra uma imagem de sonda com cinco ficheiros de segredo e um `ENV`.
#
# ## O que este gate nunca faz
#
# Dizer "limpa" sem ter varrido. Criar o contentor, exportar, listar o tar e
# extrair são quatro passos que podem falhar, e cada um sai **2**, que o
# `security_check.sh` traduz em INCONCLUSIVO e não em PASS. E **zero ficheiros
# varridos é exit 2**: com o âmbito a ser a imagem inteira, zero não significa
# "não há nada nosso aqui", significa que a extracção não produziu nada.
#
# Um nome com carácter de controlo sai 2 pelo guarda; um nome com **newline**
# não é visto pelo guarda (o `grep` parte a linha nele) mas parte a lista de
# extracção, e o `tar` falha — que é o mesmo exit 2 por outro caminho. Os dois
# falham fechados, e é isso que aqui se promete.
#
# Uso: scan-artefactos.sh [imagem...]   (sem argumentos: todas as stockflow-*)
# Saída: exit 0 limpo · 1 achados · 2 não foi possível varrer.
set -uo pipefail

# Nomes que não têm razão de existir numa imagem. Calibrado contra as 6 imagens
# reais: um único casamento, o `.env.example`, tratado à parte.
readonly RE_NOMES='(^|/)(\.env|\.env\..+|[^/]+\.env|\.netrc|\.pgpass|\.git-credentials|\.npmrc|\.yarnrc(\.yml)?|\.pypirc|\.dockercfg|id_rsa|id_dsa|id_ecdsa|id_ed25519|secrets\.(json|ya?ml)|credentials\.(json|ya?ml|ini)|service-account[^/]*\.json|terraform\.tfvars|[^/]+\.(p12|pfx|jks|keystore|kdbx)|settings\.local[^/]*|config_local[^/]*|[^/]*local_settings[^/]*)$'
readonly RE_NOMES_PATH='(^|/)(\.aws/credentials|\.aws/config|\.docker/config\.json|\.kube/config|\.config/gcloud/.+|\.ssh/id_[^/]+)$'

# Poda por **componente de caminho** e não ancorada na raiz: o conteúdo pode
# estar em `/app`, em `/opt/app` ou onde um symlink o levar.
readonly RE_PODA='(^|/)(\.venv|site-packages|node_modules|__pycache__|staticfiles|\.git)/'

# Bloco PEM ancorado à linha, não a substring — ver o cabeçalho.
readonly RE_PEM='^-----BEGIN [A-Z ]*PRIVATE KEY-----$'
# Credenciais de formato conhecido, com fronteira à esquerda.
readonly RE_CHAVES='(^|[^A-Za-z0-9])(AKIA[0-9A-Z]{16}|(sk|rk)_live_[0-9A-Za-z]{16,}|gh[pousr]_[0-9A-Za-z]{30,})'
# Atribuição com nome de segredo e valor de 16+ caracteres sem espaços. Apanha o
# `DJANGO_SECRET_KEY=<64 chars>` num `.env.example` que deixou de ser template, e
# um `settings_prod.py` com a chave escrita à mão.
# A palavra de segredo tem de estar **imediatamente antes** do `=`. Com
# `_KEY[A-Z0-9_]*=`, o `TMP_KEYRING="${GPGHOMEDIR}/tmp-keyring.gpg"` do
# `/usr/bin/apt-key` casava (3 vezes), e o binário do Caddy também. Medido
# com a forma estrita: `apt-key` 3 -> 0, `caddy` 1 -> 0, e um
# `DJANGO_SECRET_KEY=` verdadeiro continua apanhado.
readonly RE_ATRIBUICAO='(^|[^A-Za-z0-9_])[A-Z][A-Z0-9_]*(SECRET|PASSWORD|PASSWD|TOKEN|PEPPER|SALT|KEY|APIKEY)=[^[:space:]]{16,}'

# A password do DSN aceita `/` (o percent-encoding é comum) e desce a 4
# caracteres: `postgres://stockflow_owner:ab/cd@db:5432/s` passava as barras
# anteriores.
# Limite de tamanho dos dois padrões com quantificador aberto. 4 MB deixa de
# fora, no backend, duas bibliotecas partilhadas da imagem base e mais nada.
readonly LIMITE_KB=4096
readonly RE_DSN='[a-z][a-z0-9+.-]*://[^:/@[:space:]]+:[^@[:space:]]{4,}@'
# Placeholders, aplicados ao que vem depois dos `:` num DSN.
readonly RE_PLACEHOLDER=':(password|passwd|senha|muda-me[a-z-]*|changeme|secret|placeholder|exemplo|example|xxx+|[*]+|your[-_]?password|<[^>]*>|user|pass|admin|root|guest|tiger|masterkey)@'
# Placeholders, aplicados ao que vem depois do `=` numa atribuição — é um
# vocabulário diferente e por isso um padrão diferente.
readonly RE_PLACEHOLDER_VALOR='=["'"'"'`]?(\$|\{\{|%s|<|muda-me|changeme|change-me|placeholder|exemplo|example|your[-_]|xxx+|[*]+|troca-me|substitui)'

# Os únicos `ENV` com valor longo e sem espaços nas 6 imagens reais, medidos. A
# **isenção** é que é a lista: uma entrada nova aqui aparece no diff, enquanto um
# `ENV` novo com segredo não precisa de aparecer em sítio nenhum.
readonly ENV_BENIGNOS='PATH|GPG_KEY|PYTHON_GPG_KEY|PYTHON_SHA256|PYTHON_VERSION|PYTHON_SETUPTOOLS_VERSION|PYTHON_PIP_VERSION|DJANGO_SETTINGS_MODULE|NODE_VERSION|YARN_VERSION|PNPM_HOME|SSL_CERT_FILE|SSL_CERT_DIR|LANG|LC_ALL|TZ'

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
        inconclusivos=$((inconclusivos + 1)); continue
    fi
    docker export "$cid" -o "$tar_img" 2>/dev/null; estado_export=$?
    docker rm -f "$cid" >/dev/null 2>&1
    if (( estado_export != 0 )) || [[ ! -s "$tar_img" ]]; then
        echo "$img: NÃO VARRIDA — docker export falhou" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi
    if ! tar -tf "$tar_img" > "$lista" 2>/dev/null || [[ ! -s "$lista" ]]; then
        echo "$img: NÃO VARRIDA — a listagem do tar saiu vazia" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi
    # `[[:cntrl:]]` e não `grep -P`: o `-P` é do GNU grep, o macOS traz o BSD que
    # não o tem, e falharia da pior forma — o grep sai 2, a condição dá falso, e
    # a verificação nunca corre sem o dizer. (O meu grep interactivo é o ugrep,
    # que aceita `-P`: medi a portabilidade onde ela não se via.)
    if LC_ALL=C grep -q '[[:cntrl:]]' "$lista"; then
        echo "$img: NÃO VARRIDA — membro com carácter de controlo no nome" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi

    membros=$(wc -l < "$lista" | tr -d ' ')

    # (1) Nomes, na imagem inteira. O `.env.example` sai daqui porque é o
    #     template, mas **não** sai da verificação: o tier de conteúdo decide se
    #     ele ainda é template. Excluí-lo dos dois fazia dele o único sítio
    #     garantidamente ignorado da imagem.
    nomes=$(grep -E "$RE_NOMES" "$lista" | grep -vE '(^|/)\.env\.example$' || true)
    nomes_path=$(grep -E "$RE_NOMES_PATH" "$lista" | grep -vE '\.pub$' || true)

    # (2) Conteúdo: a imagem inteira menos o vendorizado.
    grep -vE '/$' "$lista" | grep -vE "$RE_PODA" > "$tmp/escopo.txt" || true
    if [[ ! -s "$tmp/escopo.txt" ]]; then
        echo "$img: NÃO VARRIDA — nenhum membro fora da poda" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi
    mkdir -p "$tmp/ex"
    if ! tar -xf "$tar_img" -C "$tmp/ex" -T "$tmp/escopo.txt" 2>/dev/null; then
        echo "$img: NÃO VARRIDA — a extracção falhou" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi
    chmod -R u+rwX "$tmp/ex" 2>/dev/null || true
    # O número honesto é o de ficheiros **regulares** extraídos: um symlink não
    # tem conteúdo próprio, e o alvo dele está no âmbito porque o âmbito é tudo.
    varridos=$(find "$tmp/ex" -type f 2>/dev/null | wc -l | tr -d ' ')
    if (( varridos == 0 )); then
        echo "$img: NÃO VARRIDA — zero ficheiros legíveis extraídos" >&2
        inconclusivos=$((inconclusivos + 1)); continue
    fi

    # Substituição de processo e **não** `grep | juntar`: num pipeline o bash
    # corre cada elemento num subshell, logo as atribuições a `conteudo` dentro
    # do `juntar` morreriam com o subshell e o gate imprimia `limpa` tendo
    # achados na mão. É o modo de falha desta sessão inteira, e escrevi-o outra
    # vez na primeira tentativa.
    #
    # `grep -r` (minúscula) não segue symlinks; o `-R` seguiria e podia ciclar.
    # Passagem de descoberta: uma só, e depois as cinco verificações apenas nos
    # ficheiros candidatos. O `-l` pára no primeiro casamento de cada ficheiro, o
    # que torna a descoberta barata.
    #
    # **Dois dos cinco padrões têm limite de tamanho, e é por medição.** O
    # `RE_CHAVES` e o `RE_ATRIBUICAO` têm quantificadores abertos (`{16,}`,
    # `{30,}`) e o motor de regex do grep do BSD faz backtracking patológico
    # sobre binários grandes: medido na imagem do backend, `RE_CHAVES` sozinho
    # levava **24 dos 30 segundos**, e caía a **zero** excluindo dois ficheiros —
    # `libpython3.12.so` (6,3 MB) e `libcrypto.so.3` (4,4 MB), 10 MB de 146 MB.
    # Os outros três, incluindo o bloco PEM que é o que interessa num ficheiro de
    # chave, correm sobre **todos** os ficheiros sem limite, em 8 s.
    #
    # Quantos ficheiros ficaram com cobertura parcial sai na linha de cobertura.
    # Um compromisso de desempenho que não se vê é um buraco; este vê-se.
    #
    # `grep -r` (minúscula) não segue symlinks; o `-R` seguiria e podia ciclar. O
    # alvo de um symlink está no âmbito de qualquer maneira, porque o âmbito é a
    # imagem toda — foi a falta disso que deixou passar a evasão do
    # `/app/prod_config.py -> /opt/alvo.txt`.
    conteudo=""
    candidatos="$tmp/candidatos.txt"
    : > "$candidatos"
    LC_ALL=C grep -rlaE "($RE_PEM)|(_authToken)|($RE_DSN)" "$tmp/ex" \
        >> "$candidatos" 2>/dev/null || true
    find "$tmp/ex" -type f -size -"${LIMITE_KB}"k -print0 2>/dev/null \
        | xargs -0 LC_ALL=C grep -laE "($RE_CHAVES)|($RE_ATRIBUICAO)" \
        >> "$candidatos" 2>/dev/null || true
    grandes=$(find "$tmp/ex" -type f -size +"${LIMITE_KB}"k 2>/dev/null | wc -l | tr -d ' ')

    # Nos dois padrões com filtro, o filtro é sobre o **valor casado** e não
    # sobre o nome do ficheiro. Escrevi-o uma vez como `grep -rloaE`, com `-l` e
    # `-o` juntos: o `-l` ganha, a saída são só nomes de ficheiro, o filtro de
    # placeholders aplicado a um nome nunca casa nada, e o gate reportava como
    # achado todo o ficheiro com um DSN de exemplo — incluindo o `.env.example`
    # e a mensagem de erro do `config/env.py`.
    while IFS= read -r f; do
        [[ -n "$f" && -f "$f" ]] || continue
        rel="/${f#"$tmp/ex/"}"
        LC_ALL=C grep -qaE "$RE_PEM" "$f" 2>/dev/null \
            && conteudo="$conteudo$rel (chave privada em bloco PEM)"$'\n'
        LC_ALL=C grep -qa '_authToken' "$f" 2>/dev/null \
            && conteudo="$conteudo$rel (token de registry)"$'\n'
        LC_ALL=C grep -oaE "$RE_DSN" "$f" 2>/dev/null | grep -qvE "$RE_PLACEHOLDER" \
            && conteudo="$conteudo$rel (credencial em DSN)"$'\n'
        # Os dois com quantificador aberto, só abaixo do limite — a mesma
        # condição da passagem de descoberta, para o relatório não afirmar uma
        # cobertura que não houve.
        if [[ $(wc -c < "$f" 2>/dev/null || echo 0) -lt $((LIMITE_KB * 1024)) ]]; then
            LC_ALL=C grep -qaE "$RE_CHAVES" "$f" 2>/dev/null \
                && conteudo="$conteudo$rel (credencial de formato conhecido)"$'\n'
            LC_ALL=C grep -oaE "$RE_ATRIBUICAO" "$f" 2>/dev/null \
                | grep -qvE "$RE_PLACEHOLDER_VALOR" \
                && conteudo="$conteudo$rel (segredo em atribuição)"$'\n'
        fi
    done < <(sort -u "$candidatos")
    rm -rf "$tmp/ex"

    for bloco in "$nomes" "$nomes_path"; do
        [[ -n "$bloco" ]] && linhas=$(printf '%s\n%s' "$linhas" \
            "$(printf '%s\n' "$bloco" | sed 's|^|  ficheiro: /|')")
    done
    [[ -n "$conteudo" ]] && linhas=$(printf '%s\n%s' "$linhas" \
        "$(printf '%s' "$conteudo" | sed 's|^|  conteúdo: |')")

    # O ambiente gravado na imagem sai num `docker inspect` a quem a puxar, sem
    # precisar de ficheiro nenhum. **Invertido**: qualquer valor longo e sem
    # espaços é suspeito e a isenção é a lista fechada. A allowlist de
    # palavras-chave que estava aqui era uma lista de adivinhações —
    # `OPENAI_APIKEY`, `GITHUB_PAT` e `ADMIN_PW` passavam os três, e nenhum é
    # exótico. O `MIGRATION_DATABASE_URL` que esteve dentro da imagem também não
    # tinha `SECRET` nem `PASSWORD` no nome.
    env_bruto=$(docker inspect "$img" \
        --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)
    ambiente=$(printf '%s\n' "$env_bruto" \
        | awk -F= 'NF > 1 {
              valor = substr($0, index($0, "=") + 1)
              if (length(valor) >= 20 && valor !~ / /) print $0
          }' \
        | grep -vE "^($ENV_BENIGNOS)=" || true)
    dsn=$(printf '%s\n' "$env_bruto" | grep -E "=$RE_DSN" | grep -vE "$RE_PLACEHOLDER" || true)
    for bloco in "$ambiente" "$dsn"; do
        [[ -n "$bloco" ]] && linhas=$(printf '%s\n%s' "$linhas" \
            "$(printf '%s\n' "$bloco" | sed -E 's/=.*/=<omitido>/; s/^/  ENV: /')")
    done

    linhas=$(printf '%s' "$linhas" | grep -v '^$' | sort -u || true)
    cobertura="$membros membros, $varridos ficheiros varridos"
    (( grandes > 0 )) && cobertura="$cobertura ($grandes acima de $((LIMITE_KB / 1024)) MB só nos padrões sem quantificador aberto)"
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
