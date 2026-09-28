# Checklist de revisão manual

Percorre só as secções que tocam nos ficheiros alterados. Para cada item: abre o código, confirma.

## A. Backend Django / DRF

### Autorização e tenancy
- [ ] Cada view com `pk`/`slug` tem `permission_classes` com `has_object_permission` que compara `tenant_id`.
- [ ] Cada `get_queryset` filtra por `request.tenant` (ou o modelo tem RLS ativa e `FORCE ROW LEVEL SECURITY`).
- [ ] Nenhum endpoint usa `AllowAny` sem comentário a justificar.
- [ ] Endpoints de listagem não expõem campos de outros utilizadores (verifica o serializer de leitura).
- [ ] Ações sensíveis (apagar, exportar, alterar plano) exigem permissão explícita, não só `IsAuthenticated`.

### Entrada
- [ ] Serializers de escrita listam `fields` explicitamente (nunca `__all__`) e têm `read_only_fields` para `id`, `tenant`, `created_by`.
- [ ] Sem `.raw()`, `.extra()`, `RawSQL`, `cursor.execute` com interpolação de strings.
- [ ] Sem `eval`, `exec`, `pickle.loads`, `yaml.load` (sem `SafeLoader`), `subprocess` com `shell=True`.
- [ ] Uploads: tipo verificado por conteúdo, extensão em allowlist, tamanho limitado, nome gerado.
- [ ] Redirects usam `url_has_allowed_host_and_scheme`.
- [ ] Templates não usam `|safe` nem `mark_safe` com dados de utilizador.

### Sessões e auth
- [ ] Login protegido por `django-axes` ou throttle equivalente.
- [ ] Password reset: token de uso único, expira, não revela se o email existe.
- [ ] Alteração de email/password exige password atual.

### Configuração
- [ ] `check --deploy` sem warnings.
- [ ] Nenhum segredo hardcoded; tudo via `env(...)`.
- [ ] `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` explícitos.
- [ ] Logging: nenhum `logger.*` com `request.data`, passwords, tokens ou emails completos.

## B. Base de dados
- [ ] Novas tabelas com `tenant_id` têm política RLS na migração.
- [ ] Campos com PII sensível (NIF, IBAN, saúde, tokens de terceiros) usam campo encriptado.
- [ ] Índices em colunas usadas em filtros de tenant e auth (evita DoS por queries lentas).
- [ ] Migrações não fazem `DROP` de colunas com dados sem passo de backup documentado.
- [ ] Utilizador da app não é superuser (verifica `DATABASES` e o role em compose/infra).

## C. Frontend React TS
- [ ] Nenhum `localStorage`/`sessionStorage` com tokens ou dados pessoais.
- [ ] Nenhum `dangerouslySetInnerHTML`; se existir, `DOMPurify` e comentário.
- [ ] Nenhuma variável `VITE_*` contém segredo (todas vão para o bundle).
- [ ] Respostas da API passam por schema Zod antes de entrar no estado.
- [ ] Links externos com `rel="noopener noreferrer"`.
- [ ] Formulários de ações destrutivas têm confirmação.
- [ ] Não há lógica de autorização só no cliente (esconder botão ≠ proteger endpoint).

## D. Agentes / LLM (`apps/agents/`)
- [ ] Output do modelo nunca chega a `subprocess`, SQL, `eval`, templates ou HTML sem escape.
- [ ] Tools têm schema Pydantic estrito; nenhuma tool executa comandos ou SQL arbitrário.
- [ ] Tools chamam `apps/<m>/api.py` com o utilizador atual, não com privilégios de sistema.
- [ ] Conteúdo externo (utilizador, web, ficheiros) entra no prompt delimitado e marcado como dados.
- [ ] `timeout`, `max_tokens` e limite de custo por utilizador definidos.
- [ ] Prompts e respostas logados sem PII.
- [ ] Chaves de API só no backend.

## E. Docker / infra
- [ ] Multi-stage; imagem final sem `uv`, `pnpm`, `git`, compiladores.
- [ ] `USER` não-root definido.
- [ ] Imagens base fixadas por tag + digest.
- [ ] Nenhum `ENV`/`ARG` com segredo; nenhum `COPY .env`.
- [ ] `HEALTHCHECK` presente.
- [ ] Compose: só o proxy expõe portas; BD e Redis sem `ports:` para o host em prod.
- [ ] Volumes de BD não commitados; `.dockerignore` exclui `.env`, `.git`, `node_modules`.

## F. Dependências
- [ ] `uv.lock` e `pnpm-lock.yaml` commitados e atualizados.
- [ ] Nenhuma dependência nova sem justificação no PR.
- [ ] `pip-audit` e `pnpm audit` sem HIGH/CRITICAL sem fix.
