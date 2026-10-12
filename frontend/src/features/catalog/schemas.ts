import { z } from "zod";

/**
 * O contrato do módulo `catalog` — produtos, embalagens, fornecedores.
 *
 * Estes schemas são o rascunho do contrato que a sessão do backend recebe:
 * validam a resposta no cliente e validam o fixture no servidor.
 */

/** `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`. */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/** A unidade base de stock do artigo. */
export const unidadeBaseSchema = z.enum(["g", "ml", "un"]);

/** Tipo de validade. */
export const tipoValidadeSchema = z.enum(["use_by", "best_before"]);

/** Conservação. */
export const conservacaoSchema = z.enum(["ambient", "chilled", "frozen"]);

/**
 * Um produto do catálogo, em resumo (para exibição em listas).
 */
export const produtoSchema = z.object({
  id: z.uuid(),
  short_name: z.string().min(1),
  base_unit: unidadeBaseSchema,
  display_unit: z.string().min(1),
  display_factor: decimal,
  track_lots: z.boolean(),
  expiry_kind: tipoValidadeSchema.nullable(),
  conservation: conservacaoSchema,
  min_quantity: decimal,
  is_active: z.boolean(),
  created_at: z.iso.datetime({ offset: true }),
});

/**
 * Uma embalagem do catálogo.
 */
export const embalagemSchema = z.object({
  id: z.uuid(),
  product: z.uuid(),
  label: z.string().min(1),
  base_quantity: decimal,
  base_unit: unidadeBaseSchema,
  ean: z.string().nullable(),
});

/**
 * Uma embalagem para criar — entrada do POST /products/{id}/packagings.
 */
export const embalagemParaCriarSchema = z.object({
  label: z.string().min(1).max(60),
  base_quantity: decimal,
  ean: z.string().nullable().optional(),
});

/**
 * Um produto para criar — entrada do POST /products.
 */
export const produtoParaCriarSchema = z.object({
  short_name: z.string().min(1).max(80),
  base_unit: unidadeBaseSchema,
  display_unit: z.string().min(1).max(20),
  display_factor: decimal,
  track_lots: z.boolean().optional(),
  expiry_kind: tipoValidadeSchema.nullable().optional(),
  conservation: conservacaoSchema.optional(),
  packaging: embalagemParaCriarSchema.optional(),
});

/**
 * Um fornecedor do catálogo.
 */
export const fornecedorSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
  nif: z.string().nullable(),
  is_active: z.boolean(),
});

/**
 * Um fornecedor para criar — entrada do POST /suppliers.
 */
export const fornecedorParaCriarSchema = z.object({
  name: z.string().min(1).max(200),
  nif: z.string().nullable().optional(),
});

/**
 * Uma localização de armazém.
 */
export const localizacaoSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
  position: z.number().int().nonnegative(),
  is_active: z.boolean(),
});

/**
 * Uma localização para criar — entrada do POST /locations.
 */
export const localizacaoParaCriarSchema = z.object({
  name: z.string().min(1).max(60),
  position: z.number().int().nonnegative().optional(),
});

// Exports de tipos
export type Produto = z.output<typeof produtoSchema>;
export type ProdutoParaCriar = z.output<typeof produtoParaCriarSchema>;
export type Embalagem = z.output<typeof embalagemSchema>;
export type EmbalagemParaCriar = z.output<typeof embalagemParaCriarSchema>;
export type Fornecedor = z.output<typeof fornecedorSchema>;
export type FornecedorParaCriar = z.output<typeof fornecedorParaCriarSchema>;
export type Localizacao = z.output<typeof localizacaoSchema>;
export type LocalizacaoParaCriar = z.output<typeof localizacaoParaCriarSchema>;
