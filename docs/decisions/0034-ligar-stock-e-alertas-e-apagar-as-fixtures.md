# ADR 0034 — Ligar o Stock e os Alertas, e apagar o servidor de dados falsos

> **Emendada pela adenda de 2026-10-27 (no fim deste ficheiro), depois do `domain-expert` e de
> quatro decisões do dono.** O corpo abaixo é a versão aprovada e fica de pé; o que a adenda
> **corrige** é: a **decisão 6** deixava a calibração da gravidade por decidir e contava **três**
> definições — está decidida (tabela por `kind`) e são **quatro**, sendo a quarta a única que o
> utilizador vê; a **decisão 5** diz que o `expiring_count` dos Alertas conta **lotes** e passa a
> contar **linhas da lista**; na tabela do contrato mudam o `Alerta.id` (colide), o corpo do
> `POST waste` (deixa de ser em unidade base), o `kind` e o `lot_code` (nuláveis) e o
> `nearest_expiry` (ganha `severity`); o **defeito (b)** do `reference` resolve-se sem mudar o que
> se grava, e o **defeito (c)** do mínimo por artigo passa de "tem de o dizer" a regra escrita. A
> adenda acrescenta ainda uma correcção que não é de contrato e que torna falsa a frase *"é leitura,
> serialização e uma renomeação de corpos de entrada"*: **o FEFO partido do `registar_waste` é
> reparado nesta fatia**. Nada que a adenda não nomeie mudou.
>
> **Segunda adenda, de 2026-10-29 (também no fim).** Acrescenta ao contrato **duas rotas** —
> `GET /stock/levels/<product_id>` e `GET /receipts/<id>`, decisões 12 a 17 — e **um campo que só a
> primeira serve** (`never_stocked`). Paga a dívida nº 2 que esta ADR deixou nomeada e, por decisão
> do dono tomada depois de a adenda estar escrita, o **caminho irmão** que ela tinha nomeado como
> fora de âmbito. Nada do que está acima deixa de ser verdade: a tabela do contrato ganha duas
> linhas e a lista não muda. **A decisão 18, escrita no fim de 29, é a primeira que tira alguma
> coisa: o `PUT /receipts/<id>` — publicado, nunca servido, só sabe dar 500 — sai do contrato neste
> PR. E a decisão 19, decidida a seguir, tira a outra: os dois `requestBody` que duas actions do
> mesmo ViewSet publicam e que o handler não lê, e com eles o componente `RececaoOutRequest` que
> eram os únicos a segurar.**

**Contexto.** Os ecrãs `/stock`, `/stock/$artigo` e `/alertas` são os **últimos** servidos por
`frontend/fixtures/` — seis rotas em `stock.ts` e `alertas.ts`. Atrás delas o Django serve quatro
rotas do painel (ADR 0024, fatia 4) e três `POST` de movimentos (ADR 0025), e **os dois lados
descrevem recursos diferentes**: três caminhos que o cliente chama não existem (`/stock/levels`, GET
`/stock/movements`, `/stock/alerts/{summary,waste}`), dois que o Django serve ninguém chama
(`by-location`, `by-product`), e `/stock/summary` **tem dois significados** — no servidor é uma lista
por artigo, no cliente são quatro números. A ADR 0032 já o nomeou (d6, "fora de âmbito") e deixou o
trabalho feito a montante: os euros do stock são de `owner|manager`, com a **chave ausente**, pelo
`SemEurosParaQuemNaoVe` do `accounts.api`. Esta fatia não reabre isso — aplica-o aos sete recursos
finais. **Toca em stock, validades, unidades e custos: consultar `domain-expert`.**

**Decisão 1 — O contrato é o do cliente, como na ADR 0030; o `by-location` e o `by-product` morrem
inteiros.** O ecrã de Stock mostra **uma linha por artigo** (quantidade somada, mínimo, estado,
validade mais próxima, e onde) — nunca uma linha por lote. O `by-location` e o `by-product` são de
grão **lote**, exigem um filtro obrigatório, e **não têm consumidor nenhum**: nem o cliente, nem o
assistente (usa `saldos_por_artigo` pela porta), nem o `reporting` (usa `valor_de_stock`). É o
critério com que a ADR 0029 d2 matou o `/reporting/projection`, e aplica-se igual. Em troca, **o que
o `/stock/summary` do servidor hoje é passa a chamar-se `/stock/levels`** e ganha os campos que lhe
faltam, e o caminho `/stock/summary` fica livre para os quatro números do cliente. A colisão de
nomes resolve-se por mudança de casa, não por arbitragem.

**Decisão 2 — Os três filtros do ecrã de Stock passam para o servidor, e isto corrige um defeito.**
Hoje o `screens/stock.tsx` filtra `?q=` e `?filtro=` em JavaScript sobre `results`. Com paginação a
sério (50) isso procura **só nas 50 piores linhas** e cala as outras em silêncio — e porque a ordem
é "o pior primeiro", cala-as exactamente onde ninguém nota. `?loja=`, `?q=` e `?filtro=falta|validade`
passam a ser `WHERE`, o `filtrar()` do ecrã morre, e com ele a segunda definição de "em falta" de que
o próprio docstring do ecrã desconfia. Os nomes dos parâmetros são os que o cliente já envia
(`loja`, `q`, `filtro`, `risco`, `periodo`, `artigo`): são os da **página**, e renomeá-los muda o URL
que alguém partilha, por nada.

**Decisão 3 — Um envelope só, o do DRF.** As quatro rotas do painel devolvem
`{items, total, page, page_size}` com `page: 1` fixo — um envelope que **não pagina** e que mente
sobre o fazer. Passam todas a `{count, next, previous, results}` com o `PAGE_SIZE = 50` do
`base.py`, que é o que o `paginated()` do cliente valida e o que todas as outras listas da casa já
usam. O `_pagina` do `StockPanelViewSet` desaparece — e com ele o sítio onde o `context` dos euros
era montado, que passa para o `get_serializer_context()` da view.

**Decisão 4 — O desperdício é do `inventory`, e a fronteira com o `reporting` fica escrita.** *O
`reporting` agrega o negócio num período e é do dono; o `inventory` lista o ledger para quem age
sobre ele.* O `/stock/alerts/waste` são as **linhas** do dia de negócio, com quem as registou, ao
lado do botão que as cria, e tem de chegar ao `staff` — pô-las no `reporting` obrigava a uma quarta
rota com outra permissão num módulo cuja identidade é "o painel é do dono" (ADR 0029 d3), ou a um
`api.py` que a ADR 0029 d6 recusa por extenso. O `waste_eur` do painel e esta lista são o mesmo
ledger em dois grãos e dois públicos; o que **não** pode haver são duas janelas, e por isso as duas
lêem o `business_day_starts_at` pelo `accounts.api.inicio_do_dia_de_negocio` e mais nada.

**Decisão 5 — Os contadores dos alertas são endpoint e não derivação.** A ADR 0029 derivou no
servidor e serviu o resultado; não serviu a lista para o cliente a somar. Aqui nem isso é possível:
`expiring_count` conta **lotes** (e o do Stock conta **artigos** — são dois números com dois
rótulos), a lista vem paginada a 50, e os dois `wasted_*_eur` são agregados do ledger em janelas de
dia de negócio que a lista de alertas não contém. Três factos, três fontes, zero fatias da lista.

**Decisão 6 — Dinheiro por papel, campo a campo; e a gravidade passa a ter **uma** definição.** A
tabela do contrato abaixo marca o que fica **ausente** para o `staff` — nunca `0`, nunca `null`. A
ordenação de nenhuma lista usa valor (ADR 0032, adenda): o `ordenar()` do fixture desempata por
`value_eur` e isso **não** atravessa. E há três definições de gravidade de validade na casa: o
`selectors.stock_alerts` dá `critical` a tudo o que venceu, o `api._gravidade_da_validade` só a
`use_by`, e o fixture nunca passa de `warning` num `best_before`. Fica **uma** função em
`selectors.py`, com o vocabulário do cliente (`danger|warning|info`), chamada pelas duas portas —
**qual é a calibração certa é pergunta ao `domain-expert`**, não desta ADR.

**Decisão 7 — A ordem de desmontagem é por recurso, e o que a fecha é fotografar com cada papel.**
(1) `/stock/alerts/waste` → (2) `/stock/alerts/summary` → (3) `/stock/alerts`, e aí **apaga-se
`fixtures/alertas.ts`** e a sua linha; (4) `/stock/summary` → (5) `/stock/movements` GET e POST →
(6) `/stock/levels`, e aí **apaga-se `fixtures/stock.ts`**. Com `ROTAS` vazio saem `servidor.ts`,
`ledger.ts`, `aurora.ts`, `decimal.ts` e a linha do `vite.config.ts`; o `check-fixtures.mjs` **fica**,
porque falha nos dois sentidos e é ele que prova que a remoção está completa. Condição por ficheiro:
`pnpm gen:api` sem diff, `uv run pytest` **também sem o `backend/.env`**, e o ecrã fotografado com
`frontend/scripts/ver-ecra.py` **em cada um dos três papéis** — nenhum gate atravessa a fronteira de
um `.optional()` que falta, e é por papel que estas chaves desaparecem.

## Contrato

Todas em `/api/v1`, `IsAuthenticated + PertenceAoTenant`, **sem `TemPapel`** (o dinheiro é coluna e
não recurso — ADR 0032 d1). `Quantidade = {base, base_unit, display, display_unit}`.
**AUSENTE** = chave fora do JSON para o `staff`.

| método · caminho | parâmetros | resposta | ausente p/ `staff` |
|---|---|---|---|
| `GET /stock/levels` | `loja?` `q?` `filtro=falta\|validade?` `page?` | página de `NivelDeStock` | `unit_cost`, `total_value` |
| `GET /stock/levels/<product_id>` | — (adenda de 29) | `NivelDoArtigo` · 404 se o artigo não existe | `unit_cost`, `total_value` |
| `GET /stock/summary` | `loja?` | `ResumoDeStock` | `stock_value_eur` |
| `GET /stock/movements` | `artigo` (**obrigatório**, 400 sem ele) `page?` | página de `Movimento`, `-occurred_at` | `unit_cost` |
| `POST /stock/movements/waste` | corpo abaixo | 201 `Movimento` | `unit_cost` |
| `GET /stock/alerts` | `risco=expira\|falta?` `page?` | página de `Alerta` | `value_eur` |
| `GET /stock/alerts/summary` | — | `ResumoDeAlertas` | `wasted_today_eur`, `wasted_week_eur` |
| `GET /stock/alerts/waste` | `periodo=hoje\|semana?` `page?` | página de `Desperdicio` | `value_eur` |
| `GET /receipts/<id>` | — (adenda de 29, d17) | `RececaoOut` · 404 se não for legível neste tenant | `document_total`, `lines_total`, `vat_breakdown` |

