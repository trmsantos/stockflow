# ADR 0030 — Ligar as contagens: o contrato que as duas pontas já assumem, e onde elas divergem

**Contexto.** O ecrã `/contar` existe na forma final e é servido por `frontend/fixtures/contagem.ts`.
Atrás dele há tabelas (`StockCount`, `StockCountLine`, as duas com RLS), serviços (`abrir_contagem`,
`adicionar_linha_contagem`, `resumo_contagem`, `fechar_contagem`), cinco serializers e até uma porta
(`inventory/api.py`: `ContagemResumo`, `LinhaDeContagem`, `ContagemDetalhe`) — e **nenhuma rota**: o
`apps/inventory/urls.py` regista `locations`, `stock` e `stock/movements` e mais nada. Ligar não é expor
o que lá está: as duas pontas foram escritas com meses de intervalo e **descrevem recursos diferentes**.
O servidor acha que contar é escrever o que se vê (o `POST` leva `sku` e quantidade e cria uma linha nova
de cada vez); o cliente acha que contar é percorrer uma lista que já existe (o `POST` leva
`{product, quantity}`, sem zona, e a linha já tem `position`, `count_unit` e `expected`). Esta ADR
escolhe **uma** das duas e nomeia o que cada lado perde. As regras de domínio das ADR 0028 e 0029
mantêm-se e não se reabrem: só `open|closed`, o `expected` é instantâneo de quando a linha nasce, a
diferença é `contado − esperado`, o fecho gera `adjustment` com `reference = <id da contagem>` e
`occurred_at = now`, e euros só a `owner|manager`.

**Decisão 1 — O contrato é o do cliente; o do servidor morre inteiro, e as divergências são estas.**
Um `ContagemViewSet` em `router.register("stock/counts", …)` no `SimpleRouter(trailing_slash=False)` que
já lá está, com duas ações aninhadas (`lines`, `closing`). Seis rotas, todas sob `/api/v1`:

| rota | entrada | resposta | papéis |
|---|---|---|---|
| `GET stock/counts` | — | página de `Contagem`, `-started_at` | `owner manager staff` |
| `POST stock/counts` | `{location: UUID}` | 201 `Contagem` | `owner manager` |
| `GET stock/counts/{id}/lines` | `?zona=<slug>&page=` | página de `LinhaDeContagem` | `owner manager staff` |
| `POST stock/counts/{id}/lines` | `{product: UUID, quantity: Decimal}` | 200 `LinhaDeContagem` | `owner manager staff` |
| `GET stock/counts/{id}/closing` | — | `FechoDeContagem` | `owner manager` |
| `POST stock/counts/{id}/closing` | `{reason?: str ≤200}` | 200 `FechoDeContagem` (`closed`) | `owner manager` |

Quem abre e quem fecha é `owner manager`; **quem conta é toda a gente**, porque contar é o fluxo de campo
e o telemóvel é do `staff`. A assimetria não é de ecrã: contar não toca no ledger e fechar escreve `N`
movimentos irreversíveis, logo é decisão de autorização, imposta em `permission_classes` com
`TemPapel.exige(…)` e não por um botão escondido — e abrir entra do lado restrito não por escrever muito,
mas por **ocupar a única contagem aberta do estabelecimento** (d2). O `closing_role` que a `Contagem`
traz é o **rótulo** disso ("Dono ou gerente"), não a permissão. Como o `GET /lines` é de toda a gente e
traz `difference_eur`, o campo vai a **`null` para o `staff`** — é a regra dos euros já validada, e o
preço é que `null` passa a dizer duas coisas ("ainda não contado" e "não te é mostrado"); é o menor dos
males contra negar a lista a quem conta.

