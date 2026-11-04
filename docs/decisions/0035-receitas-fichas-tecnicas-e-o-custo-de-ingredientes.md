# ADR 0035 — Receitas: a ficha técnica primeiro, produzir depois, e o custo de ingredientes pelo meio

**Contexto.** O `recipes` é o único módulo de domínio com o servidor pago e a porta fechada: `Recipe` e
`RecipeLineItem` existem com RLS, o `produzir()` está escrito e testado (ADR 0026), o `api.py` lê a ficha e os
custos desde a ADR 0028 — e **não existem `views.py` nem `urls.py`**, `apps.recipes.urls` não está no
`config/urls.py`, e não há rota `/receitas` na árvore do cliente. A ADR 0026 d3 escreveu por extenso *"Contrato
internamente, não há endpoint (…) um endpoint POST futuro `/recipes/<id>/produce` (fatia 7 ou posterior)"*.
**Esta é essa fatia**, e o objectivo que o dono escreveu é mais curto do que ela: **ver o custo do prato.**
**Toca em stock, validades, unidades, receitas e custos: consultar `domain-expert`** — e foi consultado a
2026-11-02, antes do `backend`. As sete perguntas estão respondidas no fim desta ADR; duas mudaram o contrato e
o dono decidiu-as: **a ficha é por fornada** (d8) e **o rótulo é "custo de ingredientes"** (d9).

**Decisão 1 — São duas fatias, e a primeira é a ficha técnica. O `produzir()`, que já está escrito, fica para
a segunda.** O corte não é de tamanho, é de dados: **não existe uma única receita em lado nenhum**. O
`apps/demo` não semeia o `recipes` (`semear_demonstracao.py` não lhe toca), não há porta para criar uma, e a
tabela está vazia em todos os ambientes — logo o `produzir()` **não é chamável** e as tools de receitas do
assistente (ADR 0028) respondem hoje sobre uma tabela vazia. Uma rota de produção ligada primeiro servia 404
em todos os tenants no dia em que fosse para produção. A ordem é a dos factos: **primeiro escreve-se a ficha,
depois produz-se a partir dela.**

- **Fatia A (esta):** `GET`/`POST /recipes`, `GET`/`PATCH /recipes/<id>`, o `batch_size` (d8), a escada do
  custo (d10), o ecrã `/receitas` (lista + ficha + formulário) e o **custo de ingredientes teórico**. É a coisa
  mais pequena que responde à pergunta do dono.
- **Fatia B (a seguir):** `POST /recipes/<id>/production`, a lista de produções, o **custo real**, a validade
  do acabado (d12), o **esperado vs obtido** de uma produção (d8) e a reparação dos defeitos que a d13 nomeia.

**Decisão 2 — O custo é calculado na leitura, e isso é a resposta à pergunta do dono; o custo real vem com a
produção.** São duas perguntas e duas respostas, e a ADR 0028 já lhes deu os dois nomes (`CustoDaReceita`):

| pergunta | número | onde vive | fatia |
|---|---|---|---|
| *"quanto me custa de ingredientes um pastel de nata?"* | **teórico** — Σ(consumo real × custo do ingrediente **hoje**) | derivado na leitura, de `inventory` | **A** |
| *"quanto custou o lote de 100 de ontem?"* | **real** — o `unit_cost` do `production_in`, gravado no momento | ledger, escrito pelo `produzir()` | **B** |

O teórico é o que o dono pediu e é o único que existe no dia 1. **O `actual` e o `actual_at` não entram no
contrato HTTP desta fatia**: sem produções, seriam `null` em 100 % das linhas, e uma coluna de "—" no dia do
lançamento ensina o dono que a coluna está partida. Nunca se recalcula o passado com os preços de hoje
(ADR 0014): os dois números coexistem, não se substituem.

**Decisão 3 — O custo teórico é **um** número, do **estabelecimento**, e isto revoga a forma por localização
do `recipes/api.py` (ADR 0028).** O `_custos()` de hoje devolve **uma linha por localização** e calcula cada
uma com `por_artigo.get(product_id, 0)` — um ingrediente sem CMP naquela localização é **saltado em silêncio**
e a linha sai `incompleto: true`. Numa pastelaria com Armazém e Cozinha a farinha está num e o creme no outro:
**todas** as linhas saem incompletas e **todas** subestimam. Dois números errados lado a lado são piores do
que um certo. Além disso o cálculo é N+1 por desenho (uma chamada a `custos_medios_por_artigo` por
ingrediente), e numa lista de receitas isso multiplica. Passa a haver **uma** definição: o custo de um
ingrediente é o **mesmo `unit_cost` que o ecrã de Stock mostra**, pela mesma função — `unit_cost = total_value
÷ (quantity − quantity_without_cost)` (ADR 0032, segunda adenda), do estabelecimento inteiro. O dono que
compara a ficha com o `/stock` vê o mesmo número, que é a propriedade que a 0034 d12 comprou para o detalhe do
artigo e pela mesma razão: *não nasce aqui uma segunda definição de custo*. **E a forma por localização não
volta pela porta das traseiras**: nenhum degrau da escada da d10 — nem o custo de recurso de um semi-acabado —
pode ler o `inventory_productcost`, que é por loja e reinstalava em silêncio o que esta decisão revogou.

