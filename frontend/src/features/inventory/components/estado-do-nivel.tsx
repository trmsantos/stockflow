import type { EstadoNivel } from "../schemas";
import { tintaDoTexto } from "../tinta-do-estado";
import { rotuloDeEstado } from "../vocabulario";

/**
 * O estado de um nível de stock, em palavra.
 *
 * ## Era um badge, e porque deixou de ser
 *
 * Chamava-se `BadgeDeEstado` e era um chip: pílula com tinta `-surface`, borda,
 * e um ícone da Lucide por estado. Estava correcto e estava medido. Saiu por
 * duas razões que não se anulam:
 *
 *  1. **O ícone dizia o que a palavra já dizia.** Um triângulo antes de "Baixo"
 *     é a palavra outra vez, em desenho. Quatro ícones da mesma família numa
 *     coluna de quinze linhas é o acessório que faz uma app parecer gerada
 *     (DESIGN.md §5), e a regra de "nunca só a cor" é cumprida pela palavra —
 *     sempre foi; o ícone era redundância a fingir que era acessibilidade.
 *
 *  2. **Um chip numa tabela densa é um cartão pequeno.** A linha tem 44px; uma
 *     pílula de 28px com tinta própria lá dentro traz radius, borda e
 *     preenchimento para dentro de uma célula cujo cromado já é a régua de 1px.
 *     O painel passa a ter duas linguagens de delimitação a competir.
 *
 * ## O `ok` não se vê, e vê-se
 *
 * Um nível saudável devolve a palavra **só para áudio**. Não é cinzento, não é
 * um visto verde: é nada, visualmente. É a mesma decisão que o trilho da linha
 * (ver `components/tabela.tsx`) e é o que faz a leitura de dois metros do §1
 * funcionar — o ecrã é monocromático até algo estar mal, e por isso o que está
 * mal salta.
 *
 * Em áudio, porém, uma célula vazia é informação perdida: quem navega a tabela
 * por teclado ouviria "Estado" e silêncio, e não saberia distinguir um artigo
 * saudável de um dado que falta. Daí o `sr-only` em vez de `null`. Silêncio
 * visual, não silêncio total.
 *
 * A cor vem do primeiro dos três papéis do DESIGN.md §2 — `--color-<estado>`
 * como cor de texto, medida contra a pior superfície pelo `pnpm lint` — e é
 * decidida no `tinta-do-estado.ts`, ao lado da tinta do trilho da mesma linha.
 * As duas derivam de uma classificação só, para a palavra e o trilho não poderem
 * dar veredictos diferentes sobre o mesmo artigo.
 */
export function EstadoDoNivel({ estado }: { readonly estado: EstadoNivel }) {
  const rotulo = rotuloDeEstado(estado);

  if (estado === "ok") {
    return <span className="sr-only">{rotulo}</span>;
  }

  return <span className={tintaDoTexto(estado)}>{rotulo}</span>;
}
