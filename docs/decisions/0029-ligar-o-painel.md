# ADR 0029 — Ligar o painel: o que o servidor sabe mesmo, e a forma de dizer o resto

**Contexto.** O ecrã `/painel` existe, está escrito na forma final (ADR 0008 d3) e é servido por
`frontend/fixtures/painel.ts`. Atrás dele, o `apps/reporting` **não está ligado** — o `config/urls.py`
não o inclui, logo o `/reporting/summary` que o cliente chama não existe — e o que lá está é anterior ao
contrato: `revenue = Σ(production_in × unit_cost)` (produção não é receita, ADR 0013 d1), itera o ledger
em Python (a d5 proíbe), as três views só têm `IsAuthenticated` (a d6 exige `{owner}`), e o
`projection_report` importa `catalog.models` e `inventory.models` directamente, com duas entradas no
`ignore_imports` do import-linter a pagar por isso. A ADR 0013 é o contrato já decidido; esta fatia não o
reabre — **liga-o, e decide o que fazer com os dois terços que ainda não têm dados**: sem `sales` não há
receita, sem `people` não há salários, sem `purchasing_othercost` não há custos fixos.

**Decisão 1 — O que falta viaja como `null` e como lista nomeada; nunca como zero.** Um `"0.00"` num
campo de euros é um facto, e o painel desenha-o (uma barra a zero, um rácio a 0%). Por isso os campos sem
fonte passam a **anuláveis** e o `null` é a palavra "não sei": `revenue_net_eur`, `revenue_gross_eur`,
`revenue_basis` e, no `/month`, `payroll_eur`, `payroll_basis`, `payroll_source`, `cost_total_eur`,
`result_eur`, `labour_cost_ratio_pct` e `prime_cost_pct`; `payroll_breakdown`, `roles`, `other_costs` e
`result_excludes` vêm vazias (uma lista de exclusões de um número que não existe é ruído). E porque um
`null` campo a campo não diz *porquê*, o `DataQualityOut` ganha **`unavailable: list[str]`**, união
fechada `revenue|payroll|other_costs`, que é a d7 da 0013 a ganhar forma: o painel declara o que não
sabe, uma vez, em palavras que o `vocabulario.ts` traduz. O `revenue_source: "none"` fica — é mais fino
(`none|manual|pos`) e sobrevive ao dia em que a receita existir mas não estiver registada.
**É servido a sério, e é tudo do ledger ao custo gravado (ADR 0014):** `purchases_eur` (`receipt` +
`return`, líquido de devoluções), `goods_consumed_eur` (`consumption` + `waste`), `waste_eur` e o
`waste_by_reason`, `unknown_shrinkage_eur` (o líquido dos `adjustment`), `stock_change_eur`,
`stock_value_eur`, `purchases_awaiting_invoice_eur` (Σ dos `receipt` com `cost_is_estimate`) e
`last_count_at`. A identidade da d4 — `stock_change == purchases − goods_consumed − unknown_shrinkage` —
fecha ao cêntimo **porque os quatro termos são o mesmo agregado do mesmo ledger na mesma janela**, e é
teste e não frase. `goods_cost_ratio_pct` é `null` por falta de denominador, que é a razão certa.

