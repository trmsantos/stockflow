# Contexto de sessão — colar como primeira mensagem no Claude Code

> Cola tudo abaixo desta linha na primeira mensagem de cada sessão nova (ou pelo menos na primeira de todas).
> O CLAUDE.md já dá as regras; isto dá o *porquê* e o estado atual.

---

Estou a construir o **StockFlow**: um SaaS multi-tenant de gestão de stock para restauração e negócios
alimentares em Portugal (restaurantes, pastelarias, cafés). O diferenciador é IA aplicada aos dados do
cliente — entrada de mercadoria por foto/PDF da fatura do fornecedor, alertas de validade e rutura,
relatório de desperdício em euros — e não um chatbot de suporte.

**Decisões já tomadas (não reabrir sem motivo forte):**
- Stack: Django 5 + DRF com uv · PostgreSQL 16 com Row-Level Security por tenant · Celery + Redis ·
  React 18 + TypeScript strict + Vite + Tailwind v4 + shadcn/ui · OpenAPI → tipos TS · Docker multi-stage · pnpm.
- Arquitetura: monólito modular (`accounts, catalog, inventory, purchasing, recipes, agents, billing,
  notifications, shared`), módulos só se importam via `api.py`, outbox para eventos. Ver ARCHITECTURE.md e ADR 0001.
- Stock é um **ledger** append-only de `StockMovement`; quantidades são projeções. Nunca editáveis.
- A IA só produz **drafts**; um humano confirma antes de qualquer escrita no ledger.
- Sem estética genérica de IA: DESIGN.md define IBM Plex, um único acento verde-azulado, densidade
  compacta, tab bar mobile (Stock · Receber · Contar · Alertas).
- Segurança e encriptação conforme SECURITY.md; `security-reviewer` tem de dar PASS no fim de cada feature.

**Como trabalhamos:**
- Uma feature por sessão, sempre via `/feature <descrição>`. O pipeline é
  architect → domain-expert → backend → frontend → security-reviewer, e pára para eu aprovar o contrato.
- Tu (agente principal) coordenas; delegas nos subagents de `.claude/agents/`; não implementas diretamente.
- Se eu decidir algo relevante nesta conversa, regista-o em `docs/decisions/` antes de terminar.
- Não instales dependências fora do lockfile, não desligues segurança "para testar", não suprimas lint.

**Estado atual (2026-09-30, sessão 2):** repo `trmsantos/stockflow`, privado, na conta pessoal, em
`main`, HEAD `43525ff`. **`/kickoff` fechado: os 8 passos estão feitos.** `backend/` com uv, os 9
módulos, 10 contratos de import-linter, a camada de settings completa, `apps/shared/` com
`tenant_scope`/outbox, `apps/accounts/` com `Tenant`/`User`/`Membership` e o `TenantMiddleware` como
último middleware, `frontend/` em Vite+TS strict com os tokens do DESIGN.md, `docker/` com 8
serviços e o Caddy construído de um `go.mod` nosso, e CI com 7 jobs. **200 testes**, ruff limpo sem
`# noqa`, `check --deploy` sem warnings, `security_check.sh` a dar **PASS** com zero ferramentas
saltadas e zero gates sem resultado.

**O passo 8 foi fechado sem PASS independente da última versão, e isso é uma decisão consciente.**
O `security-reviewer` correu **quatro** vezes e deu FAIL nas quatro. As duas primeiras rondas acharam
coisas exploráveis: o `backend/.env` dentro da imagem que servia pedidos (CRITICAL, com a password do
dono da BD), e o gate do artefacto a ser evadível por cinco vias. As duas últimas acharam
**afirmações de cobertura falsas** — graves pela norma deste projeto, mas nenhuma um segredo exposto.
Todos os bloqueadores das quatro rondas estão corrigidos e medidos (ver `0c6590e`, `4d7be15`,
`43525ff`); o que não existe é uma quinta revisão a confirmar o `43525ff`. Se voltares a este ponto:
**o gate do artefacto e o `SECURITY.md` §9 são a parte não revista**, porque foram reescritos por
completo no último commit.

**A lição que atravessou as quatro rondas, e que vale mais do que qualquer delas: uma verificação que
corre no contexto do mecanismo que avalia não é uma verificação.** Reportei 0 CVEs havendo 6 porque o
`trivy` lê o `.trivyignore` do directório actual sem lhe ser pedido e a minha "confirmação
independente" correu nesse directório. Reportei imagens limpas porque o gate corria `find /app`
*dentro* da imagem, e `/app` não existe no frontend nem no proxy. Escrevi um gate de supressões que
uma linha no `.gitignore` desarmava. As respostas estruturais estão no repo: o primeiro gate do
`security_check.sh` verifica se os outros podem ser acreditados; o gate do artefacto varre o tar
exportado **no host** e sai INCONCLUSIVO se não conseguir varrer; o veredicto tem três estados e
INCONCLUSIVO não serve como PASS; e o `check-design-tokens.mjs` mede o contraste e o gamut que o
DESIGN.md afirma, em vez de os deixar em prosa.

