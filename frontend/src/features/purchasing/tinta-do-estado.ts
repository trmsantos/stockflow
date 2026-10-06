import type { EstadoDeLinha, EstadoDeRececao } from "./schemas";

/**
 * A tinta de um estado de `purchasing`, nos **dois papéis** em que ela aparece:
 * a palavra na coluna do estado e o trilho de 4px na aresta da linha.
 *
 * Vive num módulo próprio pela mesma razão que a do `inventory`: as duas tabelas
 * desta feature — os documentos (`tabela-de-rececoes`) e as linhas de um deles
 * (`tabela-de-linhas-de-fatura`) — precisam da mesma decisão, e duas cópias dela
 * divergem na primeira correção feita só numa. Se a palavra dissesse "por rever"
 * em âmbar e o trilho da mesma linha fosse vermelho, a linha dava dois
 * veredictos.
 *
 * ## Uma só urgência, e é uma afirmação sobre o domínio
 *
 * O `inventory` tem duas (`grave` e `aviso`), porque um stock negativo é pior do
 * que um stock baixo. Aqui **não há nada grave**: um documento por rever é
 * mercadoria cujo stock ainda não existe, e isso é o estado normal de uma fatura
 * que acabou de chegar — não é uma falha. Por isso o único estado com tinta é o
 * `needs_review`, e é âmbar.
 *
 * O `confirmed` não tem tinta nenhuma, em nenhum dos dois papéis: não é verde,
 * não é cinzento, é nada. É o que faz a leitura de dois metros do DESIGN.md §1
 * funcionar — numa lista de sete documentos o único trilho aceso é o do que falta
 * rever. Um visto verde nos outros seis esconderia esse. O `skipped` de uma linha
 * também não tem: ficar de fora desta entrada é uma **decisão** de alguém, não um
 * problema a resolver.
 *
 * O estado vem sempre do servidor; nada aqui o deduz.
 */

/**
 * Os dois enums do contrato partilham os dois valores que importam a esta
 * decisão (`needs_review` e `confirmed`), e o terceiro valor da linha
 * (`skipped`) cai no mesmo sítio que o `confirmed`: sem tinta. A união em vez de
 * duas funções por enum é o que garante que um documento por rever e uma linha
 * por rever têm exactamente a mesma cor.
 */
type EstadoComTinta = EstadoDeRececao | EstadoDeLinha;

/** Primeiro papel do DESIGN.md §2: a cor de estado como **cor de texto**. */
export function tintaDoTextoDoEstado(estado: EstadoComTinta): string {
  return estado === "needs_review" ? "text-warning" : "";
}

/** O trilho é preenchimento, mas de 4px e sem nada por cima: não leva frente. */
export function tintaDoTrilhoDoEstado(estado: EstadoComTinta): string {
  return estado === "needs_review" ? "bg-warning" : "";
}
