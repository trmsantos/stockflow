# ADR 0032 — Quem vê os custos de stock: a ADR 0024 revogada por escrito

**Contexto.** A ADR 0024, decisão 4, deixou os endpoints de stock *"sem `IsStaff` ou papel
específico — qualquer membro ativo pode consultar; relatório é leitura, não escrita"*, e a ADR 0025,
decisão 3, repetiu-o nos movimentos manuais (*"sem separação de papéis"*). Em consequência,
`/stock/summary`, `/stock/by-location`, `/stock/by-product` e os três 201 de `stock/movements/*`
servem o custo de stock a qualquer membro do estabelecimento. Isso contradiz as quatro ADR seguintes:
a **0029** pôs o painel inteiro em `{owner}`, a **0030** pôs o `difference_eur` e o `GET /closing` em
`owner|manager`, e a **0031** (segunda adenda) decidiu que os euros de uma receção são de
`owner|manager` **com a chave ausente**. O `accounts.api` já tem a regra num sítio
(`PAPEIS_QUE_VEEM_EUROS`, `ve_euros`) e o assistente já a aplica desde 2026-10-16
(`test_o_staff_nao_ve_euros_no_saldo_nem_nos_movimentos`): o `saldo_de_artigo` e o
`movimentos_de_artigo` recusam ao `staff` exactamente os números que o HTTP lhe entrega. **A mesma
informação tem duas portas e duas respostas**, e a porta aberta é a do ecrã mais usado da app. O dono
confirmou a incoerência a 2026-10-20 e escolheu tratá-la em fatia própria. **Toca em stock e em
custos: consultar `domain-expert`.**

**Decisão 1 — O custo de stock é de `owner|manager`. A ADR 0024 d4 e a ADR 0025 d3 ficam revogadas
nessa parte.** O argumento da 0024 é real e merece ser dito antes de cair: o custo de stock é
informação **operacional** de quem mexe no stock — ajuda a decidir o que se deita fora primeiro, e
quem sabe que o azeite custa 9 €/l trata-o de outra maneira —, e o CMP não é o preço que o
fornecedor cobrou: é uma média já misturada entre fornecedores e meses. Cai por três razões, e a
primeira é medida e não opinativa. **(a) A distinção não sobrevive aos dados.** O `unit_cost` de uma
entrada é `line_total / quantity_received` (ADR 0023 d3, e o
`test_extracao_de_faturas.py::unit_cost == 0.000693` prova-o ao décimo milionésimo); num artigo com
um fornecedor e uma receção — o caso normal de uma padaria em quase todo o catálogo — o "custo
interno" **é**, ao cêntimo, a linha da fatura que a ADR 0031 acabou de esconder. Esconder a fatura e
servir o custo de stock é esconder um número e servir o mesmo número. **(b) O caminho irmão já
decidiu.** O porto do `agents` filtra-o por papel há cinco dias; manter o HTTP aberto é ter duas
definições da mesma política, que é a origem desta família inteira de defeitos. **(c) Os factos
mudaram debaixo da decisão**, como na adenda da 0031: a 0024 escreveu a permissão quando o ledger não
tinha linhas e o custo não tinha quem o escrevesse. Uma permissão inócua por acidente deixa de o ser
quando os dados por trás dela mudam. O que o argumento operacional ganha está na decisão 3.

**Decisão 2 — Campo a campo, e a reconstrução por multiplicação fecha-se dos dois lados.** A política
é sobre o **facto** (o custo de stock), não sobre o nome do campo — os nomes destas quatro rotas vão
mudar quando o ecrã for ligado, e a regra tem de sobreviver a isso. Sai do payload de quem não vê
euros:

| rota | sai | fica |
|---|---|---|
| `GET /stock/summary` | `unit_cost`, `total_value` | `product_id`, `product_name`, `quantity` |
| `GET /stock/by-location` | `unit_cost`, `total_value` | `product_id`, `product_name`, `location_*`, `lot_code`, `expires_at`, `quantity` |
| `GET /stock/by-product` | `unit_cost`, `total_value` | os mesmos |
| `GET /stock/alerts` | — (hoje não traz euros) | tudo |
| `POST /stock/movements/waste` · `/adjustment` (201) | `unit_cost` | `movement_id`, `product_name`, `location_name`, `lot_code`, `quantity`, `created_at` |
| `POST /stock/movements/transfer` (201) | `unit_cost` nas **duas** pernas | `transfer_id`, `movements[].{movement_id,type,product_name,location_name,lot_code,quantity}`, `created_at` |

