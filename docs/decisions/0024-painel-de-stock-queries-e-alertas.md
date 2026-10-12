# ADR 0024 — Painel de Stock: queries read-only ao ledger e alertas

**Contexto.** A ADR 0023 (Fatia 3) criou o ledger de stock com quatro tabelas (`Lot`, `StockMovement`, `StockLevel`, `ProductCost`), protegidas por RLS. A Fatia 2 do frontend desenhava o ecrã de Stock com dados de fixtures (DESIGN.md, ADR 0008, decision 3). A Fatia 4 substitui essas fixtures por queries reais — um painel read-only que agregua saldos por localização e lote, com alertas de falta de stock, validade a vencer e validade vencida.

**Decisão 1 — O que o painel mostra (saldo por (product, lot)).**

Agregação por tenant, localização (filtro opcional), e (product, lot), ordenado por FEFO (lotes que expiram primeiro):

| Campo | Origem | Visível |
|---|---|---|
| `product_id` | `StockLevel.product_id` | Não (chave de agrupamento) |
| `product_name` | `Product.name` (via `select_related`) | Sim |
| `lot_code` | `Lot.code` | Sim |
| `expires_at` | `Lot.expires_at` | Sim, ou "–" se NULL |
| `quantity` | `SUM(StockLevel.quantity)` por (location, lot) | Sim, em unidade base do produto |
| `unit_cost` | `StockLevel.unit_cost` (FIFO do lote, não média) | Sim (se > 0, senão "preço desconhecido") |
| `total_value` | `quantity × unit_cost` | Sim, agregado |

Vista sem localização (painel de entrada): `SUM(quantity)` e `total_value` agregados por product (sem lote visível). Vista com localização ou por produto: desagregado por (location, lot) conforme acima.

**Decisão 2 — Alertas em query separada.**

Cada alerta tem `severity` (crítica, aviso, info) e `product_id`, `location_id`:

| Tipo | Condição | Severidade | Query |
|---|---|---|---|
| Falta de stock | `StockLevel.quantity < Product.min_quantity` | Crítica | `SELECT DISTINCT product_id, location_id WHERE quantity < min_quantity` |
| Validade a vencer | `Lot.expires_at BETWEEN now() AND now() + 7 days` | Aviso | `SELECT DISTINCT lot_id, product_id, location_id WHERE expires_at < now() + 7 days AND expires_at >= now()` |
| Validade vencida | `Lot.expires_at < now()` | Crítica | `SELECT DISTINCT lot_id, product_id, location_id WHERE expires_at < now()` |

Um produto sem saldo (`quantity = 0`) não gera alerta de falta, mesmo se `min_quantity > 0` (o painel o marca com "fora de catálogo" se nunca entrou).

**Decisão 3 — Contrato de endpoints (GET read-only).**

1. **`GET /stock/summary?location_id=<uuid>`**
   - Resposta: lista de `{product_id, product_name, quantity, total_value}` por product, agregado de todas as localizações (se `location_id` omitido) ou de uma (se fornecido).
   - Paginação: 50 por página (cursor não necessário — totais são fixos).
   - Permissão: `IsAuthenticated + PertenceAoTenant`.

2. **`GET /stock/by-location?location_id=<uuid>&search_text=<str>&page=<int>`**
   - Resposta: lista de `{product_id, product_name, lot_code, expires_at, quantity, unit_cost, total_value}` nessa localização, agrupado por (product, lot).
   - Filtros: `location_id` obrigatório; `search_text` opcional (substring em product_name ou lot_code).
   - Paginação: 50 por página.
   - Permissão: `IsAuthenticated + PertenceAoTenant`.

3. **`GET /stock/by-product?product_id=<uuid>&search_text=<str>&page=<int>`**
   - Resposta: lista de `{product_id, product_name, location_id, location_name, lot_code, expires_at, quantity, unit_cost, total_value}` desse produto, agrupado por (location, lot).
   - Filtros: `product_id` obrigatório; `search_text` opcional (substring em location_name ou lot_code).
   - Paginação: 50 por página.
   - Permissão: `IsAuthenticated + PertenceAoTenant`.

4. **`GET /stock/alerts?severity=<critical|warning|info>&product_id=<uuid>&location_id=<uuid>&page=<int>`**
   - Resposta: lista de `{alert_type, severity, product_id, product_name, location_id, location_name, lot_code, expires_at}`.
   - Filtros: `severity`, `product_id`, `location_id` opcionais (AND).
   - Paginação: 50 por página.
   - Permissão: `IsAuthenticated + PertenceAoTenant`.

Resposta de paginação: `{items: [<item>], total: int, page: int, page_size: 50}` (padrão do projeto, ADR 0008).

**Decisão 4 — Permissões.**

- Todas as queries são `IsAuthenticated` + `PertenceAoTenant` (cada tenant vê só seu stock).
- RLS no BD já protege (ADR 0023, decisão 4): qualquer `SELECT` fora de âmbito devolve zero linhas.
- Sem `IsStaff` ou papel específico — qualquer membro activo (owner, manager, staff) pode consultar; relatório é leitura, não escrita.

