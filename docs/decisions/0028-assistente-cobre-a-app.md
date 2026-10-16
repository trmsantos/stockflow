# ADR 0028 — O assistente cobre a app: leitura total, navegação e ajuda (sem escritas)

**Estado:** proposta a aprovar pelo dono (2026-10-16). Escrita pelo agente principal depois de três
tentativas do `architect` encravarem por limite de API; emendada com o levantamento que o primeiro
`architect` entregou depois (factos verificados sobre o `reporting` e os search params do cliente).

**Contexto.** A ADR 0027 deu ao estabelecimento um assistente com sete tools de stock e um prompt que
recusa tudo o resto. O dono testou-o e achou-o "demasiado genérico": quer que responda a qualquer
pergunta sobre o seu estabelecimento e que oriente a pessoa dentro da app. A ADR 0027 continua a
valer em tudo o que esta não muda — tools puras com schema Pydantic, resultado ≤ 8 KB marcado como
dados, permissões de quem pergunta e nunca `system_scope`, tetos diários, língua do pedido, 202 +
polling, nenhuma escrita no ledger. Esta fatia acrescenta **duas camadas**: ler tudo o que a app
sabe, e navegar/ajudar. A terceira — tarefas com confirmação humana — é a fatia seguinte.

**Decisão 1 — Leitura total: treze tools novas, cada uma sobre um `api.py`.** O que o assistente
sabe é o que as portas expõem; nada lê modelos de outro módulo. Papéis seguem o padrão da 0027:
tudo o que é **euros ou compras** é `owner|manager`; o resto, os três papéis.

| Tool | Argumentos | Lê de | Papéis | A acrescentar à porta |
|---|---|---|---|---|
| `rececoes` | `estado: por_rever\|confirmadas\|hoje`, `limite≤20` | `purchasing.api` | todos (sem €) | `listar_rececoes` (DTO: id, fornecedor, data, estado, nº linhas, pendências) |
| `rececao` | `id` | `purchasing.api` | todos; `unit_price`/totais só owner\|manager | `rececao_por_id` (cabeçalho + linhas com estado) |
| `historico_de_precos` | `product_id`, `meses≤12` | `purchasing.api` | owner\|manager | `precos_confirmados_por_artigo` (por fornecedor e mês, sem IVA) |
| `contagens` | `estado: abertas\|fechadas`, `limite≤20` | `inventory.api` | todos | `listar_contagens` |
| `contagem` | `id` | `inventory.api` | todos; valor em € só owner\|manager | `contagem_por_id` (linhas, contado vs esperado, diferença) |
| `alertas` | `tipo: falta\|validade\|desperdicio\|todos`, `severidade?` | `inventory.api` | todos | `resumo_de_alertas` (o que `stock/alerts` já calcula) |
| `artigo` | `id` | `catalog.api` | todos | `embalagens_por_artigo` (o resto já existe) |
| `receitas` | `q?`, `limite≤20` | `recipes.api` (**novo**) | todos | `procurar_receitas`, `receita_por_id` |
| `receita` | `id` | `recipes.api` | todos; custo só owner\|manager | `receita_por_id` (ingredientes, `yield_factor`, custo por dose) |
| `producoes_recentes` | `dias≤30` | `recipes.api` | todos | `producoes_por_periodo` |
| `equipa` | — | `accounts.api` | todos veem nome e papel; email só owner | `membros_do_ambito` |
| `estabelecimento` | — | `accounts.api` + `inventory.api` | todos | `definicoes_do_ambito` (nome, dia de negócio, regime de IVA, nº localizações) |

Com as sete da 0027 e a `ajuda_sobre` da decisão 3 são **vinte** tools. Os esquemas crescem o
prompt em ~5 mil tokens por chamada; a ~1 s por chamada no `gemini-3.1-flash-lite` isso não pesa, e
o teto de iterações (6) não muda.

