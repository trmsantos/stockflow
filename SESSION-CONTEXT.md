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
- Sem estética genérica de IA: DESIGN.md define a identidade **"Cabine"** (escolhida pelo dono em
  2026-10-01 entre duas propostas opostas): **três paletas** desde 2026-10-07 — `escuro` (o default e
  a identidade aprovada), `claro` e `meio_termo`, escolhidas pelo atributo `data-tema` e nunca por
  `prefers-color-scheme` (ADR 0015) —, Archivo em UI e IBM Plex Mono nos
  números, um só acento ciano, densidade densa de ERP. **Desktop-primeiro** (1440 de desenho, 1280
  obrigatório); o telemóvel serve os fluxos de campo (contar, receber) e **não** há tab bar — ela
  saiu do §4 com a mudança de direcção, e o `src/shell/tab-bar.tsx` ainda existe à espera da tarefa
  do shell. Dependência concreta para quem a fizer: o `receber.tsx` tem um
  `bottom-[calc(3.5rem+env(safe-area-inset-bottom))]` em que os `3.5rem` **são** a altura da tab
  bar, e tem de sair com ela.
- Segurança e encriptação conforme SECURITY.md; `security-reviewer` tem de dar PASS no fim de cada feature.

**Como trabalhamos:**
- Uma feature por sessão, sempre via `/feature <descrição>`. O pipeline é
  architect → domain-expert → backend → frontend → security-reviewer, e pára para eu aprovar o contrato.
- Tu (agente principal) coordenas; delegas nos subagents de `.claude/agents/`; não implementas diretamente.
- Se eu decidir algo relevante nesta conversa, regista-o em `docs/decisions/` antes de terminar.
- Não instales dependências fora do lockfile, não desligues segurança "para testar", não suprimas lint.

**Estado atual (2026-10-08):** repo `trmsantos/stockflow`, privado, na conta pessoal. `main` tem o
PR #3 mergeado (i18n, definições, temas, demonstração, SMTP); o **PR #4 está aberto** com a fatia 1 da
recepção de mercadoria. **454 testes** no backend, `ruff` limpo sem `# noqa`, import-linter 11/11,
`security_check.sh` a dar **PASS** com zero achados, e os seis gates do `pnpm lint` verdes.

O que existe para além do kickoff: o **shell** navegável com o menu como dados por tenant; os ecrãs de
**Stock, Alertas, Artigo, Contar, Receber, Receção e Painel**, servidos em desenvolvimento pelo
`frontend/fixtures/servidor.ts`; **três paletas** com gate de cor e o tema como preferência da pessoa
guardada no servidor; **um ecrã para todas as definições** em secções; o **estabelecimento de
demonstração** como tenant semeado; e **duas línguas vindas do browser** (pt-PT e inglês), com sete
catálogos, 975 chaves e o teste que amarra as duas pontas da decisão — o inglês só liga com a lista
fechada do `check-textos.mjs` vazia.

**A recepção de mercadoria arrancou** (ADR 0021, três fatias: documento → catálogo+revisão → ledger).
A fatia 1 está feita: quatro tabelas com RLS, sete endpoints em `/api/v1/documents`, o ecrã de entrada
de documento, e o rasterizador pela libvips do sistema. **As outras duas apps de domínio continuam
cascas** — `catalog`, `inventory`, `recipes` e `notifications` têm zero models —, logo o Stock e o
Painel continuam a mostrar fixtures.

**Cinco decisões à espera do dono, e nenhuma é técnica:** a biblioteca de QR para a ponte
desktop→telemóvel; a quota de armazenamento por estabelecimento (hoje não há teto e um membro
autenticado escreve ~13 GiB/h); o consumidor da outbox e o `beat`, que é o que faz a divergência
deliberada ao CLAUDE.md ("efeitos secundários via outbox") deixar de ser necessária e desbloqueia o
email de convite; as três perguntas da fatia 1 (páginas máximas, retenção do original, quem apaga um
documento); e as do ledger, das quais a mais cara é **quanto vale a mercadoria que entra por guia de
remessa sem preço** — sem ela a fatia 3 não tem migração.

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
axes — ver `SECURITY.md` §5); sem beat não há quem drene a
outbox; **não há MFA** (o `SECURITY.md` §5 di-lo, e a afirmação contrária já estava em cinco
ficheiros antes de ser caçada nos cinco); encriptação campo-a-campo e o `nif` do tenant ficaram para
a sua própria sessão; a CSP de dev autoriza o `unpkg` globalmente por causa do Swagger; `testpaths`
deixaria cair testes em `apps/**` (hoje não há nenhum lá); a impersonation de suporte não tem ADR;
OpenTelemetry não está provisionado.