**Decisão 5 — Casos limite.**

1. **Produto novo (sem movimentos)**: não aparece no painel até a primeira receção confirmada (quando `StockLevel` é criado). Permissão: aparecer em busca por `product_id` se já tem saldo (mesmo que zero).

2. **Lote sintético para artigos sem rastreio** (`track_lots=False`): aparece agrupado com `lot_code='__<product_id>__'` no painel (antes da Decisão 5 da ADR 0023, era a única linha visível). Visualização: exibir como "–" em vez do código sintético se desejado (decisão de frontend).

3. **CMP zero** (`unit_cost = 0`): mostrar com flag "preço desconhecido" em vez de "€ 0". Query: `CASE WHEN unit_cost = 0 THEN NULL ELSE unit_cost END` para o campo `unit_cost`, frontend marca visualmente se NULL.

4. **Produto com `track_lots=True` mas linha confirmada com `lot_id=NULL`**: validação backend (ADR 0023, decisão 7, caso limite 2) impediu isto. Se houver (bug), aparecer uma linha com `lot_code=NULL` e `expires_at=NULL` — não é um erro de query, é um erro de migração de dados.

5. **`min_quantity` não tem default nesta fatia**: é campo de `catalog_product` a preencher no ecrã de Catálogo (Fatia 5 ou depois). Alert de falta de stock mostra "mínimo não configurado" se `min_quantity IS NULL` em vez de comparar. Alerta desligado até configuração.

6. **Cálculo de FEFO**: ordenar por `Lot.expires_at ASC NULLS LAST` (NULL é sem validade, vai para o fim); depois `Lot.received_at ASC` (mais antigo primeiro, tiebreaker). Isto é a ordem de leitura para `consumption` (Decisão 3 da ADR 0023); o painel só mostra a ordem, o consumo é no módulo `recipes`.

**Decisão 6 — Performance.**

Índices novos em `StockLevel` (migração 0024-*):
- Parcial `(tenant_id, location_id, product_id)` em `StockLevel` (filtro `WHERE quantity != 0`): acelera queries por localização.
- Parcial `(tenant_id, product_id, location_id)` em `StockLevel` (filtro `WHERE quantity != 0`): acelera queries por produto.
- Composto `(tenant_id, expires_at)` em `Lot` (filtro `WHERE expires_at IS NOT NULL AND expires_at < now() + interval '7 days'`): acelera alertas de validade.

Queries:
- `select_related('product', 'lot')` em `StockLevel` para evitar N+1 (nomes vêm junto).
- `annotate(total_value=F('quantity') * F('unit_cost'))` ao nível da view.
- Sem cache de resultados (dados mudam a cada confirmação de receção); alertas podem ter TTL de 5 min (última mudança é `confirm_receipt` que escreve a outbox).

**Decisão 7 — Bloqueadores.**

Nenhum conhecido. ADR 0023 deixou tudo pronto:
- ✅ Quatro tabelas com RLS.
- ✅ `StockLevel` agrega por (product, location, lot).
- ✅ `Lot.expires_at` existe e é indexável.
- ✅ `Product.min_quantity` será preenchido após Catálogo validar o campo.
- ✅ `StockMovement.created_by` e `created_at` existem para auditoria.

---

## Alternativas

**Sem agregação no painel**: mostrar todas as linhas de `StockLevel` sem SQL. Problema: N linhas por product (um por localização+lote), tabela explosiva para tenant grande.

**Alertas em tabela `Alert` separada**: escrever `Alert` sempre que `StockLevel` muda. Problema: tabela cresce sem limite, cada movimento gera alertas fantasma que depois desaparecem (produto reposto), complexidade de limpeza.

**Cache Redis para saldos**: TTL 1 min, invalidação por evento. Problema: RLS está no BD; Redis não conhece tenant, teria de implementar isolamento manual.

**Dois endpoints (saldo + alertas) em um só**: `GET /stock` com `?view=summary|alerts`. Problema: UX de frontend, dois tipos de resposta, duas páginas na UI — melhor dois endpoints.

---

## Consequências

- Dois novos módulos no `inventory/` (`selectors.py` para queries, `views.py` para endpoints): sem mudanças em `services.py` (read-only).
- Sem novas tabelas (reutiliza `StockLevel`, `Lot`, `StockMovement`, `Product`, `Location`).
- Sem eventos novos (painel é observação, não ação).
- Migrações: quatro índices em `StockLevel` e `Lot`; sem mudanças em estrutura.
- Frontend: substitui fixtures de `Stock.tsx` e `Alerts.tsx` por queries a estes quatro endpoints (ADR 0008 remove `GET /api/fixtures/stock`, `GET /api/fixtures/alerts`).
- Teste: factory `StockLevelFactory` e `LotFactory` em `tests/factories.py`; casos: produto sem movimento, produto com lote vencido, produto com quantidade abaixo de mínimo, alerta com filtro, paginação.

---

**Consultar `domain-expert`**: não há regras de negócio novas — ledger já foi validado em ADR 0023. As queries são projeção limpas de dados existentes.
