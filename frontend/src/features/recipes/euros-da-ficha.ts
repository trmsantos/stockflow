import type { LinhaDaReceita, ReceitaResumo } from "./schemas";

/**
 * **A chave ausente e a chave a `null` não são o mesmo facto**, e são estas as
 * funções que os separam para o ecrã (ADR 0035, decisão 6).
 *
 *  - **ausente** — *"não te compete"*. É sobre **quem** olha: o
 *    `SemEurosParaQuemNaoVe` tira a chave do JSON a quem não é `owner|manager`.
 *    Nunca `0`, que seria uma afirmação falsa sobre o preço;
 *  - **`null`** — *"não sabemos"*. É sobre a **ficha**: é o degrau 5 da escada
 *    do custo, e o ecrã imprime "—" com a palavra `desconhecido` ao lado.
 *
 * Consequência, e é por isso que esta distinção se guarda: com a chave **ausente
 * desaparece a coluna inteira**; com ela a `null` a coluna **fica**, com o traço
 * lá dentro. Colapsá-las faz o colaborador ver um traço onde devia ver nada — e
 * um traço é uma pergunta sobre um número que ele nunca devia ter visto — e faz
 * o dono ver nada onde devia ver um traço, que é a ficha a esconder-lhe que não
 * consegue responder.
 *
 * ## Porque é o payload a decidir, e não o papel da sessão
 *
 * O cliente **sabe** o papel (`useSessao().data.tenant_ativo.papel`) e seria uma
 * linha. Seria também uma **segunda definição** da regra — "quem vê dinheiro é
 * `owner|manager`" escrita onde ninguém a mantém — e é precisamente uma segunda
 * definição que não acompanhou a primeira que partiu o ecrã das receções. A
 * forma do payload não pode divergir de si própria: no dia em que o dono mudar a
 * política, o ecrã muda com ela sem um diff.
 *
 * É o mesmo ficheiro, com o mesmo argumento, que o `purchasing/euros-do-papel.ts`
 * — e **são dois de propósito**: a fronteira da ADR 0008 só deixa importar de
 * outra feature o seu `api.ts`, e o que atravessaria aqui não seria um recurso,
 * seria uma política. Quando o terceiro módulo precisar desta forma, ela desce
 * para `src/lib/` com um caso à frente, como desceu a `Quantidade`.
 */

/**
 * Esta ficha trouxe os euros? Basta **um** dos três estar presente.
 *
 * Os três (`batch_cost`, `unit_cost`, `display_cost`) saem em bloco — é a regra
 * da reconstrução por aritmética da ADR 0032 (decisão 2): com as quantidades, a
 * fornada e o rendimento no payload de toda a gente, esconder um euro e deixar
 * os outros era teatro. O `some` em vez do `every` é a rede: se um dia saírem
 * separados, o ecrã mostra o que veio em vez de esconder o que não devia.
 *
 * **Presente e a `null` conta como trazido**, e é o ponto todo: uma ficha
 * `desconhecido` serve os três a `null` a quem vê euros, e é aí que a coluna
 * tem de ficar para imprimir o traço.
 */
export function fichaMostraEuros(resumo: ReceitaResumo): boolean {
  return (
    resumo.batch_cost !== undefined ||
    resumo.unit_cost !== undefined ||
    resumo.display_cost !== undefined
  );
}

/**
 * E as **linhas** trouxeram os seus? A mesma pergunta, no outro serializer.
 *
 * São duas perguntas e não uma porque são dois serializers com dois
 * `CAMPOS_DE_DINHEIRO` — e porque a ADR 0035 (decisão 6) proíbe
 * **expressamente** a subclasse de os redeclarar, que é a porta irmã por onde o
 * dinheiro já saiu duas vezes nesta casa. Perguntar à ficha pelas colunas da
 * tabela das linhas era assumir que as duas decisões são a mesma; são duas, e o
 * ecrã lê as duas.
 *
 * `some` sobre as linhas: uma linha sem euros não prova nada sobre o papel de
 * quem olha — prova sobre a linha. Uma ficha sem linha nenhuma não existe (o
 * contrato exige ≥ 1), e o `false` desse caso não tem consequência.
 */
export function linhasMostramEuros(linhas: readonly LinhaDaReceita[]): boolean {
  return linhas.some(
    (linha) => linha.unit_cost !== undefined || linha.line_cost !== undefined,
  );
}