**Decisão 2 — Os números do painel ficam fora desta fatia; o `reporting` continua sem porta.** O
levantamento mostrou que o `apps/reporting` de hoje não é só "desligado" (`config/urls.py` não o
inclui e o `/reporting/summary` que o cliente chama não existe): está **errado** — `revenue` é
Σ `production_in × unit_cost` (produção não é receita, ADR 0013 d1), itera o ledger em Python (d5
proíbe), as views só exigem `IsAuthenticated` quando a 0013 d6 exige `owner`, e `projection_report`
importa modelos de outros módulos. Dar ao assistente um `resumo_do_mes` sobre isto era servir
números errados com cara de certos — pior do que não responder. A alternativa (compor compras e
desperdício no `agents` por `purchasing.api` + `inventory.api`) criava um segundo sumidouro de
cálculo que divergiria do painel. **Decisão:** o assistente responde "ainda não tenho o painel do
mês" e leva ao ecrã; os números entram quando a fatia **"Ligar o Painel" (ADR 0013, recomendada a
seguir)** servir `/reporting/summary|series|month` certos e com permissões — e aí a 0013 decide se
o `reporting` ganha porta. A ADR 0013 **não** é emendada aqui.

**Decisão 3 — Navegação derivada no servidor; ajuda é a única tool nova que não lê dados.**
*Navegação:* o modelo **não pede rotas nem escreve URLs**. As ações de interface derivam-se, à
leitura, das **tools que o turno chamou**, por um mapa fechado em código (`apps/agents/navegacao.py`:
tool + argumentos validados → id de rota + search params): `saldo_de_artigo`/`movimentos_de_artigo`/
`artigo` → `stock/<artigo>`; `artigos_abaixo_do_minimo` → `alertas?ver=falta`; `lotes_a_vencer` →
`alertas?ver=expira`; `rececoes(por_rever)` → `receber?estado=revisao`; `rececao(id)` →
`receber/<id>`; `contagens`/`contagem` → `contar`; `receitas`/`receita` → (sem rota hoje; nenhum
botão); `compras_por_periodo`/`historico_de_precos` → `receber`; `ajuda_sobre(tema)` → a rota do
tema (ex. perdas → `stock`, equipa → `definicoes?seccao=equipa`). Filtra-se pelos `papeis` do
`menu.py` (um botão para um ecrã que o papel não vê não sai) e os search params são exactamente os
que os schemas Zod das rotas aceitam hoje (`/stock {loja, filtro, q}`, `/alertas {ver, periodo}`,
`/receber {estado}`, `/contar {zona}`, `/painel {period, month, aba, explicar}`). Um teste nas duas
pontas (backend ↔ Zod, como o registo de rotas da ADR 0009) falha quando divergem. Não há URL
injectável porque não há URL vinda do modelo; não há coluna nova porque é derivado como o
`estado_derivado` dos documentos.
*`ajuda_sobre(tema)`*: lê um **manual curto curado por nós** em `backend/apps/agents/ajuda/<lingua>/<tema>.md`
(pt-PT e en, ~12 temas: receber uma fatura, rever e confirmar linhas, perdas/ajustes/transferências,
contar, alertas e mínimos, painel do mês, artigos/SKU/embalagens, fornecedores, receitas e
produção, equipa e convites, definições — dia de negócio, IVA, tema —, o próprio assistente). O
índice de temas vai no prompt; o texto vai como resultado da tool, marcado como dados. Um teste
afirma que cada tema existe nas duas línguas e que toda a rota citada existe no registo. Quem muda
um ecrã muda o tema — o teste da rota é o que o lembra.

**Decisão 4 — O contrato da mensagem ganha `acoes`, derivadas e não guardadas.** `MensagemOut.acoes`:
lista de `{rota, parametros, rotulo_id}` calculada pelo serializer a partir dos `tool_calls`
revalidados do turno (`rasto.py`) e do mapa da decisão 3; o cliente renderiza cada ação como botão
(`Link` do TanStack com os search params validados pelo Zod da rota; `rotulo_id` resolve-se no
catálogo do cliente — nenhum rótulo nosso viaja no arame, ADR 0019). Sem migração.

