import { textoDeQuantidade, textoNaUnidadeBase } from "@/lib/quantidade";

import type { EstadoDoCusto } from "./schemas";
import { textos } from "./textos";

/**
 * As palavras das receitas: as três do custo, e a frase que diz **quantos
 * ingredientes é que não têm preço**.
 *
 * As duas quantidades — a de apresentação e a do ledger — saem do
 * `src/lib/quantidade.ts` e são re-exportadas aqui pela mesma razão que o
 * `inventory` e o `purchasing` o fazem: os componentes deste módulo importam o
 * vocabulário do módulo, e não uma pasta do `lib/` directamente. Nada se
 * converte aqui.
 */
export { textoDeQuantidade, textoNaUnidadeBase };

/**
 * As três palavras da casa sobre o custo — **as mesmas** do stock, do
 * desperdício e dos alertas (ADR 0032, ADR 0035, decisão 10).
 *
 * Um quarto vocabulário aqui recriava a divergência que a ADR 0032 fechou, e é
 * por isso que o servidor re-exportou o `ESTADOS_DO_CUSTO` pela porta do
 * `inventory` em vez de deixar nascer um segundo enum no contrato.
 *
 * O par `Record`/`Map` de sempre: o `Record` é a garantia (exaustivo sobre o
 * enum, nos dois sentidos, sob `pnpm typecheck`) e o `Map` é por onde se lê,
 * porque o `security/detect-object-injection` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica.
 */
const PALAVRA_DO_CUSTO: Record<EstadoDoCusto, string> = {
  conhecido: textos.custo.conhecido,
  estimado: textos.custo.estimado,
  desconhecido: textos.custo.desconhecido,
};

const PALAVRAS_DO_CUSTO = new Map<string, string>(Object.entries(PALAVRA_DO_CUSTO));

/** A palavra de um estado do custo. A queda é inalcançável por construção. */
export function palavraDoCusto(estado: EstadoDoCusto): string {
  return PALAVRAS_DO_CUSTO.get(estado) ?? estado;
}

/**
 * A segunda metade da frase do custo: **a cobertura**, em contagem.
 *
 * `ingredients_without_cost` é contagem e não euro, logo chega aos três papéis —
 * é o que diz se o número está incompleto em 1 de 10 ou em 9 de 10. A ADR 0035
 * (decisão 6) escreve que esta cobertura é **mais fraca** do que a
 * `quantity_without_cost` do stock, porque um ingrediente em dez pode ser 90 %
 * do custo; é por isso que o `cost_status` por linha existe na tabela ao lado,
 * e não em vez disto.
 *
 * O caso `desconhecido` tem frase própria em vez de "6 de 6 não têm custo": é a
 * mesma contagem e é outra afirmação — não há número nenhum a mostrar, e o ecrã
 * imprime "—".
 */
export function fraseDaCobertura(
  estado: EstadoDoCusto,
  semCusto: number,
  total: number,
): string {
  if (estado === "desconhecido") return textos.custo.semNenhumCusto;
  if (semCusto === 0) return textos.custo.tudoComCusto;
  return textos.custo.semCusto(semCusto, total);
}
