import type { EstadoDoCusto } from "../schemas";
import { tintaDoTextoDoCusto } from "../tinta-do-custo";
import { palavraDoCusto } from "../vocabulario";

/**
 * A certeza do custo, **em palavra** — na coluna da lista e na de cada
 * ingrediente.
 *
 * Não é um badge e não leva ícone, pela mesma razão que o `EstadoDoNivel` do
 * `inventory` deixou de ser: um chip de 28px com tinta e borda próprias dentro
 * de uma célula de 44px é um cartão pequeno a competir com a régua de 1px que já
 * delimita a célula (DESIGN.md §3), e um ícone antes de "Estimado" é a palavra
 * outra vez, em desenho.
 *
 * **O `conhecido` devolve a palavra só para áudio.** Visualmente é nada — não é
 * verde, não é um visto. Em áudio, uma célula vazia era informação perdida: quem
 * navega a tabela por teclado ouviria "Certeza" e silêncio, e não distinguiria
 * uma ficha com o custo todo de um dado que falta. Silêncio visual, não silêncio
 * total.
 *
 * A cor — e quais das três palavras a levam — decide-se no `tinta-do-custo.ts`,
 * ao lado da tinta do trilho da mesma linha, para a palavra e o trilho não
 * poderem dar veredictos diferentes sobre a mesma ficha.
 */
export function EstadoDoCustoDaFicha({ estado }: { readonly estado: EstadoDoCusto }) {
  const palavra = palavraDoCusto(estado);

  if (estado === "conhecido") {
    return <span className="sr-only">{palavra}</span>;
  }

  return <span className={tintaDoTextoDoCusto(estado)}>{palavra}</span>;
}
