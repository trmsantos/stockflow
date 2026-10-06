import { formatDate } from "@/lib/format";

import { eZero, type ResumoDoPeriodo } from "./schemas";

/**
 * A contagem aconteceu **dentro** desta janela?
 *
 * Comparação de dois instantes que o servidor mandou, não uma conta: é a
 * diferença entre "contou-se e não havia desvio" (zero é boa notícia) e
 * "ninguém contou" (zero é ausência). As duas chegam ao ecrã como o mesmo
 * `0,00 €`, e é esta linha que as separa.
 */
function contouNestePeriodo(ultimaContagem: string | null, desde: string): boolean {
  if (ultimaContagem === null) return false;
  return new Date(ultimaContagem).getTime() >= new Date(desde).getTime();
}

/**
 * **A quebra desconhecida nunca aparece sem a data da última contagem** (ADR
 * 0013, decisão 7), e esta função é essa regra.
 *
 * Um mês sem contar dá zero, e o mês seguinte dá três meses de desvio de uma
 * vez. Quando a coluna "O QUE É" saiu das tabelas, esta frase era a única que
 * **não podia** ir para a camada do `?explicar=1`: um `0,00 €` sem a data ao
 * lado é a afirmação optimista que a decisão 7 existe para proibir. Vive na
 * **nota do cabeçalho do bloco**, que é onde o `BlocoDoPainel` guarda as
 * condições dos seus números — o mesmo sítio da fronteira ecoada —, e fica à
 * vista em qualquer camada.
 *
 * Devolve a tinta separada do texto porque o texto diz sempre o mesmo que a
 * tinta: é a regra do DESIGN.md §2 cumprida na origem, e não no sítio onde se
 * desenha.
 */
export function notaDaContagem(resumo: ResumoDoPeriodo): {
  readonly texto: string;
  readonly tinta: string;
} {
  const { last_count_at: ultima } = resumo.data_quality;
  const contou = contouNestePeriodo(ultima, resumo.period.since);
  const zero = eZero(resumo.unknown_shrinkage_eur);

  if (ultima === null) {
    return {
      texto: "nunca se contou: o zero da quebra é ausência de contagem, não ausência de quebra",
      tinta: "text-warning",
    };
  }
  if (zero && !contou) {
    return {
      texto: `sem contagem neste período — a última foi a ${formatDate(ultima)}, e o desvio aparece todo na próxima`,
      tinta: "text-warning",
    };
  }
  return { texto: `última contagem a ${formatDate(ultima)}`, tinta: "" };
}
