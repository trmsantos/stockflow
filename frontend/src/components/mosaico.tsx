/**
 * As classes de um mosaico de número — o bloco que os três ecrãs com números no
 * topo usam (Stock, Alertas, Receber).
 *
 * São classes e não um componente porque os três mosaicos são coisas
 * diferentes: um é um `<Link>` que filtra, outro é um `<div>` de leitura, outro
 * tem duas linhas de rótulo. O que **tem** de ser igual é a altura, o
 * alinhamento à direita e o tamanho do número — se divergirem, o dono vê dois
 * ecrãs que não parecem do mesmo produto, e divergem na primeira correção feita
 * só num deles.
 *
 * Viviam em `features/inventory/components/numeros-do-topo.tsx` e desceram para
 * cá quando o terceiro ecrã apareceu, e esse terceiro é de **outra feature** —
 * logo a descida deixou de ser preferência e passou a ser a única forma de não
 * haver duas definições (ADR 0008, decisão 2: "o que for para partilhar entre
 * features desce para `src/components/`").
 *
 * A altura mínima de 56px é alvo de toque (DESIGN.md §4) e é também o que faz
 * caberem os números **e** a lista nos ~530px úteis de um 360×640.
 */
export const CLASSE_MOSAICO =
  "flex min-h-14 flex-col items-end justify-center gap-0.5 rounded-xl border px-2.5 py-2 text-right";

export const CLASSE_NUMERO = "text-lg leading-none font-semibold sm:text-2xl";

export const CLASSE_ROTULO = "text-xs leading-tight text-muted-foreground";

/** A grelha onde os mosaicos vivem: duas ou três colunas, mesma densidade. */
export const CLASSE_GRELHA = "grid items-stretch gap-2 px-4 pt-3 pb-2";
