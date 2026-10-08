# ARCHITECTURE.md — StockFlow (monólito modular Django + React)

## Princípio

Um único deployable de backend (Django) com **fronteiras internas estritas**, impostas por
ferramentas e não por disciplina. Serviços só são extraídos quando há um sinal objetivo
(secção 7). Isto dá a organização dos microserviços sem o custo de rede, sagas distribuídas
e debugging entre serviços.

## 1. Vista geral

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser  ── React TS (Vite) ── chama /api/v1 via TanStack Query  │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS · cookie de sessão httpOnly · CSRF
┌──────────────────────────────▼───────────────────────────────────┐
│  Reverse proxy (Caddy ou nginx) · TLS · rate limit · headers      │
└──────────────────────────────┬───────────────────────────────────┘
┌──────────────────────────────▼───────────────────────────────────┐
│  Django (gunicorn/uvicorn)                                        │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐   │
│  │ accounts│ │ catalog │ │inventory│ │purchas. │ │  agents   │   │
│  │ tenants,│ │produtos,│ │ ledger, │ │fornec., │ │ extração  │   │
│  │ papéis  │ │unidades │ │ lotes   │ │ faturas │ │ faturas   │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └───────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                             │
│  │ recipes │ │ billing │ │ notif.  │                             │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └─────┬─────┘   │
│       └───────────┴─── só via apps/<m>/api.py ─┴───────┘         │
│  ┌──────────────── event bus interno + outbox ────────────────┐  │
└──┴──────────────────────────────┬───────────────────────────┴──┘
        ┌────────────────────────┼─────────────────────┐
┌───────▼──────┐        ┌────────▼───────┐    ┌────────▼────────┐
│ PostgreSQL 16│        │ Redis          │    │ Celery workers  │
│ RLS por      │        │ (broker, cache,│    │ (consomem outbox│
│ tenant       │        │  rate limit)   │    │  e tarefas)     │
└──────────────┘        └────────────────┘    └─────────────────┘
```

## 2. Estrutura de pastas

```
backend/
├── config/
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py
│   └── asgi.py
├── apps/
│   ├── accounts/       # Tenant (=restaurante), User, Membership (owner|manager|staff), TenantMiddleware
│   ├── catalog/        # Product, Category, Unit, ProductPackaging, Supplier, SupplierProductCode
│   ├── inventory/      # Location, Lot, StockMovement (ledger), StockLevel (projeção), StockCount, alertas
│   ├── purchasing/     # PurchaseOrder, InvoiceDocument, PurchaseReceiptDraft, SupplierPrice
│   ├── recipes/        # Recipe, RecipeLine, produção/venda → consumption
│   ├── agents/         # extract_invoice, forecasting, chat sobre stock — output sempre draft
│   ├── billing/        # planos por nº de utilizadores/localizações (fase 3)
│   ├── notifications/  # email de alertas (validade, mínimo), webhooks
│   ├── demo/           # semeia o estabelecimento de demonstração (ADR 0018) — só um comando:
│   │                   # sem models, sem migrações, sem api.py, sem endpoints. Sumidouro de
│   │                   # escrita: só arestas de saída, e um contrato proíbe que alguém o importe
│   └── shared/         # TenantModel, events.py, outbox.py — infraestrutura pura, não importa módulos
├── tests/
├── pyproject.toml      # gerido por uv
└── uv.lock

frontend/
├── src/
│   ├── components/ui/      # shadcn — não editar à mão
│   ├── features/<nome>/    # components/, hooks/, api.ts, schemas.ts
│   ├── lib/api/            # cliente HTTP, tipos gerados do OpenAPI
│   ├── routes/
│   └── styles/tokens.css
└── package.json