**Onde estamos agora (2026-10-01): a construir o shell, que não estava no plano, e a razão da
inversão importa.** O plano punha a sessão 0 (validação com donos) antes de tudo e ela bloqueava há
duas sessões. A inversão: construir um **shell navegável com dados falsos** e usá-lo como
**instrumento** para obter as respostas — mostrar um ecrã em vez de perguntar no abstracto. O
`domain-expert` validou-a: **seis das onze perguntas desenham-se para dentro do ecrã** (falta de
stock, consumo por talão vs lote, stock em trânsito, `yield_factor`, hora do dia de negócio,
faturas ao NIF pessoal), duas dão metade, três são conversa. O guião está em
`docs/sessao-0-guiao.md` e tem dois leitores: o agente que constrói e quem conduz a conversa.

Feito: ADR 0008 (TanStack Router, fronteiras do frontend, e a fronteira dos dados falsos), o shell
com sidebar/tab bar, o servidor de fixtures (`frontend/fixtures/`, fora de `src/`, plugin com
`apply: "serve"` — os dados falsos **não podem** entrar num build, não por disciplina mas por
construção), e o ecrã de **Stock** completo com as sondas da Q1, Q2 e Q7 medidas a funcionar.
Faltam Receber, Contar e Alertas.

**Nada do frontend foi verificado num browser** — não há nenhum no ambiente dos agentes, e não há
mecanismo visual no projeto. É a maior lacuna do frontend e só o utilizador a pode fechar.

**E quando ele olhou, rejeitou o visual nos quatro eixos** (2026-10-01): paleta e tom, densidade e
tamanho, "parece genérico / shadcn por defeito", **e a estrutura dos ecrãs**. A dívida está escrita
no topo do `DESIGN.md`, que é onde um agente de UI a lê antes de trabalhar, com a raiz suspeita
nomeada: a referência visual do §1 é o **Linear**, uma ferramenta densa de developers feita para
teclado, e o público usa isto de pé numa cozinha com pressa. Os tokens derivam dessa secção e a
estrutura dos ecrãs deriva do princípio de UX dela — logo o redesenho começa no §1.

Decisão: **registar e continuar.** A estrutura e as sondas sobrevivem a uma mudança visual, e o que
a sessão 0 ensinar muda a estrutura **e** o visual — redesenhar antes é redesenhar duas vezes. **O
risco aceite:** um visual que desagrada pode contaminar a própria sessão 0, com o dono a reagir ao
aspecto em vez do fluxo. Se isso acontecer, nota-o: é informação sobre o visual, não sobre o produto.

**Consequência para o guião:** o §1 do `docs/sessao-0-guiao.md` (o que cada ecrã mostra) passa a ser
**provisório**. Foi derivado do orçamento de ecrã e do domínio, mas a estrutura está contestada, e o
que o dono procurar e não encontrar vale mais do que o que lá está escrito.

**A seguir, depois dos quatro ecrãs: a sessão 0 com o shell na mão**, e só então o catálogo. As onze
decisões de domínio continuam a bloquear o catálogo e o ledger, e são caras de mudar depois de haver
migrações aplicadas — que o CLAUDE.md proíbe editar.

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
O shell de validação entrou **entre** a 1 e a 0, e não estava no plano: é o instrumento que
desbloqueia a 0, e termina por apagamento quando os endpoints reais existirem (ADR 0008, decisão 3).

Antes de fazer qualquer coisa: lê CLAUDE.md, ARCHITECTURE.md, DESIGN.md e SECURITY.md, confirma-me em
5 linhas que percebeste o produto e as regras, e diz-me qual é o próximo passo segundo o estado atual.
