import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * A tabela densa da identidade "Cabine" — **uma** definição, para as duas
 * features que já têm tabelas (convites e stock).
 *
 * ## Porque desceu para cá
 *
 * Nasceu dentro de `features/accounts/components/tabela-de-convites.tsx`, que
 * foi o primeiro ecrã do repositório com a largura toda. Quando o ecrã Stock
 * passou de lista de cartões a tabela, as convenções do cromado — altura de
 * linha, réguas verticais, cabeçalho em `surface-2`, microrótulo em caixa alta —
 * passaram a ser precisas em **duas** features, e é a descida que a ADR 0008
 * (decisão 2) deixou pré-aprovada para o primeiro caso real.
 *
 * O argumento não é reutilização, é divergência: duas tabelas com a mesma
 * intenção e dois ficheiros divergem na primeira correção feita só num deles, e
 * o dono vê dois ecrãs que não parecem do mesmo produto. É a mesma razão que fez
 * descer o mosaico de números, escrita no commit que o criou.
 *
 * ## O que esta tabela é, e o que não é
 *
 * É o ledger de um painel de operação (DESIGN.md §1: Bloomberg Terminal e os
 * KDS do Toast). Não é uma lista de cartões: não há radius por linha, não há
 * sombra por linha, não há um `gap` entre linhas. O que separa é a régua de 1px,
 * e o cromado é **contado** — cabeçalho um degrau de superfície acima, réguas
 * verticais entre colunas, e nada mais.
 *
 * Sem zebra stripes (DESIGN.md §3): numa tabela de 44px com réguas verticais a
 * zebra é uma terceira linguagem de separação a competir com as outras duas.
 */

export interface ColunaDeTabela {
  readonly chave: string;
  readonly rotulo: string;
  /**
   * Alinhamento e largura da coluna. Colunas numéricas levam `text-right` — é a
   * regra do DESIGN.md §3 e a razão é de leitura: o que se compara numa coluna
   * de quantidades são as unidades, e elas só se alinham à direita.
   */
  readonly classe?: string;
}

/**
 * A célula. `border-r` em todas menos a última: a régua vertical é o cromado da
 * identidade, e uma régua na aresta direita da tabela seria uma borda a dobrar.
 */
export const CLASSE_CELULA = "border-r border-border px-celula-x align-middle last:border-r-0";

/** A linha. 44px é o `h-linha` do §2: alvo de toque e densidade de painel. */
export const CLASSE_LINHA = "h-linha border-b border-border last:border-b-0";

/** O microrótulo do cabeçalho de coluna (DESIGN.md §2, "cromado"). */
export const CLASSE_MICROROTULO =
  "text-xs font-bold tracking-microrotulo text-muted-foreground uppercase";

/**
 * O trilho de sinal: a coluna de 4px à esquerda de cada linha.
 *
 * **É o único elemento ousado desta identidade, e é onde a ousadia toda está
 * gasta.** O DESIGN.md §1 diz o que o ecrã tem de fazer — "numa coluna de
 * quantidades uma linha em falta ou fora de prazo vê-se **sem se ler**, e vê-se
 * de dois metros". Um badge no meio da linha não faz isso: obriga a percorrer a
 * linha. Um trilho na aresta esquerda faz, porque todos os trilhos estão na
 * mesma vertical e o olho corre uma coluna de 4px em vez de quinze linhas.
 *
 * A consequência é a regra de cor desta tabela: **uma linha saudável não tem
 * trilho nenhum.** Não é cinzento, não é verde, é nada. Um visto verde em quinze
 * linhas é ruído que esconde as três que importam, e um trilho em todas as
 * linhas é uma coluna pintada que não distingue nada. O ecrã é monocromático até
 * algo estar mal, e é essa a leitura de dois metros.
 *
 * Decoração para quem lê por áudio (`aria-hidden`): o estado tem coluna própria,
 * com a palavra. A cor nunca comunica sozinha (DESIGN.md §2).
 */
export function TrilhoDaLinha({ tinta }: { readonly tinta: string }) {
  return <td aria-hidden="true" className={`w-trilho p-0 ${tinta}`} />;
}

/**
 * A moldura: o invólucro que desliza na horizontal, a largura mínima das
 * colunas, e o cabeçalho.
 *
 * `larguraMinima` é a classe `min-w-*` que garante que as colunas não se
 * esmagam. A 1280px a área de conteúdo tem ~1024px (64rem), logo não há scroll
 * em desktop; a 360px há, e o DESIGN.md §4 **declara-o** em vez de o tratar como
 * defeito — esconder colunas em mobile foi a alternativa rejeitada, porque a
 * coluna que se esconde é sempre a que faltava.
 *
 * ## O que não está aqui: o `thead` sticky
 *
 * O §3 pede cabeçalho sticky e este não o tem, e a razão é de CSS. O
 * `overflow-x-auto` desta moldura torna-se o *scrollport* do `position: sticky`;
 * como ele não rola na vertical, um `thead` sticky ficaria colado ao topo de um
 * contentor que nunca se move — a classe existiria e o efeito não. O que
 * acompanha o scroll é a **barra do ecrã**, que é sticky a `top-cabecalho`.
 * Um cabeçalho de tabela a sério exige dar altura própria à região da tabela com
 * scroll vertical interno, e isso é decisão de produto por decidir.
 */
