import type { Extracao } from "./schemas-de-documento";
import type { Rececao } from "./schemas";

/**
 * **A chave ausente e a chave a `null` não são o mesmo facto**, e são estas as
 * funções que os separam para o ecrã.
 *
 * ## Duas funções e **uma** política, porque o defeito veio de haver duas
 *
 * Este módulo nasceu para a receção e passou a servir também o **documento**, e
 * a razão é a história: a adenda dos euros fechou a receção e deixou aberta a
 * janela do lado — o painel da extração servia *a mesma fatura e os mesmos
 * preços* a qualquer papel, pela rota do documento. Escrever aqui uma segunda
 * definição de "este payload trouxe euros" era repetir a origem da família de
 * defeitos: duas cópias da mesma regra divergem na primeira correcção feita só
 * numa delas.
 *
 * Desde 2026-10-19 só `owner|manager` veem dinheiro numa receção. O servidor
 * não responde com zeros nem com `null`: **tira a chave do JSON**
 * (`SemEurosParaQuemNaoVe`), porque um zero seria uma afirmação falsa sobre o
 * preço e um `null` convidaria o ecrã a imprimir "—" como se o valor não
 * existisse. Lidas como factos:
 *
 *  - **ausente** — *"não te compete"*. É sobre **quem** está a olhar;
 *  - **`null`** — *"não há valor aqui"*. É sobre o **documento**: uma guia de
 *    remessa não traz preços, e há faturas em que o modelo não leu o preço.
 *
 * Consequência no ecrã, e é por isso que esta distinção se guarda: com a chave
 * ausente desaparece a **coluna inteira**, e com ela a `null` fica a coluna
 * com "sem preço" lá dentro. A primeira é uma pergunta sem resposta para quem
 * olha; a segunda é uma resposta sobre o papel que está na mão.
 *
 * ## Porque é o payload a decidir, e não o papel da sessão
 *
 * O cliente **sabe** o papel (`useSessao().data.tenant_ativo.papel`) e seria
 * uma linha. Seria também uma **segunda definição** da regra — "quem vê
 * dinheiro é `owner|manager`" escrita onde ninguém a mantém —, e este trabalho
 * existe precisamente porque uma segunda definição do contrato (os schemas Zod
 * à mão) não acompanhou a primeira. A forma do payload não pode divergir de si
 * própria: no dia em que o dono mudar a política, o ecrã muda com ela sem um
 * diff. É também o que o DESIGN.md §4 quer dizer com "esconder é apresentação,
 * não autorização" — quem autoriza já decidiu, antes de isto correr.
 */

/**
 * Este documento trouxe os acumulados em euros? Basta **um** dos três do
 * cabeçalho estar presente: eles saem em bloco, e se um dia saírem separados o
 * ecrã mostra o que veio em vez de esconder o que não devia.
 *
 * **Uma função e não duas**: a da linha chegou a existir e saiu, porque as
 * células que imprimem dinheiro precisam de estreitar o tipo (`undefined`,
 * `null`, ou a string) e um booleano não o faz — ficariam com o teste à mesma,
 * e a função era uma chave que ninguém lia. Quem decide as **colunas** é esta,
 * e isso é de propósito: o cabeçalho chega antes das linhas, logo o esqueleto
 * já sabe quantas colunas vêm e a tabela não salta quando os dados chegam.
 */
export function rececaoMostraEuros(rececao: Rececao): boolean {
  return (
    rececao.document_total !== undefined ||
    rececao.lines_total !== undefined ||
    rececao.vat_breakdown !== undefined
  );
}

/**
 * E esta leitura trouxe os euros? **A mesma pergunta, no outro caminho.**
 *
 * As três famílias de dinheiro deste payload saem em bloco — o `total` do
 * cabeçalho, os preços das linhas e as bases da conferência de IVA —, porque é
 * o mesmo pedido, o mesmo papel e a mesma decisão do servidor. Testam-se as
 * três pela mesma razão que a receção testa os seus três acumulados: se um dia
 * saírem separadas, o ecrã mostra o que veio em vez de esconder o que não devia.
 *
 * O `total` chega primeiro e sozinho decide o caso normal; as outras duas são a
 * rede. E é um `some` e não um `every`: uma linha sem preço não prova nada sobre
 * o papel de quem olha — prova sobre a linha.
 *
 * **Uma `Extracao` e nunca um `Documento`**: a extração é `null` enquanto não
 * houver leitura, e nesse estado não há euros nem ausência de euros — não há
 * payload. Quem ramifica sobre o `null` é o painel, que já o faz.
 */
export function extracaoMostraEuros(extracao: Extracao): boolean {
  return (
    extracao.total !== undefined ||
    extracao.lines.some((linha) => linha.unit_price !== undefined) ||
    extracao.vat_checks.some((conferencia) => conferencia.lines_base !== undefined)
  );
}
