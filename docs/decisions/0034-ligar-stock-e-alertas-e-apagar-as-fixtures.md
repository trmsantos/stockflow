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
| `GET /stock/summary` | `loja?` | `ResumoDeStock` | `stock_value_eur` |
| `GET /stock/movements` | `artigo` (**obrigatório**, 400 sem ele) `page?` | página de `Movimento`, `-occurred_at` | `unit_cost` |
| `POST /stock/movements/waste` | corpo abaixo | 201 `Movimento` | `unit_cost` |
| `GET /stock/alerts` | `risco=expira\|falta?` `page?` | página de `Alerta` | `value_eur` |
| `GET /stock/alerts/summary` | — | `ResumoDeAlertas` | `wasted_today_eur`, `wasted_week_eur` |
| `GET /stock/alerts/waste` | `periodo=hoje\|semana?` `page?` | página de `Desperdicio` | `value_eur` |

```python
NivelDeStock:   product: UUID; short_name: str; quantity: Quantidade; min_quantity: Quantidade
                status: "ok"|"baixo"|"esgotado"|"negativo"; by_location: list[{location:{id,name}, quantity}]
                nearest_expiry: {lot_id, lot_code, expires_at: date, days_away: int, kind} | None
                quantity_without_cost: Quantidade;  unit_cost: Decimal|None;  total_value: Decimal
                # ordem: estado, depois days_away (NULLS LAST), depois short_name. Nunca por valor.
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
