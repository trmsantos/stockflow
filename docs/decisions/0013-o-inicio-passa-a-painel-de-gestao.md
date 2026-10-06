# ADR 0013 — O Início passa a painel de gestão: dois módulos novos, um módulo-sumidouro, e o primeiro ecrã restrito por papel

**Contexto.** Direcção nova do dono do produto (2026-10-06), e é a maior expansão de âmbito desde o
início: a aba Início deixa de ser a lista das perguntas da manhã e passa a um painel de gestão com
gráficos — desperdício, o que foi vendido, balanço de lucro/prejuízo, salários e cargos dos
colaboradores, faturação contra gastos. Medido, o que existe é **metade disto e a metade mais fácil**:
desperdício em euros com motivo, autor, hora e localização; valor de stock; entradas de fornecedor com
linhas de fatura (que são os **gastos em produtos**); contagens; e os papéis de pertença
`owner|manager|staff`, que são de **autorização**. Não existe nada de vendas, de receita nem de
salários — nem tabela, nem módulo, nem pergunta respondida. E o backend tem um módulo implementado
(`accounts`): os quatro ecrãs de hoje vivem sobre o servidor de fixtures da ADR 0008, decisão 3.

O dono escolheu, numa pergunta explícita, **construir o layout todo já sobre as fixtures**, com o
backend atrás, e os gráficos em **SVG escrito à mão** com os tokens do `DESIGN.md` — sem biblioteca de
gráficos, para não trazer o aspecto default de painel gerado. Esta ADR não discute essa escolha:
decide onde é que as coisas vivem, qual é o contrato que as fixtures e os serializers vão partilhar, e
uma coisa que não tem precedente nenhum neste repositório. **Este é o primeiro ecrã em que os próprios
dados são restritos por papel.** Até aqui o papel só mudava a projecção do menu, e a ADR 0011 diz —
bem — que "esconder é apresentação, não autorização". Um painel com salários visto por uma conta
`staff` é uma fuga de dados pessoais, não um detalhe de UI.

**Esta ADR foi reescrita depois da consulta de domínio, e duas coisas mudaram de fundo.** A primeira
está na decisão 4 e é uma decisão minha revogada. A segunda saiu desta ADR para a **ADR 0014**: a
produção própria conta duas vezes no ledger, o que bloqueia o painel e não é problema do painel —
fazer pastéis sai como `consumption` e entra como `receipt`, e somar as saídas de stock conta os
ingredientes e o produto acabado. A ADR 0014 acrescenta `production_out`/`production_in` e fixa, numa
tabela de nove linhas, **o que cada tipo de movimento significa para o dinheiro**. Esta ADR cita essa
tabela e não a repete. **Sem a 0014 aplicada, o campo `goods_consumed_eur` não é calculável** e o
painel mostra compras e cala-se sobre consumo.

**Decisão 1 — Vendas são o módulo `sales`, irmão de `purchasing`, e nunca a mesma tabela com uma
coluna de direcção.** Partilham a *forma* (um documento, um terceiro, linhas com IVA, totais) e nada do
*significado* nem do grafo: `purchasing` escreve no ledger depois de confirmação humana e é o destino
do `agents` (extração de faturas); `sales` v1 **não escreve no ledger** e não tem extração. Uma tabela
só com `direction: in|out` põe receita e despesa na mesma relação, e um `filter(direction=...)`
esquecido num painel de lucro/prejuízo troca o sinal do resultado — é o pior defeito possível neste
ecrã e é o único que uma fronteira de módulo evita de graça. O nome importa por outra razão: `billing`
já existe e é **nós a cobrar ao cliente** (planos por utilizadores/localizações); isto é **o cliente a
faturar aos clientes dele**. São dois assuntos com uma palavra, e confundi-los uma vez é confundi-los
para sempre. E `sales` v1 **regista** vendas para gestão: o StockFlow não emite faturas, não tem série
certificada nem SAF-T, e assumir o contrário é outro produto.

Duas coisas que a revisão de domínio fixa na forma das tabelas. **O IVA guarda-se por taxa**: com 6%,
13% e 23% na mesma venda o bruto não se reparte para trás, logo `sales_saleline` leva `vat_rate`,
`net_eur` e `vat_eur`, e os totais do documento são somas. E **uma linha de venda em v1 é uma linha de
valor, não uma linha de stock** — é a consequência directa de o `sales` não escrever no ledger, e é o
que permite que um fecho de caixa diário de POS entre como um documento com uma linha por taxa, sem
inventar artigos que ninguém escolheu.

