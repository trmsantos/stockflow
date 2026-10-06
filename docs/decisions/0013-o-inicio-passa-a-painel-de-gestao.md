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
sem import) e `Compensation` (histórico, vigente desde). O cargo e o papel cruzam-se num sítio só: no
ecrã, lado a lado, porque são as duas colunas que a pessoa quer ver — e não na mesma coluna.

**Decisão 3 — A agregação vive num módulo-sumidouro, `reporting`: importa quatro `api.py`, não tem
tabelas, não tem `api.py`, e um contrato novo impede que alguém o importe.** É a decisão difícil, e o
precedente é a ADR 0011, que escolheu dois endpoints em vez de um agregado — "um endpoint de bootstrap
é como um monólito modular cria uma vista-deus". Aqui essa saída **não existe**, e a razão é medida:
margem é receita menos custo, e o cliente não pode somar dinheiro (os montantes são `Decimal` em
string, e "nenhuma conta é feita em `number` no cliente" é regra escrita no
`features/inventory/schemas.ts`). Um cliente que junta quatro respostas é um cliente a fazer
aritmética de euros em JavaScript. Logo alguém no servidor cruza os quatro módulos, e o único sítio
onde isso não inverte o grafo é um módulo cuja **única** aresta é de saída. `reporting` não é uma
vista-deus porque o perigo nunca foi importar quatro interfaces públicas — é passar a ser dependência
dos outros. Fica fechado com mecanismo e não com intenção: um 14.º contrato `forbidden` com os outros
nove módulos como `source_modules` e `apps.reporting` como proibido. Sem tabelas não tem migrações nem
política própria, e **está coberto pela RLS sem possuir nenhuma**, porque toda a query que faz nasce
dentro do âmbito do pedido, num `selectors.py` que chama `api.py`s. Sem `api.py` não tem interface
pública, e a ausência é a decisão. Regra de admissão, para o módulo não se tornar o sítio onde vão
todas as leituras: **entra em `reporting` uma leitura que cruze dois ou mais módulos; uma leitura
dentro de um módulo fica no `selectors.py` dele.**

**Decisão 4 — O contrato: três endpoints, dois parâmetros de período, e o cliente nunca soma dinheiro
nem procura um máximo.** Caminhos em `/api/v1/reporting/`, campos em inglês, como os vizinhos
(`/stock/*`, `/receipts/*`). Agregação em SQL (`GROUP BY`), nunca um ciclo em Python sobre o ledger.

```python
# GET /reporting/summary?period=<today|7d|30d|month|prev_month>&cost_basis=<consumption|purchases>
#   permissão: PertenceAoTenant + TemPapel.exige(OWNER, MANAGER)
@dataclass(frozen=True, kw_only=True, slots=True)
class PeriodOut:                      # o período resolvido, ecoado: mostrar o limiar, não esconder
    key: str; since: datetime; until: datetime; business_day_starts_at: str   # "04:00"
@dataclass(frozen=True, kw_only=True, slots=True)
class WasteByReasonOut:
    reason: str                       # expired|spoiled|prep_loss|breakage|other
    amount_eur: Decimal; share: Decimal; movements: int
@dataclass(frozen=True, kw_only=True, slots=True)
class SummaryOut:
    period: PeriodOut; cost_basis: str
    revenue_eur: Decimal; revenue_source: str          # none|manual — "none" até haver vendas
    goods_cost_eur: Decimal; waste_eur: Decimal
    waste_inside_goods_cost: bool                      # impede a soma dupla no cliente
    goods_margin_eur: Decimal                          # revenue − goods_cost; nunca toca em salários
    goods_margin_pct: Decimal | None                   # None quando revenue_eur == 0
    stock_value_eur: Decimal
    waste_by_reason: list[WasteByReasonOut]            # ordenada pelo servidor, a maior primeiro

# GET /reporting/series?period=…&cost_basis=…   (mesma permissão)
@dataclass(frozen=True, kw_only=True, slots=True)
class SeriesOut:
    period: PeriodOut; granularity: str                # day|week, derivada do período pelo servidor
    buckets: list[BucketOut]                           # {since, until, label} — uma vez, não por série
    scale_max_eur: Decimal                             # o máximo do eixo vem do servidor
    series: list[SerieOut]                             # {id, label, unit:"eur", total_eur, points}
                                                       # point = {value_eur, share}  (share = value/scale_max)
# GET /reporting/month?month=YYYY-MM&cost_basis=…
#   permissão: PertenceAoTenant + TemPapel.exige(OWNER)
@dataclass(frozen=True, kw_only=True, slots=True)
class RoleCostOut:
    role_id: UUID; name: str; headcount: int; payroll_eur: Decimal; share: Decimal
@dataclass(frozen=True, kw_only=True, slots=True)
class MonthOut:
    month: str; closed: bool                           # o mês já fechou, ou está a correr
    revenue_eur: Decimal; goods_cost_eur: Decimal; waste_eur: Decimal
    payroll_eur: Decimal; payroll_basis: str           # gross|employer_cost — ver domain-expert
    cost_total_eur: Decimal                            # só aqui, porque só aqui há salários
    result_eur: Decimal                                # o único lucro/prejuízo do produto
    roles: list[RoleCostOut]
```