```python
NivelDeStock:   product: UUID; short_name: str; quantity: Quantidade; min_quantity: Quantidade
                status: "ok"|"baixo"|"esgotado"|"negativo"; by_location: list[{location:{id,name}, quantity}]
                nearest_expiry: {lot_id, lot_code, expires_at: date, days_away: int, kind} | None
                quantity_without_cost: Quantidade;  unit_cost: Decimal|None;  total_value: Decimal
                # ordem: estado, depois days_away (NULLS LAST), depois short_name. Nunca por valor.
NivelDoArtigo:  NivelDeStock + never_stocked: bool          # adenda de 29, decisão 14
ResumoDeStock:  below_min_count: int; expiring_count: int (ARTIGOS); expiring_within_days: int
                stock_value_eur: Decimal
Movimento:      id: UUID; movement_type: <os nove>; quantity: Quantidade (com sinal); location: {id,name}
                lot_code: str|None; reason: <os cinco>|""; created_by: str|None; occurred_at: datetime
                reference: str|None; cost_status: "conhecido"|"estimado"|"desconhecido"; unit_cost: Decimal|None
POST waste ←    {product: UUID, location: UUID, quantity: Decimal>0 (unidade BASE),
                 reason: <os cinco>, lot?: UUID, reason_detail?: str[:500]}
Alerta:         id: str ("expiry:<lot_id>" | "missing:<product_id>"); product: UUID; short_name: str
                reason: "expiry"|"missing"; severity: "danger"|"warning"|"info"; location: {id,name}|None
                quantity: Quantidade; lot: {lot_id, lot_code, expires_at: date, days_away, kind}|None
                threshold_days: int|None; min_quantity: Quantidade|None; value_eur: Decimal
                # ordem: severity, days_away, short_name.
ResumoDeAlertas: expiring_count: int (LOTES); expiring_within_days: int; missing_count: int
                business_day_starts_at: "HH:MM"; wasted_since: datetime
                wasted_today_eur: Decimal; wasted_week_eur: Decimal
Desperdicio:    id: UUID; product: UUID; short_name: str; lot_code: str|None; quantity: Quantidade (POSITIVA)
                reason: <os cinco>; location: {id,name}; created_by: str|None; occurred_at: datetime
                value_eur: Decimal
RececaoOut:     == o elemento de `GET /receipts`, chave a chave.   # adenda de 29, decisão 17
                Módulo `purchasing`. Zero campos novos, zero subclasse: a rota já existe
                e o que faltava era o cliente chamá-la.
```

**Morrem:** `GET /stock/by-location`, `GET /stock/by-product`, o envelope `{items,total,page,…}`, e
os sufixos `_id` dos corpos de entrada dos **três** `POST /stock/movements/*` (`product_id` →
`product`, `location_id` → `location`, `lot_id` → `lot`, `from_location_id` → `from_location`,
`to_location_id` → `to_location`). Os três e não só o `waste`: duas convenções no mesmo ViewSet é
como se escreve o 400 seguinte.

**Alternativas.** *Manter `by-location`/`by-product` e acrescentar `/stock/levels`* — três recursos
para duas perguntas, e dois sem consumidor. *Um `/stock/levels?grao=artigo|lote`* — um parâmetro que
muda a forma da resposta é dois endpoints com um nome só, e rebenta o tipo gerado. *Mudar o cliente
para o contrato do servidor* — o ecrã perde o mínimo, o estado, a validade e o `by_location`, que é
o produto. *Derivar os contadores dos alertas da lista* — a lista vem paginada e os euros do
desperdício não estão lá. *O desperdício no `reporting`* — um `api.py` que a 0029 d6 recusa, ou uma
rota de `staff` num módulo do dono. *`value_eur` a `0` ou `null` para o `staff`* — zero é uma
afirmação falsa sobre o preço e `null` imprime-se "—". *Negar a rota inteira ao `staff`* — tira o
ecrã mais usado a quem mais o usa (ADR 0032 d1). *Manter `lot_code` no corpo do `POST`* — um código
não é chave e obriga o servidor a resolvê-lo; o alerta passa a trazer `lot_id`.

**Consequências.** **Zero tabelas novas, zero alteradas, zero migrações, zero políticas RLS, zero
tarefas Celery, zero eventos** — é leitura, serialização e uma renomeação de corpos de entrada. No
`inventory`: três selectors novos (níveis por artigo com validade e repartição; linhas de
desperdício na janela do dia de negócio; os contadores), dois apagados (`stock_by_location`,
`stock_by_product`), a gravidade de validade unificada numa função, e o `urls.py` com três rotas
novas. No cliente, **os `.optional()` que não são opcionais** (CLAUDE.md: `.nullable()` sozinho exige
a chave e o ecrã **rebenta** com o `typecheck` verde): `stock_value_eur`, `unit_cost`, `total_value`,
`value_eur` (×2) e os dois `wasted_*_eur` nascem `.optional()`; `alertaSchema.id` passa de `z.uuid()`
a `z.string()`; `created_by` passa a `.nullable()` nos movimentos e no desperdício; `lot_code?` sai
do `quebraParaRegistarSchema` e entra `lot?: z.uuid()`; `validadeProximaSchema` ganha `lot_id`. O
`filtrar()` do `screens/stock.tsx` e o `normalizar()` morrem. Perde-se o que o `servidor.ts` dava
além de dados: os modos `?_fixture=erro|sem_sessao|tenant_divergente` ficam **sem gatilho** — é perda
nomeada, não esquecimento; o `vazio` passa a ser um estabelecimento semeado sem stock (ADR 0018).

**Defeitos encontrados ao escrever isto, que quem implementar herda.** (a) `AlertSerializer.expires_at`
é `DateTimeField` e o cliente valida `z.iso.date()` — é uma **data** impressa na embalagem, e o
selector já produz `expires_on`. (b) `movimentoSchema.reference` chega como o **id cru da contagem**
(`fechar_contagem` grava `reference=str(stock_count_id)`): o ecrã diz "texto curto, para mostrar" e
imprimiria um uuid. Fica cru no contrato — resolvê-lo obrigava o `inventory` a saber como o
`purchasing` chama um documento — e o ecrã não o imprime quando é um uuid. (c) O `status` do nível e
o alerta de falta comparam contra `product.min_quantity`, que é **por artigo**: com `?loja=` o ecrã
mostra o saldo de uma loja contra um mínimo de todas, e tem de o dizer.

**Consultar `domain-expert` — obrigatório, e antes do `backend`.** (a) A calibração da gravidade:
hoje há três versões (um `use_by` vencido é `danger` nas três, mas um `use_by` a 3 dias é `warning`
no fixture e `info` na porta do assistente) — qual fica? (b) `nearest_expiry` é o lote com saldo que
vence primeiro **no âmbito pedido** (`?loja=`) ou em todas as localizações, quando o mínimo é por
artigo? (c) `expiring_count` do Stock conta artigos e o dos Alertas conta lotes: confirmar que são
dois factos e não um defeito por herdar. (d) A pergunta (c) da ADR 0032 **continua aberta e é esta
fatia que a paga**: há um agregado de desperdício defensável para o `staff` que não reconstrua o
custo unitário (uma contagem de linhas, uma quantidade por artigo), ou a resposta certa é a régua
encolher de quatro contadores para dois? (e) O desperdício de "esta semana" são sete dias de negócio
rolantes a contar do de hoje — confirmar contra a janela do `reporting`, que é de mês civil.

---

## Adenda (2026-10-27) — a gravidade decidida, o FEFO reparado, e o terceiro contador do `staff`

As cinco consultas acima foram feitas e têm resposta; o dono tomou quatro decisões em cima delas.
Fica **adenda e não ADR nova** pelo critério da 0032 d7 ao contrário: não se revoga ADR nenhuma, não
há fatia nova, e tudo isto é a consequência directa da consulta que **esta mesma ADR exigiu antes do
`backend`**. Quem ler o corpo acima tem de ler isto, e por isso o aviso está no topo do ficheiro.
As decisões 8 a 11 continuam a numeração da ADR, para se poderem citar ("0034 d9").

### Decisão 8 — O FEFO partido do `registar_waste` repara-se nesta fatia

**O que está lá, medido.** O `backend/apps/inventory/services.py:537-540` levanta
`ValidationError({"lot_id": …})` quando `lot_id is None` e `produto.track_lots`, enquanto o docstring
da mesma função promete *"Usa FEFO para escolher o lote se não for fornecido"* e *"lot_id: UUID ou
None (se None, usa FEFO)"*. O `get_fefo_lot` só é chamado no ramo em que o lote **já veio**, onde
faz apenas validação. Do outro lado, o `formulario-de-desperdicio.tsx` **nunca envia lote** e já lê
`registadoNoLote(lot_code)` da resposta: o cliente foi escrito contra o comportamento prometido.
Resultado: registar quebra pelo ecrã do artigo dá **400 em todos os artigos com `track_lots=True`** —
e é o ecrã mais usado pelo `staff`. Não é dívida a nomear: é o caminho de escrita que esta fatia
liga, e ligá-lo partido não é ligá-lo.

**A regra.** Sem `lot` no corpo, o servidor escolhe por FEFO **na localização pedida**:
`expires_at ASC NULLS LAST`, depois `received_at ASC`, **só entre lotes com saldo > 0 ali**. Não
havendo nenhum, o 400 diz *"não há saldo deste artigo nesta localização"* e **nunca** "lote
obrigatório": a segunda frase manda a pessoa procurar um campo que o ecrã não tem, e esconde a causa
real, que é a localização estar vazia. O lote sintético continua a ser encontrado pelo mesmo
caminho, porque também é um lote com saldo — o ramo especial de hoje (`code=f"__{product_id}__"`,
sem olhar à localização) deixa de ser preciso e **deixa de poder tirar stock de uma localização onde
ele não está**.

**O caso limite, decidido: quebra de 2 kg com o lote FEFO a 0,4 kg reparte-se.** A hipótese do
`domain-expert` é a certa e já tem precedente escrito na casa — é o que o consumo de receitas faz
(ADR 0026, FEFO até esgotar). Gera-se **um movimento por lote**, por ordem FEFO, até perfazer a
quantidade, **numa transação** e com a mesma `reference` nas N linhas. Em concreto:

- a `reference` comum é um `uuid4` do gesto, escrito **só quando há mais do que uma linha** — com
  uma linha não há nada para agrupar, e o índice parcial `inv_stockmv_tenant_ref_idx` existe na
  maior tabela do sistema: só se paga escrita nele quando compra alguma coisa;
- não colide com o lookup das contagens (`selectors.py:1037` e `:1064` filtram também
  `movement_type="adjustment"`), e o `MovementDTO` já tem o campo (`services.py:181`), logo o
  `record_movements` grava as N linhas sem mecanismo novo;
- **o 201 passa a ser `{movements: [Movimento, …]}`, sempre lista, mesmo com um lote só.** Uma
  resposta que é objecto no caso normal e lista no caso raro é um cliente que funciona até ao dia em
  que o lote acaba a meio. É a forma que o 201 da transferência já tem (ADR 0032 d4), e a frase do
  ecrã passa de *"registado no lote X"* a nomear os lotes que foram — a palavra é do cliente;
