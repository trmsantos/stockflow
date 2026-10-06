# ADR 0014 — Produção no ledger: dois tipos de movimento novos, e o que cada tipo significa para o dinheiro

**Contexto.** O `domain-expert` encontrou um bloqueador ao painel da ADR 0013 que não é do painel: é do
ledger. O contrato de hoje (`frontend/src/features/inventory/schemas.ts`, `tipoMovimentoSchema`) tem
sete tipos — `receipt, consumption, waste, adjustment, transfer_out, transfer_in, return` — e **nenhum
par de produção**. Numa pastelaria, fazer pastéis sai como `consumption` dos ingredientes e entra como
`receipt`, que é o tipo das compras a fornecedores; vender o pastel é outro `consumption`. Somar as
saídas de stock conta o custo dos ingredientes **e** o custo do produto acabado, e na Pastelaria Aurora
isto não é caso limite — é o fluxo principal de todos os dias. O `receipt` sobrecarregado erra para o
outro lado: quem agregar compras a partir de movimentos vê a produção própria como mercadoria comprada.

Há uma segunda razão para isto ser agora e não na sessão do ledger: **o `inventory_stockmovement` ainda
não existe.** Hoje isto são dois valores num `z.enum` e um ficheiro de vocabulário. Depois de haver
migração aplicada — que o `CLAUDE.md` proíbe editar — são uma migração nova *e* o reetiquetar de linhas
mal classificadas num ledger append-only, onde uma linha errada não se corrige: corrige-se com outra
linha. O custo desta decisão multiplica-se por cada dia em que não se toma.

**Decisão 1 — Entram `production_out` e `production_in`, com a forma do par que já existe.** Nove tipos.
A simetria com `transfer_out`/`transfer_in` não é estética: é a mesma classe de evento. Numa
transferência o valor não sai do negócio, muda de sítio; numa produção o valor não sai do negócio, muda
de forma. Os dois são pares de pernas que se anulam no total do tenant e que **não são eventos
económicos**. Recusa-se a alternativa de marcar a produção por uma `reference` que a agregação exclui:
um `reference` é um filtro por convenção — a agregação passa a ter de conhecer um formato mágico, e
esquecê-lo devolve um número errado em silêncio. Um tipo é uma união fechada que viaja no enum do
OpenAPI, entra no `types.ts` e chega ao `Record<união, …>` do frontend, onde um ramo esquecido **não
compila**. É o mecanismo que esta casa já usa para os `route_id` e para os papéis, e é a diferença entre
um defeito que falha alto e um que falha caro.

**Decisão 2 — A tabela de nove linhas: o que cada tipo significa para o dinheiro.** É esta tabela que a
ADR 0013 cita em vez de a reescrever, e é ela que impede que cada agregação futura invente a sua
própria lista de exclusões.

| Tipo | Sinal | Evento económico? | Entra em "mercadoria consumida" | Entra em "compras" |
|---|---|---|---|---|
| `receipt` | + | sim, entrada | não | sim (pela linha de fatura, não pelo movimento) |
| `return` | − | sim, reversão de entrada | **não** | sim, a **reduzir**, no período da nota de crédito |
| `consumption` | − | sim, saída | **sim** | não |
| `waste` | − | sim, saída | **sim** (é decomposição, não parcela) | não |
| `adjustment` | ± | sim, saída ou entrada não explicada | não — é **quebra desconhecida**, linha própria | não |
| `transfer_out` | − | não | não | não |
| `transfer_in` | + | não | não | não |
| `production_out` | − | **não** | **não** | não |
| `production_in` | + | **não** | não | não |

Três linhas desta tabela são as que o `domain-expert` nomeou como esquecidas por omissão. O par
`transfer_*` anula-se **ao nível do tenant** e deixa de anular no dia em que o painel for filtrado por
loja — o default da ADR 0013 é o painel do tenant, e um seletor de loja obriga a tratar transferências
como entradas e saídas daquela loja. O `return` sai do stock e **não é consumo**: reduz as compras.
E o `adjustment` não é desperdício: é a quebra que ninguém viu, e tem linha própria na ADR 0013 por
ser accionável sobre o processo e não sobre um artigo.