`period` e `month` são **parâmetros diferentes de propósito**: um salário é um facto mensal, e ratear
30 dias por uma janela de 7 inventa precisão que ninguém tem. O painel tem por isso dois blocos com
grãos diferentes — "o que está a acontecer" (período) e "o fecho do mês" (mês) — e isso lê-se melhor do
que um número de 7 dias com um terço de um salário dentro. Dois campos existem só para o cliente não
ter de calcular: `share` em cada ponto e `scale_max_eur` no topo. Com eles, a única aritmética do SVG é
`share × píxeis`; sem eles, o cliente procurava um máximo e dividia euros em `number`, que é a regra da
casa quebrada em silêncio dentro de um `viewBox`. `waste_inside_goods_cost` existe pela mesma família
de razão: se o desperdício já está dentro do custo de mercadoria, somá-los ao lado conta duas vezes, e
o cliente não é quem pode saber. **Nenhum evento emitido nem consumido** — não há consumidor da outbox
e nada a drenar; o `VendaRegistada` nasce no dia em que uma venda consumir stock. **Nenhuma tarefa
Celery, nenhuma chave de Redis, nenhum agregado materializado**: não há sinal da secção 7 do
`ARCHITECTURE.md`, e a ADR 0011 já fixou que a resposta a lentidão é `staleTime`, não agregação. O
gatilho que reabre isto é medido: p95 do endpoint sobre um tenant com doze meses de ledger acima da
banda que a ADR 0005 já nomeou ("aos 4 segundos é tolerável, ao minuto não é"). Um agregado por
(tenant, dia) é uma segunda fonte de verdade sobre dinheiro e tem ADR própria.

**Decisão 5 — O gate é no endpoint, dentro do âmbito, a resposta é 403, e nada fora do endpoint
restrito é função dos salários.** A primeira metade é a ADR 0007 aplicada: a sessão escolhe o âmbito, a
política concede-o, e quem decide o que este par (tenant, papel) pode ler é o `permission_classes` da
view — um sítio, que o `security-reviewer` lê numa linha. **403 e não 200 com blocos ausentes**, por
três razões. Um 200 parcial torna "não podes ver" indistinguível de "não há nada", e um tenant sem
colaboradores registados e um `staff` recebiam a mesma resposta para estados que precisam de ecrãs
opostos — o vazio ensina a inscrever a equipa, o restrito não pode. Um 200 parcial põe a autorização no
**serializer, campo a campo**, que é a forma que vaza no campo seguinte: alguém acrescenta uma média
salarial ao resumo e nada falha. E o cliente já sabe o papel antes de pedir (vem na sessão), pelo que
não precisa do 403 para desenhar: não monta o bloco, não dispara o pedido, e o 403 fica como rede para
o deep link e para a pertença revogada a meio da sessão — que é precisamente o caso que a ADR 0007 fez
ser verificado por pedido. Isto é exactamente o padrão que já existe e está medido: `GET /convites`
responde 403 a quem não é `owner`, o item sai do menu por apresentação, e o `podeConvidar()` do cliente
é só isso. A forma do 403 é a mesma — `detail` do DRF, **sem `code` novo**: um segundo vocabulário de
erro para um caminho que o cliente não percorre é mecanismo a mais.

