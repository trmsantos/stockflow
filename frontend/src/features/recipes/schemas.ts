import { z } from "zod";

import type { components } from "@/lib/api/types";
import { decimalSchema, quantidadeSchema } from "@/lib/quantidade";

/**
 * O contrato do módulo `recipes` — a ficha técnica e o **custo de
 * ingredientes** (ADR 0035, fatia A).
 *
 * Estes schemas são **escritos à mão** e não se geram do `types.ts`
 * (CLAUDE.md). Nenhum gate atravessa esta fronteira: o `pnpm typecheck` compara
 * o que o ecrã faz com o que *este* ficheiro diz, nunca com o contrato. O que a
 * apanha é fotografar o ecrã autenticado **com cada papel**
 * (`scripts/ver-ecra.py`), porque é por papel que as chaves desaparecem.
 *
 * ## As cinco chaves de dinheiro são `.optional().nullable()`, e as duas
 * metades dizem coisas diferentes
 *
 *  - **ausente** (`.optional()`) — *"não te compete"*. É sobre **quem** olha: o
 *    `SemEurosParaQuemNaoVe` tira a chave do JSON para quem não é
 *    `owner|manager`. Nunca `0`, que seria uma afirmação falsa sobre o preço;
 *  - **`null`** (`.nullable()`) — *"não sabemos"*. É sobre a **ficha**: é o
 *    degrau 5 da escada do custo (ADR 0035, decisão 10), e o ecrã imprime "—".
 *
 * **Não se colapsam**, e a consequência está no ecrã: com a chave ausente
 * desaparece a **coluna inteira**; com ela a `null` a coluna fica, com o traço
 * lá dentro e o `cost_status` ao lado a dizer porquê. Um `.nullable()` sozinho
 * **exige a chave presente** e o ecrã rebenta no `parse` para o `staff` — com o
 * `pnpm typecheck` verde. Foi assim que o ecrã de receções esteve partido para
 * toda a gente, incluindo o dono.
 *
 * ## Nada se divide aqui
 *
 * O servidor serve as quantidades nas duas formas (`base` e `display`) e os
 * custos nas duas unidades (`unit_cost` por unidade base, `display_cost` por
 * unidade de apresentação). Dividir por `batch_size` ou multiplicar por
 * `display_factor` no cliente é a conversão de unidades que a casa proíbe
 * (ADR 0030 d1, ADR 0034 d11, `inventory-domain` §2) — e a aritmética do
 * servidor tem a divisão **no fim** (ADR 0035, decisão 8), logo uma conta
 * refeita aqui daria outro número.
 */

/**
 * As três palavras da casa sobre o custo, **verificadas contra o enum gerado**.
 *
 * O `inventory` declara este enum à mão (`estadoDoCustoSchema`) e esta é a
 * segunda declaração, porque a fronteira da ADR 0008 só deixa importar de outra
 * feature o seu `api.ts`. O que a impede de divergir não é disciplina: é o
 * `satisfies Record<…>` sobre o `EstadoDoCustoEnum` do `types.ts`, exaustivo
 * nos dois sentidos — uma palavra nova no servidor não compila aqui, e uma
 * palavra inventada aqui também não. É o mesmo mecanismo do `ROTAS_DE_ACAO` do
 * assistente, e é o que o servidor comprou ao re-exportar o `ESTADOS_DO_CUSTO`
 * pela porta do `inventory` (ADR 0035): um `EstadoDoCusto2Enum` no `types.ts`
 * era a divergência de vocabulário que a ADR 0032 fechou.
 */
type EstadoDoCustoGerado = components["schemas"]["EstadoDoCustoEnum"];

const ESTADOS_DO_CUSTO = {
  conhecido: "conhecido",
  estimado: "estimado",
  desconhecido: "desconhecido",
} as const satisfies Record<EstadoDoCustoGerado, EstadoDoCustoGerado>;

export const estadoDoCustoSchema = z.enum(ESTADOS_DO_CUSTO);