**Os dois têm de sair juntos**, e é a lição das bases de IVA do QR na ADR 0031: ali a soma
reconstruía o total, aqui a multiplicação reconstrói-o nos dois sentidos — `unit_cost × quantity`
devolve o `total_value`, e `total_value / quantity` devolve o `unit_cost` com mais casas do que o
original. Esconder um só é teatro. **O que fica, e porquê**: as quantidades e o lote são o trabalho
de campo; o `expires_at` e a ordem FEFO são decididos no servidor e não dizem preço nenhum; e o
marcador qualitativo de **"preço desconhecido"** (ADR 0024 d5, caso 3) fica visível para todos — é o
reflexo da `vat_rate` da 0031 (*"uma taxa é 6, 13 ou 23 e não diz quanto custou nada"*) e do
`custo: "conhecido"` que o porto do `agents` já dá ao `staff`: é qualidade de dados, não um euro.
Fica como **booleano** e nunca como `unit_cost: 0`, que seria o zero mentiroso por outra porta.

**Decisão 3 — O trabalho de campo não perde nada, porque quem calcula é o servidor.** Contar,
receber, registar perdas e transferir continuam todos abertos ao `staff`, e nenhum deles precisa de
um custo no cliente: o `waste`, o `adjustment` e o `transfer` escolhem o lote por FEFO e lêem o custo
do nível **dentro** do serviço (ADR 0025 d5), o corpo de entrada nunca traz dinheiro e nunca trouxe,
e o fecho da contagem — o único sítio onde o custo decide um número que fica escrito — já é de
`owner|manager` desde a 0030. A regra geral: onde um custo for preciso para a operação funcionar, o
servidor calcula-o e devolve o resultado; nunca se manda o custo para o cliente calcular. É o mesmo
princípio que a ADR 0013 d5 escreveu para o painel (`share`, `scale_max_eur`) por outra razão.

**Decisão 4 — Uma definição só: o `SemEurosParaQuemNaoVe` sobe para o `accounts.api`, e três rotas
que não passam por serializer nenhum passam a passar.** A mecânica existe e está certa
(`CHAVE_DE_EUROS` + `SemEurosParaQuemNaoVe` em `purchasing/serializers.py`, alimentados pelo
`ve_euros`), mas vive no **único ficheiro que o `inventory` não pode importar**: a aresta permitida é
`purchasing → inventory.api` e não o contrário, e um `serializers.py` não é porta de módulo nenhum.
Vai para junto da regra que já lá está — `PAPEIS_QUE_VEEM_EUROS` e `ve_euros` no `accounts/api.py`,
pela razão que esse ficheiro já tem escrita: *"uma regra de autorização escrita em três sítios é uma
que um dia só se corrige em dois"*. O `purchasing` passa a importá-la de lá e nenhum contrato de
import-linter muda, porque toda a gente já importa `accounts.api`. **E a mecânica não chega sozinha**:
os três 201 de `stock/movements/*` montam um `dict` na view e devolvem-no sem passar pelo
`StockMovementResponseSerializer`, que só está declarado no `extend_schema` — um mixin de serializer
não os alcançaria, e no caso da transferência o serializer declarado nunca descreveu o corpo que sai
(não tem `transfer_id` nem `movements`). Passam os três a ser serializados, e o 201 da transferência
ganha o serializer que lhe falta. **Sem `euros_visiveis` no payload**: o cliente já sabe o papel pela
sessão (ADR 0013 d6) e uma segunda fonte para a mesma verdade é o que a 0013 d5 recusa.

**Decisão 5 — O `difference_eur` da contagem passa de `null` a ausente.** A ADR 0030 d1 escolheu
`null` e nomeou o preço: *"`null` passa a dizer duas coisas — ainda não contado e não te é
mostrado"*. A chave ausente diz a segunda sem apagar a primeira (`difference` presente e
`difference_eur` ausente é inequívoco), é a forma que o `CLAUDE.md` e a 0031 fixaram, e sem isto o
`inventory` fica com duas formas da mesma política no mesmo módulo — exactamente o que a decisão 4
acabou de desfazer. Custa uma linha de Zod, e é a linha que tem de ser escrita: o
`linhaDeContagemSchema` declara `difference_eur: decimal.nullable()` **sem `.optional()`**, e em Zod
isso aceita `null` mas exige a chave — o ecrã de contagens não degradava para o `staff`, **rebentava**,
que é o defeito exacto da adenda da 0031 repetido.

