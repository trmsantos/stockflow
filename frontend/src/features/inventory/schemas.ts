import { z } from "zod";

/**
 * O contrato do módulo `inventory`, em Zod.
 *
 * Estes schemas são o **rascunho do contrato** que a sessão do backend recebe
 * (ADR 0008, decisão 3): o mesmo ficheiro valida a resposta no cliente e
 * valida o fixture no servidor de desenvolvimento, logo não há duas noções do
 * payload. Quando os serializers existirem, é o `pnpm gen:api` com o gate de
 * diff do CI que apanha uma divergência — não este ficheiro.
 *
 * Convenções que vêm do domínio e não da UI:
 *  - quantidades e dinheiro são **strings** (`Decimal` no Django, para não
 *    perder precisão em JSON). Nenhuma conta é feita em `number` no cliente;
 *  - o ledger guarda sempre a **unidade base** do artigo (g, ml, un), e o
 *    servidor manda também a forma de mostrar. Converter g para kg no cliente
 *    é a fonte nº 1 de bugs de stock (`inventory-domain` §2);
 *  - um movimento é append-only: há schema para o criar e nenhum para o
 *    alterar ou apagar, o que espelha o `REVOKE UPDATE, DELETE` do ADR 0006.
 */

/**
 * `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`.
 *
 * Escrito como duas alternativas e não como `^-?\d+(?:\.\d+)?$`: a forma curta
 * tem altura de estrela 2 (um `+` dentro de um grupo opcional) e o
 * `security/detect-unsafe-regex` recusa-a. Aqui cada alternativa tem um só
 * quantificador, diz exactamente o mesmo, e a casa não suprime lint.
 */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

/** A unidade base de stock do artigo. É nesta unidade que o ledger guarda. */
export const unidadeBaseSchema = z.enum(["g", "ml", "un"]);

/**
 * Uma quantidade, nas duas formas: a do ledger e a de mostrar.
 *
 * O `display` existe porque o staff diz "3,4 kg" e o ledger guarda
 * "3400.000 g". A conversão é do servidor (o artigo sabe a sua unidade de
 * apresentação); o cliente só escolhe o formatador. Sem este campo, ou o ecrã
 * mostra `3400,000 g` — ilegível em pé, com pressa — ou o cliente divide por
 * 1000, que é exactamente a conversão que o domínio proíbe no frontend.
 */
export const quantidadeSchema = z.object({
  base: decimal,
  base_unit: unidadeBaseSchema,
  display: decimal,
  display_unit: z.string().min(1),
});

/**
 * Os dois rótulos que a lei distingue, e que o guião da sessão 0 nomeia como
 * condição para o dono confiar nos alertas: `use_by` é limite legal
 * ("consumir até"), `best_before` é qualidade ("consumir de preferência antes
 * de"). Tratar os dois igual é perder a credibilidade na primeira amêndoa
 * laminada marcada a vermelho.
 */
export const tipoValidadeSchema = z.enum(["use_by", "best_before"]);

/**
 * O estado da linha, **decidido no servidor**. O cliente não recalcula: se o
 * limiar de "baixo" mudar, muda num sítio, e a UI não ganha uma segunda
 * definição de "em falta" que divirja da dos alertas.
 */
export const estadoNivelSchema = z.enum(["ok", "baixo", "esgotado", "negativo"]);

/** Tipos de movimento do ledger (`inventory-domain` §1). */
export const tipoMovimentoSchema = z.enum([
  "receipt",
  "consumption",
  "waste",
  "adjustment",
  "transfer_out",
  "transfer_in",
  "return",
]);

/** Motivo obrigatório de um `waste` (`inventory-domain` §8). */
export const motivoQuebraSchema = z.enum(["expired", "spoiled", "prep_loss", "breakage", "other"]);

export const localizacaoSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
});

/** A validade mais próxima do artigo, com o lote que a traz. */
export const validadeProximaSchema = z.object({
  lot_code: z.string().min(1),
  expires_at: z.iso.date(),
  /** Dias até à validade; negativo se já passou. Contado pelo servidor. */
  days_away: z.number().int(),
  kind: tipoValidadeSchema,
});

