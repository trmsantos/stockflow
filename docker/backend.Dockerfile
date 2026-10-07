# syntax=docker/dockerfile:1.7
# backend.Dockerfile — Django + DRF, multi-stage (ARCHITECTURE.md §9, SECURITY.md §8).
#
# Imagens fixadas por digest, não por tag: uma tag é um alvo móvel e "reproduzível
# com :3.12-slim" é uma afirmação falsa. Para atualizar:
#   docker pull python:3.12-slim-bookworm
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim-bookworm

# ---------------------------------------------------------------- builder
FROM python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS builder

# O uv vem da imagem oficial dele, também por digest, em vez de um curl | sh
# (que não é reproduzível e não é verificável).
COPY --from=ghcr.io/astral-sh/uv@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# O lockfile primeiro, sozinho: esta camada só invalida quando as dependências
# mudam, não quando o código muda. `--frozen` recusa-se a resolver nada que não
# esteja no lock — é isso que faz a build falhar em vez de trazer uma versão
# nova em silêncio (CLAUDE.md: nunca instalar fora do lockfile).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Os catálogos de tradução, compilados aqui (ADR 0019).
#
# **Neste stage e não no runtime**, por duas razões: o `gettext` nunca entra na
# imagem que vai para produção (é uma dependência de build, como o `uv`), e o
# `COPY --from=builder /app /app` do runtime traz os `.mo` já feitos.
#
# `msgfmt` directo e não `manage.py compilemessages`: o segundo é um invólucro
# do primeiro que precisa de `django.setup()`, e isso neste stage obrigava às
# variáveis de fachada que o `collectstatic` do runtime usa — um bootstrap de
# Django para correr um compilador. O `--check` recusa um `.po` mal formado, e o
# `-o` escreve ao lado do `.po`, que é onde o Django os procura.
#
# **Um `.mo` esquecido é uma UI em inglês sem erro nenhum**, e é por isso que o
# `tests/test_i18n.py` afirma que cada msgid resolve para o seu msgstr: a rede
# está no teste e não aqui, porque aqui só se apanha o `.po` inválido.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gettext=0.21-12 \
 && rm -rf /var/lib/apt/lists/* \
 && find locale -name '*.po' -exec sh -c 'msgfmt --check "$1" -o "${1%.po}.mo"' _ {} \;

# ---------------------------------------------------------------- runtime
FROM python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime

# Correcções de segurança do sistema base, **por pacote e com versão fixada**.
#
# A imagem está fixada por digest, o que é bom para reproduzir o que se constrói
# e mau para CVE: o digest congela também os pacotes com falhas que o Debian já
# corrigiu. O trivy do CI corre com `--ignore-unfixed`, logo o que ele reporta é
# exactamente isto — falhas **com** correcção publicada que a imagem não tem.
# Em 2026-10-06 eram oito (5 HIGH, 3 CRITICAL) nestes dois pacotes.
#
# Não é `apt-get upgrade`: o `hadolint` do mesmo job recusa-o (DL3005), e com
# razão — uma actualização em bloco muda pacotes que ninguém reviu e torna a
# build dependente do dia. Dois nomes com duas versões dizem o que mudou.
#
# **O pino envelhece de propósito.** Quando a próxima CVE sair, o trivy fica
# vermelho e alguém sobe a versão aqui — e a subida aparece no diff, com o nome
# do pacote e o número. É a mesma forma das outras listas fechadas deste
# repositório: a manutenção é visível em vez de automática e silenciosa.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpcre2-8-0=10.42-1+deb12u2 \
      perl-base=5.36.0-7+deb12u4 \
 && rm -rf /var/lib/apt/lists/*

# Utilizador sem privilégios, com UID fixo: o default do Docker é root, e um
# UID atribuído dinamicamente rebenta a posse de volumes montados.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Sem default: `wsgi.py` já faz setdefault para `prod`, e é deliberado —
    # um worker sem esta variável tem de falhar por falta de segredos, não
    # servir com settings de desenvolvimento (ADR 0006, `config/celery.py`).
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

# Os estáticos do admin e do DRF, recolhidos na build: em runtime o sistema de
# ficheiros é read-only (ver compose) e um `collectstatic` no arranque falharia.
# Corre com variáveis de fachada porque o `prod.py` exige-as sem default e este
# comando não liga a nada.
#
# Nota para quem revê (SECURITY.md §8, "`docker history` não pode mostrar
# segredos"): o `docker history` **mostra** a string `DJANGO_SECRET_KEY=` desta
# linha, e verificar isso é o reflexo certo. O que ele mostra é o *comando*, com
# o `$(python -c ...)` por expandir — a expansão acontece
# dentro do contentor, em runtime de build, e o valor não fica em camada
# nenhuma. Verificado: `docker history --no-trunc` traz o literal, zero
# passwords. A chave também não serve para nada: é gerada, usada por um comando
# que não abre socket nenhum, e descartada.
RUN DJANGO_SECRET_KEY="x-collectstatic-$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    DATABASE_URL=postgres://ninguem@127.0.0.1:1/vazio \
    ALLOWED_HOSTS=localhost CSRF_TRUSTED_ORIGINS=https://localhost \
    DJANGO_ADMIN_URL=x/ REDIS_URL=redis://127.0.0.1:1 \
    python manage.py collectstatic --noinput --clear \
 && chown -R app:app /app/staticfiles

# UID numérico e não `app`: assim o runtime não precisa de resolver o nome,
# que é o que permite a um orquestrador verificar `runAsNonRoot` (DL3066).
USER 10001:10001
EXPOSE 8000

# Duas coisas que este healthcheck tem de fazer e que a versão óbvia não faz.
#
# **O `Host` é explícito.** O `ALLOWED_HOSTS` de produção traz o domínio real e
# um pedido com `Host: 127.0.0.1` dá 400 DisallowedHost — healthcheck vermelho
# num contentor saudável. Vem do próprio `ALLOWED_HOSTS`, primeira entrada, e o
# `or '127.0.0.1'` cobre o dev, onde a variável pode não estar definida porque o
# `dev.py` tem default no código.
#
# **Exige 200, e não "não é erro".** Um `curl -fsS` devolve exit 0 contra um
# **301** — medido — e em produção o `SECURE_SSL_REDIRECT` redirecionaria este
# pedido, que chega em HTTP simples sem proxy a pôr o `X-Forwarded-Proto`. O
# resultado era um contentor reportado como saudável sem nunca ter tocado na
# aplicação. O `config/settings/base.py` dispensa `healthz`/`readyz` do redirect
# (`SECURE_REDIRECT_EXEMPT`) **e** esta verificação compara o status com 200 —
# as duas coisas, porque uma só deixava o modo de falha de pé.
#
# Em python e não em curl: o interpretador já está na imagem, e instalar o curl
# era superfície acrescentada para uma linha (SECURITY.md §8, Trivy no §9).
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request as u; h=(os.environ.get('ALLOWED_HOSTS') or '127.0.0.1').split(',')[0].strip(); r=u.urlopen(u.Request('http://127.0.0.1:8000/healthz', headers={'Host': h}), timeout=3); raise SystemExit(0 if r.status == 200 else 1)"]

# O comando fica no compose: o mesmo artefacto serve o processo web e o worker
# Celery, e uma imagem por processo duplicava a superfície a analisar.
CMD ["python", "-c", "raise SystemExit('define o command no compose: gunicorn ou celery')"]