- **se o saldo da localização não chegar para a quantidade pedida, não se reparte até onde dá**:
  é 400 com o que há. Escrever menos do que foi pedido, em silêncio, é a quebra a entrar errada num
  ledger sem desfazer. (Stock negativo continua a ser possível por outras portas — ADR 0012 — mas
  não como efeito secundário de uma repartição.)

### Decisão 9 — A tabela de gravidade, como o `domain-expert` a propôs, e o corte dos 3 dias é hipótese

**São quatro definições e não três.** A d6 contou três no backend e falhou a que conta:
`frontend/src/features/inventory/leitura-da-validade.ts::leituraDe` decide a **palavra e a cor** a
partir de `days_away`/`kind`/`limiarEmDias`, e alimenta `urgenciaDaValidade` →
`tintaDoTrilhoDoNivel`. É a **única que o utilizador vê**, e existe por uma razão estrutural e não
por desleixo: o `nearest_expiry` não traz gravidade nenhuma, logo o cliente é **obrigado** a
recalculá-la para pintar o trilho. Unificar no servidor sem lhe dar o campo era deixar a quarta
definição de pé. **O `nearest_expiry` ganha `severity`** (e o `Alerta.lot` com ele); o cliente mantém
só a palavra, porque i18n é dele, e tira **cor e urgência** do servidor — a `urgenciaDaValidade`
deixa de ler o `corDoTexto` da `Leitura` e passa a ler o `severity`. Num alerta de validade, o
`Alerta.severity` e o `lot.severity` são **o mesmo número pela mesma função**.

`dias = expires_on − hoje`, com **hoje = dia civil** (`timezone.localdate`), já decidido na ADR 0028
e não reaberto aqui:

| dias | `use_by` | `best_before` | `kind` vazio |
|---|---|---|---|
| `< 0` | danger | warning | danger |
| `0` | danger | info | danger |
| `1–3` | warning | info | warning |
| `4–limiar(7)` | info | info | info |

**O tecto é legal e escreve-se.** `use_by` é **DLC** (Reg. UE 1169/2011 art. 24 e Reg. CE 178/2002
art. 14(5)): passada a data o género é não seguro e **não se vende**. `best_before` é **DDM**
(DL 26/2016): passada a data ainda se vende se estiver íntegro. Logo **um `best_before` nunca chega a
`danger`** — é um limite do domínio e não uma preferência de paleta, e quem lhe mexer está a dizer
"deita fora" sobre mercadoria vendável. Daí que as duas definições do servidor estejam **ambas
erradas**: o `selectors.stock_alerts` dá `critical` a tudo o que venceu (um iogurte com DDM de ontem
vira alarme vermelho) e o `api._gravidade_da_validade:709-716` dá **aviso** a um `use_by` que vence
hoje (o dia em que ainda se consome é o dia em que se decide, e é `danger`). O `kind` vazio lê-se
pela regra estrita: sub-avisar é o erro caro.

**Janela ≠ corte, e é isto que devolve significado ao âmbar.** Hoje o limiar de 7 dias faz também de
corte de gravidade, logo **tudo o que entra na lista é pelo menos âmbar** e âmbar deixa de querer
dizer nada. Com a tabela, o limiar decide **o que aparece** e a gravidade decide **como aparece**:
um lote a 5 dias entra na lista a `info`. A lista fica com linhas calmas, e isso é o ponto.

**O corte dos 1–3 dias é hipótese, marcada como tal.** Não vem de lei nenhuma — vem de "dá para
escoar num fim-de-semana". Fica por **validar com um utilizador real** antes de se tratar como
facto; é a candidata óbvia a mudar, e muda numa constante.

### Decisão 10 — O `staff` não perde o terceiro contador: entram duas contagens

`wasted_today_count` e `wasted_week_count` entram no `ResumoDeAlertas` e estão **presentes para os
três papéis**. O `wasted_today_eur` e o `wasted_week_eur` continuam **ausentes** para o `staff`, como
a d6 e a ADR 0032 d1 mandam.

**A razão é de navegação e não de simetria.** Os dois números em euros são as **duas únicas portas**
para a lista de desperdício: o contador em `numeros-dos-alertas.tsx:110-117` liga a `?ver=desperdicio`
e o rodapé de `screens/alertas.tsx:272-284` é a frase *"ver o que foi"*. Sem eles, o `staff` fica com
dois contadores e **sem caminho nenhum** para a lista que a **d4 desta ADR** diz expressamente que
tem de lhe chegar — a rota existiria sem ter quem lá entre.

**Porque é que uma contagem não reconstrói o custo.** A reconstrução que a ADR 0032 fechou é sempre
uma **divisão**: `value_eur ÷ quantity` devolve o custo unitário, e com uma só quebra no dia o
`wasted_today_eur` dá-o sozinho. Um `COUNT(id)` **não tem euros em ponta nenhuma** — não há numerador
nem denominador —, logo nenhuma sequência de observações o reconstrói. **Mas só enquanto o `COUNT`
ficar fora de um `values().annotate()` que inclua `unit_cost`**: agrupar a contagem por custo
unitário serve o custo unitário na chave do grupo, e a fuga volta pela mesma porta com outro nome. É
o defeito exacto que a ADR 0032 mediu no `stock_summary` (o `Case` dentro do `values()` a entrar no
`GROUP BY`), e tem de haver um teste que leia o SQL e não só o JSON.

Por cima das contagens entra a **cobertura**, pela régua da 0032: `wasted_today_lines_without_cost` e
`wasted_week_lines_without_cost` — **linhas e não euros**, iguais para os três papéis, como o
`quantity_without_cost` dos níveis. Sem isso, "7 quebras hoje" e "7 quebras hoje, 4 sem preço
conhecido" são a mesma frase.

### Decisão 11 — A unidade entra no corpo do `POST` de quebra, e a conversão é do servidor

O corpo passa a ser `quantity: Decimal>0` **mais** `unit`, e o `unit` tem de ser o `base_unit` ou o
`display_unit` **daquele artigo** — qualquer outro é 400, e não existe motor genérico de conversão
(ADR 0011). A conversão faz-se **no servidor**, nunca no cliente: é a regra da ADR 0030 d1 e do
`inventory-domain` §2, e é a mesma razão pela qual as quantidades viajam como quarteto. O ecrã
**pré-selecciona o `display_unit`** (é a unidade em que a pessoa fala) e o 201 devolve a quantidade
como `Quantidade`, com o `display` preenchido, para a frase de confirmação dizer "2 kg" a quem
escreveu 2.

Isto fecha um buraco que a versão aprovada escrevia por extenso — *"quantity: Decimal>0 (unidade
BASE)"* — contra um formulário que apresenta a unidade mostrada ao lado do campo e normaliza só a
vírgula decimal (`formulario-de-desperdicio.tsx:79-86`). Entre `g` e `kg` há um factor de 1000, o
destino é um ledger **append-only** (ADR 0006: sem `UPDATE`, sem `DELETE`) e o erro não tem botão de
desfazer. Um número sem unidade explícita num corpo de escrita é uma convenção, e convenções não
sobrevivem a dois ecrãs.

### O que isto muda no contrato (e o que rebentava o cliente em silêncio)

- **`kind` passa a nulável nos dois sítios** (`nearest_expiry` e `Alerta.lot`). O
  `tipoValidadeSchema` é `z.enum(["use_by","best_before"])` e **não aceita `""`**, enquanto o
  `expiry_kind` do `catalog` é `""` por omissão (`catalog/models.py:117`): o serializer traduz
  `""` → `null`, e um artigo sem rótulo lê-se pela coluna estrita da tabela da d9.
- **`lot_code` de lote sintético sai `null` nos quatro sítios onde aparece** (`nearest_expiry`,
  `Movimento`, `Alerta.lot`, `Desperdicio`), pela `selectors.e_lote_sintetico` que já existe
  (`__<uuid>__`). O `validadeProximaSchema.lot_code` é hoje `z.string().min(1)` e passa a
  `.nullable()` — sem isto, a primeira produção de receita no ecrã de Alertas rebenta a página.
- **O `Alerta.id` colide, e muda de forma.** O alerta de validade é por lote **× localização** — um
  lote transferido tem saldo em duas —, logo `"expiry:<lot_id>"` produz **dois ids iguais** e o
  `aberta` do `screens/alertas.tsx` expande a linha errada. Passa a `"expiry:<lot_id>:<location_id>"`
  (o `"missing:<product_id>"` fica). **Agregar por lote não é alternativa**: o `location` passaria a
  `null` e o `POST` de quebra da linha levaria `""`, que é 400 — o alerta deixaria de ser accionável,
  que é a única coisa que ele tem.
- **`expires_at` passa a `DateField`**, por `timezone.localdate` (defeito (a) do corpo). Um instante
  tem fuso e a data da embalagem não muda com quem a lê; o cliente valida `z.iso.date()`.
- **`reference`: não se muda o que se grava.** O `selectors.py:1037` e o `:1064` fazem lookup por
  `reference=str(stock_count_id)` e há índice parcial em `models.py:236-241`. Servem-se **dois campos
  novos** — `reference_kind` e `reference_label` — e o ecrã imprime o rótulo, nunca o cru. Isto
  resolve o defeito (b) sem atravessar fronteira nenhuma: **a contagem é modelo do próprio
  `inventory`**, logo nomear "Contagem de 24/10, Armazém" não obriga o módulo a saber nada do
  `purchasing`. O que vier de fora do módulo fica sem rótulo, e sem rótulo o ecrã não imprime nada.
- **`Desperdicio` e `Alerta` ganham `cost_status`** (as três palavras da ADR 0032, adenda), e o
  resumo ganha a cobertura da d10.
- **Invariante testável, e é ela que impede a divergência de voltar:** *cada contador é igual ao
  `count` da lista que filtra, no mesmo âmbito*. `expiring_count` ↔ `/stock/alerts?risco=expira`,
  `missing_count` ↔ `?risco=falta`, `wasted_*_count` ↔ `/stock/alerts/waste?periodo=…`,
  `below_min_count` ↔ `/stock/levels?filtro=falta`, `expiring_count` do Stock ↔ `?filtro=validade`.
  Daqui sai a correcção à **d5**: o `expiring_count` dos Alertas conta **linhas da lista** e não
  lotes — com o alerta a ser por lote × localização, "lotes" nem sequer estava bem definido. E a
  consulta (c) fica respondida: são dois números porque contam **duas listas**, cada um igual à sua.
- **`status`, `min_quantity` e `filtro=falta` são sempre do estabelecimento**, também com `?loja=`;
  o `?loja=` escopa **só** `quantity` e `by_location`. É o defeito (c) a passar de aviso a regra: o
  mínimo é por artigo (ADR 0024) e compará-lo contra o saldo de uma loja inventava faltas. O ecrã
  **tem de escrever "mínimo do estabelecimento"**, senão "0,4 kg · ok" lê-se como erro de cálculo.