**Decisão 2 — Salários e cargos são o módulo `people`, e o cargo de RH **não** é o papel de acesso.**
Um "pasteleiro" ou um "chefe de turno" é uma função; `owner|manager|staff` é o que o pedido pode fazer.
No mesmo campo, promover alguém muda-lhe as permissões — e o `Membership` é a tabela que *é* a
autorização, lida pelo `TenantMiddleware` no caminho crítico de **todos** os pedidos (ADR 0007). Três
razões para não ser uma extensão do `accounts`, e qualquer uma bastava: (a) o `accounts` é a base do
grafo — todos o importam, ninguém é importado por ele — logo pôr folha de salários lá dá folha de
salários a todos os módulos; (b) o `accounts` não depende de nenhum módulo de domínio por contrato, e
custo por período é domínio; (c) **não toda a pessoa que se paga tem conta**. A ajudante de cozinha que
nunca faz login tem cargo e salário e não tem `User` nem `Membership`; com o salário como coluna da
pertença, pagar a alguém obriga a criar-lhe credenciais, o que é inventar acessos por razões de
contabilidade. `people` tem `JobRole` (cargo), `Employee` (com `user` anulável, referência por string,
sem import) e `Compensation`. O cargo e o papel cruzam-se num sítio só: no ecrã, lado a lado, porque
são as duas colunas que a pessoa quer ver — e não na mesma coluna.

O `Compensation` guarda o que o **custo-empresa** precisa, tudo `Decimal` e com a conta no servidor:
`gross_monthly_eur`; `annual_months` (inteiro, default 14 — e **não** uma flag por subsídio, porque há
contratos com os duodécimos já dentro do bruto e é essa a confusão a evitar);
`meal_allowance_per_day_eur` + `meal_allowance_mode` (`cash|card`) + `work_days_per_month`, porque o
dono sabe "5,50 € por dia" e não sabe o mensal; `social_security_rate` (default `0.2375`) e
`work_accident_insurance_rate` (~`0.0125`) como **campos e não constantes**, que é a correcção mais
importante desta lista — há taxas reduzidas, agravamentos por contrato a termo e tarifas por CAE, e uma
constante em código transforma uma excepção contratual num valor errado sem sítio onde o arrumar;
`other_monthly_cost_eur` + `other_cost_note`; `fte`, porque meio-horário é regra numa pastelaria; e
`effective_from`/`effective_to`. Os subsídios de férias e de Natal entram **sempre em duodécimos no
painel**, independentemente de como são pagos: senão junho e novembro parecem catástrofes e os outros
dez meses parecem bons, que é o mesmo argumento com que esta ADR recusa ratear um salário por sete
dias. Ficam **fora** o IRS retido e os 11% de TSU do trabalhador — já estão dentro do bruto, e somá-los
inflaciona o custo em ~11%; e o FCT/FGCT, sem adesões novas desde 2023.

Uma simplificação assumida e com o erro orçamentado: o subsídio de alimentação entra **por inteiro como
custo** e o v1 **não** calcula a TSU sobre o excesso acima do limite legal de isenção. O limite difere
entre dinheiro e cartão e muda com cada Orçamento do Estado, logo não pode viver em código; mas também
não justifica hoje a primeira tabela de **dados de referência partilhados** do repositório (ADR 0005:
sem `tenant_id` e sem política, numa lista fechada do `tests/test_db_roles.py`), porque o erro é 23,75%
*do excesso* e é zero para quem paga até ao limite. Quando entrar, entra nessa forma e com histórico por
`valid_from` — um limite sem histórico reavaliaria dezembro com a regra de janeiro, que é o erro que a
ADR 0014 proíbe para o custo de stock.

**Decisão 3 — A agregação vive num módulo-sumidouro, `reporting`: importa `api.py`s, não tem
tabelas, não tem `api.py`, e um contrato novo impede que alguém o importe.** É a decisão difícil, e o
precedente é a ADR 0011, que escolheu dois endpoints em vez de um agregado — "um endpoint de bootstrap
é como um monólito modular cria uma vista-deus". Aqui essa saída **não existe**, e a razão é medida:
qualquer rácio ou resultado é uma subtracção de euros, e o cliente não pode somar dinheiro (os
montantes são `Decimal` em string, e "nenhuma conta é feita em `number` no cliente" é regra escrita no
`features/inventory/schemas.ts`). Um cliente que junta quatro respostas é um cliente a fazer aritmética
de euros em JavaScript. Logo alguém no servidor cruza os quatro módulos, e o único sítio onde isso não
inverte o grafo é um módulo cuja **única** aresta é de saída. `reporting` não é uma vista-deus porque o
perigo nunca foi importar interfaces públicas — é passar a ser dependência dos outros. Fica fechado com
mecanismo e não com intenção: um 14.º contrato `forbidden` com os outros nove módulos como
`source_modules` e `apps.reporting` como proibido. Sem tabelas não tem migrações nem política própria, e
**está coberto pela RLS sem possuir nenhuma**, porque toda a query que faz nasce dentro do âmbito do
pedido, num `selectors.py` que chama `api.py`s. Sem `api.py` não tem interface pública, e a ausência é a
decisão. Regra de admissão, para o módulo não se tornar o sítio onde vão todas as leituras: **entra em
`reporting` uma leitura que cruze dois ou mais módulos; uma leitura dentro de um módulo fica no
`selectors.py` dele.**

