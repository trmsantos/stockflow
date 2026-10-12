# ADR 0023 — Ledger de stock: quatro tabelas e como escrevem

**Contexto.** A ADR 0021 definiu a fatia 3 como a que traz o ledger de stock (quatro tabelas: `Lot`, `StockMovement`, `StockLevel`, `ProductCost`) e adiou todas as decisões de implementação para esta ADR. A fatia 2 (ADR 0022) fechou a receção sem tocar em stock — a confirmação só tranca a receção e deixa `movement_id` NULL. A fatia 3 preenche esse `movement_id` e escreve os quatro movimentos ligados (um `Lot` por guia+artigo+lote, um `StockMovement` por linha confirmada, um valor agregado em `StockLevel` por (artigo, localização, lote), e o `ProductCost` actualizado como média ponderada). O contrato das receções já existe (ADR 0022, decisão 1–6); o que falta é a forma do ledger, a semântica de cada movimento, e a resposta ao bloqueador Q8.

**Decisão 1 — Quatro tabelas, relação e responsabilidade de cada uma.** Todas herdam `TenantModel` e levam `ENABLE ROW LEVEL SECURITY FORCE` com política `NULLIF(current_setting('app.tenant_id', true), '')::uuid` na mesma migração (CLAUDE.md, ARCHITECTURE.md §4, ADR 0006).

1. **`inventory_lot`**: representa um lote de mercadoria, identificado pelo triplo `(product, code)` único por tenant. Campos:
   - `product` FK string a `catalog_product` · `code` char(150) — o lote impresso na embalagem ou gerado (se `track_lots=False`, um lote sintético)
   - `expires_at` DateTime null — a data do rótulo, lida durante receção; anulável porque artigos sem validade existem (sal, azeite, bebidas alcoólicas)
   - `received_at` DateTime — marca o primeiro movimento que o criou, immutável
   - `unique (tenant_id, product_id, code)` · sem `expiry_kind` (é do artigo, não do lote)

2. **`inventory_stockmovement`**: é o ledger, append-only. Cada linha registra uma mudança de quantidade e valor. Campos:
   - `movement_type` — um dos nove tipos (ADR 0014): `receipt, return, consumption, waste, adjustment, transfer_out, transfer_in, production_out, production_in`
   - `quantity` Decimal(12,3) **com sinal** — positivo para entrada, negativo para saída. O tipo determina o sinal esperado; `adjustment` é o único onde pode variar
   - `unit_cost` Decimal(12,6) — a avaliação de cada unidade da mercadoria movida, em euros, append-only (não pode ser NULL nem atualizado). Precisão: seis casas (correcção ADR 0021 Adenda: 4 casas davam erro de ~0,75€ em 25kg)
   - `cost_is_estimate` Boolean — se o custo é estimado (A, na guia sem fatura) ou confirmado (B, com fatura). Falso por omissão
   - `reason` CharField null — justificação livre para `waste`, `adjustment` (quebra)
   - `reference` CharField(255) null — a chave de deduplicação, importada do documento de origem (`doc_number_normalized`, ou o uuid da produção, ou o id da contagem)
   - `production_id` UUIDField null — referência opaca da produção; `production_out` e `production_in` da mesma fornada partilham este id
   - `occurred_at` DateTime — quando o movimento aconteceu (receção: a data física de entrada; produção: a hora do botão)
   - `created_by` FK User SET_NULL · `created_by_name` char(150) — quem criou o movimento (idempotência do tratamento)
   - Índice: `(tenant_id, reference)` parcial onde `reference IS NOT NULL` — deduplicação rápida
   - **Append-only na base de dados**: `REVOKE UPDATE, DELETE ON inventory_stockmovement FROM stockflow_app` na mesma migração
   - Restrição: `CHECK(quantity != 0)` — nunca há movimento de quantidade zero

3. **`inventory_stocklevel`**: é a projeção (read model) do estado, atualizado a cada movimento. Unica por tenant — `(product_id, location_id, lot_id)` com `nulls_distinct=False` (sem isso um artigo sem lote gera uma linha por cada `lot_id` NULL). Campos:
   - `product` FK string · `location` FK string · `lot` FK string null — chave composta
   - `quantity` Decimal(12,3) — a soma dos movimentos até agora
   - `unit_cost` Decimal(12,6) — custo unitário médio ponderado (FEFO: o mais antigo, não a média). Precisão: seis casas como `StockMovement`
   - Sem `updated_at` diferente de `created_at` — atualização é sempre local (a mesma transação que o movimento)

