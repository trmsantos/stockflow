# ADR 0025 — Endpoints manuais de ajuste de stock

**Contexto.** A ADR 0023 criou o ledger (quatro tabelas) com o contrato de `receipt` e `return`. A ADR 0024 trouxe o painel read-only com 4 endpoints `GET`. A Fatia 5 adiciona os 3 endpoints `POST` que criam movimentos manualmente — sem receção de fornecedor, ajustes do dia a dia que o operador faz quando descobre uma perda, faz uma contagem ou transfere entre localizações. A tabela da ADR 0014 enumera nove tipos; esta ADR escolhe os três que entram agora e o contrato de cada um.

**Decisão 1 — Os 3 tipos de movimento que entram nesta fatia.**

Dos nove tipos de `movement_type` (ADR 0014, decisão 2):
- `waste` — desperdício descoberto (saída com motivo, ex: "pastel queimado", "leite coalhado")
- `adjustment` — quebra desconhecida descoberta em contagem (entrada ou saída, ex: "contagem X vs ledger Y")
- `transfer_out` e `transfer_in` — transferência entre localizações (saída duma, entrada noutra, atomicamente)

Ficam para depois (receitas, contagem):
- `consumption` — escreverá o `recipes` quando produz/vende
- `production_out`, `production_in` — escreverá o `recipes` quando produz
- `receipt`, `return` — já entram via receção (ADR 0023)

Rationale: `waste` e `adjustment` são decisões do utilizador a corrigir o ledger manualmente; `transfer` é uma transferência interna que não sai do tenant (um par de pernas que se anula no total). Os três respondem a operações recorrentes num restaurante: encontrar comida perdida/estragada, fazer contagem física e reparar discrepâncias, e mexer em stock entre cozinha/balcão/armazém.

**Decisão 2 — Contrato de cada endpoint.**

1. **`POST /stock/movements/waste`**
   - Corpo: `{product_id: uuid, location_id: uuid, quantity: Decimal>0, lot_id: uuid|null, reason: str(1-500) }`
   - Resposta: `201`, `{movement_id: uuid, product_name: str, location_name: str, lot_code: str|null, quantity: Decimal, unit_cost: Decimal, created_at: datetime}`
   - Semantica: cria um `StockMovement` com `type=waste`, `quantity` negativa (saída), `reason` preenchido, `occurred_at=now()`
   - Usa o `unit_cost` do lote que sai (FEFO: lote mais antigo, por `expires_at` depois `received_at`)

2. **`POST /stock/movements/adjustment`**
   - Corpo: `{product_id: uuid, location_id: uuid, quantity: Decimal (±), lot_id: uuid|null, reason: str(1-500) }`
   - Resposta: `201`, estrutura igual a waste
   - Semantica: cria um `StockMovement` com `type=adjustment`, quantidade com sinal conforme a correção, `reason` preenchido (ex: "contagem 5 unidades, ledger 3, diferença +2"), `occurred_at=now()`
   - Se `quantity > 0` (entrada), usa `unit_cost` do `StockLevel` atual (média ponderada do lote); se `quantity < 0` (saída), usa FEFO
   - Se produto novo (sem `StockLevel`): cria `StockLevel` com a quantidade (pode ficar negativa se ajuste de saída)

3. **`POST /stock/movements/transfer`**
   - Corpo: `{product_id: uuid, from_location_id: uuid, to_location_id: uuid, quantity: Decimal>0, lot_id: uuid|null}`
   - Resposta: `201`, `{transfer_id: uuid, movements: [{movement_id, type: "transfer_out"|"transfer_in", ...}], ...}`
   - Semantica: cria atomicamente dois movimentos na mesma transação:
     - `transfer_out` com `quantity` negativa na `from_location`
     - `transfer_in` com `quantity` positiva na `to_location`
   - Ambos partilham um `transfer_id` (identificador do par) para agregação posterior
   - Usa FEFO em `transfer_out` (sai o lote mais antigo)
   - O lote entra inteiro em `transfer_in` (mesmo `lot_id` no destino)