**Decisão 2 — O `reporting` continua sumidouro, o `services.py` morre e nasce um `selectors.py`.** Sem
`api.py`, sem `models.py`, sem migração, sem política: a ausência é a decisão (0013 d3). O nome
`services.py` nesta casa significa *escrita*, e este módulo não escreve nada — passa a
`selectors.py` (leituras), `periodos.py` (a janela), `serializers.py` (só saída), `views.py`, `urls.py`.
**O `/reporting/projection` morre inteiro**: não está no contrato da d5, nenhum cliente o chama, e é ele
que carrega os dois `ignore_imports` — matá-lo apaga-os. Com ele morrem `movimentos_por_periodo` e
`movimentos_por_produto` da porta do `inventory`, que devolvem **instâncias ORM** através da fronteira;
medido, o `reporting/services.py` é o **único** consumidor das duas (o `agents` não as usa), logo saem
sem substituto nem período de graça. **Nascem no `inventory/api.py`, agregadas em SQL**:
`movimentos_agregados_por_tipo(tenant_id, desde, ate) -> (movement_type, n, quantidade, valor_eur,
valor_estimado_eur)`, um `GROUP BY`; `movimentos_agregados_por_dia_de_negocio(…, inicio_do_dia)`, o mesmo
com o balde; `desperdicio_agregado_por_motivo(…)`, cinco linhas sem truncatura (o `desperdicio_recente`
corta a 30 e um total truncado é um total errado); `valor_de_stock(tenant_id)`; e
`ultima_contagem_fechada_em(tenant_id)`. Nenhum ciclo em Python sobre o ledger em sítio nenhum. Nesta
fatia o `reporting` importa **`accounts.api`** (o `definicoes_do_ambito`, que já traz o
`business_day_starts_at` e o `vat_regime` num DTO só) e **`inventory.api`** — dois módulos, que é o que a
regra de admissão da d3 exige; a aresta para o `purchasing.api` chega com o `purchasing_othercost`. As
compras vêm do ledger e não do `compras_confirmadas` de propósito: é a d4 a dizer "ao custo gravado no
movimento", e um total de facturas ao lado de um termo de ledger seriam dois números para "quanto
comprei" — o primeiro bug reportado.

**Decisão 3 — Rotas e permissões, que é onde isto hoje está errado.** `config/urls.py` ganha
`path("", include("apps.reporting.urls"))` e o `urls.py` do módulo passa a trazer o prefixo
(`reporting/summary`, `reporting/series`, `reporting/month`), como os vizinhos. As **três** views levam
`[PertenceAoTenant, TemPapel.exige(Papel.OWNER)]` — não só o `/month`: o painel inteiro é do dono desde
que saiu do Início, o `menu.py` já declara `painel = {owner}` e o cliente já não dispara os pedidos. A
recusa é **403 com o `detail` do DRF e sem `code` novo** (d6), e vale para o deep link e para a pertença
revogada com a página aberta. Entra o contrato de import-linter que a 0013 prometeu e nunca existiu —
`forbidden`, os outros módulos como `source_modules`, `apps.reporting` proibido: hoje só o contrato do
`agents` o proíbe, e uma propriedade garantida por um contrato parcial não está garantida.

**Decisão 4 — `Σ(dias de negócio) == mês` por construção e não por cuidado.** Uma função só,
`periodos.py`, resolve `period` e `month` a partir do `business_day_starts_at` do `accounts`, e devolve o
par `[desde, ate)` que as três respostas ecoam. O balde diário é `date_trunc('day', occurred_at −
<hora>)` no mesmo SQL que o agregado do total: o deslocamento é um só, logo a soma dos baldes **é** o
total, não se aproxima dele. O teste compara `Σ(points)` com `total_eur` na mesma resposta e
`/summary?period=month` com `/month?month=` no mesmo mês. É o invariante da d8, e é ele que impede o
gráfico cujas barras não somam o número ao lado.

**Decisão 5 — No cliente morre a fixture e nascem três `null`.** `frontend/fixtures/painel.ts` e a sua
rota no `frontend/fixtures/servidor.ts` saem (incluindo a variante `?_fixture=restrito`: o 403 passa a
ser real). O `features/reporting/schemas.ts` ganha `.nullable()` nos campos da decisão 1 e `unavailable`
no `qualidadeDosDadosSchema`; o `vocabulario.ts` ganha as três palavras. **Onde o valor é `null` o ecrã
escreve uma frase, nunca um traço**: "Vendas — ainda não registadas neste StockFlow", com o rácio de
mercadoria a dizer que espera por elas. O gráfico fica com **uma** série (`purchases`): a união
`idDeSerieSchema` não muda, e a legenda diz porque é que a segunda não está lá. A lista das perguntas da
manhã continua a ser o último bloco, que é o que serve num dia em que isto não carregue.