- **`nearest_expiry` é no âmbito pedido** (consulta (b)): com `?loja=`, é o lote com saldo **naquela
  localização**. Mostrar a validade de outra loja ao lado do saldo desta é uma frase falsa sobre o
  que está à frente de quem lê.
- **`wasted_week` são sete dias de negócio rolantes incluindo hoje** (consulta (e)), igual ao `7d`
  que o `reporting` já tem (`periodos.py:56` e `:137`) e **não** o mês civil. A aritmética é **de
  calendário**: `hoje − timedelta(days=6)` sobre a **data**, e só depois `combine` com o
  `business_day_starts_at`. `agora − timedelta(days=7)` põe um dia inteiro no balde errado no domingo
  da mudança da hora. O `inventory` **não pode importar o `reporting`** (ADR 0029 d6), logo duplica
  três linhas — e o teste que paga a duplicação é um que corre **no dia da mudança da hora**, não um
  que compare as duas funções.
- **`unit_cost = 0` com `cost_is_estimate=False` (`services.py:568`) grava um zero mentiroso** num
  ledger append-only. Sem nível com custo: `cost_is_estimate=True` e o 201 devolve
  `cost_status: "desconhecido"`. **Nunca se bloqueia o registo por falta de preço** — quem está a
  deitar fora não anda à procura de uma fatura. (Não é o `estimado` que a ADR 0032 deixou
  inalcançável; é o `desconhecido` a deixar de se disfarçar de zero.)
- **`stock_value_eur` não soma linhas negativas.** Um `Sum` ingénuo no Django soma-as e o valor do
  stock desce por causa de um saldo que ninguém tem; o fixture já as saltava, e o servidor tem de
  fazer o mesmo. As linhas negativas continuam visíveis na lista com `status: "negativo"`, que é onde
  elas significam alguma coisa.

### Os dois relógios, e porque é que isto não é um defeito

**O mesmo ecrã tem dois relógios e está certo.** A validade é **dia civil** — a lei não sabe a que
horas a pastelaria abre — e o desperdício é **dia de negócio** (ADR 0029, `business_day_starts_at`).
Às 02:00, o "hoje" do desperdício ainda é ontem e o "expira hoje" já é o dia novo, e as duas frases
estão certas ao mesmo tempo. Quem unificar os relógios parte uma das duas verdades: ou o lote passa a
vencer à hora a que o patrão abre a porta, ou a quebra das 02:00 salta para o dia seguinte e o
fecho do dia deixa de bater certo. Está escrito aqui para a próxima "correcção" não ser esta.

### Fora de âmbito — nomeado e não resolvido

**Mínimo por (artigo, localização)** — é a dívida de que o defeito (c) é o sintoma, e custa coluna,
ecrã e migração. **`shelf_life_after_opening_days`** — o HACCP exige a validade secundária depois de
aberto, a app não a conhece e por isso **sub-avisa**; um ecrã de Alertas vazio **não pode** ler-se
como "está tudo em dia", e enquanto esta não existir não é isso que ele diz. **Janela histórica de
quebras para inspeção da ASAE** — o `periodo` nasce `hoje|semana`, mas o selector recebe
`[desde, até)`, de propósito: acrescentar datas passa a ser **um parâmetro e não uma reescrita**.
**A lista de vencidos sem fundo inferior** — um lote vencido há seis meses continua a aparecer, para
sempre, e empurra para baixo o que é accionável. **O toque único que escreve o lote inteiro num
ledger sem desfazer, e a ausência de UI para o movimento inverso** — hoje corrige-se um engano com um
`adjustment` que o ecrã não oferece. **A incoerência entre o `below_min_count` do Stock e o
`missing_count` dos Alertas**, visível a quem muda de ecrã com `?loja=` posto: são dois contadores do
mesmo facto em dois sítios, e só um deles é lido ao lado de um filtro de loja.

### Impacto que esta adenda acrescenta

Continua **zero tabelas, zero colunas, zero migrações, zero políticas RLS, zero Celery, zero
eventos**. O que deixa de ser verdade é *"é leitura, serialização e uma renomeação de corpos de
entrada"*: a **d8** e a **d11** mexem num caminho de **escrita** (`registar_waste` — FEFO,
repartição, unidade, `cost_is_estimate`), e isso muda a ordem da d7 numa coisa — o `POST
/stock/movements/waste` deixa de ser o passo barato do (5) e é o que leva mais testes: FEFO na
localização pedida, repartição por dois lotes com `reference` comum, saldo insuficiente, artigo sem
preço, e as duas unidades. No cliente, mais `.optional()`/`.nullable()` do que a lista do corpo:
`kind` e `lot_code` nuláveis no `validadeProximaSchema`, `severity` novo lá dentro, `unit` no
`quebraParaRegistarSchema`, a resposta da quebra a passar a `{movements: […]}`, `cost_status` em
`desperdicioSchema` e `alertaSchema`, e no `resumoDeAlertasSchema` os dois `wasted_*_count` e os dois
`wasted_*_lines_without_cost` — estes quatro **presentes para os três papéis**, logo sem
`.optional()`, e é exactamente aí que um `.optional()` a mais esconderia um campo em falta.
`uv run manage.py spectacular` e `pnpm gen:api`, e o ecrã fotografado **com cada papel**: o `staff`
tem agora um terceiro contador que o `owner` também tem, mas com outro número.

---

## Adenda (2026-10-29) — o detalhe do artigo passa a ser recurso, e a frase falsa morre

**O defeito, medido.** O `useArtigoEmStock` (`frontend/src/features/inventory/api.ts:223-243`) pede a
**lista sem filtros** e escolhe a linha com `results.find(…)`. Com `PAGE_SIZE = 50`
(`config/settings/base.py:352`), a lista alcança com `?q=` um artigo que está **para lá das 50
piores**; clicar nele abre o detalhe, que vai buscar a lista **sem o `q`**, não o encontra, e escreve
*"Este artigo não está no stock"* (`textos.pt.ts:373-375`). É uma frase falsa sobre mercadoria que
existe, no ecrã a partir do qual se regista a quebra. A lista é honesta sobre truncar
(`screens/stock.tsx:79-83`); o detalhe herdou a truncagem sem herdar o aviso. É a **dívida nº 2** que
esta ADR deixou nomeada. Morre pelo caminho o argumento que construiu o `select` — *"o detalhe não
paga um pedido que a lista já pagou"* —, que só é verdade quando se chegou à ficha a partir da lista
**sem filtros**, exactamente o caso em que o defeito não aparece. As decisões 12 a 16 continuam a
numeração. **Toca em stock, validades e custos: consultar `domain-expert`** — mas nenhuma delas muda
uma regra de domínio, só a porta por onde as de cima saem.

**O âmbito desta adenda cresceu depois de ela estar escrita, por decisão do dono: a decisão 17 — o
caminho irmão, `GET /receipts/<id>` — entra no mesmo PR e não numa fatia seguinte.** Estava nomeada
na secção "Fora de âmbito" desta mesma adenda, e saiu de lá pelo argumento que a adenda usa contra si
própria: o docstring do `useRececao` (`frontend/src/features/purchasing/api.ts:112-124`) **cita a
decisão do `useArtigoEmStock` por extenso como precedente**, logo corrigir um e deixar o outro não
era meia correcção — era deixar um comentário a invocar uma decisão revogada sobre o mesmo defeito.
Esta casa já foi mordida duas vezes por corrigir metade de um par (a receção e o documento serviam a
mesma fatura por portas diferentes). **A 17 não é um extra: é a outra metade**, e está escrita no fim
desta adenda porque foi decidida depois das cinco que a precedem. **A decisão 18, que lhe fecha um
defeito herdado, foi decidida depois dela e está escrita a seguir; e a 19, que fecha dois defeitos da
mesma família no mesmo ficheiro, depois dessa.**

### Decisão 12 — É uma rota de detalhe, na **mesma** view e com o **mesmo** selector

`GET /api/v1/stock/levels/<product_id>`, `operation_id: stock_level` — singular ao lado do plural, e
nunca `by_product`, que é o nome de um recurso que a d1 matou e que era de outro grão. Mora no
`StockPanelViewSet` (`views.py:336`) como `@action(detail=False, url_path="levels/(?P<product_id>[^/.]+)")`
e **não** num ViewSet próprio: o `get_serializer_context()` que monta o contexto dos euros é **um**
(`views.py:367-374`), e uma segunda classe era um segundo sítio para o esquecer. Um `product_id` mal
formado é **400** com o `DETALHE_UUID_INVALIDO` que o `?loja=` já usa, nunca 404 — "isto não é um
uuid" e "este artigo não existe" são dois factos, e o segundo seria mentira.

**A excepção a esse 400, medida ao implementar, e por isso escrita aqui em vez de ficar por
descobrir.** O `url_path` da action é `(?P<product_id>[^/.]+)` — a convenção de **todos** os `pk` da
casa —, e o padrão não casa com o ponto: `/stock/levels/nao-e-uuid` dá **400** como está escrito, mas
`/stock/levels/nao.e.uuid` dá **404**, porque o pedido nunca chega à view. O `/receipts/nao.e.uuid`
faz exactamente o mesmo. **Não se alargou a regex** — alargá-la fazia esta rota divergir de todas as
outras rotas de detalhe da casa, por um caso que nenhum cliente constrói —, logo "mal formado → 400"
lê-se "mal formado **e sem ponto** → 400".

A leitura é a `niveis_de_stock` (`selectors.py:544`) com **um parâmetro novo**, `product_id`: mais um
`WHERE` na mesma query, não uma função nova. A linha sai do mesmo `_nivel_de_stock` (`:655`), o
estado do mesmo `_estado_do_nivel` (`:443`), a validade do mesmo `_validade` (`:509`). **Não nasce
aqui uma segunda definição de nível**, como não nasceu uma quinta de gravidade na d9. Não há
paginação: é um objecto, não uma página.

*Alternativas.* `GET /stock/levels?artigo=<uuid>` — devolve uma página de zero ou uma linha, e **zero
linhas não distingue (b) de (c)**, que é metade do defeito; e o cliente voltava a ler `results[0]`,
que é o `find()` com outra máscara. *Um ViewSet só para o detalhe* — duas portas para o mesmo
dinheiro. *Mandar o `?q=` da lista no pedido do detalhe* — faz a ficha depender do filtro de onde se
veio, e um link partilhado deixa de reproduzir o que mostra.

### Decisão 13 — Três estados, três respostas, e a do meio é um **vazio** e não um erro

| estado | resposta |
|---|---|
| (a) o artigo tem `StockLevel` | `200`, `never_stocked: false` |
| (b) existe no catálogo, **sem `StockLevel` nenhum** | `200`, `never_stocked: true`, `quantity` a zero, `by_location: []`, `nearest_expiry: null`, `unit_cost: null` |
| (c) o `product_id` não existe **neste tenant** | `404` (`Http404`, a forma que o `purchasing` já usa) |

