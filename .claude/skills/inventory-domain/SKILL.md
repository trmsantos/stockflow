---
name: inventory-domain
description: Regras de negócio de gestão de stock para restauração e negócios alimentares em Portugal — ledger de movimentos, lotes e validades (FEFO), unidades de compra vs consumo, receitas que consomem stock, contagens físicas, desperdício, custo médio ponderado e particularidades de faturas portuguesas (IVA por taxa, NIF, ATCUD, QR). Usar sempre que se desenhem modelos, serviços ou UI de stock, compras, receitas ou inventário, mesmo que o utilizador não fale em "regras de negócio".
---

# Domínio: stock em restauração

## 1. O ledger (invariante central)

- A verdade é a tabela `StockMovement` (append-only). `StockLevel` (produto × armazém × lote) é uma
  projeção derivada, recalculada por serviço na mesma transação.
- Tipos de movimento: `receipt` (entrada por compra) · `consumption` (saída por venda/receita) ·
  `waste` (desperdício, com motivo) · `adjustment` (correção após contagem, com justificação obrigatória)
  · `transfer_out` / `transfer_in` (entre armazéns, sempre aos pares) · `return` (devolução ao fornecedor).
- Um movimento nunca é editado nem apagado. Erro corrige-se com movimento inverso que referencia o original.
- Todo o movimento tem: `tenant`, `product`, `location`, `lot` (nullable), `quantity` (Decimal, sinal
  pelo tipo), `unit` (a unidade base do produto), `unit_cost` (Decimal, snapshot), `reference`
  (fatura, contagem, receita…), `created_by`, `occurred_at`.

## 2. Unidades — a fonte nº 1 de bugs

- Cada produto tem **uma unidade base** de stock (g, ml, un). Tudo é armazenado nessa unidade.
- Compra em unidades diferentes: "caixa de 12 garrafas de 750 ml" → o fornecedor vende `caixa`;
  o stock guarda `9000 ml`. A conversão vive em `ProductPackaging` (nome, fator para unidade base,
  código de barras/EAN do fornecedor).
- Conversão **só no backend**, nunca no frontend. `Decimal` com 3 casas para quantidade, 4 para custo unitário.
- Rendimento: 1 kg de cebola comprada ≠ 1 kg de cebola descascada. Receitas usam `yield_factor` no
  ingrediente (default 1.0; marcar como hipótese até validar com utilizadores).

## 3. Lotes e validades

- Produtos perecíveis têm `track_lots = True`. Cada receção cria um `Lot` (número do fornecedor ou
  gerado, `expires_at`, `received_at`).
- Saídas seguem **FEFO** (first expired, first out) por default; o utilizador pode escolher outro lote.
- Validade após abertura (ex.: leite aberto = 3 dias): campo `shelf_life_after_opening_days`; abrir
  gera um lote filho com nova validade. Marcar como fase 2.
- Alertas: `expires_in_days ≤ threshold` (por categoria) e stock abaixo de `min_quantity`.

## 4. Receitas / fichas técnicas

- `Recipe` = produto vendável ou semi-acabado + lista de `RecipeLine(product, quantity, unit, yield_factor)`.
- Registar venda ou produção de uma receita gera N movimentos `consumption` (um por ingrediente),
  agrupados por `reference`.
- Receitas aninhadas (molho usado noutro prato) são permitidas; profundidade máxima 3.
- Custo teórico da receita = Σ(quantidade × custo médio atual do ingrediente). Mostrar sempre
  "teórico" — o real depende do desperdício.

## 5. Contagens físicas

- `StockCount` com linhas (produto/lote → quantidade contada). Ao fechar, gera `adjustment` por
  diferença. Diferenças acima de X% exigem motivo.
- Contagens são feitas em telemóvel, em pé, com pressa: a UI ordena por localização física
  (prateleira), não alfabeticamente, e aceita entrada rápida por código de barras.

## 6. Custo

- Custo médio ponderado (CMP) por produto, recalculado em cada `receipt`. Snapshot em cada movimento.
- Preço de compra varia por fornecedor e data → `SupplierPrice(product, supplier, packaging, price, valid_from)`.

## 7. Faturas de fornecedor (PT)

Campos que uma fatura portuguesa traz e que interessam:
- Emissor: nome, **NIF** (9 dígitos, validar dígito de controlo), morada.
- Documento: tipo (FT, FR, FS, NC), número (série/número), data, **ATCUD**, código QR (contém quase
  tudo o que precisas — se legível, preferir ao OCR do corpo).
- Linhas: descrição, quantidade, unidade, preço unitário, desconto, **taxa de IVA por linha**
  (6 % · 13 % · 23 % continente; Açores/Madeira diferentes), total da linha.
- Totais: base por taxa de IVA, IVA por taxa, total.
- Notas de crédito (NC) referenciam a fatura original → gerar `return`, não `receipt` negativo.

## 8. Desperdício

- `waste` tem motivo obrigatório: `expired | spoiled | prep_loss | breakage | other`.
- O relatório de desperdício em € é o KPI que o dono do restaurante mais quer ver. Trata-o como
  feature de primeira classe, não como relatório secundário.

## 9. O que não fazer

- Campo `quantity` editável em `Product` ou `StockLevel`.
- `float` para quantidades ou dinheiro.
- Guardar quantidades na unidade de compra.
- Deixar a IA gerar movimentos sem confirmação humana.
- Apagar movimentos "errados".
- Assumir que o utilizador conta stock ao computador.