**Decisão 5 — O prompt deixa de recusar e passa a distinguir três respostas.** Persona: "o
assistente do StockFlow para *este* estabelecimento". Sabe (a) responder com dados via tools,
(b) explicar como a app funciona via `ajuda_sobre`, (c) dizer onde na app se faz cada coisa — os botões para lá derivam das tools, não do texto. Distingue **"não existe"** (uma tool devolveu vazio: "não há receções por
rever"), **"não sei"** (nenhuma tool cobre: diz que não tem forma de ver isso) e **"fora da app"**
(recusa curta e oferece o que sabe). Pedidos de ação ("regista uma perda") recebem: a explicação de
como se faz (via `ajuda_sobre`, que traz o botão para o ecrã) — nunca a execução (fatia seguinte). Língua do pedido,
unidades e euros como na 0027.

**Decisão 6 — Fora de âmbito, por extenso.** Escritas, rascunhos e confirmações; previsões; voz;
telemóvel; pesquisa sem acentos; categorias de catálogo; qualquer tool que receba texto livre e o
passe a SQL (não há).

**Casos de aceitação** (cada um é um teste com o cliente falso):
- "Dá-me tudo o que preciso de saber sobre a loja" → `estabelecimento` + `alertas(todos)` +
  `rececoes(por_rever)` + `contagens(abertas)` → síntese; o resumo do mês em € diz "ainda sem painel" e leva ao ecrã.
- "O que recebi da Makro este mês?" → `procurar_fornecedores` + `compras_por_periodo(fornecedor)`.
- "Leva-me às receções por rever" → `rececoes(por_rever)` → resposta com a contagem + botão `receber?estado=revisao`.
- "Como registo uma perda?" → `ajuda_sobre(perdas)` → explicação + botão `stock`.
- "Quem é gerente aqui?" → `equipa` (staff vê nomes e papéis; só o owner vê emails).
- "Que receitas usam farinha?" → `procurar_artigos` + `receitas(q)`.
- "Regista 2 kg de farinha como perda" → explicação + navegação; **nenhuma escrita** (teste afirma
  contagens de `StockMovement` iguais).
- "Qual é a capital de França?" → recusa curta e oferta do que sabe.
- "Quanto faturei este mês?" → "ainda não tenho o painel do mês" + botão `painel` (decisão 2).

**Consequências.** Doze tools novas e as funções correspondentes em quatro portas (`recipes/api.py`
ganha leitura — hoje só expõe `produzir` — e o contrato do import-linter deixa de proibir `agents →
recipes.api`, revogando o "recipes fica fora" da ADR 0027 d5); `acoes` derivadas sem migração; mapa
fechado de navegação com teste nas duas pontas; manual de ajuda em duas línguas com teste; prompt
reescrito; `ARCHITECTURE.md` §6b emendada; frontend: botões de ação no turno (página e painel),
"Fontes" inclui a ajuda. **Incoerências a corrigir pelo caminho** (levantamento do `architect`,
para o `domain-expert`/`backend`): `stock_alerts` usa calendário civil e `lotes_a_vencer` o dia de
negócio; `RececaoViewSet.list(estado=hoje)` filtra desde a meia-noite mas o rótulo promete dia de
negócio; `Recipe.__str__` lê `product.name` (é `short_name`).
Os ecrãs Contar e Produção **não têm endpoints hoje** (servidos por fixtures no cliente): o
assistente lê as tabelas pelas portas na mesma — é a primeira vez que esses dados saem do
backend, e expõe o atraso desses ecrãs.

**Perguntas para o dono.** (1) `staff` vê a equipa (nomes e papéis)? (2) `staff` vê receitas com
custo por dose, ou só a ficha técnica? (3) manual de ajuda em pt-PT e en, ou só pt-PT nesta fase?
(4) a fatia "Ligar o Painel" (ADR 0013) entra logo a seguir a esta, para o assistente passar a ter os números do mês?