/** Quanto deste artigo está em cada localização — o probe da Q2 do guião. */
export const nivelPorLocalizacaoSchema = z.object({
  location: localizacaoSchema,
  quantity: quantidadeSchema,
});

/**
 * Uma linha do ecrã Stock: um artigo, agregado sobre as localizações.
 *
 * Nota para quem escrever o serializer: a projeção `StockLevel` do domínio é
 * produto × localização × lote. Esta é a **leitura agregada por artigo** que o
 * ecrã pede, com as linhas cruas em `by_location`. É um selector, não a
 * tabela — e a ordem vem do servidor ("o que está pior primeiro", guião §1),
 * porque uma segunda definição de "pior" no cliente divergiria da dos alertas.
 */
export const nivelDeStockSchema = z.object({
  product: z.uuid(),
  short_name: z.string().min(1),
  quantity: quantidadeSchema,
  min_quantity: quantidadeSchema,
  status: estadoNivelSchema,
  nearest_expiry: validadeProximaSchema.nullable(),
  by_location: z.array(nivelPorLocalizacaoSchema),
});

/**
 * Os três números do topo. Vêm do servidor porque são a mesma verdade que
 * alimenta os alertas — e o `expiring_within_days` viaja com o número para o
 * ecrã poder mostrar o limiar em vez de o esconder num painel de
 * configurações (guião §4, proibição 7).
 */
export const resumoDeStockSchema = z.object({
  below_min_count: z.number().int().nonnegative(),
  expiring_count: z.number().int().nonnegative(),
  expiring_within_days: z.number().int().positive(),
  stock_value_eur: decimal,
});

/** Uma linha do ledger. Tem autor sempre — o probe da Q7 do guião. */
export const movimentoSchema = z.object({
  id: z.uuid(),
  movement_type: tipoMovimentoSchema,
  /** Sinal pelo tipo: entradas positivas, saídas negativas. */
  quantity: quantidadeSchema,
  location: localizacaoSchema,
  lot_code: z.string().nullable(),
  reason: motivoQuebraSchema.nullable(),
  created_by: z.string().min(1),
  occurred_at: z.iso.datetime(),
  /** Referência: fatura, contagem, transferência. Texto curto, para mostrar. */
  reference: z.string().nullable(),
});

/**
 * O corpo de um `POST /stock/movements`. Só cria; não há schema para editar
 * nem para apagar, e é de propósito (ADR 0006: `inventory_stockmovement` é
 * append-only na própria base de dados).
 *
 * A quantidade é o **valor absoluto**, na unidade base, e o sinal vem do tipo
 * — quem escreve "2000" numa quebra não tem de saber que o ledger guarda
 * "-2000".
 */
export const quebraParaRegistarSchema = z.object({
  product: z.uuid(),
  location: z.uuid(),
  quantity: decimal,
  reason: motivoQuebraSchema,
});

export type UnidadeBase = z.output<typeof unidadeBaseSchema>;
export type Quantidade = z.output<typeof quantidadeSchema>;
export type TipoValidade = z.output<typeof tipoValidadeSchema>;
export type EstadoNivel = z.output<typeof estadoNivelSchema>;
export type TipoMovimento = z.output<typeof tipoMovimentoSchema>;
export type MotivoQuebra = z.output<typeof motivoQuebraSchema>;
export type Localizacao = z.output<typeof localizacaoSchema>;
export type ValidadeProxima = z.output<typeof validadeProximaSchema>;
export type NivelPorLocalizacao = z.output<typeof nivelPorLocalizacaoSchema>;
export type NivelDeStock = z.output<typeof nivelDeStockSchema>;
export type ResumoDeStock = z.output<typeof resumoDeStockSchema>;
export type Movimento = z.output<typeof movimentoSchema>;
export type QuebraParaRegistar = z.output<typeof quebraParaRegistarSchema>;
