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
2. Middleware Django: sessão → CSRF → `TenantMiddleware` (define `SET app.tenant_id` na
   ligação Postgres para ativar RLS) → logging estruturado com request id.
3. View DRF: autentica, aplica `permission_classes`, valida com serializer.
4. View chama **uma** função em `services.py`. A função corre numa transação
   (`transaction.atomic`), escreve na BD e, se necessário, insere um evento na tabela `outbox`
   **na mesma transação**.
5. Resposta serializada. Nada de efeitos secundários síncronos.
6. Um worker Celery lê a `outbox`, publica o evento aos `handlers.py` subscritos, marca como
   processado. Handlers são idempotentes (chave: `event_id`).

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

**Receção por fatura**: `purchasing.upload_invoice` → evento `InvoiceUploaded` → `agents.extract_invoice`
(Celery) → `PurchaseReceiptDraft` → utilizador revê → `purchasing.confirm_receipt` → `inventory.api.record_movements`
(uma transação: lotes + movimentos + CMP + SupplierPrice) → evento `StockReceived`.

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
  código em dev. Rede interna; só o proxy expõe portas.
- Prod: mesmas imagens, segredos por Docker secrets ou pelo orquestrador, nunca em `env_file`
  commitado.