export function MolduraDeTabela({
  colunas,
  larguraMinima,
  rotulo,
  comTrilho = false,
  children,
}: {
  readonly colunas: readonly ColunaDeTabela[];
  readonly larguraMinima: string;
  /** O nome acessível da tabela. Vai para um `<caption>` só para áudio. */
  readonly rotulo: string;
  /** Reserva a coluna de 4px do trilho de sinal. */
  readonly comTrilho?: boolean;
  readonly children: ReactNode;
}) {
  return (
    // `overscroll-x-contain`: a tabela desliza na horizontal a 360px, e sem isto
    // chegar ao fim do deslize passava o gesto à página — que num iOS é a
    // navegação para trás. Quem está a ler a última coluna não quer sair do ecrã.
    //
    // **`min-w-0` é o que faz o `overflow-x-auto` funcionar, e sem ele esta
    // moldura não continha nada.** Era um defeito em todos os ecrãs com tabela,
    // medido a 2026-10-07 com o `scripts/ver-ecra.py`: a 360px o
    // `document.documentElement.scrollWidth` era 947 num viewport de 360 — ou
    // seja, **a página inteira** deslizava, com a sidebar e a barra de topo a
    // sair do ecrã, em vez de a tabela deslizar por dentro da moldura.
    //
    // A causa é a regra de flexbox que ninguém decora: o `min-width` de um item
    // de flex é `auto`, não `0`, logo um item **cresce para caber o conteúdo**
    // mesmo com `w-full` — e esta moldura é sempre filha de um `flex flex-col`.
    // O `w-full` pedia 100% e o `min-width: auto` dava-lhe 960px, que ganha.
    //
    // É a diferença entre o que o DESIGN.md §4 declara e o que acontecia: o §4
    // aceita a **tabela** a deslizar na horizontal a 360px; nunca aceitou o ecrã
    // a deslizar. Fica aqui e não nos ecrãs porque a moldura é uma e os ecrãs são
    // quatro.
    //
    // **`relative` é a segunda metade, e sozinho o `min-w-0` não bastava.** Com
    // ele a moldura ficava nos 328px certos e o ecrã **continuava** a deslizar
    // 587px para preto — medido com `window.scrollTo(600, 0)`, que é a pergunta
    // honesta ("a página desliza?") em vez do `scrollWidth`, que é só um número.
    // A causa é que o bloco da `<table>` contribuía para a área de scroll da
    // **raiz**: sem um bloco contentor pelo meio, a sobreposição de um
    // descendente propaga-se ao documento mesmo clipada por um ancestral.
    // `position: relative` faz desta moldura esse bloco contentor e a
    // sobreposição fica local.
    //
    // Foram medidos cinco candidatos: `relative`, `contain: paint` e
    // `contain: layout` resolvem os três (deslize 0, e a tabela continua a
    // deslizar por dentro); `display: grid` e `max-width: 100%` não resolvem
    // nada. Ficou o `relative` por ser o mais barato e o que não tem efeitos
    // colaterais de containment. **E não ficou um `overflow-x-clip` no invólucro
    // do shell**, que foi a primeira tentativa: a medição mostrou deslize de 587
    // com e sem ele, e uma linha com um comentário a afirmar o que a medição nega
    // é pior do que linha nenhuma.
    <div className="relative w-full min-w-0 overflow-x-auto overscroll-x-contain">
      <table className={`w-full ${larguraMinima} border-collapse text-sm`}>
        <caption className="sr-only">{rotulo}</caption>
        <thead>
          <tr className={`${CLASSE_LINHA} bg-surface-2 text-left`}>
            {comTrilho ? <th aria-hidden="true" className="w-trilho p-0" /> : null}
            {colunas.map((coluna) => (
              <th
                key={coluna.chave}
                scope="col"
                className={`${CLASSE_CELULA} ${coluna.classe ?? ""} ${CLASSE_MICROROTULO}`}
              >
                {coluna.rotulo}
              </th>
            ))}
          </tr>
        </thead>
        {children}
      </table>
    </div>
  );
}

/**
 * O pendente da tabela: **skeleton, não spinner** (DESIGN.md §3).
 *
 * Desenha a moldura e o cabeçalho a sério, e só as células é que são barras: o
 * cromado não precisa de carregar, e assim a tabela não salta quando os dados
 * chegam — as linhas já têm os 44px que vão ter.
 *
 * O rótulo entra por propriedade porque quem ouve o ecrã tem de saber o que está
 * a carregar; "a carregar o stock" num ecrã de convites é pior do que o silêncio.
 */
export function EsqueletoDeTabela({
  colunas,
  larguraMinima,
  rotulo,
  comTrilho = false,
  linhas = 8,
}: {
  readonly colunas: readonly ColunaDeTabela[];
  readonly larguraMinima: string;
  readonly rotulo: string;
  readonly comTrilho?: boolean;
  readonly linhas?: number;
}) {
  return (
    <div aria-busy="true">
      <span className="sr-only">{rotulo}</span>
      <MolduraDeTabela
        colunas={colunas}
        larguraMinima={larguraMinima}
        rotulo={rotulo}
        comTrilho={comTrilho}
      >
        <tbody>
          {Array.from({ length: linhas }, (_, indice) => indice).map((indice) => (
            <tr key={indice} className={CLASSE_LINHA}>
              {comTrilho ? <td aria-hidden="true" className="w-trilho p-0" /> : null}
              {colunas.map((coluna) => (
                <td key={coluna.chave} className={`${CLASSE_CELULA} ${coluna.classe ?? ""}`}>
                  {/* `inline-block` para o `text-right` da coluna numérica
                      empurrar a barra para a direita, como empurra o número. */}
                  <Skeleton className="inline-block h-4 w-full max-w-24 align-middle" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </MolduraDeTabela>
    </div>
  );
}