É essa propriedade que decide onde param os **custos fixos mensais** (renda, energia, água, gás, TPA,
licenças, contabilista), que a revisão de domínio põe no v1 como condição para a palavra "resultado" ser
defensável. Não vão para o `reporting`: uma tabela lá dava-lhe `models.py`, migrações, política,
`services.py` e endpoints de escrita, e a propriedade que se perdia — ler-não-escrever — é a que
sustenta tudo nesta decisão. Também não justificam um módulo novo só para si. Vão para o
**`purchasing`**, em `purchasing_othercost` (`month`, `category` de uma lista fechada, `amount_eur`,
`note`), porque o `purchasing` já é o módulo do dinheiro que sai para terceiros e já tem o conceito de
linha com valor e sem mercadoria (`especieDeLinhaSchema`, `charge`). O nome do módulo diz "compras" e a
renda não é uma compra de mercadoria; o âmbito dele já era despesa e não aprovisionamento, e isso é
menos mau do que qualquer das outras três saídas. A aresta `reporting → purchasing.api` já existe.

**Decisão 4 — As duas bases de custo não são uma escolha: são três linhas no ecrã, e a terceira é a
diferença.** Esta decisão **revoga** o `cost_basis=<consumption|purchases>` que a primeira versão desta
ADR propunha, e vale a pena dizer o que estava errado, porque não era o valor — era a classificação.
Tratei "compras ou consumo?" como uma pergunta de uma resposta só, e apliquei-lhe o padrão da ADR 0008
decisão 3 (mostrar as duas variantes e deixar a reacção do dono decidir). Esse padrão é para perguntas
onde **uma** das respostas é a certa — bloquear ou avisar. Aqui as duas são verdadeiras e dizem coisas
diferentes: compras é dinheiro que saiu, consumo é o que saiu do stock. Era um "e" classificado como um
"ou", e um interruptor sobre um "e" esconde a informação mais útil das três.

```
Vendas                    8 240 €
Compras a fornecedores    5 130 €   ← dinheiro que saiu
Mercadoria consumida      3 980 €   ← o que saiu do stock, ao custo gravado no movimento
Variação de stock        +1 150 €   ← encheu-se a despensa em 1 150 €
```

Três razões, e a primeira resolve o maior risco deste ecrã melhor do que o parâmetro resolvia: **o mês
do stock-up natalício deixa de poder ser lido como prejuízo, porque aparece nomeado** — o dono vê o seu
próprio gesto em vez de um resultado estranho. A segunda é que a identidade fica **verificável no
próprio ecrã**, que é a coisa mais próxima de uma prova que este produto consegue dar sobre dinheiro. A
terceira é que dois valores atrás de um parâmetro são duas respostas para "quanto gastei?", e o primeiro
bug reportado seria "o painel diz 5 130 € num sítio e 3 980 € noutro".

**A identidade tem três termos e não dois, e isto é uma correcção à forma como me foi pedida.**
`compras − consumo == variação de stock` só fecha se o consumo contiver tudo o que saiu; mas o §4 abaixo
separa a quebra desconhecida numa linha própria, precisamente porque é accionável sobre outra coisa.
Logo o que o servidor afirma, ao cêntimo, é:

> `stock_change_eur == purchases_eur − goods_consumed_eur − unknown_shrinkage_eur`

com `purchases_eur` líquido de devoluções e notas de crédito do período, `goods_consumed_eur` a conter o
desperdício, e tudo valorizado ao custo gravado no movimento (ADR 0014). Isto é um **teste**, não uma
frase: uma identidade que o ecrã mostra e que a suite não verifica é uma promessa de que um dia se vê um
cêntimo a não fechar num ecrã que o dono está a mostrar a outra pessoa.

**Decisão 5 — O contrato: três endpoints, dois grãos de período, e o cliente desenha sem compor.**
Caminhos em `/api/v1/reporting/`, campos em inglês como os vizinhos (`/stock/*`, `/receipts/*`),
agregação em SQL (`GROUP BY`) e nunca um ciclo em Python sobre o ledger. **Nenhum rótulo viaja no
arame**: o servidor manda ids de uniões fechadas e as palavras vivem no `vocabulario.ts` da feature, que
é onde a copy de produto vive e onde o `Record` sobre a união gerada falha nos dois sentidos. (A
primeira versão desta ADR mandava `label` nas séries; era uma segunda fonte para a mesma palavra.)

