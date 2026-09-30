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
# ## A decisão de âmbito, que é o que faz este gate útil em vez de ruidoso
#
# Varre **o que nós pusemos na imagem** (`/app`, sem `.venv` nem `staticfiles`)
# mais um punhado de caminhos absolutos que nunca têm razão de existir. **Não**
# varre o sistema de ficheiros inteiro, e a razão é empírica: a versão que o
# fazia devolvia ~60 falsos positivos por imagem — templates de password do
# Django, ficheiros do PAM, módulos Perl do Debconf, e código de bibliotecas com
# exemplos de DSN em docstrings. Um gate que grita a cada corrida é um gate que
# alguém desliga, e aí não há gate nenhum.
#
# Um segredo dentro de uma dependência vendorizada é um problema diferente
# (cadeia de fornecimento) e um gate de nome de ficheiro não o encontraria de
# qualquer maneira — isso é o `pip-audit`, o `pnpm audit` e o `trivy image`.
#
# ## Como procura
#
# Por nome, por conteúdo fixo e por `ENV`. Não por entropia: medido, o
# `trivy image --scanners secret` devolve zero contra uma imagem de sonda com
# cinco ficheiros de segredo e um `ENV`. Um gate que depende de heurística de
# entropia não é um gate.
#
# Uso: scan-artefactos.sh [imagem...]   (sem argumentos: todas as stockflow-*)
# Saída: uma linha por achado; exit 1 se houver algum, 2 se não houver imagens.
set -uo pipefail

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

# `$NOSSO` é o código que nós copiámos para a imagem. `.venv` e `staticfiles`
# ficam de fora: são dependências vendorizadas e ficheiros gerados.
readonly PROCURA='
NOSSO="-path /app/.venv -prune -o -path /app/staticfiles -prune -o -path */__pycache__ -prune -o"

# (1) Ficheiros de ambiente e de credenciais no nosso código. Foi isto que
#     aconteceu: `COPY backend/ ./` levou o `.env`.
find /app $NOSSO -type f \( \
     -name ".env" -o -name ".env.*" -o -name "*.env" \
  -o -name ".netrc" -o -name ".pgpass" -o -name ".git-credentials" \
  -o -name "secrets.json" -o -name "secrets.ya*ml" \
  -o -name "credentials.json" -o -name "credentials.ya*ml" -o -name "credentials.ini" \
  -o -name "service-account*.json" \
  -o -name "*.p12" -o -name "*.pfx" -o -name "*.jks" \
  -o -name "settings.local*" -o -name "config_local*" -o -name "*local_settings*" \
  \) ! -name ".env.example" -print 2>/dev/null

# (2) Caminhos absolutos que nunca têm razão de existir numa imagem.
find /root /home -xdev -type f \( \
     -name ".netrc" -o -name ".pgpass" -o -name ".git-credentials" \
  -o -path "*/.ssh/id_*" ! -name "*.pub" \
  -o -path "*/.aws/credentials" -o -path "*/.config/gcloud/*" \
  -o -path "*/.docker/config.json" -o -path "*/.kube/config" \
  \) -print 2>/dev/null

# (3) Chaves privadas pelo **cabeçalho** e não pelo nome — é o que distingue um
#     `.pem` que é chave de um que é certificado. Só no nosso código.
find /app $NOSSO -type f -size -64k \( -name "*.pem" -o -name "*.key" \) -print 2>/dev/null \
  | while read -r f; do
      head -c 400 "$f" 2>/dev/null | grep -q "PRIVATE KEY-----" && echo "$f (chave privada)"
    done