**Decisão 6 — Isto é decidido antes de ligar o ecrã, e é por isso que vale a pena.** `/stock/levels`,
`/stock/movements` e os dois de `/stock/alerts` são a última superfície servida por `frontend/fixtures/`
e são ligados a seguir, na mesma fatia. Os schemas Zod são escritos à mão e já declaram quatro campos
de dinheiro: `resumoDeStockSchema.stock_value_eur`, `alertaSchema.value_eur`,
`resumoDeAlertasSchema.wasted_today_eur` e `.wasted_week_eur`, e `desperdicioSchema.value_eur`. **Os
cinco caem na decisão 1 e nascem `.optional()`**, e a razão de não serem uma excepção é a mesma
reconstrução: uma linha de desperdício traz `quantity` ao lado de `value_eur`, logo a divisão dá o
custo unitário do artigo; e com uma só quebra no dia, o `wasted_today_eur` dá-o sozinho. O que o ecrã
mostra a quem não vê euros é a mesma lista sem a coluna — nunca um traço, nunca um zero (é o que o
`difference_eur` da contagem já faz). O que esta ADR **não** decide é a forma desses quatro recursos:
o `GET /stock/summary` de hoje e o `resumoDeStockSchema` do cliente são dois recursos diferentes no
mesmo caminho, e reconciliá-los é a fatia seguinte.

**Decisão 7 — ADR nova e não adenda, e a razão é de leitura.** O precedente da casa é a adenda (a
0031 emendou a 0021 d9 no fim do próprio ficheiro) e serve quando *"uma fatia tornou necessária uma
mudança a um facto de outra ADR"*. Aqui são **duas** ADR revogadas (0024 d4 e 0025 d3) — uma adenda no
fim da 0024 não é encontrada por quem lê a 0025 —, a decisão não é consequência de outra fatia (o dono
pediu-a como fatia própria), e metade do conteúdo não é correcção de nada: a mudança de casa da
mecânica, a forma do `difference_eur` e o contrato do ecrã seguinte. Uma adenda que carrega isso é uma
ADR com outro nome.

**Alternativas.** *Manter a 0024 (o custo é operacional)* — é o argumento sério do outro lado e cai na
decisão 1(a): num artigo de uma receção o CMP é a linha da fatura, ao cêntimo. *Esconder só o
`total_value`* — `unit_cost × quantity` devolve-o. *Esconder só o `unit_cost`* — `total_value /
quantity` devolve-o com mais casas. *`null` em vez de ausente* — lê-se no ecrã como "este artigo não
tem custo", que é um facto diferente e que acontece mesmo (artigo sem preço conhecido). *Zero* — uma
afirmação falsa sobre o preço. *403 no endpoint inteiro, como o `/reporting/month`* — o 403 é certo
quando o **recurso** é dinheiro; aqui o dinheiro é uma coluna, as rotas `stock` e `alertas` são
`TODOS_OS_PAPEIS` no `menu.py`, e negá-las tirava o ecrã a quem mais o usa. *Um `euros_visiveis` no
payload* — segunda fonte para o que a sessão já diz. *Uma cópia do mixin no `inventory`* — duas
definições da mesma política, que é a doença. *O mixin em `apps/shared`* — o `shared` não importa
módulos e a regra vive no `accounts`; separar o mecanismo da política é como se chega outra vez a duas
versões dela. *Deixar o `difference_eur` a `null`* — duas formas da mesma política dentro do mesmo
módulo, uma semana depois de as termos unificado.

**Consequências.** **Zero tabelas novas, zero alteradas, zero migrações, zero políticas RLS, zero
tarefas Celery, zero eventos** — é serialização e permissão. `CHAVE_DE_EUROS` e
`SemEurosParaQuemNaoVe` mudam de ficheiro e o `purchasing` passa a importá-los do `accounts.api`;
nenhum contrato de import-linter muda. Seis serializers do `inventory` ganham o mixin, os três 201
passam a ser serializados e nasce o serializer de saída da transferência. Sete campos passam a
opcionais no `schema.yml` → `uv run manage.py spectacular` e `pnpm gen:api`, com o gate de diff do CI.
No cliente, **um `.optional()` que não é opcional**: `difference_eur` no `linhaDeContagemSchema`, e os
cinco campos da decisão 6 quando os schemas do ecrã seguinte forem ligados. Testes nos dois sentidos
por rota, no molde do `test_rececoes.py::test_o_colaborador_nao_recebe_as_chaves_de_dinheiro`, mais um
que enumera as chaves de dinheiro do módulo e falha quando alguém acrescentar a oitava. **Dois
defeitos encontrados ao listar os campos, nomeados aqui e resolvidos por quem reescrever estas
queries**: o `stock_summary` anota `total_quantity`/`avg_unit_cost` e o serializer declara
`quantity`/`unit_cost`, logo o DRF omite um e manda o outro a `null` — hoje o endpoint entrega o
`total_value` e **não** entrega a quantidade; e o `Case` sobre `quantity` dentro do
`values().annotate()` entra no `GROUP BY` e desfaz a agregação por artigo. O `by-location` e o
`by-product` têm o mesmo buraco no `quantity`. Não são desta ADR, mas é com eles que o ecrã vai ser
ligado.