```python
# GET /reporting/summary?period=<today|7d|30d|month|prev_month>
#   permissão: PertenceAoTenant + TemPapel.exige(OWNER, MANAGER)
@dataclass(frozen=True, kw_only=True, slots=True)
class PeriodOut:                      # o período resolvido, ecoado: mostrar a fronteira, não esconder
    key: str; since: datetime; until: datetime; business_day_starts_at: str   # "04:00"
@dataclass(frozen=True, kw_only=True, slots=True)
class CostComponentOut:               # o cliente desenha; não compõe e não soma
    id: str                           # purchases|goods_consumed|waste|unknown_shrinkage|payroll|other
    amount_eur: Decimal; share: Decimal
    is_part_of_total: bool            # o servidor decide o que soma
    part_of: str | None               # o id de quem o contém: "dos quais 420 € foram desperdício"
@dataclass(frozen=True, kw_only=True, slots=True)
class DataQualityOut:                 # o painel declara o que não sabe — ver a decisão 7
    consumption_registered: bool
    purchases_awaiting_invoice_eur: Decimal
    last_count_at: datetime | None
    revenue_source: str               # none|manual|pos
@dataclass(frozen=True, kw_only=True, slots=True)
class SummaryOut:
    period: PeriodOut
    revenue_net_eur: Decimal; revenue_gross_eur: Decimal; revenue_basis: str
    purchases_eur: Decimal            # líquido de IVA dedutível e de notas de crédito
    goods_consumed_eur: Decimal       # contém o desperdício (ADR 0014)
    stock_change_eur: Decimal         # a identidade da decisão 4, afirmada ao cêntimo
    waste_eur: Decimal                # decomposição de goods_consumed, nunca parcela a somar
    unknown_shrinkage_eur: Decimal    # o líquido dos adjustment de contagem
    goods_cost_ratio_pct: Decimal | None     # consumo/vendas; None quando vendas == 0
    stock_value_eur: Decimal
    costs: list[CostComponentOut]
    waste_by_reason: list[WasteByReasonOut]  # {reason, amount_eur, share, movements}, ordenada
    data_quality: DataQualityOut

# GET /reporting/series?period=…   (mesma permissão)
class SeriesOut:
    period: PeriodOut; granularity: str      # day|week, derivada do período pelo servidor
    buckets: list[BucketOut]                 # {since, until} — uma vez, não por série
    scale_max_eur: Decimal                   # o máximo do eixo vem do servidor
    series: list[SerieOut]                   # {id, unit:"eur", total_eur, points}
                                             # point = {value_eur, share}  (share = value/scale_max)
# GET /reporting/month?month=YYYY-MM
#   permissão: PertenceAoTenant + TemPapel.exige(OWNER)
class MonthOut:
    month: str; since: datetime; until: datetime; business_day_starts_at: str
    closed: bool; days_elapsed: int; days_in_month: int
    # os mesmos campos de mercadoria do SummaryOut, com o grão do mês de negócio
    payroll_eur: Decimal; payroll_basis: str          # employer_cost (default) | gross
    payroll_source: str                               # contractual | actual
    payroll_breakdown: list[PayrollPartOut]           # {id, amount_eur}: base, TSU, subsídios,
                                                      # alimentação, seguro
    roles: list[RoleCostOut]                          # {role_id, name, headcount, payroll_eur, share}
    other_costs: list[OtherCostOut]                   # {category, amount_eur, note}
    cost_total_eur: Decimal                           # só aqui, porque só aqui há salários
    result_eur: Decimal
    result_excludes: list[str]                        # depreciation|financing|income_tax|
                                                      # owner_compensation — ver a decisão 6
    goods_cost_ratio_pct: Decimal | None
    labour_cost_ratio_pct: Decimal | None
    prime_cost_pct: Decimal | None                    # mercadoria + pessoal sobre vendas
    data_quality: DataQualityOut
```

