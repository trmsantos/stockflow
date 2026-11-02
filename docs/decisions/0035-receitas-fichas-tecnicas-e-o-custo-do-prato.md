# ADR 0035 — Receitas: a ficha técnica primeiro, produzir depois, e o custo do prato pelo meio

**Contexto.** O `recipes` é o único módulo de domínio com o servidor pago e a porta fechada: `Recipe` e
`RecipeLineItem` existem com RLS, o `produzir()` está escrito e testado (ADR 0026), o `api.py` lê a ficha e os
custos desde a ADR 0028 — e **não existem `views.py` nem `urls.py`**, `apps.recipes.urls` não está no
`config/urls.py`, e não há rota `/receitas` na árvore do cliente. A ADR 0026 d3 escreveu por extenso *"Contrato
internamente, não há endpoint (…) um endpoint POST futuro `/recipes/<id>/produce` (fatia 7 ou posterior)"*.
**Esta é essa fatia**, e o objectivo que o dono escreveu é mais curto do que ela: **ver o custo do prato.**
**Toca em stock, validades, unidades, receitas e custos: consultar `domain-expert` — obrigatório, e antes do
`backend`**, porque uma das perguntas (a fornada, Q1) muda o modelo.

**Decisão 1 — São duas fatias, e a primeira é a ficha técnica. O `produzir()`, que já está escrito, fica para
a segunda.** O corte não é de tamanho, é de dados: **não existe uma única receita em lado nenhum**. O
`apps/demo` não semeia o `recipes` (`semear_demonstracao.py` não lhe toca), não há porta para criar uma, e a
tabela está vazia em todos os ambientes — logo o `produzir()` **não é chamável** e as tools de receitas do
assistente (ADR 0028) respondem hoje sobre uma tabela vazia. Uma rota de produção ligada primeiro servia 404
em todos os tenants no dia em que fosse para produção. A ordem é a dos factos: **primeiro escreve-se a ficha,
depois produz-se a partir dela.**

- **Fatia A (esta):** `GET`/`POST /recipes`, `GET`/`PATCH /recipes/<id>`, o ecrã `/receitas` (lista + ficha +
  formulário) e o **custo teórico**. É a coisa mais pequena que responde à pergunta do dono.
- **Fatia B (a seguir):** `POST /recipes/<id>/production`, a lista de produções, o **custo real**, e a
  reparação dos defeitos que a d8 abaixo nomeia.

**Decisão 2 — O custo é calculado na leitura, e isso é a resposta à pergunta do dono; o custo real vem com a
produção.** São duas perguntas e duas respostas, e a ADR 0028 já lhes deu os dois nomes (`CustoDaReceita`):

