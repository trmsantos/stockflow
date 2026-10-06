import type { ColunaDeTabela } from "@/components/tabela";

/**
 * **Duas colunas** para as três tabelas de dinheiro do painel: a rubrica e o
 * valor.
 *
 * ## Porque é que são duas e eram três
 *
 * A terceira chamava-se "O QUE É" e era a maior massa de texto do ecrã: cerca de
 * trinta frases num painel de 3630px de altura, que o dono do produto leu como
 * um manual de instruções. Saiu a 2026-10-06 e não se perdeu — cada frase está
 * no `title` da rubrica a que pertence e aparece como sub-linha com o
 * `?explicar=1` (ver `components/explicar.tsx`).
 *
 * ## Porque é que isto é um módulo `.ts` e não vive no componente da linha
 *
 * Porque um ficheiro que exporta um componente **e** uma constante desliga o
 * fast refresh do Vite para esse ficheiro inteiro, e o
 * `react-refresh/only-export-components` do `eslint.config.js` recusa-o — bem,
 * porque o sintoma é um ecrã que deixa de actualizar ao gravar e ninguém
 * percebe porquê. A mesma razão que já tinha separado o `tinta-do-painel.ts` do
 * componente que o usa.
 */
export const COLUNAS_DE_RUBRICA: readonly ColunaDeTabela[] = [
  { chave: "rubrica", rotulo: "Rubrica", classe: "w-64" },
  { chave: "valor", rotulo: "Valor", classe: "w-40 text-right" },
];

/**
 * `min-w-md` = 448px, que é o que as duas colunas pedem (256 + 160) mais folga.
 *
 * Era `min-w-3xl` (768px) quando havia uma terceira coluna de prosa. Com duas
 * colunas, 768px de mínimo punha a tabela a deslizar na horizontal dentro de uma
 * vidraça de 512px da `FilaDePaineis` — e a deslizar sem precisar, porque o
 * conteúdo cabia.
 */
export const LARGURA_MINIMA_DE_RUBRICA = "min-w-md";
