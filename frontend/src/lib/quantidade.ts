import { z } from "zod";

import { formatCount, formatQuantity } from "./format";

/**
 * Uma quantidade do domínio: a forma do payload e a forma de a escrever.
 *
 * ## Porque desceu para `src/lib/`, e porque só agora
 *
 * O `features/purchasing/schemas.ts` escreveu o gatilho por extenso quando
 * declarou a sua segunda cópia: *"no dia em que um **terceiro** módulo precisar
 * destas formas, elas descem para `src/lib/`, que é o `apps/shared` do
 * frontend, e esse diff é uma decisão com um caso à frente em vez de uma
 * generalização a dois"*. O `recipes` é esse terceiro módulo (ADR 0035): uma
 * ficha técnica serve a fornada, a quantidade por fornada e a quantidade real,
 * as três como `Quantidade`.
 *
 * Do outro lado aconteceu a mesma descida no mesmo dia e pela mesma razão: o
 * `QuantidadeOutSerializer` mudou-se para `apps/shared/serializers.py` porque
 * *"o `recipes` serve as mesmas quantidades que o `/stock/levels` e declarar
 * gémeos dava um segundo componente OpenAPI"*. Este ficheiro é o espelho
 * exacto dessa decisão: um componente do contrato, um schema do cliente.
 *
 * **O que desceu foi o que o terceiro caso precisa, e nada mais.** O
 * `localizacaoSchema` continua declarado duas vezes, no `inventory` e no
 * `purchasing`, porque o `recipes` não o usa — descer por simetria seria a
 * generalização que a nota do `purchasing` recusa.
 *
 * ## O que **não** desceu, e não é esquecimento
 *
 * Nenhum schema de recurso. O que atravessa a fronteira entre features continua
 * a ser o `api.ts` (ADR 0008, decisão 2): isto não é o `NivelDeStock` nem a
 * `Receita`, é o *value object* que os três contratos partilham — o equivalente
 * do `Decimal` ou do `UUID`, não o de um payload.
 */

/**
 * `"-2000.000"` — o que o DRF serializa a partir de um `DecimalField`.
 *
 * Escrito como duas alternativas e não como `^-?\d+(?:\.\d+)?$`: a forma curta
 * tem altura de estrela 2 (um `+` dentro de um grupo opcional) e o
 * `security/detect-unsafe-regex` recusa-a. Aqui cada alternativa tem um só
 * quantificador, diz exactamente o mesmo, e a casa não suprime lint.
 */
export const decimalSchema = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

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
  base: decimalSchema,
  base_unit: unidadeBaseSchema,
  display: decimalSchema,
  display_unit: z.string().min(1),
});

export type UnidadeBase = z.output<typeof unidadeBaseSchema>;
export type Quantidade = z.output<typeof quantidadeSchema>;

/**
 * Uma quantidade como se escreve: número, unidade visível, e as casas decimais
 * que correspondem ao passo do ledger.
 *
 * A regra é uma só: **o menor dígito visível é a unidade base**. Se a unidade de
 * apresentação é a própria unidade base (g, ml, un), o menor passo possível já é
 * o inteiro e três casas decimais seriam milésimos de grama — ruído, num ecrã
 * que se lê em pé. Se a apresentação é derivada (kg, L), as três casas são
 * exactamente os gramas e os mililitros que o ledger guarda.
 *
 * O que isto assume: uma unidade de apresentação diferente da base é múltipla de
 * 1000. É o que o catálogo tem (g→kg, ml→L) e o que o `format.ts` fixa em três
 * casas. No dia em que houver uma apresentação em caixas de 12, as casas
 * decimais passam a ser dado do servidor, ao lado do par `display`/`display_unit`
 * — não uma segunda conta aqui. Converter unidades no cliente é a fonte nº 1 de
 * bugs de stock (`inventory-domain` §2) e aqui não se converte nada: o par vem
 * pronto do servidor e isto só escolhe o formatador.
 */
export function textoDeQuantidade(quantidade: Quantidade): string {
  return quantidade.display_unit === quantidade.base_unit
    ? formatCount(quantidade.display, quantidade.display_unit)
    : formatQuantity(quantidade.display, quantidade.display_unit);
}

/**
 * A quantidade **na unidade base**, que é a unidade do ledger: "12 000 ml",
 * "5 000 g", "100 un".
 *
 * Desceu com as outras duas porque o par `display`/`base` só se lê inteiro:
 * quem mostra a forma de apresentação acaba, mais cedo ou mais tarde, a ter de
 * mostrar a do ledger ao lado — é o que a receção faz na conversão do
 * fornecedor e o que a ficha técnica faz quando a fornada está em quilos e os
 * ingredientes em gramas.
 */
export function textoNaUnidadeBase(quantidade: Quantidade): string {
  return formatCount(quantidade.base, quantidade.base_unit);
}