`period` e `month` são **parâmetros diferentes de propósito**: um salário é um facto mensal, e ratear 30
dias por uma janela de 7 inventa precisão que ninguém tem. Dois campos existem só para o cliente não ter
de calcular: `share` em cada ponto e `scale_max_eur` no topo. Com eles, a única aritmética do SVG é
`share × píxeis`; sem eles, o cliente procurava um máximo e dividia euros em `number`, que é a regra da
casa quebrada em silêncio dentro de um `viewBox`. O `costs` substitui o `waste_inside_goods_cost` que a
primeira versão desta ADR tinha, e a razão é que o booleano tinha a forma errada: sob consumo o
desperdício **está dentro** (tem de estar, senão o balanço de stock não fecha) e sob compras **não está
dentro e continua a não ser somável**, porque o que se deitou fora em outubro pode ter sido comprado em
setembro — e um booleano não sabe dizer "não está dentro e ainda assim não somes". Com `is_part_of_total`
e `part_of`, quem decide é o servidor e o cliente indenta. **Nenhum evento emitido nem consumido** — não
há consumidor da outbox e nada a drenar; o `VendaRegistada` nasce no dia em que uma venda consumir stock.
**Nenhuma tarefa Celery, nenhuma chave de Redis, nenhum agregado materializado**: não há sinal da
secção 7 do `ARCHITECTURE.md`, e a ADR 0011 já fixou que a resposta a lentidão é `staleTime`, não
agregação. O gatilho que reabre isto é medido: p95 sobre um tenant com doze meses de ledger acima da
banda que a ADR 0005 nomeou ("aos 4 segundos é tolerável, ao minuto não é"). Um agregado por
(tenant, dia) é uma segunda fonte de verdade sobre dinheiro e tem ADR própria.

**O IVA, que vale entre 6 e 23% de erro se ficar implícito.** As duas bases de custo são **líquidas de
IVA** (base tributável), porque num restaurante em regime normal o IVA das compras é dedutível e não é
custo; usar o total da fatura como custo é o erro mais caro desta lista. Isso exige saber o regime, e o
regime é um atributo da **entidade**: `vat_regime` (`normal | isento_art_53`, default `normal` — a
restauração passa o limiar dos 15 000 € com facilidade) entra como coluna do `accounts_tenant`, ao lado
do `nif` que já está prometido. Em `isento_art_53` o IVA suportado **é** custo. Na receita manda-se os
dois valores, e não é zelo: o dono diz "fiz 1 800 € ontem" e esse número é **com** IVA, porque é o fecho
de caixa — `revenue_gross_eur` é o que ele compara com a caixa, `revenue_net_eur` é a base dos rácios, e
`revenue_basis` diz qual é qual. Mostrar-lhe um líquido onde ele espera um bruto é perder a confiança por
13% sem nenhum erro de cálculo.

Isto é uma **emenda à forma 2 da ADR 0011**, e escrevo-a em vez de a contrabandear: o teste passa a ser
*uma coluna vai para o `accounts_tenant` se descreve a **entidade** — o que estaria no papel de carta:
nome, NIF, regime de IVA, hora a que o dia de negócio começa — e é lida por dois ou mais módulos; vai
para a linha de configuração de um módulo (forma 2) se **um** módulo lhe dá o significado*. Por esse
teste o `business_day_starts_at` **sai do `inventory` e vai para o `accounts_tenant`**, e a razão é a
decisão 6: ele deixou de definir só "o que foi deitado fora hoje" e passou a definir a fronteira do mês
de toda a receita. O mínimo por artigo e o horizonte de validade ficam onde a ADR 0011 os pôs. Isto não é
o motor de configuração que a 0011 proíbe — continua a ser coluna tipada que aparece no `schema.yml` — e
não custa nada hoje, porque a tabela de configuração do `inventory` ainda não existe. O que `accounts`
guarda é o valor; quem aplica a regra é quem a tem.

**Decisão 6 — O gate é no endpoint, a resposta é 403, e nada fora do endpoint restrito é função dos
salários.** A primeira metade é a ADR 0007 aplicada: a sessão escolhe o âmbito, a política concede-o, e
quem decide o que este par (tenant, papel) pode ler é o `permission_classes` da view — um sítio, que o
`security-reviewer` lê numa linha. **403 e não 200 com blocos ausentes**, por três razões. Um 200 parcial
torna "não podes ver" indistinguível de "não há nada", e um tenant sem colaboradores registados e um
`staff` recebiam a mesma resposta para estados que precisam de ecrãs opostos — o vazio ensina a inscrever
a equipa, o restrito não pode. Um 200 parcial põe a autorização no **serializer, campo a campo**, que é a
forma que vaza no campo seguinte: alguém acrescenta uma média salarial ao resumo e nada falha. E o cliente
já sabe o papel antes de pedir (vem na sessão), pelo que não precisa do 403 para desenhar: não monta o
bloco, não dispara o pedido, e o 403 fica como rede para o deep link e para a pertença revogada a meio da
sessão — que é precisamente o caso que a ADR 0007 fez ser verificado por pedido. É o padrão que já existe
e está medido: `GET /convites` responde 403 a quem não é `owner`, o item sai do menu por apresentação, e o
`podeConvidar()` do cliente é só isso. A forma do 403 é a mesma — `detail` do DRF, **sem `code` novo**.