# (4) Credencial embutida num DSN, no nosso código. É o conteúdo do incidente,
#     independentemente do nome do ficheiro — um `settings_prod.py` com
#     `postgres://user:pass@host` é apanhado aqui.
find /app $NOSSO -type f -size -256k \( -name "*.py" -o -name "*.env" -o -name "*.cfg" \
     -o -name "*.ini" -o -name "*.conf" -o -name "*.ya*ml" -o -name "*.json" -o -name "*.toml" \) -print 2>/dev/null \
  | while read -r f; do
      # Placeholders excluídos: a diferença entre "há uma credencial aqui" e
      # "há um exemplo de formato num docstring". O `config/env.py` tem
      # `postgres://utilizador:password@host` numa mensagem de erro, e era o
      # único falso positivo que sobrava.
      grep -hoE "[a-z][a-z0-9+.-]*://[^:/@[:space:]]+:[^@[:space:]/]{6,}@" "$f" 2>/dev/null \
        | grep -qvE ":(password|passwd|senha|muda-me|changeme|secret|placeholder|exemplo|example|xxx+|[*]+|your[-_]?password|<[^>]*>)@" \
        && echo "$f (credencial em DSN)"
    done

# (5) Tokens de registry.
find /app /root /home -xdev -type f -name ".npmrc" -print 2>/dev/null | while read -r f; do
    grep -q "_authToken" "$f" 2>/dev/null && echo "$f (token de registry)"
  done
'

achados=0
for img in "${imagens[@]}"; do
    linhas=""
    ficheiros=$(docker run --rm --entrypoint sh "$img" -c "$PROCURA" 2>/dev/null)
    if (( $? != 0 )); then
        # Uma imagem sem shell (um stage com só o binário) faz o `docker run
        # --entrypoint sh` sair 127. A versão anterior engolia isso com
        # `|| true` e dizia "limpa" — um gate que não corre a declarar que
        # passa. Aqui varre-se o tar, que não precisa de shell.
        ficheiros=$(docker save "$img" 2>/dev/null | tar -tf - 2>/dev/null \
            | grep -iE '(^|/)(\.env($|\..*)|[^/]*\.env|\.netrc|\.pgpass|\.git-credentials|secrets\.(json|ya?ml)|credentials\.(json|ya?ml|ini)|service-account[^/]*\.json|[^/]*\.(p12|pfx|jks)|id_(rsa|dsa|ecdsa|ed25519))$' \
            | grep -v '\.env\.example$' || true)
        [[ -z "$ficheiros" ]] && echo "$img: sem shell, varrido pelo tar — nada encontrado"
    fi
    [[ -n "$ficheiros" ]] && linhas=$(echo "$ficheiros" | sed 's/^/  ficheiro: /')

    # O ambiente gravado na imagem: sai num `docker inspect` a quem a puxar, sem
    # precisar de ficheiro nenhum. Duas passagens, porque o nome não basta — o
    # `MIGRATION_DATABASE_URL` com a password do dono, que foi o que esteve
    # dentro da imagem, não tem `SECRET` nem `PASSWORD` no nome.
    env_bruto=$(docker inspect "$img" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)
    ambiente=$(printf '%s\n' "$env_bruto" \
        | grep -iE '^[A-Z0-9_]*(SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE_KEY|API_KEY)[A-Z0-9_]*=.+' \
        | grep -viE '^GPG_KEY=' || true)
    dsn=$(printf '%s\n' "$env_bruto" \
        | grep -E '=[a-z][a-z0-9+.-]*://[^:/@[:space:]]+:[^@[:space:]/]{6,}@' || true)
    for bloco in "$ambiente" "$dsn"; do
        [[ -n "$bloco" ]] && linhas=$(printf '%s\n%s' "$linhas" \
            "$(echo "$bloco" | sed -E 's/=.*/=<omitido>/; s/^/  ENV: /')")
    done

    linhas=$(printf '%s' "$linhas" | grep -v '^$' | sort -u || true)
    if [[ -n "$linhas" ]]; then
        echo "$img:"
        echo "$linhas"
        achados=$((achados + $(echo "$linhas" | wc -l | tr -d ' ')))
    fi
done

if (( achados > 0 )); then
    echo "$achados achado(s) de segredo em imagens" >&2
    exit 1
fi
echo "ok (${#imagens[@]} imagens)"