| pergunta | número | onde vive | fatia |
|---|---|---|---|
| *"quanto me custa um pastel de nata?"* | **teórico** — Σ(consumo real × custo do ingrediente **hoje**) | derivado na leitura, de `inventory` | **A** |
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
artigo e pela mesma razão: *não nasce aqui uma segunda definição de custo*.

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
irmã por onde o dinheiro sai, e esta casa já lá caiu duas vezes. Nunca `0` (afirmação falsa sobre o preço),
nunca `null` (que o ecrã imprime "—"). **E saem todos juntos**, pela regra da reconstrução por aritmética
(ADR 0032 d2): `line_cost ÷ quantity_real` devolve o `unit_cost` do ingrediente, e a soma dos `line_cost`
devolve o custo da receita — as três pontas da divisão (`quantity`, `quantity_real`, `yield_factor`) estão no
payload de quem não vê euros e continuam a estar, porque **as quantidades são o produto**. O que fica para os
três papéis: as quantidades, o rendimento, o `cost_status` por linha (as mesmas três palavras da casa,
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

## Contrato da fatia A

Todas em `/api/v1`, `SimpleRouter(trailing_slash=False)`, `router.register("recipes", ReceitaViewSet)`.
`IsAuthenticated + PertenceAoTenant`. `Quantidade = {base, base_unit, display, display_unit}`.
**AUSENTE** = chave fora do JSON para o `staff`.

| método · caminho | parâmetros / corpo | resposta | papéis | ausente p/ `staff` |
|---|---|---|---|---|
| `GET /recipes` | `q?` `ingrediente?` `estado=activas\|todas?` `page?` | página de `ReceitaResumo` | todos | `unit_cost`, `display_cost` |
| `POST /recipes` | `ReceitaIn` | 201 `ReceitaDetalhe` | `owner manager` | idem |
| `GET /recipes/<id>` | — | `ReceitaDetalhe` · 404 | todos | idem + os da linha |
| `PATCH /recipes/<id>` | `ReceitaPatchIn` | 200 `ReceitaDetalhe` | `owner manager` | idem |

```python
ReceitaResumo:   id: UUID; product: UUID; short_name: str; sku: str
                 base_unit: str; display_unit: str; display_factor: Decimal
                 is_active: bool; yield_factor: Decimal; line_count: int
                 ingredients_without_cost: int      # contagem, p/ os três papéis
                 unit_cost: Decimal|None            # €/unidade BASE do acabado — AUSENTE
                 display_cost: Decimal|None         # €/unidade de APRESENTAÇÃO — AUSENTE
ReceitaDetalhe:  ReceitaResumo + lines: list[LinhaDaReceita]      # herança, zero campos repetidos
LinhaDaReceita:  ingredient: UUID; short_name: str; sku: str
                 quantity: Quantidade               # o que a ficha escreve
                 quantity_real: Quantidade          # quantity ÷ yield_factor — o que sai do stock
                 cost_status: "conhecido"|"estimado"|"desconhecido"   # p/ os três papéis
                 unit_cost: Decimal|None            # o CMP do ingrediente — AUSENTE
                 line_cost: Decimal|None            # quantity_real × unit_cost — AUSENTE
ReceitaIn:       product: UUID; yield_factor: Decimal(5,3)>0; is_active: bool = true
                 lines: list[LinhaIn]               # ≥1
LinhaIn:         ingredient: UUID; quantity: Decimal>0; unit: str
ReceitaPatchIn:  yield_factor?; is_active?; lines?  # `product` NÃO é alterável: é a identidade da ficha
```

**`display_cost` ao lado do `unit_cost`, e não em vez dele.** O `unit_cost` é por unidade **base**, como todo o
ledger e como o `/stock/levels` — uma definição. Mas a pergunta do dono é literalmente *"quanto me custa **um
pastel**"*, e um pastel é uma unidade de apresentação: fazer o cliente multiplicar pelo `display_factor` é a
conversão no cliente que a casa proíbe (ADR 0030 d1, ADR 0034 d11, `inventory-domain` §2). Os dois reconstroem-se
um ao outro pelo `display_factor`, que é público, logo saem juntos.

**`unit` no corpo de entrada, e a conversão é do servidor** (ADR 0034 d11): tem de ser o `base_unit` ou o
`display_unit` **daquele ingrediente** e qualquer outro é 400 — não existe motor genérico de conversão
(ADR 0011). O pasteleiro escreve "500 g de farinha" num catálogo cujo artigo é base `g` e apresentação `kg`.

**Erros.** `400`: `yield_factor <= 0`; `lines` vazio; `quantity <= 0` numa linha; `unit` que não é a base nem a
de apresentação do ingrediente; ingrediente repetido; **artigo a ser ingrediente de si próprio**. `404`: o
`product` ou um `ingredient` não é legível neste tenant (e é 404 **porque a RLS não devolve a linha**, não
porque alguém comparou tenants em Python); a receita não existe. **`409 receita_ja_existe`** quando o artigo já
tem receita — `Recipe.product` é `OneToOneField`, logo a segunda inserção é `IntegrityError` e tem de sair com
o **`id` da que existe no corpo**, para o ecrã levar lá quem tentou em vez de lhe dizer "erro" (precedente: o
409 da contagem já aberta, ADR 0030 d2). Uma receita **inactiva** responde `200` e nunca 404. **Não há o estado
(b) da 0034 d13**: a linha **é** a receita e não há segundo dono da identidade a quem perguntar — é o argumento
da 0034 d17(b), e por isso o 404 quer dizer uma coisa só desde o primeiro dia.

## Impacto

**RLS — confirmado e sem surpresa.** `recipes_recipe` e `recipes_recipelineitem` têm `ENABLE` **e** `FORCE`
ROW LEVEL SECURITY e o predicado é exactamente o do `CLAUDE.md` —
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` — na migração que as cria
(`recipes/migrations/0001_initial.py`, linhas 76–100). As duas não estão em `SEM_POLITICA` e não têm de estar.
**A fatia segue como desenhada.**

**Tabelas e migrações.** **Zero tabelas novas e zero colunas — se a resposta à Q1 for "a ficha é por unidade
base do acabado"**, que é o que o `produzir()` implementa hoje. **Se a resposta for "por fornada"**, que é o que
uma pastelaria a sério escreve, isto ganha uma coluna (`Recipe.batch_size`) e uma migração, e muda o divisor de
todo o cálculo de custo — é por isso que a consulta ao `domain-expert` é **antes** do `backend` e não depois.
**Uma migração entra de qualquer forma, e não é de esquema:** o `RotaDeMenu` ganha o id `receitas` e ele é
`choices` da coluna `TenantMenuItem.route_id`, logo o `makemigrations` produz um `AlterField`.

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
   `inventory/serializers.py` e não alcança o `recipes`**. As quatro chaves de dinheiro novas
   (`ReceitaResumoOut.unit_cost`, `.display_cost`, `LinhaDaReceitaOut.unit_cost`, `.line_cost`) nascem **sem
   gate nenhum**. A fatia leva a lista fechada irmã para `tests/test_receitas.py`, no mesmo molde e com os dois
   testes — o segundo (`…esta_mesmo_no_mixin`) lê o `CAMPOS_DE_DINHEIRO` **na subclasse** e é o guarda
   independente contra a redeclaração da d6.
3. **`tests/test_db_roles.py`** — **não muda, e está escrito para não surpreender.** O `APPEND_ONLY` fica
   `{inventory_stockmovement}`: uma ficha técnica corrige-se, o que é append-only é o ledger, e a tabela do
   ledger já lá está. O `SEM_POLITICA` não ganha nada (ver o parágrafo da RLS).
4. **O registo de rotas, nos dois lados, e a ordem não se inverte** (ADR 0009): o id `receitas` entra
   **primeiro** no `RotaDeMenu` do Django, o `pnpm gen:api` leva-o ao `RotaIdEnum` do `types.ts`, e só então o
   `Record<RotaId, EntradaDoRegisto>` do `frontend/src/shell/registo-de-rotas.ts` compila — com a entrada nova
   **e** com a rota `/receitas` a existir na árvore, porque o `caminho` é do tipo `CaminhoDeRota`. Entre os dois
   passos o `pnpm typecheck` falha com `TS2741`, e **o erro é o mecanismo**. Entrada no
   `accounts/menu.py::REGISTO_DE_ROTAS` com `papeis=TODOS_OS_PAPEIS` (a leitura é dos três, d5) e `campo=False`.
5. **`apps/agents/navegacao.py`** — o `TEMAS["receitas-e-producao"]` é `None` com o comentário *"hoje só as
   receitas, cuja produção não tem rota na árvore do cliente"*. Com a rota a existir, passa a
   `Destino(rota="receitas", …)` e **o comentário fica falso**; o `_MAPA` ganha as tools de receitas, que hoje
   não produzem botão por não haver onde pousar. Corrige-se no mesmo PR — é a espécie de dívida que a 0034 d17
   existiu para pagar (um comentário a citar por extenso uma decisão já revogada).

**Backend.** Ficheiros novos: `recipes/serializers.py` (entrada e saída **separados**, `fields` explícitos, sem
`__all__`), `recipes/views.py`, `recipes/urls.py`. Alterados: `config/urls.py` (`+ include("apps.recipes.urls")`),
`recipes/services.py` (`criar_receita`, `actualizar_receita`, `@transaction.atomic`), `recipes/selectors.py`
(ordenação e página da lista), `recipes/api.py` (o `_custos()` reescrito pela d3; o `CustoDaReceita` muda de
forma e o assistente melhora pela mesma mudança). **Uma função nova na porta do `inventory`** —
`custos_de_artigos(tenant_id, product_ids) → Mapping[UUID, …]`, com o `unit_cost` do estabelecimento e a
cobertura, lida do mesmo `niveis_de_stock` que o `/stock/levels` usa (que a 0034 d12 já ensinou a receber um
`product_id`; passa a receber a sequência). Aresta `recipes → inventory.api` já permitida.
**Zero tarefas Celery. Zero eventos novos** — uma ficha técnica é uma definição e não um facto do ledger; a
ADR 0026 já tinha decidido que nem a produção emite evento.

**Frontend.** Rotas `/receitas` e `/receitas/<id>` (TanStack Router, search params validados por Zod, ADR 0008),
`features/recipes/{api,schemas}.ts`, lista + ficha + formulário, estados loading/empty/error, mobile primeiro.
**Os `.optional()` que não são opcionais** (CLAUDE.md): `unit_cost`, `display_cost` e `line_cost` nascem
`.optional()` e nunca só `.nullable()` — `.nullable()` sozinho exige a chave presente e o ecrã **rebenta** com o
`pnpm typecheck` verde. `uv run manage.py spectacular` e `pnpm gen:api`, com o gate de diff. E o que nenhum gate
atravessa: `frontend/scripts/ver-ecra.py` sobre os dois ecrãs **com cada um dos três papéis** — é por papel que
estas chaves desaparecem.

**Decisão 8 — O que a fatia B herda, medido agora para não ser descoberto lá.** O `produzir()` está testado, e o
teste prova menos do que parece: **o `_get_fefo_lots_with_stock` só encontra stock através de linhas de `Lot`**
(`Lot.objects.filter(product_id=…)`), e o `tests/test_production.py` cria `Lot` para a massa e os ovos apesar de
os declarar `track_lots=False`. A convenção do lote sintético `__<product_id>__` existe no
`inventory/services.py` (ajuste e transferência) mas **não é universal**, e um nível com `lot_id = NULL` é
invisível a esta função: se a receção deixar níveis assim, produzir responde **409 "sem stock"** com o armazém
cheio. É a mesma família do FEFO partido do `registar_waste` (ADR 0034 d8) — um caminho de escrita testado
contra um mundo que a app não produz. **Verificar antes de ligar a fatia B, e ligá-lo partido não é ligá-lo.**
No mesmo lote: o `unit_cost` do `production_in` sai `0` com `cost_is_estimate=False` quando um ingrediente não
tem custo — é o **zero mentiroso** num ledger append-only que a adenda de 27 da 0034 já corrigiu no `waste`, e
aqui ele propaga-se para o custo de tudo o que o semi-acabado entrar.

**Alternativas.** *Uma fatia só* — onze operações, dois ecrãs e um caminho de escrita no ledger no mesmo PR, com
a Q1 por responder **debaixo** do `produzir()`: produzir com a ficha errada escreve movimentos que não têm
`UPDATE` nem `DELETE` (ADR 0006). *Produzir primeiro, porque já está escrito* — não há receitas em lado nenhum
para produzir. *Só leitura nesta fatia, expondo o `api.py` da 0028* — mesma razão: o ecrã nascia com o estado
vazio como único estado. *Linhas como sub-recurso* — é a forma da contagem e da receção, e as duas são
percursos; uma ficha escreve-se de uma vez (d4). *`PUT` para a substituição total* — a 0034 d18 a repetir-se.
*`DELETE` a sério* — apaga a ficha técnica de mercadoria que já entrou no ledger. *Custo por localização, a
forma de hoje* — N números todos incompletos e todos por baixo (d3). *Manter `actual: null` nesta fatia* — uma
coluna de "—" em 100 % das linhas. *Negar `GET /recipes` ao `staff`* — tira a ficha a quem produz, e o dono já
decidiu o contrário. *`unit_cost: 0` ou `null` para o `staff`* — zero é uma afirmação falsa sobre o preço e
`null` imprime-se "—".

**Fora de âmbito, por extenso.** Produzir (é a fatia B, por decisão desta ADR); escalar uma receita ("faz-me
meia fornada") sem produzir; versões da ficha e histórico de alterações de quantidades — **e isto é dívida
nomeada e não esquecimento**: hoje um `PATCH` reescreve a ficha e o custo teórico de ontem deixa de ser
reproduzível, enquanto o custo **real** de cada produção fica gravado no ledger, que é o que importa para a
auditoria; preço de venda, margem e food-cost percentual (precisa de um preço de venda, que o `catalog` não
tem); mão-de-obra e custos indirectos (Q5); alergénios e rotulagem (Reg. UE 1169/2011 — é uma tabela e um ecrã);
importar fichas de folha de cálculo; receitas partilhadas entre estabelecimentos; e a detecção de **ciclos** no
grafo de semi-acabados para lá da profundidade 1 (Q3).

## Perguntas para o `domain-expert` — obrigatórias, e antes do `backend`

**Q1 — A fornada, e é a que pode mudar a fatia.** O `quantity_per_base_unit` é hoje *"por uma unidade **base** do
acabado"*, que é o que o `produzir()` implementa. Uma ficha de pastelaria escreve-se por **fornada** ("1 kg de
massa + 2 l de creme → 100 pastéis"), não "10 g de massa por pastel". Se a resposta for "por fornada", entra uma
coluna (`Recipe.batch_size`) e uma migração. *Defeito a reportar com a pergunta:* o cabeçalho de
`apps/recipes/api.py` diz *"a ficha é por uma unidade de **apresentação** do acabado"* e o
`IngredienteDaReceita.quantidade_lista` diz *"por unidade **base** de acabado"* — as duas frases não podem estar
certas ao mesmo tempo, e a implementação segue a segunda.

**Q2 — O `yield_factor` numa pastelaria a sério.** O que é que ele mede: merma de corte e cozedura, produto fora
de especificação, ou evaporação? A ADR 0026 d2 mete-o no divisor do consumo e **não** no custo final (100 pastéis
a 0,9 consomem massa para 111), logo a perda fica embutida no custo do acabado em vez de aparecer como quebra —
confirma-se, ou a perda de rendimento devia ser um movimento visível? E `yield_factor > 1` (sopa que ganha água,
massa que leveda) é caso real ou é sempre erro de dados? Hoje a validação só pede `> 0`.

**Q3 — Semi-acabados.** A ADR 0026 d5(5) diz *"não há restrição"*. Confirma-se que massa folhada → pastel são
**duas** produções (duas entradas no ledger, dois custos gravados) e nunca uma receita que explode em cascata? E
o que se faz quando A é ingrediente de B e B de A — hoje nada o impede, e o custo teórico sobre esse grafo não
termina.

**Q4 — O lote sintético do acabado e a validade, que cheira a sub-aviso de HACCP.** A ADR 0026 d5(4) grava
`expires_at=NULL` no lote do produto acabado. Um pastel de nata produzido hoje **tem** validade — `use_by`, em
horas. Com `NULL`, o acabado **nunca aparece** nos Alertas de validade: é a família exacta da dívida
`shelf_life_after_opening_days` nomeada na ADR 0034, e aqui é sobre mercadoria que se vende. A validade do
acabado deriva de quê — de um `shelf_life_days` no `catalog` (coluna nova), do lote de ingrediente mais antigo
que entrou (a regra da indústria), ou escreve-se à mão ao produzir? **É a pergunta que mais provavelmente abre
fatia própria.**

**Q5 — Mão-de-obra.** A ADR 0014 diz "não em v1". Aguenta-se agora que o objectivo escrito é *o dono ver o custo
do prato*? Um custo sem mão-de-obra é o **custo de matéria-prima** — que é um número real e é o que a restauração
chama *food cost* —, mas chamar-lhe "custo do prato" no ecrã é uma frase falsa. A pergunta é de **rótulo** antes
de ser de cálculo: o ecrã escreve "custo de ingredientes" e a 0014 aguenta-se, ou o dono quer a mão-de-obra e
isso é fatia própria?

**Q6 — O CMP é o custo certo para orçamentar?** A d3 usa o custo médio do estabelecimento. Um pasteleiro
orçamenta ao **último preço pago** ou ao **médio**? E o CMP **escrito** tem a diluição que a ADR 0032 (segunda
adenda) deixou nomeada como dívida maior — o `record_movements` divide por `Σ quantidade` **incluindo** as
entradas sem preço —, logo o custo teórico de uma receita **herda** essa subestimação. Esta é a primeira
superfície onde ela se lê como um número de gestão e não como uma linha de stock.

**Q7 — para o dono, não para o `domain-expert`.** Escrever a ficha é `owner|manager` (d5). Numa pastelaria quem
sabe a ficha é o pasteleiro-chefe, que pode ser `staff`. É assim que fica?