As divergências medidas, todas resolvidas a favor do cliente: `location_id`+`location_name` → `location:
{id, name}`; `line_count`/`lines_counted` → `total_lines`/`counted_lines`; `quantity_expected`/
`quantity_counted`/`variance` → `expected`/`counted`/`difference`; `product_id`+`product_name`+`sku` →
`product`+`short_name`; e as quantidades passam de `Decimal` solto a **`quantidadeSchema`**
(`{base, base_unit, display, display_unit}`), porque a conversão é do servidor (`inventory-domain` §2) e
sem o par o ecrã mostra `3400,000 g` a quem diz "3,4 kg" — e é barato, porque o `display_factor` já
atravessa a porta do módulo nos DTOs da 0028. O `sku` do corpo de entrada morre (e com ele a chamada a
`produto_por_sku`); o `unit` do `StockCountLineInSerializer` morre por ser pior que morto — hoje é aceite
e **silenciosamente ignorado** pelo serviço. O `can_close` morre (d5). Ficam sem fonte quatro campos que
o cliente pede: `counted_at` e `counted_by` (o docstring do modelo promete `counted_at`, a tabela não o
tem), `closing_reason` e `position` — os três primeiros são colunas novas, o `position` não é (d4). Do
lado do cliente **não muda um schema**: a fixture morre e o Zod fica. A porta do módulo não é tocada: os
seus DTOs servem o assistente, não o HTTP, e os nomes de lá (`n_linhas`, `n_por_contar`) não são nomes
de fio.

**Decisão 2 — Uma contagem aberta por estabelecimento, imposta por índice único parcial, 409 à segunda.**
O cliente trata "a contagem aberta" como `results.find(status === "open")` — com duas abertas a seleção
é arbitrária e o ecrã mostra uma à sorte. O servidor hoje não impede nenhuma: o `abrir_contagem` nem
sequer procura. Passa a haver `UniqueConstraint(fields=["tenant"], condition=Q(status="open"))`, e **no
índice e não num `filter().exists()`**: dois telemóveis a carregar em "começar" no mesmo instante veem
os dois zero abertas e inserem os dois. A segunda tentativa é **409** com `code="contagem_ja_aberta"` e o
`id` da aberta no corpo, para o ecrã levar lá quem tentou em vez de lhe dizer "erro". Por
estabelecimento e não por localização porque o `expected` é um instantâneo (ADR 0029): duas contagens
abertas sobre stock que se cruza congelam dois instantâneos que divergem, e ao fechar, a segunda aplica
diferenças contra um nível que a primeira já ajustou. Contar o Armazém, fechar, contar a Cozinha.

**Decisão 3 — Zonas: nesta fatia a zona *é* a localização, e há uma por contagem.** O `zonaSchema` do
cliente é um objeto (`slug`, `name`, `position`, `blind`) e a fixture inventa a lista *e* a atribuição
artigo→zona. **Nenhuma das duas tem fonte**: `StockCountLine.zone` é texto livre que ninguém preenche, o
catálogo não sabe onde na cozinha está um artigo, e declarar isso custa uma tabela, um ecrã de
configuração e uma atribuição por artigo e por localização. Em vez disso: `zones` traz **uma** entrada,
a localização contada (`slug` do nome, `position: 0`, `blind: false`), `current_zone` é ela enquanto
houver linhas por contar e `null` quando não houver, e o `?zona=` continua a filtrar por `slug` (um
`slug` desconhecido dá página vazia, estado que o ecrã já tem). "Contei a câmara fria toda" responde-se
**abrindo uma contagem da localização «Câmara fria»**: o `GET /locations` já devolve as localizações
ordenadas por `position`, e no seed elas já são o percurso (Armazém → Cozinha → Sala). O `blind: false`
é facto e não marcador de lugar — nenhuma zona é cega porque a contagem cega não existe; é sonda do
guião §3, fica fora de âmbito, e no dia em que o dono a escolher é um booleano e o `expected` deixa de
viajar. A coluna `zone` fica sem ser escrita, e é ela que a fatia das zonas substitui.