/**
 * Uma linha da ficha: o ingrediente, as **duas** quantidades e o custo dele.
 *
 * `quantity` é o que a ficha escreve **por fornada** e `quantity_real` é
 * `quantity ÷ yield_factor`, o que de facto sai do stock. São números
 * diferentes e a confusão entre eles é o erro clássico do rendimento — por isso
 * viajam os dois e nenhum se calcula aqui.
 *
 * `ingredient_is_active` é do **artigo**: uma ficha activa pode conter um artigo
 * arquivado, e isso aceita-se. Quem recusa é a produção, na fatia B.
 */
export const linhaDaReceitaSchema = z.object({
  ingredient: z.uuid(),
  short_name: z.string().min(1),
  sku: z.string(),
  ingredient_is_active: z.boolean(),
  quantity: quantidadeSchema,
  quantity_real: quantidadeSchema,
  /** Qualidade de dados e não euro: chega aos três papéis. */
  cost_status: estadoDoCustoSchema,
  /** € por unidade **base** do ingrediente, pela escada da decisão 10. */
  unit_cost: decimalSchema.optional().nullable(),
  /** `quantity_real × unit_cost`. */
  line_cost: decimalSchema.optional().nullable(),
});

/**
 * Uma linha do `GET /recipes`: o acabado, a fornada e o custo dela.
 *
 * `base_unit` e `display_unit` são `z.string()` e não o `unidadeBaseSchema`,
 * de propósito: o contrato declara-os `CharField` e o que o ecrã faz com eles é
 * **imprimi-los**. Apertar aqui o que o contrato não aperta trocava um rótulo
 * por um ecrã rebentado no dia em que o catálogo ganhar uma unidade.
 */
export const receitaResumoSchema = z.object({
  id: z.uuid(),
  /** O artigo acabado. É a identidade da ficha e não se altera num `PATCH`. */
  product: z.uuid(),
  short_name: z.string().min(1),
  sku: z.string(),
  base_unit: z.string().min(1),
  display_unit: z.string().min(1),
  display_factor: decimalSchema,
  is_active: z.boolean(),
  /** Quanto acabado sai de **uma** fornada, nas duas formas. */
  batch_size: quantidadeSchema,
  /** Nasce a `1,000`: a perda já está na fornada. Sem tecto de 1. */
  yield_factor: decimalSchema,
  line_count: z.number().int().nonnegative(),
  /**
   * O agregado: **nunca** `conhecido` se alguma linha não o for, e
   * `desconhecido` só quando nenhuma linha tem custo — e aí os três euros saem
   * `null`, que é a afirmação verdadeira (*não há valor*).
   */
  cost_status: estadoDoCustoSchema,
  /**
   * Quantas linhas não têm custo nenhum. É **contagem** e não euro, logo chega
   * aos três papéis — é o que diz se o número está incompleto em 1 de 10 ou em
   * 9 de 10. É uma cobertura mais fraca do que a `quantity_without_cost` do
   * stock (um ingrediente em dez pode ser 90 % do custo), e é por isso que o
   * `cost_status` **por linha** existe ao lado.
   */
  ingredients_without_cost: z.number().int().nonnegative(),
  /** € da **fornada** inteira. Ver o cabeçalho sobre ausente contra `null`. */
  batch_cost: decimalSchema.optional().nullable(),
  /** `batch_cost ÷ batch_size.base` — € por unidade **base** do acabado. */
  unit_cost: decimalSchema.optional().nullable(),
  /** `unit_cost × display_factor` — € por unidade de **apresentação**. */
  display_cost: decimalSchema.optional().nullable(),
});

/**
 * O corpo do `GET /recipes/<id>`: o resumo **mais as linhas**.
 *
 * Um `.extend()` e **não um segundo schema** — é o que o próprio serializer do
 * servidor escreve que o cliente faria. Os dezasseis campos do resumo não se
 * repetem aqui, logo o cabeçalho da ficha **é** a linha da lista por
 * construção, e não por coincidência.
 */