**Decisão 3 — Permissões e auditoria.**

- Classe: `IsAuthenticated + PertenceAoTenant` (qualquer membro ativo: owner, manager, staff)
- Sem separação de papéis — qualquer membro da casa pode registar perdas (o operário no armazém vê uma laranja no chão, o chefe faz contagem à noite)
- Audit trail: cada movimento leva `created_by` (FK User) e `created_by_name` (texto imutável do nome da altura), para idempotência e rastreio em revisão
- RLS: tabela `StockMovement` já tem política (ADR 0023, decisão 4), nenhum membro de outro tenant vê nada

**Decisão 4 — Validações.**

1. **Lote obrigatório se `product.track_lots=True`:**
   - Backend: `409` se linha confirmada tiver `lot_id=NULL` e artigo com `track_lots=True`
   - Frontend: campo marcado com asterisco, obrigatório no formulário

2. **Quantidade nunca zero:**
   - BD: `CHECK(quantity != 0)` no `StockMovement` (já existe, ADR 0023, decisão 1)
   - Backend: `400` se `quantity == 0`

3. **Unidade base (não pode mudar tipo):**
   - Backend: valida que o artigo existe e está activo no catálogo
   - `quantity` entra na unidade base do artigo (ex: quilogramas, litros, unidades)

4. **Localização obrigatória:**
   - Ambos `waste` e `adjustment`: `location_id` é obrigatório (onde se descobriu a perda)
   - `transfer`: `from_location_id` e `to_location_id` obrigatórios e **diferentes** (senão `409 "mesma_localizacao"`)

5. **Motivo obrigatório para waste e adjustment:**
   - Backend: `400` se `reason` em branco ou `null`
   - `reason` é enum obrigatório: `expired` | `spoiled` | `prep_loss` | `breakage` | `other`
   - Se `reason='other'`: campo extra `reason_detail` (text livre, opcional) para contexto
   - `reason` serve o audit trail e permite agregação de KPIs por motivo (ex: "% desperdício por causa")

6. **Quantidade não pode exceder stock existente para saída:**
   - Backend: permite ficar negativo (é uma contagem, pode haver erro no ledger)
   - Aviso visual no frontend: "stock atual: X, você quer sair Y, fica negativo"

**Decisão 5 — Casos limite.**

1. **Produto novo (sem `StockLevel`):**
   - `waste` / `adjustment`: cria `StockLevel` com a quantidade negativa (saída). Não é recomendado mas é possível (correção manual)
   - `unit_cost`: usa 0 (não tem histórico)
   - Consequência: pode ficar negativo no painel, marcado com flag

2. **Quantidade > stock existente:**
   - Permitido, fica negativo (ex: contagem descobriu que havia menos do que o ledger dizia)
   - Painel mostra em vermelho, alerta crítico de falta de stock ativa até reposição

3. **Transfer para mesma localização:**
   - Backend: `409 "mesma_localizacao"` — não faz sentido, operador cometeu erro

4. **FEFO em transfer_out e waste:**
   - Respeitado pelo backend: lê o lote com `expires_at` mais próximo (ou NULL se sem validade), depois `received_at` mais antigo
   - Se múltiplos lotes: a saída escolhe o primeiro; o segundo só sai num `waste` ou `transfer` posterior

5. **Lote sintético em transfer:**
   - Se produto tem `track_lots=False`, o lote é `'__<product_id>__'` (sintético)
   - Transfer copia o `lot_id` para nova localização (mesma linha de `StockLevel` no novo sítio com novo `location_id`)

6. **Stock em múltiplos lotes na mesma localização:**
   - `waste`: escolhe FEFO automaticamente, sem intervenção do utilizador (operador só diz "1 kg perdido aqui")
   - Frontend: mostra qual lote foi escolhido na resposta (para transparência)

7. **Ajuste com quantidade zero:**
   - Backend: `400` — já coberto por `CHECK` e validação

**Decisão 6 — Bloqueadores.**