docker/
├── backend.Dockerfile
├── frontend.Dockerfile
└── compose.yml
```

## 3. Anatomia de um módulo (`apps/<módulo>/`)

| Ficheiro | Responsabilidade | Pode ser importado por outros módulos? |
|---|---|---|
| `models.py` | Persistência | **Não** |
| `serializers.py` | Validação de entrada/saída HTTP | **Não** |
| `services.py` | Lógica de negócio; única forma de escrever na BD | **Não** |
| `selectors.py` | Queries de leitura reutilizáveis | **Não** |
| `views.py` / `urls.py` | Transporte HTTP; sem lógica | **Não** |
| `api.py` | **Interface pública** do módulo: funções e DTOs (dataclasses) | **Sim — a porta do módulo** |
| `events.py` | Eventos de domínio que o módulo emite | Sim (só as classes de evento) |
| `handlers.py` | Subscrições a eventos de outros módulos | Não |
| `tasks.py` | Tarefas Celery | Não |
| `permissions.py` | Classes DRF `has_permission` / `has_object_permission` | Não |

Imposição: 10 contratos `forbidden` em `backend/pyproject.toml` — um transversal (entre módulos só
se importa `api.py`, `events.py` e `apps.shared`) e um por módulo-origem, todos com
`allow_indirect_imports = true`: só as arestas diretas são proibidas. Nem a interface pública é
livre — `apps.notifications` a importar `apps.inventory.api` dá `BROKEN` e exit 1 no `lint-imports`.

## 4. Fluxo de um request

1. Proxy termina TLS, aplica rate limit e headers de segurança.
2. Middleware Django, de fora para dentro: logging estruturado (cria o `request_id`) → segurança →
   CSP → sessão → CSRF → autenticação → axes → `TenantMiddleware`, que é o **último**.
3. O processo que serve pedidos liga-se como `stockflow_app`: `NOSUPERUSER`, `NOBYPASSRLS`, não é
   dono de nenhuma tabela e não tem `CREATE` no esquema. É essa ligação que a RLS alcança — um
   superuser ou o dono da tabela não seriam sujeitos à política (ADR 0006). O `migrate` corre num
   processo separado, com `stockflow_owner`, cuja credencial não existe no ambiente do servidor web
   nem do worker.
4. O `TenantMiddleware` (em `apps/accounts/`) **não** consulta a base de dados antes do âmbito — não
   poderia, porque o `Membership` tem política e uma leitura sem âmbito devolve zero linhas. Lê o
   `tenant_id` da **sessão** (tabela sem política), abre `tenant_scope(tenant_id)` de
   `apps/shared/db.py` a envolver o `get_response()` inteiro — uma transação por pedido, com
   `SELECT set_config('app.tenant_id', %s, true)` como primeira instrução, âmbito de transação,
   valor parametrizado, nunca interpolado (ADR 0005) — e a **primeira e única** instrução dentro do
   âmbito antes de entregar o pedido é a query ao `Membership` de (utilizador autenticado, âmbito):
   zero linhas é 403 com `transaction.set_rollback(True)`. A sessão escolhe o âmbito, a política
   concede-o (ADR 0007), e a verificação é por pedido — revogar um `Membership` corta o acesso no
   pedido seguinte, não na sessão seguinte. Pedido sem tenant (login, registo, healthcheck,
   anónimo) não abre âmbito nem transação, e a dispensa é declarada na view
   (`tenant_scope_exempt`): o default é ter âmbito. Nesses, `app.tenant_id` fica a NULL, as políticas
   devolvem zero linhas e nada falha com erro — e devolvem porque a ligação está sujeita a elas
   (ADR 0006). Ser o último middleware é deliberado — a escrita da sessão
   (`SESSION_SAVE_EVERY_REQUEST`) e o `AccessAttempt` do axes ficam fora da transação do pedido,
   onde têm de estar.
5. View DRF: autentica, aplica `permission_classes`, valida com serializer. O `request.tenant` é o
   dataclass `TenantContext` de `apps/accounts/api.py`, não a instância do modelo.
6. View chama **uma** função em `services.py`. O `@transaction.atomic` da função é um savepoint
   dentro da transação do pedido: se o service falhar, desfaz o que escreveu sem derrubar o pedido.
   O evento vai para a tabela `outbox` na mesma transação.
7. A resposta é serializada ainda dentro do âmbito — é por isso que as leituras de `selectors.py`
   avaliadas durante a serialização estão cobertas. Se a resposta sair 5xx, o middleware marca
   `transaction.set_rollback(True)`: o DRF trata a exceção dentro da view e sem isto um 500
   commitava escritas parciais. Nada de efeitos secundários síncronos.
8. `ATOMIC_REQUESTS` continua `False`: abriria a transação em volta da view, dentro da cadeia de
   middleware, onde nenhum middleware lhe consegue pôr o `set_config`.
9. O Celery não tem middleware. `TenantTask` é o `task_cls` do app, logo toda a tarefa o herda:
   `tenant_id` é argumento obrigatório e o corpo corre dentro de `tenant_scope`. A dispensa é
   explícita (a base `SystemTask`, com `tenant_scope_exempt`) e só a podem ter duas coisas: o cron
   que itera tenants e o consumidor da outbox, que lê a linha sob `system_scope()` e reentra em
   `tenant_scope(row.tenant_id)` antes de tocar em mais nada. **Das duas, existe uma** — a do
   consumidor. O cron que itera tenants não existe e não é esquecimento: teria de ler o
   `accounts_tenant`, cuja política não tem o disjunto `app.scope`, logo dentro de `system_scope()`
   devolve zero linhas sem erro. Dar-lho é uma decisão de ADR, porque alarga o alcance do âmbito de
   sistema, que hoje é uma tabela só.
10. Um worker Celery lê a `outbox`, publica o evento aos `handlers.py` subscritos, marca como
   processado — a marca commita **na mesma transação** que os handlers. Handlers são idempotentes
   (chave: `event_id`), porque a reentrega existe: um handler que levante desfaz os irmãos que
   correram antes dele. O `apps.shared` não importa módulos, logo é cada módulo que registra os seus
   handlers no `ready()` do seu `AppConfig`; o registo (`event_type` → handlers) vive em
   `apps/shared/handlers.py` e só conhece strings e funções. A passagem é agendada pelo `beat` a cada
   5 segundos, e uma linha que falhe `TETO_DE_TENTATIVAS` vezes deixa de ser candidata **sem** ser
   marcada: fica pendente e visível, que é a diferença entre esta tabela e um broker.

## 5. Contratos e compatibilidade

O maior risco de "problemas de compatibilidade" é a API divergir do frontend. Solução:

- `drf-spectacular` gera `schema.yml` a partir dos serializers.
- `openapi-typescript` gera `src/lib/api/types.ts`. Está commitado.
- CI corre a geração e falha se o diff não estiver vazio → ninguém muda a API sem atualizar o cliente.
- Respostas críticas ainda passam por Zod no frontend (defesa contra dados inesperados em runtime).
- Versionamento: `/api/v1/`. Mudanças breaking → `v2` a coexistir por um período definido.
- Dependências fixadas em `uv.lock` e `pnpm-lock.yaml`; Renovate/Dependabot abre PRs semanais.

## 6. Módulo `agents/` — regras específicas

Agentes são componentes de primeira classe, mas o seu output é **entrada não confiável**.

- Só chamam o resto do sistema via `apps/<m>/api.py`, com as mesmas permissões que o
  utilizador que despoletou a ação. Nunca com privilégios de sistema.
- Cada chamada tem: `timeout`, `max_tokens`, `idempotency_key`, custo em tokens logado,
  `trace_id` no OpenTelemetry.
- Tools expostas ao modelo são funções puras com schema Pydantic; sem shell, sem SQL, sem
  filesystem.
- Conteúdo vindo de utilizadores ou da web é marcado como untrusted no prompt e nunca
  interpretado como instrução.
- Chamadas longas correm em Celery com resultado guardado; a API devolve um `job_id`.

## 6b. Fluxos-chave do StockFlow

**Receção por fatura**: `POST /documents` → evento **`DocumentoFechado`** → (outbox) →
`purchasing.normalizar_pagina` + `agents.extrair_documento` (Celery) → `Receipt` com linhas →
utilizador revê linha a linha → `purchasing.confirm_receipt` → `inventory.api.record_movements`
(uma transação: lotes + movimentos + CMP) → evento `StockReceived`.

> Os nomes desta linha mudaram quando a fatia 1 da ADR 0021 a construiu, e a diferença não é
> cosmética: **`DocumentoFechado` e não `InvoiceUploaded`** porque o que entra pode não ser uma
> fatura (uma guia de remessa não traz preços) e porque o momento que interessa é o **fecho** — num
> documento de várias folhas o upload acontece N vezes e o fecho uma. O `PurchaseReceiptDraft`
> passou a `Receipt` e o `SupplierPrice` saiu (o histórico de preços lê-se das linhas confirmadas).
> **O que está escrito aqui a partir do `Receipt` ainda não existe**: é a fatia 2, e a revisão linha
> a linha é a primeira coisa dela.

**Venda/produção de receita**: `recipes.api.consume(recipe, qty)` → N `consumption` por FEFO → `StockConsumed`.

**Contagem**: `inventory.open_count` → linhas em telemóvel → `close_count` → `adjustment` por diferença.

**Alertas**: tarefa periódica lê `StockLevel`/`Lot` → `notifications` envia digest diário por tenant.

Dependências permitidas (import-linter): `agents → purchasing.api, catalog.api` · `purchasing → inventory.api, catalog.api`
· `recipes → inventory.api, catalog.api` · `inventory → catalog.api` · todos → `accounts.api, shared` e `<m>.events`
de qualquer módulo · `shared → nada` (nem `accounts.api`). Nada mais.

## 7. Quando extrair um serviço

Candidato óbvio no futuro: `agents/` (perfil de escala e custo muito diferente). Até lá, fica no monólito.

Extrai um módulo para serviço próprio apenas se **dois ou mais** forem verdade:

- O módulo precisa de um perfil de escala muito diferente do resto (ex.: workers de IA com GPU).
- Duas equipas bloqueiam-se mutuamente nos deploys do mesmo repo.
- Requisito de isolamento regulatório ou de dados (ex.: dados de saúde noutro perímetro).
- Uma tecnologia diferente é claramente superior para esse módulo (ex.: Go para um gateway de alta
  concorrência).

Como o módulo já só expõe `api.py` e comunica por eventos, a extração é mecânica: `api.py`
torna-se cliente HTTP/gRPC, a outbox passa a publicar num broker externo.

## 8. Observabilidade mínima

- Logs JSON com `request_id`, `tenant_id`, `user_id` (hash), nunca PII.
- OpenTelemetry: traces em views, services, queries e chamadas a LLM.
- Métricas: latência p95 por endpoint, taxa de erro, tamanho da outbox, custo LLM/dia.
- Alertas: 5xx > 1% em 5 min; outbox com itens > 10 min; falhas de login por IP.

## 9. Docker

- `backend.Dockerfile`: stage `builder` com `uv sync --frozen --no-dev`, stage final
  `python:3.12-slim` (ou distroless) copia só `.venv` e código; `USER app`; `HEALTHCHECK`.
- `frontend.Dockerfile`: `pnpm build` num stage, servido por Caddy num stage final.
- `compose.yml` dev: `backend`, `worker`, `frontend`, `db`, `redis`, `proxy`. Volumes só para
  código em dev. Rede interna; só o proxy expõe portas, e no host em `127.0.0.1` com as portas
  do ADR 0002.
- Dois serviços de setup em `profiles: ["setup"]`, que não arrancam com um `up` normal e são os
  únicos que veem credenciais privilegiadas: `db-roles` (corre `docker/db/roles.sql`, idempotente
  — o init dir do Postgres só corre na primeira inicialização do volume, e em base de dados
  gerida não existe) e `migrate` (o único processo com `MIGRATION_DATABASE_URL`). O `backend` e o
  `worker` recebem `DATABASE_URL` e nunca a credencial do dono (ADR 0006).
- Prod: mesmas imagens, segredos por Docker secrets ou pelo orquestrador, nunca em `env_file`
  commitado.