A segunda metade é a que faz o gate ser real em vez de decorativo, e não estava na pergunta: **esconder
o bloco dos salários não chega, porque um total os revela.** Se um `manager` vê "gastos: 24.500 €" com
mercadoria e perdas discriminadas, a subtracção dá-lhe a folha salarial do estabelecimento. Por isso o
`summary` **não tem campo de total de gastos nem de resultado**: o único número derivado lá é
`goods_margin_eur`, e o nome diz a base. O total e o `result_eur` vivem no `/month`, com os salários,
porque são função deles. O invariante é escrito e verificável: *nenhum campo fora do `/reporting/month`
é função de `people`*. O default é o mais fechado: `/month` é `{owner}`, e o `manager` **não** vê
salários — não por uma ordem entre papéis, que não existe neste projecto (é a Q7, e a ADR 0010 e o
`menu.py` já recusaram inventá-la), mas por um conjunto de um elemento, que se alarga sem se desfazer.
A rota `inicio` continua aberta aos três papéis e o `route_id` fechado **não muda**: um `staff` aterra
no Início e vê a lista das perguntas da manhã, que é o que ele já vê hoje. São três projecções do mesmo
ecrã, e a do `manager` não é a do `owner` com uma barra escondida: o gráfico de gastos por categoria do
`owner` tem três categorias (mercadoria, perdas, salários) e o do `manager` tem duas — é outro gráfico.

**Decisão 6 — RLS nas cinco tabelas novas, append-only em nenhuma, e nenhuma excepção nova.**
`sales_sale`, `sales_saleline`, `people_jobrole`, `people_employee` e `people_compensation` têm
`tenant_id`, e portanto `ENABLE` + `FORCE` + política com
`NULLIF(current_setting('app.tenant_id', true), '')::uuid` na migração que as cria. As listas fechadas
do `tests/test_db_roles.py` não ganham entrada nenhuma — a igualdade de conjuntos cobre-as sozinha, e é
esse o sinal de que esta ADR não abriu excepção. `APPEND_ONLY` **continua vazio**: o StockFlow não
emite documentos fiscais, logo uma venda registada para gestão corrige-se; e em `people_compensation`
um aumento é linha nova mas um erro de dedo é um `UPDATE` legítimo, e sem um conceito de linha
corretiva o append-only transformava uma gralha num registo histórico falso. É a candidata nomeada à
segunda entrada da lista, e o CLAUDE.md exige o `domain-expert` antes dela.

Sobre a pergunta "RLS **e** uma restrição adicional" para os salários: sim, e nenhuma delas é uma
segunda política. Um predicado por papel exigia o papel num GUC, que é o `app.user_id` que a ADR 0007
rejeitou com argumento (matriz de conflitos de 2×2 para 3×3, ou um GUC de sessão que a ADR 0005
fechou). As três que entram são estruturais: o montante vive numa tabela **separada** da pessoa, logo a
lista da equipa lê-se sem tocar em dinheiro; o `people/api.py` **não tem nenhuma função que devolva o
salário de uma pessoa** — só agregados por cargo e por mês, o que é tudo o que o painel precisa, e é a
razão pela qual o `reporting` nunca vê um valor individual; e **nenhum valor de salário entra no
payload de um evento**, porque a `outbox` é a única tabela com o disjunto `app.scope = 'system'` na sua
política (ADR 0005) e o ticket D4 diz que esse disjunto é `FOR ALL` — pôr um salário num evento é
pôr dados pessoais na única tabela legível fora do âmbito do tenant. Nem em logs: o
`ARCHITECTURE.md` §8 já diz "nunca PII", e um custo por cargo com `headcount: 1` é o salário de uma
pessoa com outro nome. (Essa última é também a condição de qualquer alargamento futuro ao `manager`:
um agregado por cargo não anonimiza nada quando o cargo tem uma pessoa, e quem alargar resolve isso
primeiro.)

**Alternativas.** *Vendas em `purchasing` com uma coluna de direcção* — respondida na decisão 1: um
filtro esquecido troca o sinal do lucro, e o `agents` passava a alcançar as vendas pelo contrato que
já tem. *Vendas em `recipes`* (que já tem "produção/venda → consumption" no `ARCHITECTURE.md` §6b) —
confunde o consumo de uma receita, que é ledger, com a receita em euros, que é dinheiro; e o dia em que
a venda consumir stock a aresta é `sales → recipes.api`, que é o desenho que mantém **um** ponto de
entrada no ledger, como o `agents` nunca toca em `inventory`. *Salários como colunas do `Membership`* —
o painel precisava de um `accounts` que exporta dinheiro, e quem não tem conta não tem salário.
*Salários num `JSONField` de perfil* — invisível ao único gate de contrato que existe (ADR 0011).
*Agregação com um endpoint por módulo e o cliente a juntar* — é o que a ADR 0011 escolheu para a
configuração e é a alternativa mais forte; rejeitada aqui porque a margem é uma subtracção de euros e o
cliente não a pode fazer, e porque quatro pedidos resolvem quatro períodos que podem não ser o mesmo.
*A agregação dentro do `inventory`*, que já tem o desperdício e o valor de stock — fazia o `inventory`
importar `sales` e `people`, invertendo o grafo na camada mais usada do sistema. *Uma view materializada
ou um agregado por dia em Celery* — sem sinal da secção 7, e com um gatilho medido escrito acima.
*Biblioteca de gráficos* — decisão do dono, e o `DESIGN.md` §5 dá-lhe a razão.