Nenhum conhecido. ADR 0023 deixou tudo pronto:
- ✅ `StockMovement` append-only, RLS, auditoria (`created_by`)
- ✅ `StockLevel` atualiza-se sozinho em cada movimento
- ✅ `Lot` suporta FEFO por `expires_at` + `received_at`
- ✅ `ProductCost` atualiza-se no final (CMP ponderada)
- ✅ Lote sintético para `track_lots=False` (ADR 0023, decisão 7, caso 5)

---

## Alternativas

**`waste` sem endpoint dedicado, usando `adjustment` com `reason="waste: ..."`:** Perde semântica — `adjustment` é "quebra desconhecida", `waste` é "perda conhecida"; a distinção conta para relatórios de qualidade. Fechado pela tabela da ADR 0014.

**Transfer com um endpoint só (`POST /stock/movements/transfer`):** Nesta ADR, é assim — ambos os tipos entram no mesmo pedido (`from_location`, `to_location`, `quantity`). Alternativa seria dois pedidos (`transfer_out` depois `transfer_in`), mas perdia-se a atomicidade e criava-se uma janela onde a quantidade saía sem saber para onde.

**Quantidade de transfer limitada ao stock de origem:** Rejeita-se — operador pode estar a retirar de um sítio onde o ledger está errado; se a restrição falseia a intenção da operação, falha a confiança. O pós-facto é o painel mostrando negativo.

**Lote obrigatório sempre, mesmo para `track_lots=False`:** Torna a entrada de genéricos (sal, água) uma fricção extra. O lote sintético resolve sem UI.

**Ajuste só com entrada (quantity > 0):** Recusa porque a contagem física pode descobrir falta — se ledger diz 10 e contagem acha 8, o ajuste é de -2.

**Três endpoints separados (`/waste`, `/adjustment`, `/transfer_out`, `/transfer_in`):** `transfer` são dois tipos mas **um** pedido lógico (um utilizador faz uma operação, não duas). Duas URLs confundem e separam o que é atomicamente uma.

---

## Consequências

- Três novos endpoints em `inventory/views.py` (ou `inventory/api.py` conforme o padrão — ver com arquiteto)
- Serializers de escrita: `WasteMovementSerializer`, `AdjustmentMovementSerializer`, `TransferMovementSerializer` (validam `quantity`, `location_id`, `lot_id`, `reason`)
- Função em `inventory/services.py`: `record_manual_movements(tenant_id, movement_dto, user)` — uma por cada tipo, ou uma genérica que chama a lógica comum
- Seletor em `inventory/selectors.py`: função FEFO que escolhe o lote a sair (`get_fefo_lot_for_product(product_id, location_id, quantity)`)
- Testes: factory `ManualMovementFactory`, casos — produto novo, lote único, múltiplos lotes com FEFO, transfer entre localizações, ajuste com negativo, erro de validação
- Frontend: novo componente `AdjustaStockModal` (ou janela dentro de `Stock.tsx`), formulários para waste/adjustment/transfer, feedback visual (lote escolhido, stock antigo/novo)
- Sem eventos novos (movimentos manuais são observação de facto, não causam ação automática); painel `Stock.tsx` carrega dados real-time

**Consultar `domain-expert` antes da implementação:**
- `waste` em produto sem rastreio (`track_lots=False`): há problema se houver múltiplos lotes de facto (ex: comprados em dois dias) mas nós só sabemos de um? Ou a regra é sempre um só? (Resposta esperada: sempre sintético, um lote por artigo, sem problema.)
- FEFO: é sempre por `expires_at` depois `received_at`, ou há contexto em que seja LIFO ou por localização física do armazém? (Resposta esperada: é FEFO conforme ADR 0023, decisão 3.)
- Ajuste: quando a contagem descobrir falta, o utilizador cria um `adjustment` com `-X`, ou a contagem é um tipo diferente com ferramenta própria? (Resposta esperada: contagem é ferramenta da fatia 6, este ajuste é manual ad-hoc; são dois paths.)
