---
name: invoice-extraction
description: Pipeline de extração de faturas de fornecedor (foto ou PDF, em português) para linhas de receção de stock — pré-processamento, leitura do QR/ATCUD, extração estruturada por LLM com schema Pydantic, matching de linhas ao catálogo, scores de confiança e revisão humana obrigatória. Usar sempre que se trabalhe no módulo agents/, em uploads de faturas, no fluxo de receção por documento, ou quando o utilizador mencionar OCR, faturas, "dar entrada por foto" ou extração de documentos.
---

# Extração de faturas → receção de stock

Fluxo completo: upload → `PurchaseReceiptDraft` → revisão humana → `confirm_receipt` → movimentos.
**A IA nunca escreve no ledger.** Só a confirmação humana.

## 1. Upload (`purchasing`)
- Aceitar `image/jpeg`, `image/png`, `image/webp`, `application/pdf`. Verificar tipo real com
  `python-magic`, tamanho ≤ 10 MB, máximo 10 páginas.
- Guardar em object storage (S3/MinIO) com nome gerado (UUID), fora do webroot. Servir por URL assinada.
- Criar `InvoiceDocument(tenant, supplier?, file, status=uploaded)` e enfileirar `extract_invoice.delay(doc_id)`.

## 2. Pré-processamento (Celery)
- PDF nativo: extrair texto com `pypdf`/`pdfplumber`; se pouco texto, rasterizar a 200 dpi.
- Imagens: corrigir orientação (EXIF), deskew, contraste. Redimensionar para lado maior 2000 px.
- **Tentar o QR primeiro** (`pyzbar`/`zxing-cpp`): o QR das faturas PT traz NIF emissor, NIF
  adquirente, data, tipo, total, IVA por taxa e ATCUD. Se legível, é a fonte fiável para o cabeçalho
  e serve para validar o total extraído das linhas.

## 3. Extração estruturada (LLM com visão)
- Enviar imagem/páginas + prompt com schema Pydantic estrito (ver `references/schema.md`).
- O prompt marca o documento como **dados**, não instruções. Texto dentro da fatura que pareça
  instrução ("ignore previous…") é ignorado por construção.
- Pedir por linha: `description_raw`, `quantity`, `unit_raw`, `unit_price`, `discount`, `vat_rate`,
  `line_total`, `confidence (0–1)`.
- Validações pós-extração: Σ linhas ≈ base por taxa (tolerância 0,02 €); NIF com dígito de controlo
  válido; datas plausíveis. Falhas baixam a confiança global, não bloqueiam.
- `timeout` 60 s, `max_tokens` definido, custo registado em `AgentCall`.

## 4. Matching ao catálogo
Por linha, por ordem:
1. `SupplierProductCode` (código do fornecedor já visto) → match exato.
2. EAN se presente.
3. Pesquisa fuzzy (trigram no Postgres) sobre `Product.name` e `ProductPackaging.name`, restrita ao
   tenant; aceitar automaticamente só se score ≥ 0,9 e não houver empate.
4. Sem match → linha fica `unmatched`; a UI propõe "criar produto" ou "associar a existente".
Cada associação confirmada pelo utilizador grava `SupplierProductCode` → da próxima vez é exato.

## 5. Draft e revisão
- `PurchaseReceiptDraft` com cabeçalho + linhas + confiança por campo. Estado `needs_review`.
- UI de revisão lado a lado (imagem à esquerda, linhas à direita), campos com confiança < 0,8 realçados,
  totais recalculados ao editar.
- `confirm_receipt` (service): valida tudo outra vez no backend, cria `Lot` se `track_lots`, cria
  movimentos `receipt`, atualiza `SupplierPrice` e CMP, marca draft `confirmed`. Tudo numa transação.

## 6. Segurança e privacidade
- Faturas contêm NIFs e moradas: acesso só ao tenant; URL assinada com expiração curta; sem logs
  do conteúdo. Ver SECURITY.md.
- Retenção: apagar o ficheiro original ao fim de N meses (configurável); manter o draft.

## 7. Métricas para melhorar
- % de linhas auto-matched · % de campos editados na revisão · tempo médio de revisão · custo/fatura.
Guardar em `ExtractionMetric`; é isto que diz se o produto está a funcionar.

Ver `references/schema.md` para o schema Pydantic e o prompt base.