(b) é **200 e não um 404 com código**, e a razão é de estado e não de protocolo: (b) é o **vazio** de
um ecrã e (c) é o **erro**. Servir (b) como erro obrigava o cliente a traduzir um 404 num vazio, e é
essa tradução que apodrece. A casa já decidiu isto uma vez, neste módulo: a tool do assistente
responde 200 com `nunca_entrou: true` e saldo zero (ADR 0027 d6, `agents/tools.py:622-629`), e a
`selectors.saldos_do_artigo` existe por causa dessa distinção. Com (b) a ser 200, **o 404 passa a
querer dizer uma coisa só** e o cliente não tem de ler códigos de erro.

Quem distingue (b) de (c) é o `catalog`: no estado (b) o `inventory` não tem linha nenhuma para
olhar, logo a pergunta "este artigo existe?" **não é dele**. É `catalog.api.produto_por_id`, já
importado neste ficheiro (`views.py:51`) e já usado três vezes no `services.py` para a mesma
pergunta — aresta permitida (`inventory → catalog.api`), zero funções novas.

No ecrã: (b) escreve **"ainda não deu entrada no stock"** e **nomeia o artigo** (o nome vem no
corpo); (c) escreve "este endereço não aponta para nenhum artigo deste estabelecimento". Hoje os dois
dizem a mesma frase e ela está errada nos dois. O `status` de (b) sai `"esgotado"` pelo
`_estado_do_nivel` sem alteração nenhuma, **e o ecrã não o pinta quando `never_stocked`** — não por
ser falso (há zero unidades), mas porque "esgotado" responde a uma pergunta sobre o passado que
ninguém fez.

**E a regra é do contrato, não do ecrã.** *"Esgotado" é uma afirmação sobre consumo — tínhamos e
acabou*; sobre o que nunca entrou é falsa no sentido que importa, mesmo sendo verdadeira na
aritmética. Logo **nenhuma superfície escreve "esgotado" sobre um artigo com `never_stocked: true`**:
nem este ecrã, nem um alerta, nem o assistente, nem uma exportação. Escrevê-la aqui e não dentro do
`screens/artigo.tsx` é o que impede a segunda apresentação daqui a três fatias — quem servir a
superfície seguinte lê o campo, não o código deste ecrã. Hoje a regra sai de graça em todo o lado
menos aqui: a lista de Stock e a de faltas partem do `StockLevel` (`selectors.py:582` e `:810`), logo
nunca alcançam um artigo que nunca entrou, e o assistente já responde `nunca_entrou: true`
(ADR 0027 d6). **Esta rota é a primeira superfície capaz de produzir o caso; a regra existe para ser
a única.**

**E (b) não é estado de onde se registe quebra — pela entrada que falta, não pela forma do
`by_location`.** **Não se dá baixa do que nunca deu entrada.** Um `waste` sobre (b) escrevia uma
saída sem entrada num ledger append-only: saldo negativo a partir do nada, custo médio sem origem, e
uma linha a `cost_status: "desconhecido"` no relatório de desperdício em euros, que é o KPI que o
dono mais olha. A sequência certa são sempre **dois factos**: primeiro a entrada, depois a quebra. (A
razão de forma que aqui esteve escrita — *"um artigo esgotado em todo o lado já tem `by_location: []`
hoje"* — é verdadeira e não serve: deixa a impressão de que o caso físico não existe, e ele **existe
e é semanal numa pastelaria** — entrega com guia de remessa e fatura ao fim do mês, compra a dinheiro
no Recheio ou no Makro, oferta ou amostra do fornecedor, produção interna que nunca foi "recebida".)
O mesmo raciocínio vale para `never_stocked: false` com `by_location: []` — entrou e acabou: também
aí a quebra não tem onde pousar. Não é caso novo, é o mesmo.

**O vazio aponta para a porta da entrada.** O texto de (b) é
*"O açúcar amarelo ainda não deu entrada no stock."* / *"A primeira entrada faz-se pela fatura do
fornecedor."* — e **pára aí**. A segunda frase que o `domain-expert` propôs (*"Se já cá está,
conta-o numa contagem"*) seria a certa — a contagem é a porta que a casa tem para "existe fisicamente
e o sistema não sabe", e gera o `adjustment` com justificação (ADR 0030/0033) —, **mas não se pode
prometer hoje**: a folha materializa só artigos com nível não-zero naquela localização
(`count_services.py:257-265`), o ecrã de contar não tem campo de procura para lá chegar, e um artigo
com `track_lots=True` sem lote a sério é recusado por desenho. Fica como dívida nomeada no fim desta
adenda; no dia em que a porta existir, a frase acrescenta-se e o texto de (b) passa a ter duas saídas.

**Um artigo arquivado responde `200`, e isso passa a estar escrito.** Arquivar é `is_active=False`
(`catalog/models.py:164`) e o `catalog.api.produto_por_id` (`catalog/api.py:303-308`) lê por
`(tenant_id, id)` **sem filtrar `is_active`** — logo o que o domínio exige (mercadoria que existiu
continua auditável; o histórico não desaparece porque o artigo saiu da lista de compras) **já
acontece hoje, por acaso, e não está escrito nem testado em lado nenhum**. Basta alguém "corrigir"
aquele `get` para filtrar inactivos e a ficha de um artigo arquivado passa a **404 em silêncio**, com
todos os testes verdes. Fica aqui como estado — arquivado é (a) ou (b), **nunca (c)** — e ganha perna
no teste (2). A lista não entra nesta conversa: o `niveis_de_stock` também não filtra `is_active`
(`selectors.py:582`), e quem exclui inactivos é a lista de **faltas** (`:812`), que responde a outra
pergunta.

*Alternativa recusada: um quinto valor em `ESTADOS_DO_NIVEL`.* Essa tupla é a **ordem da lista**
(`selectors.py:138-142`) e é o `EstadoDoNivelEnum` do OpenAPI (`base.py:478`): um valor que a lista
nunca pode produzir não tem posição numa ordem de "o pior primeiro", e pagava-se com um enum alterado
em toda a casa — e com um `z.enum` do cliente que **rebenta o ecrã** se ficar para trás — por um
facto que só o detalhe conhece.

### Decisão 14 — O corpo é a linha da lista **mais um campo**, por herança

`NivelDoArtigo = NivelDeStock + never_stocked: bool`. O serializer é
`class NivelDoArtigoOutSerializer(NivelDeStockOutSerializer)` com **um** campo declarado; os outros
doze não se repetem. Do lado do cliente **não nasce um segundo schema**:
`nivelDoArtigoSchema = nivelDeStockSchema.extend({ never_stocked: z.boolean() })`, e o
`nivelDeStockSchema` continua a ser a única definição da linha. O campo **não vai na lista**: lá seria
constante (`false` por construção), e um campo que nunca varia num sítio é onde se começa a não olhar
para ele. `never_stocked` é "nunca houve `StockLevel` deste artigo" — não é saldo zero, é **não haver
história nenhuma**: nem receção, nem contagem, nem ajuste. É o `nunca_entrou` da ADR 0027 com o nome
em inglês que o resto de `/stock` usa.

### Decisão 15 — Os euros herdam-se, e onde são impostos escreve-se aqui

Três sítios, os mesmos de sempre: a **política** em `accounts/api.py:354-398`
(`PAPEIS_QUE_VEEM_EUROS` → `ve_euros` → `SemEurosParaQuemNaoVe.to_representation`); a **lista de
campos** no `CAMPOS_DE_DINHEIRO = ("unit_cost", "total_value")` do `NivelDeStockOutSerializer`
(`serializers.py:276`); o **contexto** no `get_serializer_context()` do `StockPanelViewSet`
(`views.py:367-374`), cujo default é falso — esquecê-lo esconde dinheiro a toda a gente, que é a
direcção certa para falhar. A subclasse herda os três e **não redeclara o `CAMPOS_DE_DINHEIRO`**:
redeclará-lo é literalmente a porta irmã por onde o dinheiro sai, que é o padrão que esta casa já
apanhou duas vezes. Para o `staff` as duas chaves ficam **ausentes**, também em (b) — onde
`total_value` seria `0`, e um zero é uma afirmação sobre o preço. O `quantity_without_cost` continua
a chegar aos três papéis, porque é quantidade.

### Decisão 16 — O `?loja=` **não existe** nesta rota

O detalhe é sempre do estabelecimento inteiro: `location_id=None`, sem caso especial. Três razões, e
a primeira chega: é do `by_location` que o formulário escolhe **onde** registar a quebra, e o FEFO da
d8 é na localização pedida — um detalhe escopado a uma loja escondia as outras e tirava à pessoa a
única coisa accionável do ecrã. Segunda: `status` e `min_quantity` já são do estabelecimento (adenda
de 27), logo um detalhe escopado misturava o saldo de uma loja com o veredicto de todas, num ecrã sem
a lista ao lado para o explicar. Terceira: "`nearest_expiry` no âmbito pedido" e "âmbito = o
estabelecimento" são a mesma frase, sem ramo novo.

**A razão de domínio é mais forte do que a de desenho, e traz uma condição.** A pergunta que leva
alguém ao detalhe é *"onde é que isto está?"*; escopar à loja filtrada respondia com uma parte e
mandava comprar açúcar havendo 10 kg no armazém — compra a dobrar, às vezes em cima de validade
curta. **Mas é condição de domínio e não gosto: um número que muda de âmbito entre dois ecrãs tem de
trazer o âmbito escrito.** Quem vem da lista com a Loja 2 filtrada viu "2 kg" e abre a ficha a ver
"12 kg"; sem uma palavra, lê isso como erro de cálculo e deixa de confiar no ecrã. O saldo total do
detalhe escreve-se **"em todo o estabelecimento"** — mesmo precedente e mesma razão do "mínimo do
estabelecimento" que a adenda de 27 impôs: ali era o veredicto que mudava de âmbito, aqui é o número.

O `validateSearch` da rota (`frontend/src/routes/artigo.tsx:19`) **fica** — é o que devolve a lista
como estava —, e o comentário que lá está (*"os parâmetros não filtram o detalhe"*) passa de intenção
do cliente a facto do servidor; só ganha a segunda metade: **e o servidor não os aceita**. O cliente
não os envia, e um `?loja=` que lá chegue é ignorado como qualquer parâmetro fora do contrato.

### Impacto

**Zero tabelas, zero colunas, zero migrações, zero políticas RLS, zero Celery, zero eventos** — e se
alguma destas aparecer pelo caminho, pára-se: não é esta adenda. O isolamento é o das políticas que
já existem na `inventory_stocklevel` e no `catalog_product`, e (c) é 404 **porque a RLS não devolve a
linha**, não porque alguém comparou tenants em Python.

No `backend`: `selectors.niveis_de_stock` ganha `product_id`; nascem `nivel_do_artigo` (a linha ou
`None`) e `nivel_sem_entradas` (o **mesmo** `_nivel_de_stock` com zeros, a partir do `ProdutoResumo`);
`serializers.py` ganha a subclasse de um campo; `views.py` ganha a action e o `extend_schema` com o
parâmetro de caminho **tipado** (`OpenApiTypes.UUID`, senão sai `string`); `urls.py` não muda, porque
a rota é da action. `uv run manage.py spectacular` **e** `pnpm gen:api`: há caminho novo e componente
novo.

