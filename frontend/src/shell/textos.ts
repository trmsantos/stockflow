import { escolher } from "@/lib/i18n";

import { EN } from "./textos.en";
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
 * ## O inglês entrou aqui a 2026-10-07, e foi o `tsc` que o obrigou
 *
 * Enquanto a lista de línguas teve um elemento, este `Record` tinha uma chave e
 * importar o inglês dava uma variável não usada — que o `eslint` e o `tsc`
 * recusam, e com razão. O inglês era verificado mesmo assim, por estar anotado
 * com `typeof PT` num `tsconfig` que inclui `src/` inteiro (medido com uma
 * sonda: tirar-lhe uma chave dava `TS2741` sem ninguém o importar).
 *
 * Acrescentar `"en"` ao `LINGUAS` fez **esta linha** deixar de compilar até ter
 * a segunda entrada, nos sete catálogos ao mesmo tempo. Era o gate da ADR 0019 a
 * funcionar: não se serve uma língua em que metade dos ecrãs está traduzida, e
 * quem o impõe é o compilador e não a disciplina de quem escreve.
 */
export const textos = escolher({ "pt-PT": PT, en: EN });