**Decisão 6 — O assistente continua sem `resumo_do_mes`, e isso é a decisão e não a omissão.** Dar-lhe
o painel só tem três formas e as três são piores: um `api.py` no `reporting` revoga a d3 (a única
propriedade que ela comprou é não ser dependência de ninguém); o `agents` a compor os mesmos agregados
põe a mesma aritmética de euros em dois sítios, que é o que a d3 recusou; e chamar o próprio HTTP não se
discute. O que muda é a frase: o assistente já tem `compras_confirmadas`, `desperdicio_recente` e
`resumo_de_alertas`, logo em vez de "ainda não tenho o painel do mês" responde com o que **sabe** e
aponta o `/painel`. Reabre-se no dia em que ele precisar da *identidade* (a subtracção de três termos) —
e nesse dia é ADR própria, a revogar a d3 com argumento.

**Fora de âmbito, por extenso:** os módulos `sales` e `people` e tudo o que deles depende (receita,
salários, `result_eur`, `cost_total_eur`, `prime_cost_pct`); o `purchasing_othercost` e a sua lista
fechada de categorias; o `/reporting/projection` e qualquer projecção ou previsão; comparação com o
período anterior; exportação CSV/PDF; e — sem sinal da secção 7 do `ARCHITECTURE.md` — qualquer agregado
materializado, tarefa Celery, chave de Redis ou evento de outbox. O gatilho medido da d5 mantém-se: p95
acima da banda da ADR 0005 sobre doze meses de ledger.

**Alternativas.** *Servir zeros com `revenue_source: "none"` ao lado* — é o painel optimista que a d7
nomeia; o zero desenha-se e o rótulo não. *Omitir os campos do payload* — quebra o tipo gerado e troca
"não sei" por "não existe", que são coisas diferentes e o cliente não as distingue. *Não servir o
`/month` nesta fatia* — o grão mensal da mercadoria é real hoje e é metade do valor do ecrã. *Manter o
`services.py` e corrigi-lo* — o nome mente sobre a escrita e o ficheiro inteiro é anterior ao contrato.
*Manter `movimentos_por_periodo` por compatibilidade* — não tem outro consumidor, e uma instância ORM
através da porta é a fronteira a existir só no papel. *Compras pelas facturas* — dois números para a
mesma pergunta e a identidade da d4 a não fechar.

**Consequências.** **Zero tabelas novas, zero alteradas, zero migrações, zero políticas RLS** — e o
`reporting` continua coberto pela RLS sem possuir nenhuma, porque toda a query nasce dentro do âmbito do
pedido. Nenhuma tarefa Celery, nenhum evento. Cinco leituras novas na porta do `inventory` e duas
removidas; dois `ignore_imports` apagados; um contrato de import-linter novo. No cliente:
`schemas.ts` com os anuláveis, `vocabulario.ts` com as palavras, o ecrã com as frases, a fixture apagada,
`uv run manage.py spectacular` e `pnpm gen:api`.

**Consultar `domain-expert` — obrigatório, e antes do `backend`.** (a) A identidade fecha mesmo ao
cêntimo com `unit_cost` a seis casas e apresentação a duas — arredonda-se por termo ou no fim? (b) O
`unit_cost` gravado num `receipt` já é **líquido de IVA**, e em `isento_art_53` (onde o IVA suportado *é*
custo) quem corrige: o custo gravado ou o painel? Se for o painel, a correcção não pode viver no
`reporting`. (c) `last_count_at` é a última contagem **fechada** (a que gerou ajustes) ou a última
iniciada, e conta por localização? Um mês sem contar dá `unknown_shrinkage == 0`, que é o modo de falha
que a d7 nomeia. (d) `goods_consumed_eur` é `consumption + waste` e **não** `production_out` — confirmar
contra a tabela de nove linhas da ADR 0014, sob pena de contar a produção própria duas vezes; e o
`prep_loss` é desperdício ou custo normal de produção? (e) O sinal de `unknown_shrinkage_eur`: o cliente
lê "positivo = quebra", o ledger grava `adjustment` negativo para falta — a inversão tem de ser decidida
num sítio só. (f) Uma nota de crédito **de preço** (sem devolução de mercadoria) não move stock e
portanto não entra em `purchases_eur`: é aceitável, ou é um erro visível no mês?
