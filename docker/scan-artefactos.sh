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
# Vive num ficheiro próprio porque é chamado de **dois** sítios — o
# `security_check.sh` e o job `docker` do CI — e a versão duplicada já tinha
# divergido: o CI ficou com um padrão que só via `.env*`.
#
# Procura por nome e por `ENV`, não por entropia. Medido: o
# `trivy image --scanners secret` devolve zero contra uma imagem de sonda com
# cinco ficheiros de segredo e um `ENV`. Um gate que depende de heurística de
# entropia não é um gate.
#
# Uso: scan-artefactos.sh [imagem...]   (sem argumentos: todas as stockflow-*)
# Saída: uma linha por achado; exit 1 se houver algum.
set -uo pipefail

imagens=("$@")
if [[ ${#imagens[@]} -eq 0 ]]; then
    # Sem `mapfile`: é do bash 4 e o macOS traz o 3.2. Este ficheiro corre na
    # máquina de quem desenvolve e no runner do CI, logo é portável.
    while IFS= read -r linha; do
        [[ -n "$linha" ]] && imagens+=("$linha")
    done < <(docker images --format '{{.Repository}}' 2>/dev/null | grep -E '^stockflow-' | sort -u)
fi

if [[ ${#imagens[@]} -eq 0 ]]; then
    echo "nenhuma imagem para analisar" >&2
    exit 2
fi

# Duas famílias, e a distinção importa porque a versão larga disto deu três
# falsos positivos que valem como lição: `secrets.py` é da biblioteca padrão do
# Python, `credentials.py` é da do Redis, e `cacert.pem` é um bundle de CAs.
#   (i)  nomes que nunca têm razão de existir, com a extensão fixada;
#   (ii) chaves privadas e tokens pelo **conteúdo** — uma string fixa, não
#        entropia. É o que distingue um `.pem` que é chave de um que é
#        certificado.
readonly PROCURA='
find / -xdev -type f \( \
     -name ".env" -o -name ".env.*" \
  -o -name ".netrc" -o -name ".pgpass" -o -name ".git-credentials" \
  -o -name "secrets.json" -o -name "secrets.yaml" -o -name "secrets.yml" -o -name "secrets.env" \
  -o -name "credentials.json" -o -name "credentials.yaml" -o -name "credentials.yml" -o -name "credentials.ini" \
  -o -name "service-account*.json" \
  -o -name "*.p12" -o -name "*.pfx" -o -name "*.jks" \
  -o -name "settings.local" -o -name "settings.local.*" \
  -o -name "config_local" -o -name "config_local.*" \
  \) ! -name ".env.example" 2>/dev/null
find / -xdev -type f -size -64k \( \
     -name "*.pem" -o -name "*.key" -o -name "id_rsa" -o -name "id_dsa" \
  -o -name "id_ecdsa" -o -name "id_ed25519" \
  \) 2>/dev/null | while read -r f; do
    head -c 400 "$f" 2>/dev/null | grep -q "PRIVATE KEY-----" && echo "$f (chave privada)"
  done
find / -xdev -type f -name ".npmrc" 2>/dev/null | while read -r f; do
    grep -q "_authToken" "$f" 2>/dev/null && echo "$f (token de registry)"
  done
'

achados=0
for img in "${imagens[@]}"; do
    ficheiros=$(docker run --rm --entrypoint sh "$img" -c "$PROCURA" 2>/dev/null || true)
    # Um `ENV` com segredo fica na config da imagem e sai num `docker inspect`
    # a quem a puxar — não precisa de estar em ficheiro nenhum.
    ambiente=$(docker inspect "$img" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | grep -iE '^[A-Z_]*(SECRET|PASSWORD|TOKEN|CREDENTIAL|PRIVATE_KEY|API_KEY)[A-Z_]*=.+' || true)

    if [[ -n "$ficheiros" || -n "$ambiente" ]]; then
        echo "$img:"
        [[ -n "$ficheiros" ]] && echo "$ficheiros" | sed 's/^/  ficheiro: /'
        # O valor é omitido: este output vai para logs de CI.
        [[ -n "$ambiente" ]] && echo "$ambiente" | sed -E 's/=.*/=<omitido>/; s/^/  ENV: /'
        achados=$((achados + 1))
    fi
done

if (( achados > 0 )); then
    echo "segredos em $achados imagem(ns)" >&2
    exit 1
fi
echo "ok (${#imagens[@]} imagens)"
