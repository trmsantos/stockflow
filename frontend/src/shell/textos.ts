import { escolher } from "@/lib/i18n";

import { PT } from "./textos.pt";

/**
 * A copy do invólucro, na língua desta visita.
 *
 * Resolve-se **ao nível do módulo** e não num hook, porque a língua é fixa por
 * documento (ADR 0019, decisão 2): é isso que permite que quem lê daqui seja uma
 * constante de módulo — um `aria-label`, uma entrada do registo de rotas — em vez
 * de ter de ser uma função. Com um selector de idioma, cada um destes acessos
 * passava a reactivo.
 *
 * Lê-se por propriedade (`textos.rodape.definicoes`) e não por `t("chave")`:
 * sem união de chaves, sem `detect-object-injection`, e sem o ramo de fallback
 * que toda a biblioteca tem para a chave que não existe — aqui ela não compila.
 *
 * ## O `textos.en.ts` existe e **não** é importado aqui, de propósito
 *
 * A lista de línguas tem um elemento, logo este `Record` tem uma chave e
 * importar o inglês dava uma variável não usada — que o `eslint` e o `tsc`
 * recusam, e com razão: era código morto.
 *
 * O inglês continua a ser **verificado** mesmo sem ser importado, porque o
 * `tsconfig` inclui `src/` inteiro e o `textos.en.ts` está anotado com
 * `typeof PT`. Medido com uma sonda: tirar uma chave do inglês dá `TS2741`
 * apesar de nada o importar. A garantia é do compilador e não deste import.
 *
 * E acrescentar `"en"` ao `LINGUAS` faz **esta linha** deixar de compilar, até
 * ela ter a entrada inglesa — que é o gate da ADR 0019: não se serve uma língua
 * em que metade dos ecrãs está traduzida.
 */
export const textos = escolher({ "pt-PT": PT });