4. **`inventory_productcost`**: único por tenant, artigo e localização. Campos:
   - `product` FK string · `location` FK string · `unit_cost` Decimal(12,6) — a média ponderada de todos os movimentos de entrada de um artigo **por localização** (somando `quantity` positiva × `unit_cost`, dividindo por `Σ quantity` positiva). Rationale: um tenant pode ser rede de N filiais com preços diferentes por fornecedor e localização
   - Sem `quantity`: lê-se do `SUM(quantity)` do `StockLevel` da mesma transação

Relação: um `StockMovement` cria ou atualiza zero ou um `Lot` (só `receipt` e `return`; `consumption` lê de lote existente e não cria). Um `StockMovement` **sempre** atualiza um `StockLevel` (insert or update). Confirmação de uma receção é **uma transação**: cria os lotes, escreve todos os movimentos, atualiza todos os níveis, escreve o `ProductCost`.

**Decisão 2 — O que cada tipo de movimento significa e quando entra no ledger.** A tabela da ADR 0014 já existe; o que esta ADR precisa é de *quem o escreve* e *quando*.

| Tipo | Quem escreve | Quando | Entra em "valor de stock" |
|---|---|---|---|
| `receipt` | `purchasing.confirm_receipt` | confirmação da receção | sim |
| `return` | `purchasing.confirm_receipt` | confirmação de nota de crédito | sim, a reduzir |
| `consumption` | `recipes.consume` | venda ou produção | não (custo de vendas, não stock) |
| `waste` | manual, endpoint `POST /stock/movements` | quando se descobrir perda | não (quebra conhecida) |
| `adjustment` | manual, endpoint `POST /stock/movements` | contagem fechada ou correção manual | não (quebra desconhecida) |
| `transfer_out` | manual, endpoint `POST /stock/movements` | pedido de transferência | não (dentro do tenant) |
| `transfer_in` | manual, endpoint `POST /stock/movements` | receção da transferência | não (dentro do tenant) |
| `production_out` | `recipes.produce` | produção de receita | não (é o custo de COGS) |
| `production_in` | `recipes.produce` | produção de receita | sim, ao custo dos `production_out` |

Conseqüência: esta fatia escreve dois tipos (`receipt`, `return`); os outros entram nas fatias de produção, contagem, transferência e gestão manual.

**Decisão 3 — O custo unitário de cada movimento.** Nunca é nulo; append-only garante que toda a história fica congelada.

- **`receipt` e `return`**: `unit_cost = line_total_eur / quantity_received` (a linha já vem com desconto e IVA excluído, ADR 0022 adenda)
- **`production_in`**: `unit_cost = Σ production_out.quantity × production_out.unit_cost / qty_produced` (a soma dos custos das pernas de saída dividida pela quantidade produzida; o `yield_factor` entra aqui)
- **`consumption`, `waste`, `adjustment`, `transfer_*`**: lê o `unit_cost` do lote que sai (FEFO: lê o mais antigo)
- **Precisão**: `Decimal(12,6)` — seis casas (correcção ADR 0021 Adenda: quatro casas dão erro). Exemplo: `25kg a 17,33€ = 0,0006932€/g`. A quatro casas arredonda para `0,0007` (erro ~0,75€); a seis casas é `0,006930` (exacto). O `ProductCost` redondo (`unit_cost` do `StockLevel`) reusa a mesma escala

Nota: O `cost_is_estimate` é verdadeiro quando o custo vem de um preço anterior (opção A do Q8), falso quando é confirmado (opção B: entrar a zero e corrigir depois, ou opção A com preço estimado).

**Decisão 4 — RLS e append-only.** 

- **RLS**: `ENABLE ROW LEVEL SECURITY FORCE` com política `(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)` na mesma migração que cria `inventory_stockmovement`
- **Append-only**: `REVOKE UPDATE, DELETE ON inventory_stockmovement FROM stockflow_app` na mesma migração. Uma vez escrito, o movimento **nunca** se altera nem se apaga; a correcção é com outro movimento (regra: dois movimentos não se anulam, cada um fica e reflete o que aconteceu)
- **Integridade**: FK `product` e `lot` com `ON_DELETE=RESTRICT` (artigo com histórico não se apaga); FK `location` com `ON_DELETE=RESTRICT` (localização com movimentos não se apaga)