**Decisão 3 — O `production_in` entra ao custo das pernas que o produziram, e isso faz do `yield_factor`
um valor estrutural.** O custo unitário do produto acabado é a soma dos `production_out` daquela
produção dividida pela quantidade produzida; sem isto o pastel entra no stock a zero e o valor de stock
cai a cada fornada. Duas consequências que ficam escritas em vez de descobertas: **o `yield_factor` (a
Q4 das onze) deixa de ser um refinamento e passa a estar no denominador de um custo** — 10 kg de massa
que dão 9 kg de pastéis são 11% de erro no custo unitário de tudo o que se venda a partir dali; e o
desperdício de um produto acabado (os pastéis que ficaram ao fim do dia) é um `waste` sobre o produto
acabado, valorizado ao seu custo de produção, e **é uma perda a sério** — a exclusão da produção não o
apanha, e é assim que deve ser. Mão-de-obra **não** entra no custo de produção em v1: o custo de pessoal
é do painel, por mês, e metê-lo aqui contá-lo-ia duas vezes — o mesmo erro que esta ADR existe para
fechar, uma camada abaixo.

**Decisão 4 — As duas pernas nascem na mesma transação, escritas pelo `recipes` através do
`inventory.api`.** O `recipes` é o módulo que sabe o que é uma receita e uma produção
(`ARCHITECTURE.md` §2), e a aresta `recipes → inventory.api` já é permitida. O invariante é "nenhum
`production_out` sem o `production_in` correspondente", e a imposição é a transação: um savepoint que
falha não deixa meia produção. **Não há restrição de base de dados a garanti-lo** — é um invariante
entre linhas de uma tabela append-only, e uma `CHECK` não o alcança. Fica nomeado como tal: o que o
garante é um ponto de escrita único em `inventory.services` e um teste, não o esquema. Os dois
movimentos partilham um `production_id` (a referência da produção) para que a soma de uma fornada seja
uma query e não uma heurística por hora.

**Alternativas.** *Uma `reference` de produção excluída pela agregação* — respondida na decisão 1:
filtro por convenção contra união fechada. *Reutilizar `adjustment` para as duas pernas* — perde o único
significado que o `adjustment` tem (quebra não explicada) e torna a quebra desconhecida impossível de
medir, que é precisamente o número que o §4 da revisão de domínio quer ver. *Um tipo só,
`production`, com sinal* — o sinal é dado pelo tipo em todos os outros pares desta tabela, e um tipo cujo
significado depende do sinal obriga toda a leitura a ramificar duas vezes. *Não modelar produção em v1 e
tratar a pastelaria como quem revende* — é a alternativa honesta se a sessão 0 disser que o dono não quer
registar fornadas, e nesse caso o painel **não pode** mostrar "mercadoria consumida": mostra compras e
cala-se sobre consumo, com o bloco de qualidade de dados da ADR 0013 a dizê-lo. Fica como caminho
aberto, não como default.

**Consequências.** `tipoMovimentoSchema` passa de sete a nove valores, e com ele o `vocabulario.ts` (a
palavra de cada tipo), o `fixtures/ledger.ts` e o `historico-de-movimentos.tsx` — o ecrã do artigo passa
a poder mostrar uma fornada. **Zero migrações e zero tabelas**: a tabela do ledger não existe, e é esse o
argumento de oportunidade. A valorização de qualquer agregado é **sempre pelo `unit_cost` gravado no
movimento** e nunca pelo CMP de hoje; um mês fechado que muda de valor quando a manteiga sobe é um número
que o dono já imprimiu a ser falsificado, e o append-only do ledger não serve de nada se a leitura for
reavaliada. **Consultar `domain-expert`, e levar à sessão 0:** se o `yield_factor` é por receita ou por
fornada; se um semi-acabado (massa folhada que alimenta três produtos) é um artigo com stock próprio ou
um passo dentro da receita — a resposta decide se há uma ou duas produções em cadeia; e se o café que só
revende tem de ver estes tipos (se não, a UI esconde-os, mas o enum existe).