**Consequências.** Três módulos novos em `backend/apps/` e os contratos de import-linter passam de 10 a
14: um por módulo novo, mais o que proíbe importar o `reporting`; e as nove listas `forbidden_modules`
de hoje ganham as três entradas. É mecânico, e é o que torna a direcção do grafo verificada em vez de
prometida. No frontend, o Início **deixa de ser um ecrã sem domínio**: o `src/shell/screens/inicio.tsx`
sai de `shell/` (que não pode importar features, ADR 0008 decisão 2) e passa a
`src/features/reporting/`, com `src/routes/inicio.tsx` a ligar os dois e um
`src/routes/busca-do-painel.ts` a validar `period`, `cost_basis` e `month` em Zod — o estado que define
o ecrã pertence ao URL (ADR 0008, decisão 1). A lista das perguntas da manhã sobrevive como último
bloco: num dia em que os dados não carreguem, é ela que continua a servir. `frontend/fixtures/painel.ts`
entra com a sentinela `dados-falsos-stockflow`, validado pelos mesmos schemas Zod, com as variantes
vazia e de erro que o servidor já sabe fazer, mais uma nova: `?_fixture=restrito` devolve o 403 do
`/month`, na forma exacta do DRF. Não é fingir uma sessão (que a ADR 0010 proíbe) — é devolver uma
**recusa**, na mesma direcção do `RECUSA_SEM_SESSAO` que já existe. Dois limites que o SVG à mão herda
dos tokens e que são desenho e não detalhe: a paleta tem **um** acento e três cores de estado, logo um
gráfico com mais de quatro séries não é desenhável nesta identidade — e como o desperdício tem cinco
motivos, "desperdício por motivo" é uma **barra ordenada**, não um donut de cinco cores, que é também o
que o `DESIGN.md` §3 pede (a excepção em cima). E um SVG não tem nome acessível: cada gráfico viaja com
o equivalente textual dos mesmos dados, porque numa casa onde "o estado é a palavra, não um chip" um
gráfico sem tabela é comunicar só por posição.

**O que fica por decidir, e consultar `domain-expert` — não é formalidade: esta feature toca em stock,
validades, receitas e faturas de uma vez.** A primeira é a que decide se o ecrã é credível: **"gastos em
produtos" são as compras do período (caixa) ou o consumo valorizado a CMP (custo da mercadoria
vendida)?** Receita menos compras não é margem — é tesouraria, e um mês em que se encheu a arca aparece
como prejuízo; o dono deixa de confiar no painel na primeira vez que isso acontece. Enquanto a resposta
não vier, `cost_basis` é um parâmetro com as duas variantes à vista, que é como esta casa pergunta
(ADR 0008, decisão 3), e espera-se que uma ganhe e o parâmetro desapareça. A seguir, pela mesma
família: **o desperdício já está dentro do consumo?** Se sim, somá-lo ao lado conta duas vezes — o
`waste_inside_goods_cost` existe para o servidor responder, não para o cliente adivinhar. **Salário é
bruto ou custo-empresa** (bruto + TSU + subsídios + alimentação)? O número que o dono tem na cabeça é o
segundo, e o primeiro engana-o em quase um terço. **A receita é com ou sem IVA**, e de onde vêm as
vendas — export de POS, inserção manual, por talão ou agregado ao dia? É a Q3 das onze ("consumo por
talão de POS ou em lote") e decide se `sales` v1 é um formulário ou um importador. E **a fronteira do
dia de negócio**, que a ADR 0011 pôs no `inventory` porque lá define "deitado fora hoje", passa a ser
lida pelo `reporting` para a receita: ou é um facto do tenant mal colocado, ou é uma coincidência que
vale a pena — fica nomeado e não mexido, porque mudá-la para o `accounts` dava domínio ao módulo que
não pode ter nenhum. Ficam fora do v1, com gatilho no primeiro pedido real: comparação com o período
anterior (duplica cada query e ninguém a pediu), exportação para CSV/PDF, e o ecrã de gestão da equipa
— `people` entra com as tabelas e os endpoints de leitura que o painel precisa, e o CRUD dos
colaboradores é a sessão seguinte.