**Tickets abertos, nenhum bloqueador, todos avaliados como tal por um revisor:**
- **D3** — o guarda de âmbito do `conftest.py` filtra por `sql.lstrip()[:6]`, logo uma instrução que
  comece por `WITH` ou `(` salta-o. Nada na árvore emite uma.
- **D4** — a política da outbox é `FOR ALL`, logo o disjunto `app.scope = 'system'` concede
  UPDATE/DELETE nas linhas de **todos** os tenants a quem corra em `system_scope()`. Vira decisão a
  sério (duas políticas, uma `FOR SELECT` e uma `FOR UPDATE` estreita) no dia em que existir um
  consumidor da outbox — hoje não existe.
- **D5** — `apply_async` valida que há `tenant_id` e que é um UUID, não o direito de quem enfileira a
  esse tenant. Código em `tenant_scope(A)` pode enfileirar para B. Não há tarefas de domínio.
- **Frescura das imagens** — o gate varre todas as `stockflow-*` que existirem, sem noção de idade,
  logo varre uma imagem obsoleta e conta-a como cobertura. Já não sustenta nenhuma afirmação falsa (a
  tabela de números saiu do §9), mas a correcção barata é imprimir a data de criação de cada imagem
  na linha de cobertura.
- **Partições** — `relkind IN ('r','p')` vai listar também as partições **folha** quando existirem, e
  isso exige uma decisão: excluí-las por `pg_inherits` ou exigir política em todas. Nomeado no
  `test_db_roles.py`.

**Dívida nomeada:** a escada de lockout acima dos 30 min não tem efeito (limitação estrutural do
axes — ver `SECURITY.md` §5); o 429 do lockout não tem corpo JSON útil; sem beat não há quem drene a
outbox; **não há MFA** (o `SECURITY.md` §5 di-lo, e a afirmação contrária já estava em cinco
ficheiros antes de ser caçada nos cinco); encriptação campo-a-campo e o `nif` do tenant ficaram para
a sua própria sessão; a CSP de dev autoriza o `unpkg` globalmente por causa do Swagger; `testpaths`
deixaria cair testes em `apps/**` (hoje não há nenhum lá); a impersonation de suporte não tem ADR;
OpenTelemetry não está provisionado.

**A seguir: sessão 2, o catálogo** — mas lê o parágrafo abaixo primeiro, porque há seis decisões de
domínio que o bloqueiam e que nenhum agente pode inventar.

**Sessão 0 (validação com donos de restaurante) continua por confirmar, e agora custa.** O
`domain-expert` marcou seis decisões como "não inventes default sem falar com um utilizador real":
bloquear ou avisar quando falta stock, clientes com várias lojas serem um NIF ou vários, consumo por
talão de POS ou em lote, cozinha central com stock em trânsito, `yield_factor`, e a hora a que
começa o dia de negócio (o desperdício da 01h30 pertence ao serviço anterior). Nenhuma bloqueia o
kickoff; todas bloqueiam o catálogo e o ledger, e são caras de mudar depois de haver migrações
aplicadas — que o CLAUDE.md proíbe editar. A conversa do NIF (sessão 2) acrescentou cinco: o
conjunto de papéis (o segundo sócio é `owner` igual, ou há um papel intermédio? — bloqueia a ADR do
convite); com que frequência acontece ENI → Lda e se esperam que o histórico transite (decide se a
mudança de NIF é self-service ou só suporte); se a contabilista é utilizadora do produto ou só
recebe exports (decide quanto vale o seletor de tenant); se as faturas emitidas ao NIF pessoal do
sócio são frequentes (decide se os "NIFs alternativos" entram no v1); e se grupos com N sociedades
estão no mercado-alvo ao lançamento (decide se `Organization` é fase 2 ou nunca).

**Plano de sessões (README §2):** 0 validação com donos de restaurante · 1 `/kickoff` · 2 catálogo ·
3 ledger de stock · 4 listagem + alertas · 5 contagem em telemóvel · 6–7 receção por fatura · 8 receitas + desperdício.

Antes de fazer qualquer coisa: lê CLAUDE.md, ARCHITECTURE.md, DESIGN.md e SECURITY.md, confirma-me em
5 linhas que percebeste o produto e as regras, e diz-me qual é o próximo passo segundo o estado atual.
