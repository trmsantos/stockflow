import type { EstadoDoCusto } from "./schemas";

/**
 * A tinta de um estado do custo, nos **dois papéis** em que ela aparece: a
 * palavra na coluna da certeza e o trilho de 4px na aresta da linha.
 *
 * É o irmão do `inventory/tinta-do-estado.ts` e existe pela mesma razão
 * mecânica (um ficheiro que exporta um componente **e** uma função perde o fast
 * refresh, e o `react-refresh/only-export-components` recusa-o) e pela mesma
 * razão de produto: os dois papéis têm de concordar, senão a mesma linha dá dois
 * veredictos.
 *
 * ## Quais das três palavras é que ganham tinta, e porquê só uma
 *
 * **`conhecido` não tem tinta nenhuma.** Não é verde, não é um visto: é nada. É
 * a regra do DESIGN.md §3 e do trilho — "uma linha saudável não o tem" — e é o
 * que faz a leitura de dois metros funcionar.
 *
 * **`estimado` também não tem.** E esta é a decisão que vale a pena escrever,
 * porque a tentação é pintá-la de âmbar: **"estimado" é informação, não
 * avaria.** A escada de custo da ADR 0035 (decisão 10) tem cinco degraus e
 * **três** deles são estimativas legítimas — stock com parte sem preço, o último
 * preço do ledger dentro de um ano, o custo cascateado de um semi-acabado. Num
 * dia 1 sem produções, *todas* as fichas com semi-acabados saem estimadas: um
 * âmbar aqui pintava a coluna inteira e deixava de distinguir o que quer que
 * fosse, que é exactamente o defeito do "trilho em todas as linhas". A palavra
 * **aparece** (em `muted-foreground`, sem cor de estado) porque é informação que
 * se lê; o que não leva é sinal.
 *
 * **`desconhecido` leva âmbar e leva trilho.** É o único estado em que o ecrã
 * **não responde à pergunta que o traz aqui** — "quanto me custa de
 * ingredientes?" —, e é a linha que o dono tem de ver sem a ler. Âmbar e não
 * vermelho: é uma lacuna de dados, não comida a estragar-se, e gastar o
 * vermelho aqui tirava-lhe o significado que ele tem nos Alertas.
 *
 * A cor nunca comunica sozinha: a palavra está sempre na coluna, e o
 * `conhecido` devolve-a só para áudio (silêncio visual, não silêncio total).
 */

/** Primeiro papel do DESIGN.md §2: a cor de estado como **cor de texto**. */
const TINTA_DO_TEXTO = new Map<EstadoDoCusto, string>([
  ["estimado", "text-muted-foreground"],
  ["desconhecido", "text-warning"],
]);

/** O trilho é preenchimento, mas de 4px e sem nada por cima: não leva frente. */
const TINTA_DO_TRILHO = new Map<EstadoDoCusto, string>([["desconhecido", "bg-warning"]]);

export function tintaDoTextoDoCusto(estado: EstadoDoCusto): string {
  return TINTA_DO_TEXTO.get(estado) ?? "";
}

export function tintaDoTrilhoDoCusto(estado: EstadoDoCusto): string {
  return TINTA_DO_TRILHO.get(estado) ?? "";
}