**Dois gates de lista fechada que esta adenda não previa, e que dispararam os dois.** (i) O
`tests/test_rls_isolation.py` tem a **lista fechada das rotas com âmbito**, na forma em cru do
resolver, e uma rota nova entra lá: `api/v1/^stock/levels/(?P<product_id>[^/.]+)$`. (ii) O
`tests/test_custos_de_stock.py::TestAsChavesDeDinheiroDoModulo` varre as **classes** do
`inventory/serializers.py`, logo a subclasse da d14 conta como classe nova e as suas três entradas
entram na tabela `CHAVES_QUE_PARECEM_DINHEIRO`. O segundo é um **bónus** e vale a pena dizê-lo: o
`test_o_que_a_tabela_diz_que_o_mixin_esconde_esta_mesmo_no_mixin` lê o `CAMPOS_DE_DINHEIRO` **na
subclasse**, logo uma redeclaração a menos cai ali — é um segundo guarda sobre a **d15**, independente
do teste dos euros por papel. **Regra para a próxima adenda:** a secção "Impacto" lista os **gates de
lista fechada** que uma rota nova toca. São precisamente os que não aparecem no diff do `spectacular`
nem no do `pnpm gen:api`, e por isso são os que se esquecem até ficarem vermelhos.

No `frontend`: o `useArtigoEmStock` passa a pedir `${CAMINHO_NIVEIS}/${produto}` com
`queryKeys.detail(tenant, RECURSO_NIVEIS, produto)`, e o `select` e o `| null` morrem. A invalidação
**não muda**: o `invalidarRecursos` apanha o prefixo do recurso, logo apanha o `detail`. O ecrã
(`screens/artigo.tsx:156-171`) troca o ramo `data === null` por dois — `never_stocked` (vazio) e 404
(erro) —, **e o do 404 tem de vir antes do ramo de erro genérico**, senão o `mensagemDeErro` imprime
o "Não encontrado." do DRF a quem está numa cozinha. Dois textos novos, e o `semArtigoCorpo` de hoje,
que junta as duas causas numa frase, desaparece.

### Os testes, e os dois que não se dispensam

Em `backend/tests/test_stock_e_alertas.py` — **menos o (3), que vive noutro ficheiro**: **(1) a mesma
linha** — para um artigo que está nos dois, o corpo do detalhe menos o `never_stocked` é **igual** ao
elemento de `/stock/levels` com o mesmo `product`; falha nos dois sentidos e é ele que impede a
segunda definição de nascer. **(2) (b) contra (c), nos dois sentidos** — artigo criado no catálogo sem
`StockLevel` → 200 com `never_stocked is True`; artigo **de outro tenant** e uuid inexistente → 404; a
terceira perna, sem a qual um servidor que respondesse sempre `true` passava: artigo que entrou e
acabou (nível a zero) → 200 com `never_stocked is False` e `status == "esgotado"`; e a quarta, que
guarda um comportamento que hoje existe por acaso: artigo **arquivado** (`is_active=False`) → **200 e
nunca 404**, com `StockLevel` e sem ele. **(3) os euros com os três papéis, em
`backend/tests/test_custos_de_stock.py` e não aqui** — é o ficheiro dessa política, e o docstring do
`test_stock_e_alertas.py` di-lo por extenso: *"duplicá-las aqui era a segunda lista a divergir da
primeira"*. `owner`, `manager` e `staff` sobre o mesmo artigo, a afirmar **presença e ausência de
chave** e nunca valores, mais um `assert` que compara o **conjunto de chaves** do detalhe com o da
linha da lista, por papel: é esse que apanha a porta irmã. **(4)** `?loja=` no detalhe: corpo idêntico
com e sem, e `by_location` com as duas localizações. **(5)** `product_id` mal formado → 400 com o
`detail` do `?loja=`, e não 404 — com a excepção do ponto, nomeada na d12: `nao.e.uuid` é 404 porque
não casa com o `url_path`, e o teste afirma as duas pernas.

**Os quatro casos-limite que se esquecem**, curtos e com sítio nos testes acima:

- **Saldo negativo** (a ADR 0012 admite-o): é `never_stocked: false` com `status: "negativo"` — um
  **terceiro facto**, que não se mistura com os outros dois. Um teste que só tenha "tem" e "nunca
  teve" deixa-o passar.
- **Lote sintético** (`__<uuid>__`): `nearest_expiry` e `lot_code` saem `null` (adenda de 27). É o
  caso em que alguém escreve "sem validade" no ecrã, quando o certo é **não escrever nada**.
- **A unidade em (b)**: o artigo tem `display_unit` no catálogo (`ProdutoResumo`), logo o corpo de (b)
  traz a `Quantidade` completa, na unidade em que a pessoa fala. Não se cai para a unidade base só
  porque o saldo é zero.
- **`never_stocked` não se deduz de saldo zero** em código novo: é **ausência de `StockLevel`**, e as
  duas condições divergem no dia em que o artigo entra e acaba — que é exactamente a terceira perna
  do teste (2).

O que nenhum destes atravessa: `frontend/scripts/ver-ecra.py` sobre `/stock/<artigo>` **com cada um
dos três papéis**, e sobre o estado (b) — que precisa de um artigo semeado sem stock. Um `.optional()`
a faltar no Zod rebenta o ecrã com o `pnpm typecheck` verde, e é por papel que as chaves de dinheiro
desaparecem.

### Decisão 17 — O caminho irmão, no `purchasing`: o que falta **não é a rota, é o cliente**

**O defeito é o mesmo, e está medido.** O `useRececao` (`frontend/src/features/purchasing/api.ts:126-134`)
pede `GET /receipts` **sem filtro** e escolhe com `results.find(…)`; com o mesmo `PAGE_SIZE = 50`
(`config/settings/base.py:352`), a 51.ª receção abre como *"esta receção não existe"*
(`screens/rececao.tsx:150-161`). A lista vem por `-received_at`, logo a que não se alcança é a **mais
antiga** — que é precisamente a que ficou por rever, e a que o contador de "por rever" do topo conta.

**O que torna esta decisão diferente da 12: a rota já existe.** `GET /api/v1/receipts/<id>` é o
`retrieve` do `RececaoViewSet` (`views.py:680-686`), está no `schema.yaml` como `receipts_retrieve`
(`:1325-1347`), está no `types.ts` (`:799-818`) e já tem dois testes (`tests/test_rececoes.py:156-200`
e `:282-296`). **A frase *"Não há `GET /receipts/<id>`"* do docstring do cliente é falsa desde que o
`purchasing` serviu a fatia 2 — e é ela o defeito.** Não nasce aqui rota nenhuma, serializer nenhum,
selector nenhum: o que a 17 fecha é o **contrato do que já se serve**, para o cliente o poder chamar
sem adivinhar, e as mesmas perguntas que a 12–16 responderam do outro lado. Onde a resposta certa
aqui é outra, está dito porquê — não se alinha por simetria.

**(a) A forma: nem action nem rota própria — é o `retrieve` que já lá está.** O argumento da d12
aplica-se e com mais força: o contexto dos euros é montado **uma** vez, no `get_serializer_context()`
do `RececaoViewSet` (`views.py:660-669`), e por ele passam **todas** as respostas desta classe,
incluindo os serializers aninhados. Um ViewSet de detalhe era um segundo sítio para o esquecer. O
`operation_id` **fica `receipts_retrieve`**, e aqui a d12 não se copia: ali declarou-se `stock_level`
porque a rota nascia como action e o nome automático descreveria a action e não o recurso; aqui os
ids desta classe são **todos** automáticos, e renomear um só punha duas convenções no mesmo ViewSet —
que é a frase com que o corpo desta ADR matou os sufixos `_id`.

**(b) Os estados: são dois e não três, e isso confirma-se em vez de se assumir.**

| estado | resposta |
|---|---|
| (a) a receção é legível neste tenant | `200`, `RececaoOut` |
| (b) não é — nunca existiu, era rascunho e foi apagada, ou é de outro estabelecimento | `404` |

Procurou-se o análogo do estado (b) da d13 e **não existe**, por três factos verificados: o `Receipt`
**não tem descarte suave** — o `discarded_at` é do `InvoiceDocument` (`models.py:229`) e o
`apagar_rascunho` **apaga a linha** (`services.py:1601-1617`); o `get_queryset` é **um só** para a
lista e para o detalhe (`views.py:656-658`), ao contrário do `DocumentoViewSet`, que tem duas e cujo
detalhe serve o que a lista esconde; e, sobretudo, **nenhum outro módulo é dono da identidade de uma
receção**. Em (b) do `inventory`, quem sabia que o artigo existe era o `catalog`; aqui a linha *é* a
receção, não há segundo dono a quem perguntar, e portanto não há nada que exista sem ter corpo. O 404
quer dizer uma coisa só desde o primeiro dia, sem o trabalho que a d13 teve de fazer para lá chegar.

Os dois candidatos que se pesaram e **não são estados desta rota**: a receção **por rever**
(`status: "needs_review"`) é um campo do corpo, e o ecrã já ramifica nele (`screens/rececao.tsx:114`
e `:196`); a receção **sem linhas** — documento ainda em leitura — é o vazio de
`GET /receipts/<id>/lines`, que é outro pedido com o seu próprio estado. Nenhum dos dois muda o
status da resposta.

**Logo, e isto é o inverso da d13: o texto do ecrã fica.** O `naoExisteTitulo`/`naoExisteCorpo`
(`screens/rececao.tsx:150-161`) diz hoje **uma** frase e ela é **verdadeira**, porque só há uma causa
— ao contrário do `semArtigoCorpo`, que juntava duas e morre. O que muda é de onde vem: deixa de ser
`data === null` e passa a ser o **404**, e o ramo do 404 **tem de vir antes do ramo de erro genérico**
(`:140-148`), senão o `mensagemDeErro` imprime o "Não encontrado." do DRF a quem está ao lado de uma
palete. É a única metade da d13 que atravessa.

**(c) Um `id` mal formado dá 404 e fica assim — e aqui a resposta é diferente da d12.** O
`get_object()` do DRF passa pelo `get_object_or_404` dos `generics`, que apanha `ValueError` e
`ValidationError` e levanta `Http404`: um "abc" nunca chega ao Postgres. A d12 escolheu 400 porque a
action nascia sozinha e o `?loja=` ao lado já tinha o `DETALHE_UUID_INVALIDO` para reutilizar. Aqui o
mesmo `pk` atravessa **nove** operações desta classe (as quatro de `/receipts/<id>`, as duas de
`/lines`, a confirmação da linha, a temperatura e a confirmação da receção): fazer só o `GET`
responder 400 era dar duas respostas ao mesmo erro no mesmo recurso, e o cliente nunca constrói este
id — recebe-o de um link. Fica escrito para ninguém o "corrigir" por simetria com a 12.