**Decisão 5 — Bloqueador explícito Q8.** Este ADR **não pode ser implementada enquanto Q8 não tiver resposta do dono.** A pergunta:

> **"A guia de remessa entra sem preço. Quanto vale essa mercadoria no dia em que entra?"**

Duas opções já medidas (ADR 0021, bloqueador 8):

- **Opção A — Custo estimado**: entrar ao último preço conhecido (a coluna `ProductCost.unit_cost` ou zero se for artigo novo) com `cost_is_estimate=True`. Problema: se ninguém comprou nunca, entra a zero. Painel de Stock fica com entradas "a confirmar preço", visível num badge.
- **Opção B — Zero até haver fatura**: entrar com `unit_cost=0` e `cost_is_estimate=False`. Problema: o cálculo da média ponderada fica cego até à fatura chegar. Painel de Stock mostra "preço desconhecido". Quem chega à fatura cria um `adjustment` que revalida tudo.

**Sem resposta, o contrato não muda e a tabela `inventory_stockmovement` fica como código comentado.** A migração pausa aqui.

**Decisão 6 — Contrato de `POST /receipts/<id>/confirmation`.** O endpoint **não muda entre fatia 2 e fatia 3**; o que muda é o que acontece dentro.

*Entrada (fatia 2 e 3 igual):*
- Path: `POST /receipts/<id>/confirmation`
- Corpo: vazio
- Permissão: `IsAuthenticated` + `PertenceAoTenant` (qualquer membro ativo)

*Saída (fatia 2):*
- Status: `201` primeira confirmação, `200` repetição (idempotência observável)
- Corpo: `ReceiptOut` (todas as linhas com `status`, `movement_id` NULL)

*Saída (fatia 3):*
- Status: `201` / `200` igual
- Corpo: `ReceiptOut` igual (todas as linhas com `status`, **`movement_id` preenchido** para linhas confirmadas)
- Eventos: novo evento `StockReceived(tenant_id, receipt_id, lines: [{product_id, quantity, unit_cost}])`

*Invariantes de execução (transação atómica):*
1. Lê a receção; se confirmada, devolve o estado antigo (idempotência, código 200)
2. Valida que existe pelo menos uma linha com `status=confirmed` (senão 409 `sem_linhas_revistas`)
3. **Cria os lotes** (uma chamada em lote a `inventory.api.get_or_create_lots(tenant_id, [(product_id, code, expires_at, received_at)])`)
4. **Escreve os movimentos** (uma chamada em lote a `inventory.api.record_movements(tenant_id, [movement_dto])`)
5. **Atualiza os níveis** (a mesma chamada do passo 4 atualiza `StockLevel` + `ProductCost` na mesma transação)
6. Preenche `movement_id` nas linhas de receção (UPDATE em banda na mesma transação)
7. Escreve `confirmed_at`, `confirmed_by`, passa `needs_review → confirmed` ou `skipped`
8. Enfileira `StockReceived` na outbox

Chaves de cada movimento:
- `product_id`, `location_id`, `lot_id` (ou `lot_id=NULL` se `track_lots=False`)
- `quantity` (sempre positivo nesta fatia; sinal é do tipo)
- `unit_cost` (do cálculo da decisão 3)
- `cost_is_estimate` (segundo bloqueador Q8)
- `movement_type` (`receipt` para documento normal, `return` para nota de crédito)
- `reference` (do `doc_number_normalized` da receção)
- `occurred_at` (do `received_at` da receção)
- `created_by`, `created_by_name` (do utilizador a confirmar)

**Decisão 7 — Casos limite.** 

1. **Receção parcial**: cinco rolos faturados, três confirmados na revisão. Um `StockMovement` com `quantity=+3` (confirmado, o que entrou). A quantidade 2 fica `skipped` (não foi confirmada na revisão, sem movimento). Se houver nota de crédito de dois rolos depois, um novo `return` com `quantity=-2`. O painel mostra três rolos (o que entrou) e o contabilista vê a fatura com cinco linhas (o que se deveu): são dois números diferentes porque são duas verdades diferentes.