export const receitaDetalheSchema = receitaResumoSchema.extend({
  lines: z.array(linhaDaReceitaSchema),
});

/* ---------------------------------------------------------------------------
 * Escrita. `owner|manager`, e a ficha grava-se inteira.
 * ------------------------------------------------------------------------ */

/**
 * Uma linha a gravar: o artigo, a quantidade **por fornada** e a unidade dela.
 *
 * O `unit` tem de ser o `base_unit` ou o `display_unit` **daquele** ingrediente
 * e qualquer outro é 400: não existe motor genérico de conversão (ADR 0011). O
 * pasteleiro escreve "500 g de farinha" num catálogo cujo artigo é base `g` e
 * apresentação `kg`, e **a conversão é do servidor**.
 */
export const linhaParaGravarSchema = z.object({
  ingredient: z.uuid(),
  quantity: decimalSchema,
  unit: z.string().min(1),
});

/**
 * O corpo do `POST /recipes`: a ficha inteira, linhas incluídas.
 *
 * As linhas viajam **dentro do corpo** e não num sub-recurso (ADR 0035,
 * decisão 4): a contagem e a receção têm `POST /…/lines` porque são percursos —
 * uma folha que se anda com o telemóvel na mão —, e uma ficha técnica
 * escreve-se de uma vez, num formulário com **um** botão de gravar. Oito `POST`
 * para oito ingredientes é uma receita meio gravada, e uma receita meio gravada
 * é um custo errado que ninguém vê.
 */
export const receitaParaCriarSchema = z.object({
  product: z.uuid(),
  batch_size: decimalSchema,
  batch_unit: z.string().min(1),
  yield_factor: decimalSchema.optional(),
  is_active: z.boolean().optional(),
  lines: z.array(linhaParaGravarSchema).min(1),
});

/**
 * O corpo do `PATCH /recipes/<id>`. **Sem `product`**: é a identidade da ficha.
 *
 * `lines` **ausente** não toca nas linhas; `lines` **presente** substitui-as
 * todas. É a única parte do contrato que não se adivinha, e por isso está
 * escrita aqui e na ADR. Arquivar é `{is_active: false}` — não há `DELETE`,
 * porque a ficha técnica de mercadoria que já entrou no ledger não se apaga.
 *
 * A fornada e a unidade dela viajam **juntas ou não viajam**: um `batch_size`
 * sozinho não se consegue interpretar (2,4 é quilos ou gramas?) e o servidor
 * recusa-o com 400. O formulário manda sempre as duas.
 */
export const receitaParaAlterarSchema = z.object({
  batch_size: decimalSchema.optional(),
  batch_unit: z.string().min(1).optional(),
  yield_factor: decimalSchema.optional(),
  is_active: z.boolean().optional(),
  lines: z.array(linhaParaGravarSchema).min(1).optional(),
});

export type EstadoDoCusto = z.output<typeof estadoDoCustoSchema>;
export type LinhaDaReceita = z.output<typeof linhaDaReceitaSchema>;
export type ReceitaResumo = z.output<typeof receitaResumoSchema>;
export type ReceitaDetalhe = z.output<typeof receitaDetalheSchema>;
export type LinhaParaGravar = z.output<typeof linhaParaGravarSchema>;
export type ReceitaParaCriar = z.output<typeof receitaParaCriarSchema>;
export type ReceitaParaAlterar = z.output<typeof receitaParaAlterarSchema>;

/**
 * Os dois estados do `?estado=` da lista, e são do contrato.
 *
 * Um terceiro valor é **400** no servidor e não uma lista a fingir que filtrou,
 * logo o conjunto é fechado dos dois lados. Vive aqui e não no `busca-de-*.ts`
 * da rota porque o `api.ts` precisa dele para montar o pedido, e uma feature
 * não pode importar `@/routes/*`.
 */
export const estadoDaListaSchema = z.enum(["activas", "todas"]);

export type EstadoDaLista = z.output<typeof estadoDaListaSchema>;