**Decisão 4 — As linhas nascem com a contagem, do `StockLevel` daquela localização.** `abrir_contagem`
materializa **uma linha por artigo** (não por lote) com nível não-zero naquela localização, com
`expected` = a soma dos seus lotes naquele instante. É o que o ecrã assume de ponta a ponta: o campo
seguinte é "a próxima linha por contar", a linha é identificada na mutação pelo `product`, e `total_lines`
existe antes de se contar o primeiro artigo. Contar é **percorrer uma lista**. O `POST /lines` passa a
ser um **upsert por `(contagem, artigo)`** — hoje cria uma linha nova a cada chamada, logo contar duas
vezes o mesmo artigo deixa duas linhas e duas diferenças — travado também na base com
`UniqueConstraint(tenant, stock_count, product, lot, nulls_distinct=False)`, o padrão do `Lot`. Um artigo
que **aparece e não estava na lista** entra pelo mesmo `POST`, com `expected` tirado nesse momento (zero,
se nunca entrou): o contrato aceita-o mesmo que o ecrã desta fatia ainda não tenha onde o procurar. O
`position` **não é coluna**: é o índice da linha na ordenação do servidor, que nesta fatia é a do
catálogo e não a do percurso — e isto é dívida nomeada, porque o guião diz "nunca alfabética" e o
percurso não existe enquanto as zonas não existirem.

**Decisão 5 — O fecho mostra tudo antes de escrever, e fechar com linhas por contar é possível.** O
`GET /closing` não escreve nada: `differences` são só as linhas contadas com diferença, a maior em euros
primeiro; `loss_eur` e `gain_eur` positivos os dois, `net_eur = gain − loss`; `reason_required_above_eur`
é uma constante do módulo (não há ecrã de configuração) e `reason_required` é `loss + gain` acima dela.
O `can_close` do serializer de hoje morre com a regra que o serviço impõe — **o `fechar_contagem` recusa
fechar se faltar uma linha**, e o guião §4 proíbe exactamente isso: fechar uma contagem imperfeita tem de
ser possível, senão quem conta inventa números para o botão acender. Uma linha nunca contada **não gera
movimento**: ausência de observação não é diferença de zero. O `POST /closing` escreve numa transação os
`adjustment` (um por linha contada com diferença, ao custo do nível, `reference` e `occurred_at` como na
0029) e `status`, `closed_at`, `closed_by` e `closing_reason`; devolve o mesmo corpo já `closed`. É
irreversível na base e não por convenção: `inventory_stockmovement` **já** está no `APPEND_ONLY` de
`tests/test_db_roles.py`, com `UPDATE` e `DELETE` revogados ao `stockflow_app` (ADR 0006) — a linha do
`CLAUDE.md` que diz que o conjunto está vazio está desactualizada e é um `/review` à parte. Não reabrir
também não é validação: **não existe rota que escreva `status`** a não ser o fecho, o `abrir_contagem` só
insere, e as duas escritas filtram `status="open"` — fechar duas vezes é 409.

**Decisão 6 — Telemóvel: o que muda no contrato são três coisas pequenas, e nenhuma é offline.** (a) A
página das linhas tem de **cobrir a contagem inteira** (`page_size` explícito, 200), porque o ecrã não
tem paginador e uma lista truncada é uma contagem errada que ninguém vê; acima disso o `?page=` existe e
o paginador passa a ser trabalho de frontend. (b) O `POST /lines` devolve **a linha** e não a lista: numa
rede de cozinha a resposta é o que se paga 40 vezes seguidas. (c) O upsert da d4 dá **idempotência de
graça** — repetir o mesmo `POST` depois de um timeout não conta duas vezes, que é o modo de falha real de
contar em pé com 3G. Offline, fila local, `POST` em lote: **nada nesta fatia** — uma fila offline é um
ledger do lado do cliente e uma regra de conflito, e isso é ADR própria.

**Impacto.** Zero tabelas novas. `inventory_stockcount`: `+closing_reason` e o índice único parcial da
d2. `inventory_stockcountline`: `+counted_at`, `+counted_by_name` (cópia do nome, como nos movimentos,
sobrevive à conta ser apagada) e a `UniqueConstraint` da d4. As duas já têm `tenant_id` e política RLS;
as colunas novas não mudam o predicado, e a migração não cria tabela nenhuma, logo não cria política
nenhuma. **Zero tarefas Celery, zero eventos novos** — o `record_movements` emite o que já emite. No
cliente: apagar `frontend/fixtures/contagem.ts` e as duas rotas `/api/v1/stock/counts` e
`/api/v1/stock/counts/` do `fixtures/servidor.ts`, `uv run manage.py spectacular` e `pnpm gen:api`. Os
schemas Zod ficam como estão.