A segunda metade é a que faz o gate ser real em vez de decorativo: **esconder o bloco dos salários não
chega, porque um total os revela.** Se um `manager` vê "gastos: 24.500 €" com mercadoria e perdas
discriminadas, a subtracção dá-lhe a folha salarial. Por isso o `summary` **não tem total de gastos nem
resultado**, e o `cost_total_eur`, o `result_eur`, o `labour_cost_ratio_pct` e o `prime_cost_pct` vivem só
no `/month`. O invariante é escrito e verificável: *nenhum campo fora do `/reporting/month` é função de
`people`* — o que inclui o `prime_cost_pct`, que com o `goods_cost_ratio_pct` ao lado daria a folha
salarial por subtracção de rácios. O default é o mais fechado: `/month` é `{owner}`, e o `manager` **não**
vê salários — não por uma ordem entre papéis, que não existe neste projecto (é a Q7, e a ADR 0010 e o
`menu.py` já recusaram inventá-la), mas por um conjunto de um elemento, que se alarga sem se desfazer. Se
um dia alargar, há um problema a resolver primeiro: um custo por cargo com `headcount: 1` é o salário de
uma pessoa com outro nome, e o agregado não anonimiza nada. A rota `inicio` continua aberta aos três
papéis e o `route_id` fechado **não muda**: um `staff` aterra no Início e vê a lista das perguntas da
manhã, que é o que ele já vê hoje. São três projecções do mesmo ecrã, e a do `manager` não é a do `owner`
com uma barra escondida: o gráfico de gastos do `owner` tem as categorias de pessoal e o do `manager` não
— é outro gráfico.

