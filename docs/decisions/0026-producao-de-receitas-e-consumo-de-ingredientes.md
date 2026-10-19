# ADR 0026 — Produção de receitas: consumo de ingredientes e criação de produto acabado

**Contexto.** A ADR 0014 definiu `production_out` e `production_in` como dois tipos de movimento; a ADR 0023 detalhou como entram no ledger; a fatia 5 fechou os movimentos manuais. A fatia 6 desenha o contrato de `recipes.api.produzir()`, a função que escreve os dois movimentos atomicamente quando um operador produz uma receita.

**Decisão 1 — Fluxo de produção e assinatura de contrato.** Uma receita tem N ingredientes, cada um com quantidade em unidade base e `yield_factor`. Produzir: `recipes.api.produzir(recipe_id: UUID, quantity: Decimal, location_id: UUID, tenant_id: UUID, user: User) → production_id: UUID`. Quantidade é a de produto acabado desejada. Interno: multiplica por `1 / yield_factor` para obter a quantidade de ingredientes a consumir. Atomicamente na mesma transação: cria `production_out` por cada ingrediente (quantidade negativa = `−quantity_base / yield_factor`, FEFO), depois `production_in` (quantidade positiva = `quantity` ao custo derivado).

**Decisão 2 — Custo unitário de production_in.** `unit_cost = Σ(|production_out.qty| × production_out.unit_cost) / quantity`. O `yield_factor` entra no cálculo de production_out.qty, não no custo final: se 10kg de massa dão 9kg de pastéis (`yield_factor=0.9`), um lote de 100 pastéis (quantidade=100, unidade=unidade) consome 100 / 0.9 ≈ 111kg de massa (production_out.qty = −111). Custo unitário = custos da massa / 100. Precisão: `Decimal(12,6)` como `StockMovement.unit_cost`.

**Decisão 3 — Contrato internamente, não há endpoint.** O `recipes.api.produzir()` é uma função síncrona chamada por: (a) um endpoint POST futuro `/recipes/<id>/produce` no `recipes/views.py` (fatia 7 ou posterior); (b) um talão de venda que consume e produz no mesmo passo (futuro); (c) Celery para cálculo de previsões (futuro). Hoje: só DTO e testes. A função retorna `production_id: UUID` para referência posterior.

**Decisão 4 — Validações.** (1) Receita existe, ativa (não deletada); (2) quantidade > 0; (3) localização ativa; (4) stock suficiente de cada ingrediente, respeitando FEFO; (5) `yield_factor > 0`; (6) receita tem ≥1 ingrediente. Erro: `400` se quantity ≤ 0 ou yield_factor ≤ 0; `404` se receita não existe; `409` se localização inativa ou stock insuficiente (por ingrediente).

**Decisão 5 — Casos limite.** (1) **Ingrediente novo (sem stock)**: `409 "sem_stock_de_ingrediente"`; (2) **Ingrediente com `track_lots=True`**: FEFO automático (sai o lote mais antigo); (3) **Múltiplos lotes de um ingrediente**: soma de saldos suficiente, sai FEFO até completar a quantidade; (4) **Produto acabado com `track_lots=True`**: cria novo lote único com `code='__<production_id>__'` (sintético) e `received_at=now()`, `expires_at=NULL`. Se `track_lots=False`, nenhum lote (entrada sem rastreio); (5) **Receita com ícone de produto** (semi-acabado): a mesma receita pode ser ingrediente de outra — não há restrição, o `production_in` é um artigo como outro qualquer.

**Decisão 6 — Contrato de models da receita (placeholder).** `Recipe` e `RecipeLineItem` ainda não existem; a desenho presume: `Recipe(tenant, product, is_active, yield_factor)`, `RecipeLineItem(recipe, ingredient_product, quantity_per_base_unit, unit)`. O `unit` é a unidade de medida (kg, litro, unidade) — lido de `ingredient_product.base_unit`. A receita não é perecível (não tem `track_lots` nem `expires_at`).

**Decisão 7 — Bloqueadores.** Nenhum. A fatia 3 deixou tudo pronto: `inventory.api.record_movements` escreve `production_out` e `production_in`, `get_fefo_lot` encontra o lote a sair, `Lot` suporta lotes sintéticos. ADR 0014 já respondeu ao `yield_factor`. Precisa: `domain-expert` confirmar se há casos onde um ingrediente pode sair por LIFO (o mais recente) em vez de FEFO — respondida ADR 0023 como FEFO sempre.

**Alternativas.** *Endpoint imediato `/recipes/<id>/produce`*: prematuro (modelo Recipe não existe); o contrato de API vira na próxima fatia que o implemente. *Lote do produto acabado com `track_lots=True` em vez de sintético*: perde a distinção entre "rastreado porque o comprador pediu" e "rastreado porque foi produzido"; o lote sintético é invisível mas correto. *Defer yield_factor para o passo de venda, não de produção*: falseia o custo de stock; o valor de remanescente fica errado.

**Consequências.** Função em `recipes/services.py`: `produzir(tenant_id, recipe_id, quantity, location_id, user)` com `@transaction.atomic`. DTOs: `RecipeLineDTO` (ingrediente + quantidade), `ProductionDTO` (recipe_id, quantity, location_id, production_id). Seletor em `recipes/selectors.py`: função que lê receita com ingredientes. Testes: factory `RecipeFactory` + `RecipeLineFactory`, casos — receita ativa/inativa, quantidade positiva/zero/negativa, stock exato/insuficiente, FEFO com múltiplos lotes, produto acabado com rastreio. Sem eventos novos (produção é facto, não causa ação automática — o alertar de baixo stock já existe).

**Consultar `domain-expert` antes da implementação:** se há casos de LIFO em vez de FEFO (respondida: não); se semi-acabado (produto que é ingrediente) é suportado (respondida: sim, não há restrição); se mão-de-obra entra no custo de production_in (respondida ADR 0014: não em v1); se há limite de `yield_factor` (ex: máximo 0.95 para evitar perda impraticável) — resposta esperada: não em v1, livre a partir de 0.1.

---

## Contrato de `recipes.api.produzir()`

```python
def produzir(
    *,
    tenant_id: UUID,
    recipe_id: UUID,
    quantity: Decimal,  # quantidade de produto acabado desejada
    location_id: UUID,
    user: User,
) -> UUID:  # production_id
    """Produzir uma receita: consome ingredientes (production_out), cria produto (production_in).
    
    Custo unitário: unit_cost = Σ(|production_out.qty| × production_out.unit_cost) / quantity
    
    Levanta:
    - 404: receita não existe
    - 409: receita inativa, localização inativa, stock insuficiente, yield_factor <= 0
    - 400: quantity <= 0
    
    Retorna: production_id (UUID partilhada por production_out e production_in)
    """
```

Atomicidade: uma transação que falha em qualquer validação desfaz sem deixar movimentos parciais.
