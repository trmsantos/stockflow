# SECURITY.md — Modelo de ameaças e controlos

Aplica-se a todo o código do repositório. O agente consulta este ficheiro sempre que toca em
autenticação, permissões, dados pessoais, uploads, integrações externas ou configuração.
A verificação automática está na skill `security-check`.

## 1. Ameaças que assumimos

| Ameaça | Controlo principal |
|---|---|
| Injeção (SQL, comando, template) | ORM + parâmetros; sem `eval`/`subprocess` com input; autoescape |
| Auth quebrada / sessões roubadas | Sessões server-side, cookies httpOnly+Secure+SameSite, Argon2id |
| Acesso a dados de outro tenant | Permissões por objeto **e** RLS no Postgres (duas exceções tratadas — ver §3; e o que a RLS **não** cobre, abaixo) |
| XSS | React escapa por defeito; `dangerouslySetInnerHTML` proibido sem sanitização (DOMPurify); CSP |
| CSRF | Django CSRF middleware + `X-CSRFToken` no cliente |
| Fuga de segredos | `.env` ignorado; gitleaks no CI; segredos em runtime |
| Dependência vulnerável | `pip-audit`, `pnpm audit`, lockfiles, Renovate |
| Upload malicioso | Validação de MIME real, tamanho máximo, armazenamento fora do webroot, nomes gerados |
| Prompt injection (agentes) | Output de LLM nunca executado; tools sem shell/SQL; conteúdo externo marcado untrusted |
| Exposição de dados em logs | Logs sem PII; filtros de campos sensíveis |
| DoS | Rate limit no proxy e por utilizador; limites de payload; timeouts |
| Roubo do disco/backup | Encriptação at rest + campo a campo para PII sensível |

### O que a RLS garante, e o que não garante

Medido, não presumido. **Protege contra um filtro esquecido:** um `objects.all()` sem `tenant_id`
devolve zero linhas em vez das de todos os clientes, e é para isso que ela existe — é a rede, não a
regra (ADR 0005). Provado também que o role da aplicação **não** consegue desarmá-la: `ALTER TABLE
... DISABLE ROW LEVEL SECURITY`, `NO FORCE` e `DROP POLICY` são as três recusadas, porque ele não é
dono de nenhuma tabela (ADR 0006); e um `RESET app.tenant_id` faz a política devolver zero linhas, não
todas.

**Não protege contra código que execute SQL arbitrário.** O âmbito é um GUC, e quem pode correr SQL
pode trocá-lo: dentro de `tenant_scope(A)`, um `set_config('app.tenant_id', B, true)` passa a ver os
dados de B — medido, com as linhas a mudarem de A para B.

A consequência é sobre **severidade, e é ela que justifica a regra ser absoluta**: uma injeção de SQL
neste sistema não expõe um restaurante, expõe **todos**. É por isso que `.raw()` com f-strings,
`.extra()` e qualquer interpolação em SQL não são uma questão de estilo, e é a resposta a dar a quem
propuser "só esta query é que precisa de SQL cru".

## 2. Configuração Django obrigatória (`settings/prod.py`)

```python
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
SECRET_KEY = env("DJANGO_SECRET_KEY")          # ≥ 50 chars, rotacionável

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher", ...]
AUTH_PASSWORD_VALIDATORS = [...]               # mínimo 12 chars, não comum, não numérico

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle",
                                 "rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min", "anon": "60/min"},
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
```

`uv run manage.py check --deploy` tem de passar sem warnings. Faz parte do `security-check`.

CSP via `django-csp`: `default-src 'self'`; scripts só do próprio domínio com nonce; sem
`unsafe-inline`; `frame-ancestors 'none'`.

## 3. Base de dados

### Ligação
- TLS obrigatório (`sslmode=verify-full` em prod).
- **Três roles, nenhum com duas funções** (ADR 0006):
  - `stockflow_app` — `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`, sem `CREATE` no
    esquema, sem `TRUNCATE`, e **não é dono de nenhuma tabela**. É a única ligação que serve
    pedidos. Um `migrate` com esta credencial morre no primeiro `CREATE TABLE`, de propósito.
  - O que esta credencial lê **sem âmbito nenhum**, e é o custo aceite da ADR 0007: o
    `accounts_user` inteiro — `email`, hash Argon2id, `last_login`, `tenant_ids`, e as flags
    `is_active`/`is_staff`/`is_superuser`. As duas últimas dizem a um atacante **quais** contas
    abrem o admin, e o `tenant_ids` é o grafo de pertenças entre clientes. Nenhuma tabela de dados
    de tenant é legível assim.
  - `stockflow_owner` — dono da base de dados e das tabelas. É a credencial do `migrate` e do
    setup da base de dados de teste, e de nada mais: não existe no ambiente do processo web
    nem do worker.
  - Superuser de bootstrap — só provisionamento (`docker/db/roles.sql`). Fora de qualquer
    `DATABASE_URL`.