**Respostas do dono (2026-10-19).** (1) **Uma contagem aberta de cada vez por estabelecimento**:
conta-se o Armazém, fecha-se, conta-se a Cozinha — quem chega sabe sempre qual é a que está a
decorrer, e a alternativa (uma por localização) pagava isso com um ecrã de várias em curso.
(2) **A zona é a localização**: "contei a câmara fria" é uma contagem da câmara fria, sem conceito
novo por cima das localizações que já organizam o stock. (3) **Quem conta vê o esperado**, por
agora: é mais rápido e tem menos erros de digitação, e é o que o ecrã já assume. O risco está
nomeado — quem vê o número tende a confirmá-lo em vez de contar —, e a **contagem cega** fica como
candidata a fatia própria, não esquecida.

**Fora de âmbito, por extenso.** Zonas como entidade (tabela, ordem do percurso, atribuição artigo→zona,
o ecrã que as declara) e com elas a coluna `zone`; contagem cega e o `blind: true`; contar por lote;
procurar no ecrã um artigo que não está na lista; offline, fila local e `POST` em lote; uma contagem
sobre várias localizações; reabrir, cancelar ou apagar uma contagem ou uma linha; exportação; limiar do
motivo configurável por tenant; o paginador do ecrã; e as outras quatro fixtures (`/stock/levels`,
`/stock/movements`, `/stock/alerts/summary`, `/stock/alerts/waste`), que são outra fatia.

**Alternativas.** *Servir o contrato do servidor e mudar o cliente* — o ecrã deixa de ter lista,
progresso e percurso, e o que se perde é o produto; o contrato do cliente é o que tem o domínio escrito
dentro. *Zona como texto que o contador escreve* — é o modelo de hoje, e com as linhas a nascerem com a
contagem não há ninguém para o escrever. *Uma aberta por localização* — contar várias ao mesmo tempo com
instantâneos que se cruzam, e o `find(open)` do cliente a escolher à sorte. *Manter o `can_close`* —
obriga a inventar números para o botão acender. *`PATCH` na linha em vez de `POST` na coleção* — quem
anda pela cozinha não tem o `id` da linha, só o artigo.

**Consequências.** Uma migração com três alterações pequenas. O `count_services.py` muda de forma: o
`abrir_contagem` passa a materializar linhas, o `adicionar_linha_contagem` passa a upsert por artigo, o
`resumo_contagem` ganha perda/ganho/líquido e perde o `can_close`, o `fechar_contagem` deixa de recusar
contagens incompletas. Cinco serializers reescritos. A `/contar` passa a mostrar números do ledger, e o
pico de `adjustment` no dia do fecho aparece no painel — correcto, e já decidido na 0029.

**Consultar `domain-expert` — sim, e antes do `backend`.** (a) `expected` de um artigo que **nunca
entrou**: zero (o ledger diz zero) ou ausência? A d4 assume zero. (b) A linha é por artigo e o custo da
diferença é por **lote** (ADR 0028) — com que custo se valoriza a diferença de um artigo com dois lotes
na mesma localização: média ponderada, lote FEFO, ou a linha tem de ser por lote? **Hoje o
`fechar_contagem` procura o nível com `lot_id = NULL` e, não o achando, valoriza a zero, em silêncio.**
(c) Contagem parcial: uma linha por contar não gera movimento (d5) — confirmar, e dizer se uma contagem
fechada com linhas por contar ainda conta como "contagem feita" para o `last_count_at` do painel.
(d) Um artigo que aparece e não estava na lista entra com `expected = 0` e gera um `adjustment` positivo
a que custo, se não há nível? (e) O limiar do motivo obrigatório: que valor, e incide sobre `loss + gain`
ou sobre o líquido? (f) Contar um artigo com lotes de validades diferentes numa linha só perde a
informação de qual lote faltou — é aceitável nesta fatia?
