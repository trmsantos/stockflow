# ADR 0028 — O assistente cobre a app: leitura total, navegação e ajuda (sem escritas)

**Estado:** proposta a aprovar pelo dono (2026-10-16). Escrita pelo agente principal depois de três
tentativas do `architect` encravarem por limite de API; o conteúdo segue o mesmo método.

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
| `resumo_do_mes` | `mes: YYYY-MM` | `reporting.api` (**novo**, d2) | owner\|manager | `resumo_do_mes` (compras, desperdício €, valor de stock, variação) |
| `equipa` | — | `accounts.api` | todos veem nome e papel; email só owner | `membros_do_ambito` |
| `estabelecimento` | — | `accounts.api` + `inventory.api` | todos | `definicoes_do_ambito` (nome, dia de negócio, regime de IVA, nº localizações) |

Com as sete da 0027 e as duas da decisão 3 são **vinte e duas** tools. Os esquemas crescem o
prompt em ~6 mil tokens por chamada; a ~1 s por chamada no `gemini-3.1-flash-lite` isso não pesa, e
o teto de iterações (6) não muda.

**Decisão 2 — O `reporting` ganha um `api.py` mínimo, e a ADR 0013 é emendada.** A 0013 decidiu
que o `reporting` não tem porta porque nenhum módulo precisava de o ler — era o fim da linha. O
assistente é um consumidor da mesma natureza que o painel (apresentação de números já calculados), e
recalcular compras/desperdício no `agents` por `inventory.api`+`purchasing.api` duplicava a lógica
do mês em dois sítios que divergiriam. A porta expõe **um** DTO congelado (`ResumoDoMes`) e nada
mais; o import-linter passa a permitir `agents → reporting.api` e continua a proibir tudo o resto do
`reporting`. `ARCHITECTURE.md` §6b e a ADR 0013 levam a mesma linha.

**Decisão 3 — Navegação e ajuda são duas tools, não texto livre.**
*`propor_navegacao(rota, parametros)`*: o modelo **nunca escreve URLs**. Pede uma rota pelo id e
parâmetros nomeados; o backend valida contra uma **lista fechada servida em código**
(`apps/agents/navegacao.py`: id de rota → caminho → parâmetros permitidos e os seus tipos:
`receber{estado: revisao|hoje}`, `stock{q?}`, `stock/<artigo:uuid>`, `produtos/<produtoId:uuid>`,
`receber/<rececao:uuid>`, `alertas{tipo?}`, `contar`, `painel{mes?: YYYY-MM}`, `definicoes{seccao?}`),
grava a ação validada no turno (`acoes`, JSON) e devolve ao modelo "ação registada" para a poder
citar. A lista é a versão servidor dos search params do cliente, e um teste nas duas pontas
(`tests/test_assistente_navegacao.py` + um `check-navegacao` no lint do frontend) falha quando
divergem — a forma da ADR 0009. Um `rota` ou `parametros` fora da lista é recusado à tool, não ao
utilizador.
*`ajuda_sobre(tema)`*: lê um **manual curto curado por nós** em `backend/apps/agents/ajuda/<lingua>/<tema>.md`
(pt-PT e en, ~12 temas: receber uma fatura, rever e confirmar linhas, perdas/ajustes/transferências,
contar, alertas e mínimos, painel do mês, artigos/SKU/embalagens, fornecedores, receitas e
produção, equipa e convites, definições — dia de negócio, IVA, tema —, o próprio assistente). O
índice de temas vai no prompt; o texto vai como resultado da tool, marcado como dados. Um teste
afirma que cada tema existe nas duas línguas e que toda a rota citada existe no registo. Quem o
mantém: quem muda um ecrã muda o tema — o teste da rota é o que o lembra.

**Decisão 4 — O contrato da mensagem ganha `acoes`.** `ChatMessage.acoes: JSONField` (lista de
`{rota, parametros, rotulo_id}`), validada na escrita pela lista fechada; o serializer de saída
expõe-a e o cliente renderiza cada ação como botão (`Link` do TanStack com os search params já
validados pelo Zod da rota; o `rotulo_id` resolve-se no catálogo do cliente — nenhum rótulo nosso
viaja no arame, ADR 0019). Sem migração destrutiva: coluna nova com default `[]`.

**Decisão 5 — O prompt deixa de recusar e passa a distinguir três respostas.** Persona: "o
assistente do StockFlow para *este* estabelecimento". Sabe (a) responder com dados via tools,
(b) explicar como a app funciona via `ajuda_sobre`, (c) levar a pessoa ao ecrã certo via
`propor_navegacao`. Distingue **"não existe"** (uma tool devolveu vazio: "não há receções por
rever"), **"não sei"** (nenhuma tool cobre: diz que não tem forma de ver isso) e **"fora da app"**
(recusa curta e oferece o que sabe). Pedidos de ação ("regista uma perda") recebem: a explicação de
como se faz + a ação de navegação para o ecrã — nunca a execução (fatia seguinte). Língua do pedido,
unidades e euros como na 0027.

**Decisão 6 — Fora de âmbito, por extenso.** Escritas, rascunhos e confirmações; previsões; voz;
telemóvel; pesquisa sem acentos; categorias de catálogo; qualquer tool que receba texto livre e o
passe a SQL (não há).

**Casos de aceitação** (cada um é um teste com o cliente falso):
- "Dá-me tudo o que preciso de saber sobre a loja" → `estabelecimento` + `alertas(todos)` +
  `rececoes(por_rever)` + `contagens(abertas)` (+ `resumo_do_mes` se owner|manager) → síntese.
- "O que recebi da Makro este mês?" → `procurar_fornecedores` + `compras_por_periodo(fornecedor)`.
- "Leva-me às receções por rever" → `propor_navegacao(receber, {estado: revisao})` → botão.
- "Como registo uma perda?" → `ajuda_sobre(perdas)` + `propor_navegacao(stock)`.
- "Quem é gerente aqui?" → `equipa` (staff vê nomes e papéis; só o owner vê emails).
- "Que receitas usam farinha?" → `procurar_artigos` + `receitas(q)`.
- "Regista 2 kg de farinha como perda" → explicação + navegação; **nenhuma escrita** (teste afirma
  contagens de `StockMovement` iguais).
- "Qual é a capital de França?" → recusa curta e oferta do que sabe.

**Consequências.** Treze tools novas e as funções correspondentes em cinco portas (`recipes/api.py`
e `reporting/api.py` nascem); coluna `acoes`; lista fechada de navegação com teste nas duas pontas;
manual de ajuda em duas línguas com teste; prompt reescrito; `ARCHITECTURE.md` §6b e ADR 0013
emendadas; frontend: botões de ação no turno (página e painel), "Fontes" inclui ajuda e navegação.
Os ecrãs Contar e Produção **não têm endpoints hoje** (servidos por fixtures no cliente): o
assistente lê as tabelas pelas portas na mesma — é a primeira vez que esses dados saem do
backend, e expõe o atraso desses ecrãs.

**Perguntas para o dono.** (1) `staff` vê a equipa (nomes e papéis)? (2) `staff` vê receitas com
custo por dose, ou só a ficha técnica? (3) manual de ajuda em pt-PT e en, ou só pt-PT nesta fase?
(4) "Dá-me tudo sobre a loja" deve incluir o resumo do mês em € para o owner por omissão?