- O dono é um role separado porque **o dono de uma tabela pode
  `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`**, e um role que desliga o seu próprio
  isolamento não tem isolamento. Um `SUPERUSER` ou um role com `BYPASSRLS` não é sujeito a
  política nenhuma — é por isso que a app não pode ser nem uma coisa nem outra.
- `FORCE ROW LEVEL SECURITY` continua obrigatório, agora pela sua razão verdadeira: sujeitar o
  `stockflow_owner` quando corre migrações de dados.
- O ledger é append-only **na base de dados**, não por disciplina:
  `REVOKE UPDATE, DELETE ON inventory_stockmovement FROM stockflow_app`, na migração que cria
  a tabela.
- Os GRANTs das tabelas que as migrações futuras criam vêm de `ALTER DEFAULT PRIVILEGES` do
  role dono, nunca de GRANTs à mão numa migração.

### Isolamento multi-tenant (RLS)
```sql
ALTER TABLE core_document ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_document FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON core_document
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```
O `NULLIF` não é decoração. `app.tenant_id` é um *placeholder*, e o valor a que o fim da transação
o devolve é a **string vazia**, não NULL — medido no PostgreSQL 16.15, na mesma ligação. Sem o
`NULLIF`, `''::uuid` levanta `invalid input syntax for type uuid: ""` a partir da segunda transação
de cada ligação persistente, e o pedido *sem* tenant — login, healthcheck, anónimo, 404 antes da
view — responde 500 em vez de ver zero linhas.
O `TenantMiddleware` abre uma transação por pedido e corre nela
`SELECT set_config('app.tenant_id', %s, true)` — parametrizado, nunca interpolado, e com âmbito de
transação (ADR 0005). Um `SET LOCAL` fora de um bloco de transação não tem efeito.
Qualquer tabela com `tenant_id` tem esta política. Sem `app.tenant_id` definido, a query
devolve zero linhas — falha fechada.

### Encriptação — três camadas
1. **At rest**: encriptação de disco/volume no fornecedor (RDS, Neon, ou LUKS self-hosted).
   Protege contra roubo físico e de snapshots. Não protege contra a app.
2. **In transit**: TLS na ligação (acima).
3. **Ao nível de campo** (para PII sensível: NIF, IBAN, dados de saúde, tokens OAuth de
   terceiros): `django-fernet-fields` ou `EncryptedTextField` próprio com AES-256-GCM.
   - **O NIF do tenant é um caso especial e não é folclore.** Uma fatia relevante dos clientes
     são ENI (empresário em nome individual) — cafés e pastelarias constituem-se assim e faturam
     com o **NIF pessoal do dono**, prefixo 1 ou 2. Logo o NIF do tenant é PII de pessoa singular
     numas vezes e não noutras, e não há como saber de antemão qual. Isso colide com a
     unicidade: um campo encriptado não serve de índice único. A forma é `nif_encrypted`
     (AES-256-GCM, `key_id` para rotação) mais `nif_hmac` **único e indexado**, HMAC-SHA256 com
     **pepper secreto fora da base de dados** — nunca um hash simples: 9 dígitos são 10⁹
     candidatos e a coluna inteira quebra-se num portátil. Rodar o pepper obriga a reescrever a
     coluna e o índice, ao contrário de rodar a chave de encriptação.
   - O NIF é **único mas não imutável**: ENI → Lda ao fim de ~2 anos é o mesmo restaurante com
     NIF novo, e o hmac antigo tem de continuar pesquisável, porque as faturas antigas trazem o
     NIF antigo. A mudança escreve uma linha append-only com autor e motivo.
   - **Consequência de RGPD a nomear:** se o NIF do tenant pode ser de pessoa singular, o próprio
     registo do tenant é dado pessoal, e o direito ao apagamento de um ENI é apagar um tenant com
     um ledger append-only lá dentro. Não está resolvido.
   Chave (`FIELD_ENCRYPTION_KEY`) vem de um KMS/Vault ou de secret de runtime, **nunca** do
   `.env` commitado. Rotação: campos guardam `key_id`; job de re-encriptação.
   - Passwords: nunca encriptadas — só Argon2id (hash).
   - O que é encriptado não é pesquisável por `LIKE`; se precisares de pesquisa, guarda um
     HMAC do valor num campo separado (`nif_hash`) e pesquisa por igualdade.