**Decisão 4 — A ficha é um documento e não uma colecção: as linhas viajam dentro do corpo, por substituição
total.** A contagem e a receção têm sub-recurso de linhas (`POST /…/lines`) porque são **percursos** — uma
folha que se anda com o telemóvel na mão, um papel que se confere linha a linha contra uma palete. Uma ficha
técnica escreve-se de uma vez, num formulário com **um** botão de gravar: oito `POST` para oito ingredientes é
uma receita meio gravada, e uma receita meio gravada é um custo errado que ninguém vê. O `unique_together
(recipe, ingredient_product)` que a tabela já tem torna a substituição naturalmente idempotente. No `PATCH`, o
campo `lines` **ausente** não toca nas linhas e `lines` **presente** substitui-as todas — e está escrito aqui
porque é a única parte do contrato que não se adivinha.

**Decisão 5 — Os papéis são assimétricos, como nas contagens, e a assimetria é ao contrário.** **Ler a ficha é
dos três papéis** — decisão do dono a 2026-10-16 (ADR 0028, resposta 2: *"o `staff` vê só a ficha técnica; o
custo por dose é `owner|manager`"*), e quem está na cozinha precisa das quantidades para produzir. **Escrever
a ficha é `owner|manager`**: a ficha é a definição do produto e do seu custo, mudar uma quantidade muda o custo
de tudo o que dali sair, e isso não é trabalho de campo. **Na fatia B, produzir é dos três** — é o turno das
6h, é a lição da ADR 0033 d2 (abrir a contagem era restrito e bloqueava quem conta de madrugada), e o
precedente está fechado: o `waste`, o `adjustment` e o `transfer` escrevem no ledger e são todos do `staff`
(ADR 0032 d3). Logo a assimetria do `recipes` é o **espelho** da das contagens: ali o campo abre e o gabinete
fecha; aqui o gabinete escreve a ficha e o campo produz a partir dela.

**Decisão 6 — Os euros saem por papel, com a chave **ausente**, e a mecânica é a da casa sem uma linha nova.**
Três sítios, os mesmos de sempre: a **política** em `accounts/api.py` (`PAPEIS_QUE_VEEM_EUROS` → `ve_euros` →
`SemEurosParaQuemNaoVe.to_representation`); a **lista de campos** no `CAMPOS_DE_DINHEIRO` de cada serializer de
saída; o **contexto** no `get_serializer_context()` do `ReceitaViewSet`, cujo default é **falso** — esquecê-lo
esconde dinheiro a toda a gente, que é a direcção certa para falhar. **A `ReceitaDetalheOut` herda da
`ReceitaResumoOut` e NÃO redeclara o `CAMPOS_DE_DINHEIRO`** (ADR 0034 d15): redeclará-lo é literalmente a porta
irmã por onde o dinheiro sai, e esta casa já lá caiu duas vezes. Nunca `0` (afirmação falsa sobre o preço) —
`null` aqui é legítimo e quer dizer uma coisa só: *não há número nenhum* (d10, degrau 5), e é o que o ecrã
imprime como "—". **E saem todos juntos**, pela regra da reconstrução por aritmética (ADR 0032 d2):
`line_cost ÷ quantity_real` devolve o `unit_cost` do ingrediente, `Σ(line_cost)` devolve o `batch_cost` e
`batch_cost ÷ batch_size` devolve o `unit_cost` da receita — as quatro pontas da divisão (`quantity`,
`quantity_real`, `yield_factor`, `batch_size`) estão no payload de quem não vê euros e continuam a estar,
porque **as quantidades são o produto**. O que fica para os três papéis: as quantidades, a fornada, o
rendimento, o `cost_status` **por linha e no agregado** (as mesmas três palavras da casa,
`conhecido|estimado|desconhecido` — um quarto vocabulário aqui recriava a divergência que a 0032 fechou) e a
**cobertura** no agregado (`ingredients_without_cost`), que é contagem e não euro. A cobertura aqui é mais
fraca do que a `quantity_without_cost` da 0032 — um ingrediente em dez pode ser 90 % do custo — e **não há
forma melhor sem euros**: está dito, e é por isso que o `cost_status` por linha existe ao lado.

**Decisão 7 — O contrato publica `request=` e `responses=` em todas as operações, desde a primeira.** Ontem
fecharam-se três defeitos da mesma família no mesmo ficheiro (ADR 0034 d18 e d19) e ficaram **cinco respostas
erradas** nomeadas como dívida, todas com uma causa: sem `request=`/`responses=`, o `drf-spectacular` cai no
`get_serializer_class()` e publica a resposta da classe como se fosse o pedido. Um ViewSet novo não tem desculpa
para nascer assim. E `http_method_names = ["get", "post", "patch", "head", "options"]` **na classe**: sem
`PUT` (é a 0034 d18 a repetir-se — um método publicado sem quem o sirva) e **sem `DELETE`**, porque uma receita
não se apaga, arquiva-se com `PATCH {is_active: false}` — foi a ficha técnica de mercadoria que entrou no
ledger, e o precedente do artigo arquivado que responde 200 é o da 0034 d13.

**Decisão 8 — A ficha é por **fornada**, e as linhas são por fornada.** Decisão do dono a 2026-11-02, depois
da Q1. `Recipe.batch_size`, `Decimal(12,3) > 0`, na unidade **base** do acabado e servido **também em
apresentação** — senão o cozinheiro lê "2400" onde escreveu "2,4 kg". Três razões, e a primeira não é
ergonomia:

1. **Perda de dados.** O `quantity_per_base_unit` é `Decimal(12,3)`. Dividir pela fornada ao escrever arrasa
   os ingredientes pequenos, que são os caros: 2 g de corante ÷ 400 = `0,005`; essência de baunilha numa
   fornada grande = **`0,000`**. E um ingrediente a zero desaparece do custo **e** do consumo no `produzir()`.
2. **Uma ficha é um documento e tem de reler-se como foi escrita.** Se o servidor dividir ao gravar, quem a
   escreveu ontem não reconhece os números e "corrige-os".
3. **O momento.** A tabela está vazia em todos os ambientes (d1). É o último instante em que mudar o
   significado da coluna custa zero.

Para um prato sem fornada, `batch_size = 1` unidade base e o formulário pré-preenche: **o modelo de hoje passa
a ser o caso particular.** A aritmética é `Σ(linhas) ÷ batch_size` com a **divisão no fim** — dividir por linha
e somar dá um total diferente do da fornada, e o dono vai somar à mão.

**Consequência obrigatória: o `yield_factor` nasce a `1,000`, porque o rendimento vive na fornada.** *"1 kg de
massa → 100 pastéis"* **já contém** a perda do processo; pôr também `yield_factor = 0,9` conta a mesma perda
duas vezes e inflaciona o custo em 11 %. E **não há tecto de 1**: arroz 1 kg cru → 2,7 kg cozido é caso real, e
o ganho é água da torneira, que não é artigo de stock. A validação continua a ser `> 0` e mais nada.

**Os três sentidos do rendimento, e só dois são custo.** *Merma de preparação* (descascar, limpar) é custo.
*Perda de processo* (evaporação, o que fica no tacho) é custo, e dilui-se bem na fornada. **Fora-de-especificação**
— queimados, caídos, a bandeja que foi ao chão — **não é a mesma coisa**: varia por dia e por pessoa, é o
número sobre o qual o dono pode agir, e embutido no rendimento fica invisível para sempre. A visibilidade
disso é **esperado vs obtido numa produção** e é da **fatia B**; e **não** se transforma num `waste` sobre o
acabado, que seria registar a quebra de stock que nunca existiu.

**Dívida nomeada, não resolvida: a merma por ingrediente.** Cebola ~0,85, lombo limpo ~0,70, raspa de limão
~0,10 — é custo real e é **por ingrediente**. O modelo de hoje tem um factor só para a ficha toda e não a
consegue exprimir; a skill `inventory-domain` (§2 e §4) põe o factor **na linha**, não na receita. Fica
nomeada em vez de ser fingida com o factor global, que é exactamente o que a tornaria invisível.

**Decisão 9 — O rótulo é "custo de ingredientes", nunca "custo do prato".** Decisão do dono a 2026-11-02,
depois da Q5. É o *food cost*, o número universal da restauração, e é contra ele que um dono compara de cor os
25–30 % do preço de venda. "Custo do prato" com só ingredientes é falso — numa pastelaria por um factor de **2
a 4**, porque num produto com 20 cêntimos de matéria a mão-de-obra é o custo dominante. **A ADR 0014 (sem
mão-de-obra em v1) aguenta-se com este rótulo e fica.** O rótulo vale no ecrã, nos nomes de campo e no texto
desta ADR. E o que o dono vai querer a seguir **não é um modelo de mão-de-obra**: é a **percentagem de food
cost contra o preço de venda**, que é o número com que o sector decide preços — e que precisa de um **preço de
venda que o `catalog` não tem**.

**Decisão 10 — O custo de um ingrediente é uma escada de cinco degraus, e só o primeiro é `conhecido`.** No dia
1 não há produções, logo um semi-acabado **não tem stock, logo não tem CMP** — e **todo** o prato construído
sobre massa folhada sairia "desconhecido", que é o exemplo que esta ADR usa. Três regras do `domain-expert`
entram no contrato por aqui, e a escada é a forma de as escrever uma vez só. Por ingrediente, por esta ordem:

| # | quando | número | palavra |
|---|---|---|---|
| 1 | há quantidade com custo e **toda** tem preço | o `unit_cost` do `/stock/levels` (d3) | `conhecido` |
| 2 | há quantidade com custo mas `quantity_without_cost > 0` | o mesmo `unit_cost` | **`estimado`** |
| 3 | não há quantidade com custo (acabou, ou nunca teve preço) | o **último `unit_cost > 0`** do ledger do artigo, dentro de um ano | **`estimado`** |
| 4 | nada no ledger, mas o artigo **tem ficha activa** | o custo teórico **dessa ficha, por unidade base** | **`estimado`** |
| 5 | nada disto | nenhum — a chave de euro sai `null` | `desconhecido` |

**Degrau 2 — `conhecido` só com cobertura completa.** Com parte do stock sem preço o CMP está **por baixo**, e
`ingredients_without_cost = 0` afirmaria uma precisão que a ficha não tem. É a diluição que a ADR 0032 deixou
como dívida a chegar aqui como número de **gestão** pela primeira vez.

**Degrau 3 — stock zero não pode apagar o custo.** O `_custo_unitario` devolve `None` quando não há quantidade
com custo (`backend/apps/inventory/selectors.py:362`, verificado): o creme acaba ao domingo e o custo do pastel
ficava "desconhecido" **no dia de maior movimento**. Um custo que desaparece porque o frigorífico esvaziou é um
custo em que o dono deixa de acreditar. A janela é **um ano**, a mesma do `_JANELA_DO_CUSTO_REAL` que já existe
no `recipes/api.py` e pela mesma razão escrita lá. Lê-se do **ledger**, sem agrupar por localização: o
`inventory_productcost` daria o número por loja e era a d3 a voltar pela porta das traseiras.

**Degrau 4 — o custo cascateia na leitura.** Profundidade **máxima 3** (`inventory-domain` §4) e **conjunto de
visitados**, sempre. **Na escrita, os ciclos recusam-se**: o acabado em qualquer ponto do seu próprio grafo
transitivo é `400 ciclo_de_receitas`. **Na leitura garante-se a terminação com visitados de qualquer forma** —
a guarda de escrita só vale até à última escrita, e a leitura de hoje corre sobre dados escritos antes dela. O
reaproveitamento real **não é ciclo**: as aparas de folhada voltam como *outro* artigo e o pão de ontem vira
pão ralado, que é outro artigo. **Um ciclo no grafo é sempre erro de dados.**

**O agregado.** O total **nunca** é `conhecido` se alguma linha não o for; é `desconhecido` só quando
**nenhuma** linha tem custo — e aí os euros saem `null`, que é a afirmação verdadeira (*não há valor*). Entre
os dois é `estimado`, com o `ingredients_without_cost` a dizer quantas faltam. **E a escada corre em lote**:
uma leitura por página, não um degrau por ingrediente — a d3 matou um N+1 e isto não o reabre.

**Decisão 11 — A água e o sal não se listam na ficha.** É a primeira coisa que um pasteleiro tenta escrever, e
criar um artigo "água" dá um ingrediente **sem CMP para sempre** a poluir o `ingredients_without_cost` e a
puxar todas as fichas que o usem para `estimado`. A regra fica escrita, e o **mecanismo é o texto do
formulário, nunca uma lista negra de nomes no servidor**: "água das pedras" é um artigo de stock a sério num
café, e um filtro por nome recusaria o artigo certo pela palavra errada. O que o contrato já garante é que uma
linha só pode apontar a um **artigo do catálogo** — não há ingrediente em texto livre.

**Decisão 12 — A validade do acabado: do **artigo**, em **horas**, decidida agora e entregue com a fatia B.**
Resposta à Q4. A fonte é o artigo acabado, no `catalog`: coluna nova **ao lado do `expiry_kind` que já existe**
(`backend/apps/catalog/models.py:151-157`), em **horas e não em dias** — pastel de nata 24 h, massa folhada
72 h, natas batidas 12 h, e "1 dia" num produto feito às 06:00 é ambíguo exactamente onde importa. Chama-se
`produced_shelf_life_hours` porque só responde pelo que **este estabelecimento produz**: a validade do que se
compra vem do lote do fornecedor.

**Não deriva do ingrediente mais antigo.** Essa regra é de **montagem a frio** (sandes, natas batidas, mousse);
o que passa pelo forno **reinicia o relógio**. Fica como **tecto** e não como fonte —
`min(produced_shelf_life_hours, validade do lote de ingrediente mais curto)` — e **a fatia B decide onde o
aplica**: hoje nada no catálogo distingue montagem a frio de cozedura, e aplicar o `min` a tudo encurtava a
validade de um bolo até à da farinha. Ou o artigo ganha essa marca, ou o tecto não se aplica.

**O que custa ligar a fatia B com `expires_at = NULL`**, que é o argumento para não o fazer: (a) o acabado
**nunca** aparece nos Alertas — e numa pastelaria o que mais provavelmente caduca hoje é o que está na montra;
(b) **o FEFO do acabado parte-se**, e o tabuleiro de ontem vende-se depois do de hoje, o que é segurança
alimentar e não relatório; (c) com `lot_id = NULL` a cadeia de rastreabilidade do Reg. (CE) 178/2002
**parte-se no último elo**, apesar de o `production_id` já ligar os lotes de ingrediente ao acabado. **A coluna
não tem leitor na fatia A**: decide-se agora, entrega-se com a B.

## Contrato da fatia A

Todas em `/api/v1`, `SimpleRouter(trailing_slash=False)`, `router.register("recipes", ReceitaViewSet)`.
`IsAuthenticated + PertenceAoTenant`. `Quantidade = {base, base_unit, display, display_unit}`.
**AUSENTE** = chave fora do JSON para o `staff`.

| método · caminho | parâmetros / corpo | resposta | papéis | ausente p/ `staff` |
|---|---|---|---|---|
| `GET /recipes` | `q?` `ingrediente?` `estado=activas\|todas?` `page?` | página de `ReceitaResumo` | todos | `batch_cost`, `unit_cost`, `display_cost` |
| `POST /recipes` | `ReceitaIn` | 201 `ReceitaDetalhe` | `owner manager` | idem |
| `GET /recipes/<id>` | — | `ReceitaDetalhe` · 404 | todos | idem + os da linha |
| `PATCH /recipes/<id>` | `ReceitaPatchIn` | 200 `ReceitaDetalhe` | `owner manager` | idem |

```python
ReceitaResumo:   id: UUID; product: UUID; short_name: str; sku: str
                 base_unit: str; display_unit: str; display_factor: Decimal
                 is_active: bool; batch_size: Quantidade; yield_factor: Decimal
                 line_count: int
                 cost_status: "conhecido"|"estimado"|"desconhecido"   # agregado, d10
                 ingredients_without_cost: int      # contagem, p/ os três papéis
                 batch_cost: Decimal|None           # € da FORNADA inteira — AUSENTE
                 unit_cost: Decimal|None            # €/unidade BASE do acabado — AUSENTE
                 display_cost: Decimal|None         # €/unidade de APRESENTAÇÃO — AUSENTE
ReceitaDetalhe:  ReceitaResumo + lines: list[LinhaDaReceita]      # herança, zero campos repetidos
LinhaDaReceita:  ingredient: UUID; short_name: str; sku: str; ingredient_is_active: bool
                 quantity: Quantidade               # o que a ficha escreve, POR FORNADA
                 quantity_real: Quantidade          # quantity ÷ yield_factor — o que sai do stock
                 cost_status: "conhecido"|"estimado"|"desconhecido"   # p/ os três papéis
                 unit_cost: Decimal|None            # o custo do ingrediente pela escada d10 — AUSENTE
                 line_cost: Decimal|None            # quantity_real × unit_cost — AUSENTE
ReceitaIn:       product: UUID; batch_size: Decimal(12,3)>0; batch_unit: str
                 yield_factor: Decimal(5,3)>0 = 1.000; is_active: bool = true
                 lines: list[LinhaIn]               # ≥1
LinhaIn:         ingredient: UUID; quantity: Decimal>0; unit: str
ReceitaPatchIn:  batch_size?; batch_unit?; yield_factor?; is_active?; lines?
                 # `product` NÃO é alterável: é a identidade da ficha
```

**A aritmética, e a ordem dela.** `line_cost = quantity_real × unit_cost`; `batch_cost = Σ(line_cost)`;
`unit_cost = batch_cost ÷ batch_size.base`; `display_cost = unit_cost × display_factor`. A **divisão é no fim**
(d8) e cada número deriva do `batch_cost` por arredondar — só a saída arredonda, ao cêntimo os totais e a seis
casas os custos unitários, como o resto da casa.

**`display_cost` ao lado do `unit_cost`, e não em vez dele.** O `unit_cost` é por unidade **base**, como todo o
ledger e como o `/stock/levels` — uma definição. Mas a pergunta do dono é literalmente *"quanto me custa **um
pastel**"*, e um pastel é uma unidade de apresentação: fazer o cliente multiplicar pelo `display_factor` é a
conversão no cliente que a casa proíbe (ADR 0030 d1, ADR 0034 d11, `inventory-domain` §2). Os dois reconstroem-se
um ao outro pelo `display_factor`, que é público, logo saem juntos. O `batch_cost` entra pela mesma regra: é o
número que o pasteleiro lê ("esta fornada custa-me 14,20 €") e é o numerador dos outros dois.

**`unit` no corpo de entrada, e a conversão é do servidor** (ADR 0034 d11): tem de ser o `base_unit` ou o
`display_unit` **daquele ingrediente** e qualquer outro é 400 — não existe motor genérico de conversão
(ADR 0011). O pasteleiro escreve "500 g de farinha" num catálogo cujo artigo é base `g` e apresentação `kg`. O
`batch_unit` segue a mesma regra contra o **acabado**: "2,4 kg" ou "2400 g", e nada mais.

**Erros.** `400`: `yield_factor <= 0`; `batch_size <= 0`; `lines` vazio; `quantity <= 0` numa linha; `unit` ou
`batch_unit` que não é a base nem a de apresentação do artigo respectivo; ingrediente repetido; **artigo a ser
ingrediente de si próprio** e, em geral, **`ciclo_de_receitas`** — o acabado em qualquer ponto do seu grafo
transitivo (d10). `404`: o `product` ou um `ingredient` não é legível neste tenant (e é 404 **porque a RLS não
devolve a linha**, não porque alguém comparou tenants em Python); a receita não existe. **`409
receita_ja_existe`** quando o artigo já tem receita — `Recipe.product` é `OneToOneField`, logo a segunda
inserção é `IntegrityError` e tem de sair com o **`id` da que existe no corpo**, para o ecrã levar lá quem
tentou em vez de lhe dizer "erro" (precedente: o 409 da contagem já aberta, ADR 0030 d2). Uma receita
**inactiva** responde `200` e nunca 404. **Não há o estado (b) da 0034 d13**: a linha **é** a receita e não há
segundo dono da identidade a quem perguntar — é o argumento da 0034 d17(b), e por isso o 404 quer dizer uma
coisa só desde o primeiro dia.

**Artigo arquivado dentro de ficha activa: aceita-se a ficha e assinala-se a linha.** O `ingredient_is_active`
existe para isso, e quem recusa é a **produção**, na fatia B. Arquivar um artigo não pode partir a gravação de
uma ficha que já o continha, e o sítio onde a decisão tem consequência é o movimento de stock, não o documento.

## Impacto

**RLS — confirmado e sem surpresa.** `recipes_recipe` e `recipes_recipelineitem` têm `ENABLE` **e** `FORCE`
ROW LEVEL SECURITY e o predicado é exactamente o do `CLAUDE.md` —
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` — na migração que as cria
(`recipes/migrations/0001_initial.py`, linhas 76–100). As duas não estão em `SEM_POLITICA` e não têm de estar.
**Nenhuma tabela nova nesta fatia**: as colunas abaixo entram em tabelas que já têm política, e uma coluna não
mexe no predicado. **A fatia segue como desenhada.**

**Tabelas e migrações.** Zero tabelas novas; **três migrações**, e já não é "zero":

1. **`recipes`** — `Recipe.batch_size` `Decimal(12,3)`, **NOT NULL**, com `CheckConstraint > 0`, e
   `Recipe.yield_factor` ganha `default=Decimal("1.000")` (d8). **Sem backfill e sem default temporário**: a
   tabela está vazia em todos os ambientes (d1), que é precisamente o argumento do momento.
2. **`accounts`** — `AlterField` do `TenantMenuItem.route_id`, porque o `RotaDeMenu` ganha o id `receitas` e
   ele é `choices` da coluna. Não é de esquema no sentido útil, mas o `makemigrations` produz-a.
3. **`catalog`** — `Product.produced_shelf_life_hours` (d12). **Não é desta fatia**: decide-se aqui,
   entrega-se com a fatia B, que é quem lhe dá leitor.

**Import-linter — isto é um bloqueador e tem de mudar no mesmo PR.** O contrato *"recipes só depende de
inventory e catalog"* (`backend/pyproject.toml`) tem **`apps.accounts` nos `forbidden_modules`**, com o
comentário *"Excepto TYPE_CHECKING"* e um `ignore_imports` só para `apps.recipes.** -> apps.accounts.models`.
Um `views.py` no `recipes` importa `PertenceAoTenant`, `TemPapel`, `Papel`, `ve_euros`, `CHAVE_DE_EUROS` e
`SemEurosParaQuemNaoVe` de **`apps.accounts.api`** — e isso dá `BROKEN` e exit 1 no `lint-imports`. **A
correcção é tirar `apps.accounts` dos `forbidden_modules` desse contrato**, e não acrescentar um
`ignore_imports`: o ARCHITECTURE.md §6b diz `todos → accounts.api, shared`, nenhum outro módulo de domínio tem
o `accounts` na sua lista, e o `recipes` só o contradiz porque nunca serviu HTTP. O `ignore_imports` do
`accounts.models` fica, porque é o `TYPE_CHECKING` que já lá está.

**Os gates de lista fechada que esta fatia toca** (ADR 0034, adenda de 29: *"a secção Impacto lista os gates de
lista fechada"* — são os que não aparecem no diff do `spectacular` nem do `gen:api` e rebentam na primeira
corrida):

1. **`tests/test_rls_isolation.py`** — a lista fechada das **rotas com âmbito**, na forma em cru do resolver,
   ganha `api/v1/^recipes$` e `api/v1/^recipes/(?P<pk>[^/.]+)$`. (A fatia B acrescenta
   `api/v1/^recipes/(?P<pk>[^/.]+)/production$`.) Nenhuma leva `tenant_scope_exempt`: a lista das **dispensas**
   não cresce, e é essa ausência que as torna normais.
2. **`tests/test_custos_de_stock.py::TestAsChavesDeDinheiroDoModulo`** — e aqui há um **buraco**, não um bónus:
   o `_campos_que_parecem_dinheiro()` varre `vars(serializers_do_inventory)`, logo **está preso ao
   `inventory/serializers.py` e não alcança o `recipes`**. As **cinco** chaves de dinheiro novas
   (`ReceitaResumoOut.batch_cost`, `.unit_cost`, `.display_cost`, `LinhaDaReceitaOut.unit_cost`, `.line_cost`)
   nascem **sem gate nenhum**. A fatia leva a lista fechada irmã para `tests/test_receitas.py`, no mesmo molde
   e com os dois testes — o segundo (`…esta_mesmo_no_mixin`) lê o `CAMPOS_DE_DINHEIRO` **na subclasse** e é o
   guarda independente contra a redeclaração da d6.
3. **`tests/test_db_roles.py`** — **não muda, e está escrito para não surpreender.** O `APPEND_ONLY` fica
   `{inventory_stockmovement}`: uma ficha técnica corrige-se, o que é append-only é o ledger, e a tabela do
   ledger já lá está. O `SEM_POLITICA` não ganha nada (ver o parágrafo da RLS).
4. **O registo de rotas, nos dois lados, e a ordem não se inverte** (ADR 0009): o id `receitas` entra
   **primeiro** no `RotaDeMenu` do Django, o `pnpm gen:api` leva-o ao `RotaIdEnum` do `types.ts`, e só então o
   `Record<RotaId, EntradaDoRegisto>` do `frontend/src/shell/registo-de-rotas.ts` compila — com a entrada nova
   **e** com a rota `/receitas` a existir na árvore, porque o `caminho` é do tipo `CaminhoDeRota`. Entre os dois
   passos o `pnpm typecheck` falha com `TS2741`, e **o erro é o mecanismo**. Entrada no
   `accounts/menu.py::REGISTO_DE_ROTAS` com `papeis=TODOS_OS_PAPEIS` (a leitura é dos três, d5) e `campo=False`.
5. **`apps/agents/navegacao.py` — e são duas listas fechadas, não uma.** O `TEMAS["receitas-e-producao"]` é
   `None` com o comentário *"hoje só as receitas, cuja produção não tem rota na árvore do cliente"*; com a rota
   a existir passa a `Destino(rota="receitas", rotulo_id="ver_receitas")` e **o comentário fica falso**. O
   `rotulo_id` novo obriga o `ROTULOS` (`navegacao.py:112-128`), que vira `RotuloIdEnum` no `types.ts` e tem de
   entrar **à mão** no `frontend/src/features/assistente/schemas.ts` e no `vocabulario.ts` — é a fronteira dos
   Zod escritos à mão, que nenhum gate atravessa. O `_MAPA` ganha as tools de receitas, que hoje não produzem
   botão por não haver onde pousar. Tudo no mesmo PR — é a espécie de dívida que a 0034 d17 existiu para pagar.

**Backend.** Ficheiros novos: `recipes/serializers.py` (entrada e saída **separados**, `fields` explícitos, sem
`__all__`), `recipes/views.py`, `recipes/urls.py`, a migração do `batch_size`. Alterados: `recipes/models.py`
(d8), `config/urls.py` (`+ include("apps.recipes.urls")`), `recipes/services.py` (`criar_receita`,
`actualizar_receita`, a guarda de ciclos, `@transaction.atomic`), `recipes/selectors.py` (ordenação, página e o
grafo de semi-acabados até à profundidade 3), `recipes/api.py` (o `_custos()` reescrito pelas d3/d8/d10 — o
`CustoDaReceita` muda de forma e o assistente melhora pela mesma mudança) **e o cabeçalho do `recipes/api.py`,
que está errado hoje** (ver "Defeitos"). **Duas funções novas na porta do `inventory`** —
`custos_de_artigos(tenant_id, product_ids, desde) → Mapping[UUID, CustoDeArtigo]`, que serve os degraus 1 a 3
da d10 já com a palavra decidida (`unit_cost`, `cost_status`) porque é o `inventory` que é dono das três
palavras; e a **re-exportação do `ESTADOS_DO_CUSTO`** pela porta, que hoje só existe em
`inventory/selectors.py:312` e que o `recipes` não pode importar — sem isso nasce um segundo `EstadoDoCusto2Enum`
no `types.ts`, que é a divergência de vocabulário que a 0032 fechou. O `inventory/selectors.py` ensina o
`niveis_de_stock` a receber uma **sequência** de `product_id` (a 0034 d12 já lhe deu um) e ganha a leitura do
último custo do ledger. Aresta `recipes → inventory.api` já permitida. **Zero tarefas Celery. Zero eventos
novos** — uma ficha técnica é uma definição e não um facto do ledger; a ADR 0026 já tinha decidido que nem a
produção emite evento.

**Frontend.** Rotas `/receitas` e `/receitas/<id>` (TanStack Router, search params validados por Zod, ADR 0008),
`features/recipes/{api,schemas}.ts`, lista + ficha + formulário, estados loading/empty/error, mobile primeiro.
O formulário pede a **fornada** primeiro (pré-preenchida a 1 na unidade base) e o `yield_factor` fica fora do
caminho principal: nasce a 1,000 e o rendimento vive na fornada (d8). **Os `.optional()` que não são opcionais**
(CLAUDE.md): `batch_cost`, `unit_cost`, `display_cost` e `line_cost` nascem `.optional().nullable()` e nunca só
`.nullable()` — a chave **falta** para o `staff` e **é `null`** no degrau 5, e `.nullable()` sozinho exige a
chave presente e o ecrã **rebenta** com o `pnpm typecheck` verde. `uv run manage.py spectacular` e
`pnpm gen:api`, com o gate de diff. E o que nenhum gate atravessa: `frontend/scripts/ver-ecra.py` sobre os dois
ecrãs **com cada um dos três papéis** — é por papel que estas chaves desaparecem.

## Defeitos nomeados, para corrigir no mesmo PR

**O cabeçalho do `recipes/api.py:25-29` está errado, e verificou-se.** Diz *"A ficha é por **uma unidade de
apresentação** do acabado"*, enquanto o `IngredienteDaReceita.quantidade_lista` (`:79`) diz *"por unidade
**base** de acabado"* — e a implementação segue a segunda. Num artigo com base em gramas e apresentação em
quilos as duas frases diferem por **mil vezes** no custo. Nenhuma das duas sobrevive à d8: passa a ser **por
fornada**, e o cabeçalho corrige-se com o resto.

**Decisão 13 — O que a fatia B herda, medido agora para não ser descoberto lá.** O `produzir()` está testado, e
o teste prova menos do que parece: **o `_get_fefo_lots_with_stock` só encontra stock através de linhas de
`Lot`** (`Lot.objects.filter(product_id=…)`), e o `tests/test_production.py` cria `Lot` para a massa e os ovos
apesar de os declarar `track_lots=False`. A convenção do lote sintético `__<product_id>__` existe no
`inventory/services.py` (ajuste e transferência) mas **não é universal**, e um nível com `lot_id = NULL` é
invisível a esta função. **Isto é o bloqueador nº 1 da fatia B e é o caminho principal, não um canto**: um
semi-acabado com `track_lots=False` — que é precisamente o que o `produzir()` acabou de criar — responde **409
"sem stock" com a arca cheia**. É a mesma família do FEFO partido do `registar_waste` (ADR 0034 d8): um caminho
de escrita testado contra um mundo que a app não produz. **Verificar antes de ligar a fatia B, e ligá-lo
partido não é ligá-lo.** No mesmo lote: o `unit_cost` do `production_in` sai `0` com `cost_is_estimate=False`
quando um ingrediente não tem custo (`services.py:223` lê o custo do nível, `:288` afirma que não é estimativa)
— é o **zero mentiroso** num ledger append-only que a adenda de 27 da 0034 já corrigiu no `waste`, e aqui
propaga-se para o custo de tudo o que o semi-acabado entrar.

## Testes — os casos-limite que ficam escritos

Além do caminho feliz, dos três papéis e dos erros do contrato: **unidade de compra ≠ unidade da ficha** (a
falha é do **catálogo** e não da receita, e esperam-se muitos 400 no primeiro dia); **ovos em gramas vs
unidades** — não há motor de conversão (ADR 0011) e o 400 é a resposta certa; **receita de reembalagem**
("caixa de 6 pastéis" = 6 × "pastel", fornada 1) — **não é ciclo** e o custo não pode contar em dobro;
**fornada parcial** ("fiz meia fornada"), que é da fatia B mas aparece no primeiro dia; **edição concorrente**
da ficha — o `PATCH` substitui as linhas todas, logo é last-write-wins em silêncio: risco baixo na fatia A com
o `staff` só a ler, corrida a sério na B; **a ordem da aritmética** (`Σ(linhas) ÷ batch_size`, divisão no fim —
d8); e **os cinco degraus da d10**, um teste por degrau, com o 3 e o 4 a serem os que ninguém adivinha.

## Enquadramento legal — indicativo, nunca facto assente

Nomeado pelo `domain-expert` de cor e **a confirmar com fonte oficial ou jurista antes de qualquer afirmação no
produto**: Reg. (UE) 1169/2011 e DL 26/2016 (informação ao consumidor, alergénios em não pré-embalados, e a
distinção `use_by`/`best_before` que o `expiry_kind` já usa); Reg. (CE) 852/2004 (HACCP — justificar a validade
do que o estabelecimento produz é pré-requisito, e é o que a coluna da d12 serve); Reg. (CE) 178/2002
(rastreabilidade um-passo-atrás e um-passo-à-frente, o que a d12(c) mede). **Regra: nunca afirmar conformidade
HACCP em lado nenhum do produto** — nem no ecrã, nem no marketing, nem num `help_text`. O sistema guarda
registos que ajudam; quem é conforme é o estabelecimento.

**Alergénios, para quando chegarem:** o alergénio é propriedade do **artigo** e o do prato é a **união** dos
artigos da ficha. Ninguém deve pôr um campo de texto livre na linha da receita — é a forma garantida de ter o
mesmo ingrediente com dois alergénios diferentes em duas fichas.

**Alternativas.** *Uma fatia só* — onze operações, dois ecrãs e um caminho de escrita no ledger no mesmo PR.
*Produzir primeiro, porque já está escrito* — não há receitas em lado nenhum para produzir. *Só leitura nesta
fatia, expondo o `api.py` da 0028* — o ecrã nascia com o estado vazio como único estado. *Linhas como
sub-recurso* — é a forma da contagem e da receção, e as duas são percursos (d4). *`PUT` para a substituição
total* — a 0034 d18 a repetir-se. *`DELETE` a sério* — apaga a ficha técnica de mercadoria que já entrou no
ledger. *Custo por localização, a forma de hoje* — N números todos incompletos e todos por baixo (d3). *Manter
`actual: null` nesta fatia* — uma coluna de "—" em 100 % das linhas. *Negar `GET /recipes` ao `staff`* — tira a
ficha a quem produz. *`unit_cost: 0` para o `staff`* — zero é uma afirmação falsa sobre o preço. **E as desta
revisão:** *dividir pela fornada ao gravar e guardar por unidade* — arrasa os ingredientes pequenos para
`0,000` e muda os números que o cozinheiro escreveu (d8); *embutir a merma por ingrediente no `yield_factor`
global* — finge que a resolve e torna-a invisível (d8); *limitar o `yield_factor` a ≤ 1* — recusa o arroz
cozido, que é caso real; *derivar a validade do acabado do ingrediente mais antigo* — o forno reinicia o
relógio (d12); *orçamentar ao **último preço pago*** — responde a outra pergunta (*"quanto me vai custar a
próxima fornada"*), já existe derivado no `purchasing`, e trazê-lo abria a aresta `recipes → purchasing` que
hoje não existe: é o número **seguinte**, não o desta fatia; *chamar-lhe "custo do prato"* — falso por um
factor de 2 a 4 numa pastelaria (d9).

**Fora de âmbito, por extenso.** Produzir (é a fatia B); escalar uma receita sem produzir; **versões da ficha e
histórico de alterações** — dívida nomeada e não esquecimento: hoje um `PATCH` reescreve a ficha e o custo
teórico de ontem deixa de ser reproduzível, enquanto o custo **real** de cada produção fica gravado no ledger,
que é o que importa para a auditoria; **percentagem de food cost contra o preço de venda** (d9 — é o número
seguinte e precisa de um preço de venda que o `catalog` não tem); mão-de-obra e custos indirectos (ADR 0014,
confirmada pela d9); **merma por ingrediente** (d8); **fora-de-especificação visível** (esperado vs obtido, é
da fatia B); alergénios e rotulagem; importar fichas de folha de cálculo; receitas partilhadas entre
estabelecimentos.

## As sete perguntas, respondidas (`domain-expert` + dono, 2026-11-02)

**Q1 — fornada.** Sim, **por fornada**: d8, com coluna e migração. **Q2 — rendimento.** `yield_factor` nasce a
`1,000` porque a perda já está na fornada; sem tecto de 1; e os três sentidos do rendimento separados, com o
fora-de-especificação a não ser um `waste` (d8). **Q3 — semi-acabados.** Duas produções e dois custos
gravados, como a 0026 dizia — mas **a leitura cascateia** até à profundidade 3 com visitados, e os ciclos são
400 na escrita (d10). **Q4 — validade do acabado.** Do artigo, em horas, `produced_shelf_life_hours`; o lote de
ingrediente é tecto de montagem a frio e não fonte; entrega-se com a fatia B (d12). **Q5 — mão-de-obra.** Não:
muda-se o **rótulo** para "custo de ingredientes" e a ADR 0014 aguenta-se (d9). **Q6 — CMP.** Fica como estava,
porque quem compara a ficha com o `/stock` tem de ver o mesmo número (d3) — mas ganha a escada que o impede de
desaparecer e de mentir sobre a sua própria precisão (d10). **Q7 — quem escreve a ficha.** `owner|manager`,
confirmado pelo dono; o pasteleiro-chefe que precise de escrever fichas é `manager`.
