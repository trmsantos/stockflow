import type { ReactNode } from "react";

/**
 * A régua de contadores — a faixa de números no topo de um ecrã de operação.
 *
 * ## Porque substituiu os mosaicos, e o que isso corrigiu
 *
 * Isto era o `mosaico.tsx`: três cartões `rounded-xl`, com borda própria e
 * sombra própria, numa `grid grid-cols-3 gap-2`. Funcionava e estava medido. O
 * problema não era de implementação, era de **forma**: uma grelha de três
 * cartões iguais com um número grande e um rótulo pequeno é o cartão de
 * estatística que aparece em todos os painéis gerados, e o DESIGN.md §5 proíbe-o
 * quase pela letra ("cards ... repetidos em grelha de 3"). Era o tell mais
 * visível do repositório: o dono do produto olhou para a app e disse que parecia
 * gerada por IA, e este era o primeiro bloco de cada ecrã.
 *
 * A forma que o substitui vem da referência que o §1 nomeia — um painel de
 * operação, não um dashboard. Os contadores são **campos de uma régua**, não
 * cartões: sem radius, sem borda individual, sem sombra, sem `gap`. O que os
 * separa é a régua vertical de 1px, que é o mesmo cromado das colunas da tabela;
 * e a régua encosta à tabela por baixo, com o microrótulo do campo a usar o
 * **mesmo** tratamento tipográfico do cabeçalho de coluna. É essa rima que faz o
 * topo e a tabela lerem-se como um instrumento só em vez de três widgets a
 * flutuar sobre uma lista.
 *
 * ## Dois detalhes que não são estética
 *
 * **Os campos empacotam-se à esquerda e não esticam para encher a linha.** Três
 * células a dividir 1024px dariam 340px cada para mostrar um número de dois
 * dígitos. O espaço à direita fica vazio porque não vive lá nada, e isso é mais
 * honesto do que três cartões esticados — é também o que deixa a régua aguentar
 * dois contadores num ecrã e quatro noutro sem reconfigurar uma grelha.
 *
 * **Os campos alinham ao topo e não ao centro.** Com `justify-center` um campo
 * sem nota centrava as duas linhas que tem, e a sua figura ficava 10px abaixo das
 * dos vizinhos — medido no ecrã de Stock, onde o "valor de stock" não tem nota e
 * os outros dois têm. Alinhados ao topo, os três rótulos e as três figuras ficam
 * nas mesmas duas linhas, e o espaço que falta fica em baixo, onde não se nota.
 *
 * **O rótulo está acima do número**, que é o contrário do default. Não é um
 * rótulo tipográfico a mais sobre o conteúdo: é um **cabeçalho de campo**, com o
 * mesmo peso, caixa e tracking do `<th>` da tabela que vem logo abaixo. Lido de
 * cima para baixo, o ecrã é uma folha de ledger — campo, valor, colunas, linhas.
 */

/**
 * A régua. `border-b` à largura toda mesmo quando os campos acabam a meio: o que
 * fecha a faixa é a régua horizontal, não a última célula.
 */
export function ReguaDeContadores({
  children,
  rotulo,
  ...resto
}: {
  readonly children: ReactNode;
  /** Só para áudio, quando a faixa está a carregar. */
  readonly rotulo?: string;
  readonly "aria-busy"?: "true";
}) {
  return (
    <div className="w-full overflow-x-auto overscroll-x-contain border-b border-border" {...resto}>
      <div className="flex divide-x divide-border">
        {rotulo === undefined ? null : <span className="sr-only">{rotulo}</span>}
        {children}
      </div>
    </div>
  );
}

/**
 * As classes de um campo da régua.
 *
 * São classes e não um componente por a mesma razão que o mosaico documentava:
 * os campos são coisas **diferentes** — um é um `<Link>` que filtra, outro é um
 * `<div>` de leitura. O que tem de ser igual é a altura, o espaçamento e o
 * tamanho da figura, e é isso que estas constantes fixam. O `relative` é o que
 * dá âncora ao trilho.
 */
export const CLASSE_CONTADOR =
  "relative flex min-w-48 shrink-0 flex-col items-start justify-start gap-1 px-celula-x py-3 text-left";

/** O campo activo: um degrau de superfície acima, mais o trilho. */
export const CLASSE_CONTADOR_ATIVO = "bg-surface-2";

/** O campo que responde ao toque. Um `<div>` de leitura não leva isto. */
export const CLASSE_CONTADOR_TOCAVEL = "transition-colors hover:bg-surface-2";

/**
 * O interior de um campo: microrótulo, figura, e uma linha de nota opcional.
 *
 * A figura é mono e é a **única** coisa grande do ecrã (DESIGN.md §2: todo o
 * dado numérico é mono, nada de prosa é). 2rem é o degrau `text-3xl` da escala —
 * a escala tem nove degraus e os ecrãs usavam dois, o que é a outra metade da
 * razão pela qual a app parecia gerada: sem hierarquia de tamanho, um painel é
 * uma mancha cinzenta uniforme.
 */
export function CorpoDoContador({
  campo,
  figura,
  nota,
  ativo = false,
}: {
  readonly campo: string;
  readonly figura: string;
  /** A segunda linha — a hora a que o dia de negócio começa, por exemplo. */
  readonly nota?: string;
  readonly ativo?: boolean;
}) {
  return (
    <>
      {/* O trilho de 4px, só quando o campo está activo — o mesmo idioma do item
          de menu e da linha da tabela. Decoração: o estado é dito pelo
          `aria-current` que o `<Link>` põe, e pela superfície, que se distingue
          por luminosidade e não por matiz. */}
      {ativo ? (
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-trilho bg-primary" />
      ) : null}

      <span className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
        {ativo ? <span className="sr-only">A filtrar por </span> : null}
        {campo}
      </span>

      {/* `text-left` explícito: o `[data-numeric]` do `base.css` alinha à
          direita, que é o certo numa célula de tabela e o errado debaixo do seu
          próprio rótulo — media-se e via-se, o rótulo à esquerda e a figura
          encostada à direita da célula, como se fossem de dois blocos. A utility
          ganha ao `@layer base`, logo basta declará-la. */}
      <span data-numeric className="text-left text-3xl leading-none font-semibold">
        {figura}
      </span>

      {nota === undefined ? null : (
        <span className="text-xs leading-tight text-muted-foreground">{nota}</span>
      )}
    </>
  );
}