### Backups
- Diários, encriptados, testados por restore mensal automatizado. Retenção definida por lei
  (RGPD: minimização — não guardar mais do que o necessário).

## 4. Entrada de dados

- Serializers DRF com `max_length`, `validators`, `choices`. Nunca `fields = "__all__"` em
  serializers de escrita.
- IDs expostos são UUIDv4, nunca inteiros sequenciais.
- Uploads: verificar tipo real (`python-magic`), extensão numa allowlist, tamanho máximo,
  guardar em S3/MinIO com nome gerado, servir por URL assinada com expiração.
- Redirects só para URLs na allowlist (`url_has_allowed_host_and_scheme`).
- Frontend: Zod em todas as respostas; formulários com validação client + server.

## 5. Autenticação e autorização

- Login com rate limit no `django-axes` por **conta** e pelo **par (IP, conta)** — dois contadores, para
  que nem credential stuffing (1 IP, N contas) nem password spraying (N IPs, 1 conta) passem sem teto.
  Rate limit por IP puro é do proxy. Requer `django-ipware` instalado: sem ele o axes cai no `REMOTE_ADDR`,
  que atrás do proxy é o mesmo para todos, e o eixo IP desaparece em silêncio.
- Bloqueio de 30 min a contar da última falha. O valor é simultaneamente a **janela de contagem** das
  falhas no axes, por isso não pode ser curto: com 1 minuto, um atacante a tentar uma password a cada
  70 s nunca chega ao limite.
- A escada progressiva (30 min → 1 h → 4 h → 12 h → 24 h) está escrita em `config/lockout.py` mas
  **os degraus acima do primeiro não têm efeito hoje**: no caminho onde o axes decide o lockout, o
  `request.axes_failures_since_start` ainda é `None` (`axes/handlers/proxy.py:96` põe-no a `None` e
  `database.py:247` só lhe dá valor depois de já ter chamado `get_failures`). Progressão a sério exige
  contar as falhas fora do axes, com TTL próprio, porque um único valor não pode ser janela curta de
  contagem e bloqueio longo ao mesmo tempo. Fica para ADR; até lá o que vale é a linha acima.
- MFA (TOTP) disponível; obrigatório para admins.
- Sessões expiram em 14 dias inativas; rotação de session key após login.
- Permissão por objeto em todas as views que recebem um `pk`: `has_object_permission` verifica
  `obj.tenant_id == request.tenant.id` **antes** de qualquer outra regra.
- Admin Django num path não óbvio (vem do ambiente, `DJANGO_ADMIN_URL`), com rate limit de
  **5 tentativas/minuto por IP** no proxy — o `django-axes` trava brute-force de *uma* conta e não
  trava varrer contas, e quem entra no admin lê o `accounts_user` inteiro, de todos os tenants.
- **A restrição por IP/VPN do admin é plumbing, não um controlo activo.** O proxy tem o matcher e o
  `handle`, ligados pela variável `ADMIN_ALLOW_CIDRS` (`docker/caddy/proxy.Caddyfile`), e o default
  não restringe nada — em desenvolvimento não pode, porque o Docker Desktop faz NAT e o IP do host é
  imprevisível. **Produção tem de definir `ADMIN_ALLOW_CIDRS`**, ou pôr a restrição no orquestrador.
  Enquanto isso não acontecer, o que protege o admin é o path não óbvio, o rate limit e o lockout —
  e não a rede.
- MFA (TOTP) obrigatória para admins: **não implementada**, dívida nomeada. Sem ela, o que sobra
  contra credenciais roubadas de um operador é o lockout.

## 6. Agentes e LLMs

- Output do modelo é texto. Nunca vai para `exec`, `subprocess`, SQL, `render_template_string`
  ou `dangerouslySetInnerHTML`.