2. **Lote obrigatório se `track_lots=True`**: a revisão **impede** confirmar uma linha sem `lot_code` preenchido. O campo torna-se vermelho com a pergunta "este artigo precisa de um lote, qual é?". O backend valida (409 se uma linha `confirmed` de artigo com `track_lots=True` tiver `lot_id` NULL), mas a validação no frontend é a defesa de primeira linha.

3. **FEFO (First Expired, First Out)**: a leitura de um movimento de `consumption` ou `waste` escolhe o lote mais antigo (`expires_at` primeiro, depois `received_at`). A ordem é imposta pelo `recipes` e pelo endpoint manual de `waste`, não pelo ledger; o `StockLevel` guarda o custo FIFO de quem entrou primeiro, nunca a média.

4. **Validade obrigatória se `track_lots=True` E `expiry_kind IS NOT NULL`**: a revisão marca o campo com asterisco vermelho e o backend valida — 409 se a linha ficar confirmada sem `expires_at`.

5. **Lote sintético para artigos sem rastreio**: se `track_lots=False`, o movimento cria um lote com `code='__<product_id>__'` (sintético, nunca impresso), `expires_at=NULL`. Todos os movimentos de saída deste artigo leem deste lote. Não há FEFO sem rastreio.

6. **Nota de crédito que não devolve tudo**: uma fatura de cinco sacos de farinha, uma nota de crédito de três. O `return` escreve `quantity=-3`, reduzindo o stock e as compras. Se houver nota de crédito de dois sacos depois (do mesmo lote ou de outro), é um segundo `return` com `quantity=-2`, mesma receção ou não — são duas correções, duas linhas, dois `references` distintos.

**Alternativas.** *`inventory_stockmovement` sem `quantity` com sinal* — força um `CASE` por tipo em toda a leitura (`SUM(CASE WHEN type=... THEN quantity ELSE -quantity END)`), menos eficiente e menos legível. *Custo de `production_in` como zero até haver consumo* — perde o valor de stock e torna impossível o painel de valor de remanescente. *Três tabelas de movimento em vez de uma (entrada, saída, ajuste)* — duplica o schema e obriga cada agregação a unir as três; um único tipo em um único lugar é o mecanismo que impede esquecimento. *Lote obrigatório mesmo para artigos sem rastreio* — torna a entrada de artigo genérico (água, sal) um extra de cliques; o lote sintético resolve sem UI. *`StockLevel` sem `lot_id`* — impossibilita FEFO e torna todos os artigos indiferenciáveis mesmo após separados por data.

**Consequências.** Quatro tabelas novas com `tenant_id` e RLS, nenhuma delas com contrato novo no `import-linter` (as arestas já existem: `purchasing → inventory.api`, `recipes → inventory.api`, `inventory` não importa módulos); uma tabela `append-only` (primeira da história); um evento novo (`StockReceived`, consumido depois quando o painel entrar); uma função síncrona por módulo (`inventory.api.get_or_create_lots`, `inventory.api.record_movements`, `purchasing.confirm_receipt` modificada); e um bloqueador que pausa a migração.

O apagamento de `fixtures/stock.ts` e `fixtures/rececoes.ts` fica nomeado como consequência: o Stock real cresce quando se confirma uma receção, e as fixtures deixam de ser verdade. O `apps/demo` semeia receções confirmadas via `purchasing.api` e `inventory.api`, arestas de saída conforme ADR 0018.

**Consultar `domain-expert`** antes da implementação: se `unit_cost` deve ser o preço da linha ou o preço com portes rateados (respondida na adenda ADR 0021: é o preço da linha); se o CMP é por artigo ou por (artigo, localização) — **respondida aqui: por (artigo, localização)** porque um tenant pode ser rede de N filiais com preços diferentes; se a dimensão da unidade base é fixa (`KG→g ×1000`) ou lida por fornecedor (respondida ADR 0022 adenda: é fixa, tabela fechada).

**Bloqueadores resolvidos:**
- Q8: "Guia sem preço — custo estimado (A) ou zero (B)?" → ✅ **Opção B** (custo zero com ajuste depois)
- CMP por artigo ou (artigo, localização)? → ✅ **Por (artigo, localização)** (um tenant pode ser rede de N filiais com preços diferentes)
- Default de `track_lots`? → ✅ **False** (utilizador marca True para perecíveis; mais seguro)