**Fora de âmbito, por extenso.** A forma dos quatro recursos do ecrã seguinte (`/stock/levels`, o
`/stock/summary` do cliente, `/stock/movements`, `/stock/alerts/*`) e a reconciliação do caminho
`/stock/summary`, que hoje tem dois significados; os dois defeitos de query do parágrafo acima; um
quarto papel ou uma permissão por campo que separasse "custo de stock" de "preço de fornecedor" (é a
Q7, e não há ordem entre papéis neste projecto); configurar por tenant quem vê euros (a ADR 0011
proíbe o motor genérico); mascarar por categoria de artigo ("o `staff` vê o custo do pão e não o das
trufas"); esconder quantidades de alguém — nunca, as quantidades **são** o produto; registo de
auditoria de quem consultou custos; exportação; e o `reporting` e o `agents`, que já estão certos e
não se tocam.

**Consultar `domain-expert`.** (a) O marcador de "preço desconhecido" é um booleano por linha ou vale
só no agregado — e um artigo com dois lotes, um com custo e outro sem, mostra o quê a quem não vê
euros? (b) A ordem FEFO que o painel mostra é derivada de validade e não de custo — confirmar que
nenhuma ordenação servida ao `staff` é por valor, porque uma lista ordenada por euros é os euros sem o
número. (c) O `wasted_today_eur` é o número que mais muda o comportamento de quem deita fora: há um
agregado de desperdício defensável para o `staff` que não reconstrua o custo unitário (por exemplo,
só em quantidade por artigo), ou a resposta certa é não haver nenhum?

---

## Adenda (2026-10-21) — o que a implementação e a revisão mudaram

**O marcador não é booleano: são três palavras e uma cobertura.** A decisão 2 escrevia *"fica como
booleano"* e deixava a pergunta (a) ao `domain-expert`. Ele respondeu, e a resposta mudou a forma:

- **as mesmas três palavras do porto do `agents`** — `conhecido | estimado | desconhecido`
  (`ESTADOS_DO_CUSTO`, com teste que as compara com `agents.tools._custo`). Um booleano novo aqui
  **recriava exactamente a divergência que esta ADR fecha**: o `staff` já recebia três estados por
  aquela porta, e uma quarta palavra era uma segunda política;
- **o facto é por lote, não por artigo** (`StockDetail.cost_status`): *"esta entrada ficou sem
  preço"* é defeito de uma receção e corrige-se nessa receção;
- **no agregado não há palavra nenhuma** — há **cobertura**: `StockSummary.quantity_without_cost`.
  É **quantidade e não euro**, e diz o que interessa, que é se a subestimação é de 5 % ou de 95 %.
  Não se criou *"parcialmente desconhecido"*: seria a quarta palavra por outro nome.

`estimado` fica **nomeado como dívida**: nenhum caminho escreve `cost_is_estimate=True` hoje, logo o
estado é inalcançável. Está no vocabulário porque o vocabulário é partilhado, não porque funcione.

**`preco_desviado` mantém-se visível a todos os papéis — decisão do dono, 2026-10-21.** A revisão
nomeou-o, e bem: é um limiar sobre preço (±30 % contra o histórico), da mesma família do
`reason_required_above_eur` que esta ADR foi fechar, e o `discount_pct` — também uma percentagem —
já está escondido. Fica assim por duas razões: limita um **rácio** e nunca um **nível**, o que é
estritamente mais fraco do que um limiar em euros; e quem recebe a mercadoria é quem pode dizer *"este
preço está estranho"* no momento em que ainda dá para perguntar ao fornecedor. **Está considerado e
mantido de propósito** — uma revisão futura que o levante outra vez deve ler isto primeiro.

**A política continua escrita em dois sítios, e agora dói se divergirem.** O `agents/tools.py` tem o
seu `OWNER_E_MANAGER`, independente do `PAPEIS_QUE_VEEM_EUROS`; os dois conjuntos são iguais e **nada
o obrigava**. Não se unificaram os símbolos — o `agents` está fora do âmbito e a aresta é matéria do
import-linter — mas acrescentou-se o teste que prende a igualdade.

**Verificado no SQL e não só nos testes.** A revisão confirmou `GROUP BY 1, 2` no `stock_summary` (o
`Case` ficou dentro do `Sum`, logo um artigo com N custos dá **uma** linha) e `ORDER BY` sem nenhuma
expressão de valor nas quatro rotas. Não existe `OrderingFilter` nem parâmetro de ordenação em
`apps/` — o cliente não escolhe a ordem em lado nenhum.

**Ficou em aberto, com o `domain-expert` consultado:** o `unit_cost` era `valor_total ÷ quantidade
total`, incluindo a parte sem preço — 30 un a 2,00 € mais 70 un sem preço davam **0,60 €/un**.
Mantinha a invariante `unit_cost × quantity == total_value`, que é o que fecha a reconstrução por
aritmética, mas era um número que alguém lê para decidir compras. A resposta está na adenda seguinte.

---

## Adenda (2026-10-21, a seguir) — o custo diluído era um defeito, e corrigiu-se o divisor

**O `domain-expert` foi inequívoco: não era uma escolha de produto.** O diluído não é uma grandeza de
gestão — nenhum manual, nenhum TOC e nenhum ERP a calcula —, logo não tem nome honesto possível:
*"dividem-se euros por unidades que não contribuíram com um cêntimo"*. O numerador era a soma **só da
parte com preço** e o denominador somava **tudo**; o numerador certo exige o denominador certo.

**A correcção é uma linha:** `unit_cost = total_value ÷ (quantity − quantity_without_cost)`. O mesmo
princípio já estava escrito do outro lado da casa, no `purchasing.selectors.linhas_com_preco_confirmado`
(ADR 0028): *"uma linha sem preço calculável não é um preço de zero"*.

**A invariante sobrevive, que é o que não podia partir.** Passa a ser `unit_cost × (quantity −
quantity_without_cost) == total_value`, e continua a fechar a reconstrução por aritmética: as duas
pontas do divisor são **quantidades**, as duas estão no payload de quem não vê euros, e esconder as
duas chaves de euro continua a não deixar reconstruir nenhuma delas. Mudou o divisor, não a política
— a decisão 2 fica intacta.

**Divisor a zero — e as duas formas são diferentes de propósito.** Num artigo em que *toda* a
quantidade está sem preço, o `unit_cost` é `null` ("não se conhece custo") e o `total_value` é
`0,00`, porque é mesmo a soma de nada: é uma afirmação verdadeira, somável com o resto do painel, e a
cobertura (`quantity_without_cost == quantity`) distingue-a de mercadoria oferecida. Os dois zeros
não se confundem porque só um deles existe. E `null` continua a não ser a **chave ausente**: `null` é
"não se conhece custo" e a ausência é "não te compete" — é a distinção que as alternativas desta ADR
já tinham feito, e que um `unit_cost` ausente aqui apagava.

**O cálculo só existia num sítio**, confirmado: `inventory.selectors._custo_unitario`, usado pelas
três rotas do painel através do `_linha_de_stock`. O porto do `agents` (`_custo`) multiplica linha a
linha e não divide; o `reporting` soma `quantity × unit_cost` e não divide; o `by-location` e o
`by-product` passam pela mesma função corrigida, e nelas a linha é **um lote** — tem preço ou não
tem, e por isso nunca puderam diluir.

**Fica nomeado, e é maior do que esta fatia:** o CMP **escrito** tem a mesma forma de diluição. O
`inventory.services.record_movements` recalcula `unit_cost = Σ(quantidade × custo) ÷ Σ(quantidade)`
sobre as entradas, com as entradas sem preço no denominador, e grava-o no `StockLevel` e no
`ProductCost`. Uma receção sem preço baixa o CMP do nível em vez de não lhe tocar. Não se corrigiu
aqui — é um caminho de **escrita** (ADR 0023), muda números já gravados e alcança o fecho de
contagens, o custo teórico das receitas e o `reporting` —, mas a correcção do painel não o resolve e
quem ler o painel e a projeção lado a lado vê dois custos diferentes para o mesmo artigo.