- Tools têm schema estrito; o modelo não escolhe endpoints nem tabelas, só argumentos validados.
- Conteúdo de utilizadores/web entra no prompt dentro de delimitadores explícitos e o prompt de
  sistema diz para o tratar como dados.
- Limite de custo por utilizador/dia. Logs de prompts sem PII (ou com PII redigida).
- Chaves de API de LLM com scope mínimo, rotacionadas, nunca no frontend.

## 7. Frontend

- Sem tokens em `localStorage`/`sessionStorage`.
- `fetch` com `credentials: "include"` e header `X-CSRFToken`.
- Sem `dangerouslySetInnerHTML`; se inevitável, `DOMPurify.sanitize` e revisão obrigatória.
- Links externos com `rel="noopener noreferrer"`.
- Sem segredos em `VITE_*` — tudo o que começa por `VITE_` vai para o bundle público.
- Dependências: `pnpm audit --audit-level=high` no CI.

## 8. Docker e infra

- Imagens não-root, read-only filesystem onde possível, `cap_drop: [ALL]`.
- Scan de imagens com Trivy no CI; sem CVEs HIGH/CRITICAL com fix disponível.
- Rede interna do compose; só o proxy expõe 80/443.
- Segredos por Docker secrets / orquestrador. `docker history` da imagem final não pode mostrar
  segredos.

## 9. CI — gates obrigatórios

Tudo isto corre em cada PR (o script `security_check.sh` corre o subconjunto local):

| Gate | Ferramenta |
|---|---|
| Segredos | gitleaks |
| Python SAST | bandit, semgrep (regras `p/django`, `p/python`, `p/owasp-top-ten`) |
| Python deps | pip-audit |
| Django config | `manage.py check --deploy` |
| JS/TS SAST | semgrep (`p/react`, `p/typescript`), eslint-plugin-security |
| JS deps | pnpm audit |
| Docker | hadolint, trivy |
| Fronteiras | import-linter |
| Roles e GRANTs da BD | `uv run pytest tests/test_db_roles.py` |

Ordem do pipeline: `docker/db/roles.sql` (bootstrap dos roles) → `migrate` com
`MIGRATION_DATABASE_URL` → `pytest` (setup como dono, testes como app) → os gates acima. O
`check --deploy` não abre ligação à base de dados e corre só com a credencial da app.

### Estado dos CVEs das imagens, medido em 2026-09-29

**Zero HIGH/CRITICAL com correcção disponível nas três imagens.** As do `proxy` e do `frontend` estão
a zero mesmo **sem** `--ignore-unfixed`. Houve aqui uma excepção aceite de seis CVEs, nas dependências
transitivas do Caddy, e deixou de ser necessária: com o Caddy construído do código (Go 1.26.8, ver
`docker/proxy.Dockerfile`) e as imagens reconstruídas sem cache, nenhum dos seis é reportado. O
`.trivyignore` que os listava foi apagado — uma lista de excepções que já não esconde nada é uma
lista que alguém vai reaproveitar para esconder a próxima.

**O `backend` é o caso a ler com cuidado.** Zero **com correcção disponível**, e **60 HIGH/CRITICAL
sem correcção** — pacotes do Debian 12 (`perl-base`, `libsqlite3-0`, `zlib1g`, a família
`util-linux`, `ncurses`) para os quais não há versão corrigida. O gate corre com `--ignore-unfixed`
de propósito: falhar por uma vulnerabilidade que ninguém pode corrigir é um gate que se desliga na
semana seguinte. Mas "o backend está a zero" sem esta qualificação é uma frase que engana o próximo
leitor, e é a única forma honesta de a escrever.

O gatilho para reavaliar os sem-fix: uma imagem base mais magra (distroless ou Alpine) tira a maior
parte deles, ao preço de perder o `apt` e de compilar `psycopg` — decisão de quando houver razão, não
agora.

## 10. Resposta a incidentes (mínimo)

1. Rotacionar credenciais afetadas (SECRET_KEY, chaves de BD, chaves de API).
2. Invalidar todas as sessões (`Session.objects.all().delete()` ou mudar `SECRET_KEY`).
3. Preservar logs. Identificar tenants afetados.
4. Notificar a CNPD em ≤72h se houver dados pessoais envolvidos (RGPD art. 33).
5. Post-mortem escrito; controlo novo adicionado a este ficheiro.