**(d) Os euros: é uma porta nova para o mesmo dinheiro, e a herança é total.** Três sítios, os mesmos
de sempre: a **política** em `accounts/api.py:354-398` (`PAPEIS_QUE_VEEM_EUROS` → `ve_euros` →
`SemEurosParaQuemNaoVe.to_representation`); a **lista de campos** no
`CAMPOS_DE_DINHEIRO = ("document_total", "lines_total", "vat_breakdown")` do `RececaoOutSerializer`
(`serializers.py:875-879`) — e, no pedido vizinho que o mesmo ecrã faz, o
`("unit_price", "discount_pct", "line_total", "price_history")` do `LinhaOutSerializer` (`:789-794`);
o **contexto** no `get_serializer_context()` do `RececaoViewSet` (`views.py:660-669`), cujo default é
falso, logo esquecê-lo esconde dinheiro a toda a gente — a direcção certa para falhar.

**Não se declara nada, e é esse o ponto.** O `retrieve` já serializa com o contexto desta view
(`views.py:683-685`), logo os três sítios do detalhe são **os mesmos** da lista e não há um quarto.
Como na d15, o que aqui se proíbe é o reflexo contrário: redeclarar o `CAMPOS_DE_DINHEIRO` numa
classe de detalhe é literalmente a porta irmã por onde o dinheiro sai, e foi assim que a ADR 0031
fechou os euros da receção e deixou o `ExtracaoOut` do documento aberto **sobre a mesma fatura**.
Para o `staff` as três chaves ficam **ausentes** — nunca `0`, que é uma afirmação falsa sobre o preço,
nunca `null`, que o ecrã imprime "—". Isto **já é o comportamento de hoje e já tem teste**
(`test_rececoes.py:282-296`); o que a 17 acrescenta é a obrigação de o provar por **conjuntos de
chaves contra a lista**, em (g).

Uma consequência que o cliente tem de absorver: o ecrã decide as **colunas** de dinheiro pela
presença das chaves no cabeçalho (`euros-do-papel.ts:57-63`, `screens/rececao.tsx:115-120`) e não
pelo papel da sessão. Isso continua certo e é o desenho. O que deixa de ser verdade é a razão escrita
ao lado — *"o cabeçalho chega antes das linhas"* e *"vem da mesma entrada de cache que a lista"*: o
cabeçalho passa a ser um pedido com o seu próprio tempo. Não há salto de layout, porque a tabela só
renderiza dentro do ramo em que o cabeçalho já existe (`:162`), mas os **dois comentários ficam
falsos** e corrigem-se no mesmo PR — é a mesma espécie de dívida que a 17 existe para pagar.

**(e) As linhas não entram no detalhe, e a lista não muda.** O `RececaoOut` serve `line_count` e
`lines_to_review` e **não** as linhas; quem as serve é o `GET /receipts/<id>/lines`, que o ecrã já
pede em paralelo (`api.ts:158-168`) e que tem o seu próprio corpo `{count, results}`. Embebê-las aqui
dava duas fontes para a mesma tabela e um segundo sítio por onde os euros da linha saem. O argumento
de custo que morreu na d12 — *"o detalhe não paga um pedido que a lista já pagou"* — aqui nem chega a
levantar-se: a lista **já compõe as linhas de todas as receções da página** para calcular os
acumulados do cabeçalho (`views.py:715` → `_compor_rececao`), logo o detalhe de uma receção é o mais
barato dos dois pedidos.

**(f) O corpo é o elemento da lista, chave a chave, e não nasce um segundo schema.** A lista e o
detalhe constroem-se com o **mesmo** serializer, sobre o **mesmo** `_compor_rececao` e com o **mesmo**
contexto (`views.py:680-686` e `:713-721`): são iguais por construção e não por coincidência. Não há
aqui o `+ never_stocked` da d14 — **zero campos novos, zero subclasse, zero `.extend()`**. Do lado do
cliente, o `rececaoSchema` (`schemas.ts:315`) continua a ser a única definição de uma receção; o que
muda é o tipo de retorno do hook, que passa de `Rececao | null` a `Rececao` — o `| null` era o
`find()` a falhar, e com a rota isso é o 404.

**(g) Os testes, em `backend/tests/test_rececoes.py`.** **(1) a mesma linha** — para uma receção que
está nos dois, o corpo de `GET /receipts/<id>` é **igual** ao elemento de `GET /receipts` com o mesmo
`id`; falha nos dois sentidos e é ele que impede uma segunda definição de receção de nascer.
**(2) o alcance, que é o defeito** — semear 51 receções e pedir a que **não** está na primeira página,
afirmando 200: sem esta perna, o (1) passa com o defeito intacto. **(3) os conjuntos de chaves por
papel** — `owner`, `manager` e `staff` sobre a mesma receção, a comparar `set(detalhe)` com
`set(linha_da_lista)` e a afirmar **presença e ausência de chave**, nunca valores; é o equivalente ao
teste (3) acima e é ele que apanha a porta irmã. **(4)** receção de outro tenant e uuid inexistente →
404 (o primeiro já existe, `:156-200`). **(5)** `id` mal formado → **404 e não 500**, que é a alínea
(c) a ficar com guarda em vez de ficar só escrita.

O que nenhum destes atravessa: `frontend/scripts/ver-ecra.py` sobre `/receber/<rececao>` **com cada um
dos três papéis**. O `rececaoSchema` é escrito à mão e os três acumulados já lá são `.optional()`
desde a ADR 0031; o que muda de forma é o tipo de retorno do hook e os ramos do ecrã, e nenhum gate
atravessa essa fronteira.

**Defeito herdado, e já não fica só nomeado: é a decisão 18, a seguir.** O `RececaoViewSet` é um
`ModelViewSet` completo, logo **`PUT /api/v1/receipts/<id>` está no contrato**
(`schema.yaml:1348-1378`, com o docstring da classe como descrição) e responde 500. Tirá-lo é uma
mudança de contrato que precisava do dono; o dono decidiu, e sai neste PR.

**Impacto da decisão 17.** **Zero tabelas, zero colunas, zero migrações, zero políticas RLS, zero
Celery, zero eventos** — e, ao contrário das 12–16, **zero endpoints novos**: esta decisão não
acrescenta uma linha ao diff do `uv run manage.py spectacular` e do `pnpm gen:api`, **mas o diff
deixou de poder sair vazio — a d18, no mesmo PR, tira o `receipts_update` do contrato** (e a **d19**,
decidida depois das duas, acrescenta-lhe os dois `requestBody` que mentem e o componente que eles
seguravam: o diff esperado está escrito no fim da d19, e é lá que se lê, não aqui). No `backend`: nada
além dos testes de (g). No `frontend`: o `useRececao` troca a lista por `${CAMINHO_RECECOES}/${rececao}`
com `queryKeys.detail(tenant, RECURSO_RECECOES, rececao)`, e o `select` e o `| null` morrem; o
`invalidarRececoes` **não muda**, porque invalida por `queryKeys.resource` e esse prefixo apanha o
`detail`; o `screens/rececao.tsx` troca o ramo `dados === null` pelo ramo do 404, **antes** do ramo de
erro genérico; e os dois comentários caducos — o do `api.ts:112-124`, que afirma que a rota não existe
e cita por extenso uma decisão que esta adenda revoga, e o do `euros-do-papel.ts:50-55` — são **parte
da correcção** e não arrumação: foi um deles que trouxe a 17 para dentro do âmbito. **Toca em faturas
e em dinheiro: consultar `domain-expert`** — ainda que, como nas 12–16, nenhuma regra de domínio mude;
o que muda é a porta.

### Decisão 18 — O `PUT /receipts/<id>` sai do contrato, e sai pela lista de métodos

**O que está publicado, medido.** O `RececaoViewSet` é um `viewsets.ModelViewSet`
(`views.py:643`), logo o router liga o `put` ao `update` herdado. Esse `update` pede o serializer ao
`get_serializer_class`, que para tudo o que não é `create` nem `partial_update` devolve o
`RececaoOutSerializer` — um `serializers.Serializer` **sem `update()`** (`serializers.py:872`) —, e o
`save()` levanta `NotImplementedError`. A rota está **publicada** (`schema.yaml:1348`,
`receipts_update`) e já chegou ao cliente gerado (`types.ts:809`). O remate: os campos daquele
serializer **não são read-only** (`doc_type`, `received_at`, `doc_number`, `customer_nif`, …), logo
**o único corpo que o contrato publicado aceita é exactamente o que chega ao 500** — um corpo errado
dá 400, um corpo certo dá 500, e não há terceiro caminho. Alcançável por qualquer membro autenticado
do tenant (`IsAuthenticated + PertenceAoTenant`, `views.py:646`) e também sobre uma receção
**confirmada**, porque o `update` não tem a guarda do `_resposta_de_rececao_confirmada` que o
`partial_update` e o `destroy` têm. **Não corrompe nada** — o `NotImplementedError` é antes de
qualquer escrita —, e é por isso que isto se fecha **tirando o método** e não escrevendo-lhe um corpo:
o que está partido é o contrato, não o comportamento.

**A decisão: `http_method_names` na classe.**
`http_method_names = ["get", "post", "patch", "delete", "head", "options"]`. É um atributo e não
código, e é o atributo que **as duas pontas lêem**: o DRF compara-o no `dispatch` (fora dele é 405,
antes de haver view) **e** o `drf-spectacular` cruza-o com as actions do router para decidir o que
publica (`EndpointEnumerator.get_allowed_methods`). Uma lista, dois efeitos, sem poderem divergir: o
que o servidor recusa é o que o schema não tem. **O `PATCH` fica** — é o que o ecrã usa para o
cabeçalho, pelo `CabecalhoInSerializer` — e o `PUT` sai. O `trace` sai de caminho; o `head` e o
`options` ficam, porque o DRF mapeia `head` → `get` na própria `as_view` e o `OPTIONS` é o preflight e
a metadata.

*Porque não um `update()` que levante 405 à mão.* Fazia o contrário do que se quer: o servidor
passava a recusar com elegância **uma rota que continuava publicada**, o `pnpm gen:api` continuava a
gerar o `receipts_update`, e o cliente continuava a poder construí-lo a partir do tipo. É código
escrito para dizer "não" onde bastava não oferecer, e é mais um sítio para esquecer. *E porque não
trocar a base para `viewsets.GenericViewSet`* — que faria o `update` deixar de existir e o router
deixar de o ligar: resolve o caso de hoje e protege por **ausência**, que dura até alguém voltar a
`ModelViewSet` por hábito; o `http_method_names` protege por **afirmação**, que é o que esta casa
escreve. (O preço, dito: a lista vale para a classe inteira, logo uma action futura em `PUT` nasceria
405 até alguém mexer nesta linha. É a direcção certa para falhar.)

