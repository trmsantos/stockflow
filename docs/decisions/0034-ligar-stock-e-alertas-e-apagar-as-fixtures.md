# ADR 0034 — Ligar o Stock e os Alertas, e apagar o servidor de dados falsos

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