**O campo que saiu por esta mesma razão, e que era meu.** A primeira versão tinha `goods_margin_eur`
(vendas − mercadoria) e inventei-o para ter *alguma* coisa derivada que não fosse derivável dos salários.
Sai, e o argumento que o mata é esse mesmo: **um campo que existe por uma restrição de segurança é o campo
que alguém interpreta mal.** "Margem", na cabeça de um dono de restaurante, é lucro; um número que exclui
pessoal — 25 a 35% da facturação — lê-se como lucro e é cerca do dobro do resultado real. Em vez dele
entra `goods_cost_ratio_pct`, que é o número que a restauração usa e compara ("a mercadoria está nos
31%"), é accionável, não se confunde com lucro e não revela nada sobre salários: serve o `manager` sem
abrir a fuga. Um campo em vez de dois.

**E a palavra "lucro" não aparece no ecrã em v1.** O `result_eur` ficaria a faltar renda, energia, água,
gás, TPA, licenças, contabilista e amortizações — a mesma bomba de confiança do stock-up, mais lenta. Os
custos fixos entram (decisão 3, `purchasing_othercost`) e é isso que torna a palavra "resultado"
defensável; o que continua de fora viaja no contrato, em `result_excludes`, e o ecrã imprime-o ao lado do
número. É também assim que o **sócio-gerente** fica dito em vez de escondido: em pastelaria o dono não se
paga ou paga-se o mínimo, e a margem fica excelente por omissão — se não houver remuneração de gerência
registada, `owner_compensation` aparece em `result_excludes` e o ecrã diz que não a inclui. O
`payroll_breakdown` existe pela mesma família de razão: um `payroll_eur` sozinho, 32% acima do bruto que o
dono tem na cabeça, parece erro, e a decomposição é o que transforma desconfiança em verificação.

**Decisão 7 — O painel declara o que não sabe, e a declaração é parte do contrato.** É a adição mais
valiosa depois da variação de stock, e nasce da minha própria decisão 1: como o `sales` v1 não escreve no
ledger, pode não existir consumo registado nenhum, e aí o painel mostra 85% de margem. **Um painel
optimista por omissão destrói a confiança mais depressa do que um prejuízo falso**, porque o prejuízo
falso faz perguntar e o lucro falso faz acreditar. Daí o `DataQualityOut` nas três respostas, e três
regras que vêm com ele. **Zero quebra desconhecida não é boa notícia, é ausência de contagem**: o campo
viaja com `last_count_at` e o ecrã escreve "última contagem: 28/09" — um mês sem contar dá zero e o
seguinte dá três meses de desvio de uma vez. Quando o líquido dos ajustes for positivo o rótulo é
**"excedente de contagem"** e não desperdício negativo. E as perdas são **duas linhas e não uma**:
"Desperdício" (movimentos `waste`, com motivo, autor e hora, accionável sobre um artigo e sobre uma
pessoa) e "Quebra desconhecida" (o líquido dos `adjustment`, accionável sobre o processo) — se um
agregado "Perdas" existir, é somado pelo servidor. No `/month`, `days_elapsed`/`days_in_month`, porque um
mês a correr ao dia 9 não se compara com um fechado e o `closed: bool` sozinho não evita a leitura errada.

**Decisão 8 — A fronteira do mês é a união dos dias de negócio, e tudo agrega por `occurred_at`.** O mês
é `[dia 1 às 04:00, dia 1 do mês seguinte às 04:00)`, logo uma venda das 02:00 de 1 de maio é de abril. A
razão é um invariante e não uma preferência: **Σ(dias de negócio do mês) == mês**. Com a fronteira do dia
às 04:00 e a do mês às 00:00, o dia de negócio de 30 de abril parte-se em dois meses e as barras diárias
deixam de somar o total mensal — e um gráfico cujas barras não somam o número ao lado perde credibilidade
mais depressa do que um sinal trocado. Por isso o `MonthOut` ecoa `since`, `until` e
`business_day_starts_at` como o `PeriodOut`, e o rodapé diz "mês de negócio: 1 abr 04:00 → 1 mai 04:00" —
o mesmo gesto do "desde as 04:00" que o ecrã Alertas já faz. **O mês de negócio não é o mês fiscal**, e
isso diz-se uma vez, no ecrã. As **faturas não têm hora**, logo as compras agregam-se pela **entrada da
mercadoria** (`occurred_at` da receção) e nunca pela data do documento, para haver uma fronteira só em
todo o painel; sempre por `occurred_at` e nunca por `created_at`. A guia de remessa com fatura a fim de
mês é mercadoria que entrou sem preço: entra ao último preço conhecido e a diferença fica **à vista**, em
`purchases_awaiting_invoice_eur` ("1 240 € ainda sem fatura"), em vez de aparecer sozinha num mês
seguinte que o dono já tinha lido.

**Alternativas.** *O `cost_basis` como parâmetro* — era a minha proposta e está revogada na decisão 4, com
o erro de classificação nomeado. *Vendas em `purchasing` com uma coluna de direcção* — um filtro esquecido
troca o sinal do lucro, e o `agents` passava a alcançar as vendas pelo contrato que já tem. *Vendas em
`recipes`* — confunde o consumo de uma receita, que é ledger, com a receita em euros, que é dinheiro; e o
dia em que a venda consumir stock a aresta é `sales → recipes.api`, que mantém **um** ponto de entrada no
ledger, como o `agents` nunca toca em `inventory`. *Salários como colunas do `Membership`* — o painel
precisava de um `accounts` que exporta dinheiro, e quem não tem conta não tem salário. *Salários ou
limites legais num `JSONField`* — invisível ao único gate de contrato que existe (ADR 0011). *Custos fixos
no `reporting`* — custa-lhe a propriedade de não escrever, que é a que sustenta a decisão 3; *num módulo
próprio* — um módulo inteiro para uma tabela de três colunas. *Agregação com um endpoint por módulo e o
cliente a juntar* — é o que a ADR 0011 escolheu para a configuração e é a alternativa mais forte;
rejeitada porque todo o número interessante é uma subtracção de euros e porque quatro pedidos resolvem
quatro períodos que podem não ser o mesmo. *A agregação dentro do `inventory`* — fazia o `inventory`
importar `sales` e `people`, invertendo o grafo na camada mais usada. *Uma view materializada ou um
agregado diário em Celery* — sem sinal da secção 7, com o gatilho medido escrito acima. *Biblioteca de
gráficos* — decisão do dono, e o `DESIGN.md` §5 dá-lhe a razão.

**Consequências.** Três módulos novos em `backend/apps/` e os contratos de import-linter passam de 10 a
14: um por módulo novo, mais o que proíbe importar o `reporting`; e as nove listas `forbidden_modules` de
hoje ganham as três entradas. É mecânico, e é o que torna a direcção do grafo verificada em vez de
prometida. **Tabelas novas (6)**, todas com `tenant_id` e portanto todas com `ENABLE` + `FORCE` +
política com `NULLIF(current_setting('app.tenant_id', true), '')::uuid` na migração que as cria:
`sales_sale`, `sales_saleline`, `people_jobrole`, `people_employee`, `people_compensation`,
`purchasing_othercost`. Mais duas colunas no `accounts_tenant` (`vat_regime`, `business_day_starts_at`),
onde a política já existe sobre `id`. As listas fechadas do `tests/test_db_roles.py` não ganham entrada
nenhuma — a igualdade de conjuntos cobre-as sozinha, e é esse o sinal de que esta ADR não abriu excepção.
`APPEND_ONLY` **continua vazio**: o StockFlow não emite documentos fiscais, logo uma venda registada para
gestão corrige-se; e em `people_compensation` um aumento é linha nova mas um erro de dedo é um `UPDATE`
legítimo, e sem um conceito de linha corretiva o append-only transformava uma gralha num registo
histórico falso. É a candidata nomeada à segunda entrada da lista, e o `CLAUDE.md` exige o
`domain-expert` antes dela.

Sobre a pergunta "RLS **e** uma restrição adicional" para os salários: sim, e nenhuma delas é uma segunda
política. Um predicado por papel exigia o papel num GUC, que é o `app.user_id` que a ADR 0007 rejeitou com
argumento. As três que entram são estruturais: o montante vive numa tabela **separada** da pessoa, logo a
lista da equipa lê-se sem tocar em dinheiro; o `people/api.py` **não tem nenhuma função que devolva o
salário de uma pessoa** — só agregados por cargo e por mês, o que é tudo o que o painel precisa, e é a
razão pela qual o `reporting` nunca vê um valor individual; e **nenhum valor de salário entra no payload
de um evento**, porque a `outbox` é a única tabela com o disjunto `app.scope = 'system'` na sua política
(ADR 0005) e o ticket D4 diz que esse disjunto é `FOR ALL` — pôr um salário num evento é pôr dados
pessoais na única tabela legível fora do âmbito do tenant. Nem em logs: o `ARCHITECTURE.md` §8 já diz
"nunca PII", e um custo por cargo com `headcount: 1` é o salário de uma pessoa com outro nome.

No frontend, o Início **deixa de ser um ecrã sem domínio**: o `src/shell/screens/inicio.tsx` sai de
`shell/` (que não pode importar features, ADR 0008 decisão 2) e passa a `src/features/reporting/`, com
`src/routes/inicio.tsx` a ligar os dois e um `src/routes/busca-do-painel.ts` a validar `period` e `month`
em Zod — o estado que define o ecrã pertence ao URL (ADR 0008, decisão 1). A lista das perguntas da manhã
sobrevive como último bloco: num dia em que os dados não carreguem, é ela que continua a servir.
`frontend/fixtures/painel.ts` entra com a sentinela `dados-falsos-stockflow`, validado pelos mesmos
schemas Zod, com as variantes vazia e de erro que o servidor já sabe fazer, mais uma nova:
`?_fixture=restrito` devolve o 403 do `/month`, na forma exacta do DRF. Não é fingir uma sessão (que a ADR
0010 proíbe) — é devolver uma **recusa**, na mesma direcção do `RECUSA_SEM_SESSAO` que já existe. E a
fixture tem de conter um mês com stock-up e um mês sem contagem, senão os dois modos de falha que esta ADR
passou a nomear não aparecem no ecrã que se mostra ao dono.

Dois limites que o SVG à mão herda dos tokens e que são desenho e não detalhe: a paleta tem **um** acento
e três cores de estado, logo um gráfico com mais de quatro séries não é desenhável nesta identidade — e
como o desperdício tem cinco motivos, "desperdício por motivo" é uma **barra ordenada** e não um donut de
cinco cores, que é também o que o `DESIGN.md` §3 pede (a excepção em cima). E um SVG não tem nome
acessível: cada gráfico viaja com o equivalente textual dos mesmos dados, porque numa casa onde "o estado
é a palavra, não um chip" um gráfico sem tabela é comunicar só por posição.

**Dependências e o que fica por decidir.** A **ADR 0014** é pré-requisito do `goods_consumed_eur`.
**Consultar `domain-expert`** continua a valer para a lista fechada de categorias de `purchasing_othercost`
e para o append-only do `people_compensation`. Ficam fora do v1, com gatilho no primeiro pedido real:
comparação com o período anterior (duplica cada query e ninguém a pediu), exportação para CSV/PDF, TSU
sobre o excesso de subsídio de alimentação, trabalho suplementar (`payroll_source: actual`), e o ecrã de
gestão da equipa — `people` entra com as tabelas e as leituras que o painel precisa, e o CRUD dos
colaboradores é a sessão seguinte.

**As perguntas que isto põe na sessão 0** (para o `docs/sessao-0-guiao.md`): qual dos dois números é
"quanto gastei" na cabeça do dono, e se ele reconhece a variação de stock como o seu próprio gesto; se
fala em valores com ou sem IVA quando diz quanto fez e quanto gastou, e o regime de IVA do
estabelecimento; se "desperdício" e "quebra desconhecida" são a mesma coisa para ele ou duas, e se já
soube a segunda; se o desperdício se conta ao custo ou ao preço de venda (o que se perdeu, ou o que se
deixou de ganhar); se "o que me custa a Ana" é o bruto ou o custo-empresa; se os subsídios devem aparecer
diluídos nos doze meses ou nos meses em que os paga; **se se conta a si próprio um salário** — e se não,
se quer ver o resultado com uma remuneração de gerência estimada ou com o aviso de que não a inclui; onde
é que o mês começa e acaba para ele, e se já teve uma venda das duas da manhã no mês errado; e quais são
os custos fixos que tem na cabeça quando pensa se o mês foi bom.