**A varredura, feita antes de escolher a lista.** As doze operações publicadas por esta classe:
`GET`/`POST /receipts` (`list`, `create`); `GET`/`PUT`/`PATCH`/`DELETE /receipts/<id>` (`retrieve`,
**ninguém**, `partial_update`, `destroy`); `GET`/`POST /receipts/<id>/lines`;
`POST /receipts/<id>/lines/<linha>/confirmation`; `POST /receipts/<id>/temperature`;
`POST /receipts/<id>/confirmation`; `GET /receipts/summary`. **Todas têm corpo escrito nesta classe
menos o `PUT`** — a herança do `ModelViewSet` contribui com um método, e é o partido. **Não há um
segundo**: nada mais está publicado sem quem o sirva, e é essa varredura que torna a lista acima uma
escolha e não um palpite. (A varredura é sobre **handlers**; a **d19** mede a outra direcção e
encontra dois, e por isso esta frase continua verdadeira no que afirma.)

**O teste, em `backend/tests/test_rececoes.py`, (6).** Um mapa fechado de (caminho, método), na forma
do `APPEND_ONLY` do `tests/test_db_roles.py`: o `PUT /receipts/<id>`, com um corpo que satisfaz o
schema que hoje se publica, responde **405** — e nunca 500, que é a afirmação que importa; e cada um
dos servidos (`GET` e `POST` em `/receipts`, `GET`, `PATCH` e `DELETE` em `/receipts/<id>`, e as
actions) responde **qualquer coisa menos 405**. Falha nos dois sentidos: devolver o `PUT` derruba a
primeira perna, e encolher a lista a mais — um `http_method_names = ["get"]` apagava o ecrã Receber
inteiro — derruba a segunda. O cabeçalho `Allow` do 405 **não** serve de âncora: o DRF levanta
`MethodNotAllowed` e não o escreve.

**Consequência, e é a única que atravessa o PR.** O critério de aceitação da d17 dizia *diff vazio* no
`pnpm gen:api`; com a d18 passa a ser **uma rota a menos** — o caminho `/api/v1/receipts/{id}` perde a
chave `put`, o `types.ts` perde a operação `receipts_update`, e mais nada muda. Qualquer outra linha
no diff é alguém a mudar o contrato sem o dizer. Nenhum Zod mexe: o cliente nunca chamou esta rota.
**A d19, decidida depois desta e no mesmo PR, alarga este critério — o diff esperado passa a ser o da
d19, e é lá que está escrito.**

### Decisão 19 — Os dois `requestBody` que mentem, e a lição dos três no mesmo dia

**Medido, não deduzido.** Duas operações do `RececaoViewSet` publicam um `requestBody` **obrigatório**
(`required: true`) que o handler não lê: o `POST /receipts/<id>/confirmation`
(`backend/apps/purchasing/views.py:924`) **não lê corpo nenhum** e publica o `RececaoOutRequest`
(`frontend/openapi/schema.yaml:1441-1449`); o `POST /receipts/<id>/temperature` (`views.py:902`) lê o
`TemperaturaInSerializer` (`:909`) e publica o **mesmo** `RececaoOutRequest` (`schema.yaml:1564-1572`).
A causa é uma e é comum: o `extend_schema` destas actions não declara `request=`, logo o
drf-spectacular cai no `get_serializer_class()` e apanha o `RececaoOutSerializer` — a resposta da
classe, servida como se fosse o pedido.

**É a mesma espécie da d18, e a d18 não a apanhou por desenho e não por descuido.** Ali havia um
método publicado **sem quem o sirva**; aqui há um corpo publicado **que ninguém lê**. A varredura da
d18 foi sobre *handlers* — "o que está publicado tem quem o sirva?" — e estas duas **têm** handler: o
que mente não é o método, é o corpo. Debaixo das duas está a mesma coisa: o `get_serializer_class()` a
servir de resposta por omissão a uma pergunta que ninguém fez.

**A decisão: declara-se o corpo em cada uma.** `request=TemperaturaInSerializer` na temperatura,
`request=None` na confirmação. **Zero mudança de comportamento**: o servidor já acerta hoje — a
confirmação ignora o que lhe mandem e a temperatura valida pelo serializer certo. O que está partido é
o **contrato**, e com ele o `types.ts` que o cliente gera, que hoje exige ao programador o objecto de
uma **receção inteira** para confirmar uma receção.

**O diff esperado, que é o critério de aceitação do PR.** Estas duas eram os **únicos** consumidores
do `RececaoOutRequest` depois de a d18 tirar o `PUT` — é por isso que o componente sobreviveu à d18 e
é isso que o torna falsificável aqui. O `pnpm gen:api` passa a mostrar, e nada mais: o `put` de
`/api/v1/receipts/{id}` a menos (d18), os dois `requestBody` corrigidos, e o componente
`RececaoOutRequest` a **desaparecer** do `schema.yaml` e do `types.ts`. Nenhum Zod mexe: o cliente
nunca enviou corpo a nenhuma das duas.

**O teste, em `backend/tests/test_rececoes.py`, (7).** Um mapa fechado de
(`operation_id` → corpo publicado), na forma do `METODOS_SERVIDOS` da d18 e lido do
`SchemaGenerator().get_schema()` como o `test_health.py:184` já faz: a confirmação **sem**
`requestBody`, a temperatura com o `TemperaturaInRequest`, e o `RececaoOutRequest` **ausente** dos
componentes. Falha nos dois sentidos. A segunda perna é a do comportamento, e é curta: a confirmação
com um corpo arbitrário responde o mesmo que sem corpo — é o que prova que isto se arruma no contrato
e não na semântica.

**A lição, que é o que vale para a próxima.** Três defeitos desta família apareceram no **mesmo
ficheiro no mesmo dia**: um método sem corpo (d18) e dois corpos sem método (d19). O que os une não é
o `RececaoViewSet` — é o `get_serializer_class()` a responder por omissão onde ninguém perguntou, e
isso existe em todas as classes da casa. Se três apareceram num ficheiro, **o padrão é provavelmente
da casa e não deste**. A varredura que daí sai fica nomeada e por fazer, no "Fora de âmbito".

### Fora de âmbito — nomeado

**Os acentos do `?q=`** continuam por corrigir no `WHERE` (dívida nº 1 desta ADR) e são a outra
metade da frase falsa — quem procura "acucar" também não alcança o artigo. **`?loja=` no detalhe**
volta a ser pergunta legítima no dia em que o mínimo for por (artigo, localização), porque aí deixa
de misturar âmbitos. **O caminho irmão saiu desta lista**: o `useRececao` passou a estar **dentro** do
âmbito por decisão do dono e é a **decisão 17**, acima — o que aqui ficava escrito era que esta
adenda o deixava de pé, e já não deixa.

**A varredura da família da d19, em toda a casa — por fazer, e o dono não a mandou fazer neste PR.**
É isto: **todos os ViewSets, à procura de operações cujo `requestBody` publicado não seja o que o
handler lê**. Fica nomeada porque o sinal está medido e não é local — três defeitos da mesma família
num ficheiro só (d18 e d19), com uma causa (`get_serializer_class()` a responder por omissão) que
nenhuma das duas decisões conserta fora da classe onde foram vistas. O que daí deve sair é um **gate**
e não uma lista: a lista apodrece — esta ADR já o viu acontecer duas vezes —, e um gate que leia o
schema gerado falha nos dois sentidos sem ninguém o regenerar.

**Artigo com mínimo definido e sem `StockLevel` nenhum é uma falta — decidido pelo dono a
2026-10-29, por implementar em fatia própria.** Hoje nunca aparece como falta, e é deliberado: o
`selectors.py:810-813` parte do `StockLevel` e o docstring (`:805`) exclui por extenso *"artigos sem
`StockLevel` nenhum (nunca entraram)"*. O argumento de domínio que ganha: definir um mínimo é a
decisão humana *"quero ter sempre isto"*, e zero unidades contra essa decisão **é** uma falta — a app
**sub-avisa** em silêncio, na mesma família do `shelf_life_after_opening_days`. Não entra neste PR
porque muda o selector (passa a partir do **catálogo** e não do `StockLevel`), muda o `missing_count`,
muda a invariante *"cada contador é igual ao `count` da lista que filtra"* (adenda de 27) e muda o
ecrã de Alertas — nada disso é desta fatia. Fica escrito **como decisão tomada**, e não como pergunta,
para quem abrir a fatia não a voltar a discutir.

**Um artigo que nunca entrou não tem porta de contagem** — medido, e é por isso que o texto de (b) da
d13 não a promete. A folha materializa **uma linha por artigo com nível não-zero naquela
localização** (`count_services.py:257-265`), logo um `never_stocked` nunca lá está; o
`POST /stock/counts/<id>/lines` **aceita** um artigo fora da folha, com `expected` tirado no momento —
zero se nunca entrou (`count_services.py:345-349`) —, mas o `screens/contar.tsx` só rende as linhas da
folha e **não tem campo de procura** para lá chegar; e, mesmo com esse campo, um artigo com
`track_lots=True` e sem lote a sério é **recusado por desenho** (ADR 0030, segunda ronda, resposta 4),
e um artigo que nunca entrou não tem lote nenhum. São **duas** dívidas e não uma: a porta no ecrã, e o
que fazer com o `track_lots` na primeira contagem de um artigo que ainda não deu entrada.

**Três dívidas de conformidade, ditas de cor pelo `domain-expert` e por confirmar contra o plano
HACCP de um cliente real** — ficam nomeadas com essa ressalva, e não como facto assente:

- **"Onde está o lote L2345?" não tem resposta neste ecrã.** Numa recolha do fornecedor a pergunta é
  **por lote** e a resposta tem de ser lote → localizações → quantidade. É o único cenário em que
  este ecrã é usado sob pressão e com a ASAE à frente. É o grão que a d1 matou no `by-product` por
  não ter consumidor — o que continua verdadeiro **hoje**: a recolha é o consumidor que ainda não
  existe, e reconstruí-lo é decisão de outra fatia, não um arrependimento desta.
- **"De quem veio este lote?"** — um-passo-atrás, Reg. CE 178/2002 art. 18: o operador é obrigado a
  identificar o fornecedor de cada género, e o que o inspector pede é **fornecedor + documento + data
  de recepção, por lote**. O histórico traz o `receipt` na `reference`, mas crua, e o
  `reference_label` da adenda de 27 só sabe nomear **contagens** — o que vem de fora do módulo fica
  sem rótulo, por decisão. É dívida de **conformidade** e não de conforto. Nomear uma receção obriga o
  `inventory` a saber como o `purchasing` chama um documento: a porta é um campo que o `purchasing`
  sirva, nunca um `import`.
- **A validade secundária não é só a abertura.** O `shelf_life_after_opening_days` já está nomeado na
  adenda de 27; o que falta dizer é que a **descongelação** cria um prazo do mesmo tipo — dias, a
  contar do descongelado, e **nunca** de volta ao prazo do congelado. É a mesma dívida com dois
  gatilhos, e enquanto durar um ecrã de Alertas vazio continua a não querer dizer "está tudo em dia".
