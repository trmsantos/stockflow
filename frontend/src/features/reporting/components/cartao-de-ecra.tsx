import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Um **cartão de pré-visualização**: a vidraça que mostra as primeiras linhas de
 * um ecrã e leva a ele.
 *
 * ## A distância ao anti-padrão, que é onde este ecrã se ganha ou se perde
 *
 * O DESIGN.md §5 proíbe "cards com ícone colorido em círculo + título + duas
 * linhas, repetidos em grelha de 3". Isto é uma grelha de cartões e **não** é
 * isso, e a diferença não é de grau:
 *
 *  - o conteúdo são **dados reais em miniatura** — as três piores linhas da
 *    tabela que o cartão previsualiza, com os mesmos números, as mesmas palavras
 *    e o mesmo trilho de sinal —, não uma frase a descrever o que lá está. Um
 *    cartão que dissesse "veja aqui o que está a expirar" era o anti-padrão
 *    escrito por extenso;
 *  - **não há ícone nenhum**, muito menos em círculo colorido. O cabeçalho é o
 *    nome do destino em microrótulo, com o tratamento do `<th>` da tabela que
 *    vem lá dentro — é essa rima que faz a grelha ler-se como um instrumento;
 *  - **a cor continua a ser sinal.** O trilho acende nas linhas que estão mal e
 *    nada nas que estão bem, logo um cartão sem problemas é monocromático. Uma
 *    tinta por cartão, para os distinguir, seria decoração a fingir que é sinal;
 *  - **zero prosa dentro do cartão.** As únicas frases que existem são o vazio
 *    ("nada a expirar") e o erro, que são estados e não descrições.
 *
 * ## Porque é que a grelha substituiu a fila de linhas
 *
 * O Início era oito linhas finas encostadas ao topo. A 1280px funcionava; num
 * monitor de 2000px eram oito linhas de 1744px de largura com um número à
 * esquerda, uma frase no meio e um rótulo colado à direita — e um deserto por
 * baixo. **Uma lista não tem como usar a largura**: cresce para baixo, e o que
 * sobra à direita fica vazio por construção. Uma grelha de cartões cresce nas
 * duas direcções, e é por isso que a forma mudou com a largura do monitor do
 * dono do produto e não com a moda.
 *
 * ## O cartão inteiro é o alvo, e o `::after` é o que o torna isso
 *
 * O `<Link>` vive no cabeçalho — é lá que está o nome do destino, que é o texto
 * acessível do link — e estica-se sobre a vidraça inteira com `after:inset-0`.
 * Tocar em qualquer ponto do cartão navega; o foco por teclado desenha o anel à
 * volta da faixa de 44px do cabeçalho, que é um alvo visível e não um fio de
 * texto.
 *
 * O `tabela-de-stock.tsx` documenta a razão pela qual **não** se faz isto numa
 * tabela: um link esticado rouba a selecção de texto às células, e numa tabela
 * de ERP copiar um número é uso real. Num cartão de pré-visualização não é —
 * ninguém copia de uma miniatura, vai-se ao ecrã. A troca é a inversa, e por
 * isso a decisão é a inversa.
 *
 * **O `after:z-10` não é defensivo: sem ele a camada não cobria nada.** Medido
 * com `document.elementFromPoint` no fundo de cada cartão: cinco dos seis
 * devolviam o `<li>` e não o link. A razão é a ordem de pintura — cada linha é
 * `relative` (precisa disso para ancorar o trilho de 4px), logo é um elemento
 * **posicionado** que vem depois no DOM e pinta por cima de outro elemento
 * posicionado com `z-index: auto`. O cartão parecia clicável e só o cabeçalho
 * era. O único que passava no ensaio era o do gráfico, que não tem `<li>`
 * nenhum — ou seja, o defeito escondia-se exactamente no cartão que se testaria
 * primeiro.
 *
 * O botão de "tentar outra vez" do estado de erro leva `relative z-20`, logo
 * fica **acima** da camada esticada e continua a ser carregável. Um `<button>`
 * dentro de um `<a>` não existe em HTML, e era o que aconteceria se o cartão
 * inteiro fosse o elemento `<Link>`.
 */

/**
 * O cabeçalho do cartão, como classe e não como componente — a mesma razão que o
 * `regua-de-contadores.tsx` e a antiga fila do dia documentam: cada cartão é um
 * `<Link>` para um destino **diferente**, com `search` tipado por rota, e um
 * componente que recebesse "o destino" por propriedade teria de desistir dessa
 * tipagem, que é exactamente o que impede um link para um ecrã que já não
 * existe.
 *
 * `bg-surface-2` e o microrótulo em caixa alta: é o tratamento do `<th>` do
 * `components/tabela.tsx`, e é deliberado que seja o mesmo.
 */
export const CLASSE_DO_DESTINO =
  "flex h-linha shrink-0 items-center border-b border-border bg-surface-2 px-celula-x " +
  "text-xs font-bold tracking-microrotulo text-muted-foreground uppercase transition-colors " +
  "after:absolute after:inset-0 after:z-10 after:content-[''] group-hover:text-foreground";

/**
 * Uma linha da miniatura: trilho de sinal, nome à esquerda, dados à direita.
 *
 * Os 44px são o `h-linha` da tabela a sério, e não uma altura menor "porque é
 * uma miniatura": é o que faz a miniatura parecer a tabela, e é o alvo de toque
 * do §4. Sem sub-linhas — uma segunda linha de 13px dentro de uma célula de 44px
 * cresce a linha e desfaz o ritmo, que é a lição 3 do DESIGN.md §4 e já custou
 * meia tabela de Alertas.
 */
export function LinhaDoCartao({
  trilho,
  nome,
  titulo,
  children,
}: {
  /** `bg-danger`, `bg-warning`, `bg-primary` — ou vazio, se a linha está bem. */
  readonly trilho: string;
  readonly nome: string;
  /** O texto completo, para quem passa o rato por cima de um nome truncado. */
  readonly titulo?: string;
  /** A célula da direita: números em mono, ou a frase da validade. */
  readonly children: ReactNode;
}) {
  return (
    <li className="relative flex h-linha items-center gap-3 border-b border-border px-celula-x last:border-b-0">
      {/* Decoração (`aria-hidden`): o sentido está na palavra e no número ao
          lado, e a cor nunca comunica sozinha (DESIGN.md §2). */}
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-trilho ${trilho}`} />
      {/* `truncate` e não quebra de linha: uma linha que quebrasse em duas
          crescia a célula de 44px e desfazia o ritmo.

          **`grow basis-24` e não `flex-1`, e a diferença foi medida.** O
          `flex-1` é `flex: 1 1 0%` — base zero —, logo o nome só recebe o que
          sobra depois de a célula da direita ter o que quer. Com "perde
          qualidade depois de amanhã" (236px) numa vidraça de 314px, o que
          sobrava eram 34px e o nome do artigo ficava em "A…". Com uma base de
          6rem o nome entra na repartição em vez de a sofrer: a 2000px nada
          trunca, e a 1280px os dois cortam a cauda e ambos se lêem. */}
      <span className="min-w-0 grow basis-24 truncate text-sm" title={titulo ?? nome}>
        {nome}
      </span>
      {/* `min-w-0` e encolhível: é o que deixa uma **frase** à direita repartir
          a largura com o nome. Os números não encolhem — cada um traz o seu
          `shrink-0`, porque uma quantidade truncada é um número errado. */}
      <span className="flex min-w-0 items-baseline gap-2 text-sm">{children}</span>
    </li>
  );
}

/**
 * A vidraça, com os seus três estados.
 *
 * Os estados são **do cartão** e não do ecrã, e essa é a vantagem desta forma
 * sobre a lista que ela substitui: cada cartão lê a sua chave de cache, e um
 * cartão em erro não derruba os outros cinco. O Início antigo tinha um aviso só,
 * no fundo, para três pedidos — falhava um e o ecrã inteiro dizia que estava
 * incompleto, sem dizer onde.
 */
export function CartaoDeEcra({
  destino,
  aCarregar,
  rotuloDeCarga,
  erro,
  aoTentarOutraVez,
  vazio,
  linhasDoEsqueleto = 3,
  largo = false,
  children,
}: {
  /** O `<Link>` do cabeçalho, com a `CLASSE_DO_DESTINO`. */
  readonly destino: ReactNode;
  readonly aCarregar: boolean;
  /** "A carregar o que expira…" — específico, para quem ouve o ecrã. */
  readonly rotuloDeCarga: string;
  /** A mensagem já pronta (`mensagemDeErro`), ou `null`. */
  readonly erro: string | null;
  readonly aoTentarOutraVez: () => void;
  /**
   * A frase curta de quando não há nada ("nada a expirar"), ou `null` quando há
   * conteúdo. Curta de propósito: um cartão vazio diz o que não há e cala-se.
   */
  readonly vazio: string | null;
  readonly linhasDoEsqueleto?: number;
  /**
   * Duas colunas a `2xl`, e só a `2xl`.
   *
   * Existe por **conteúdo** e não por tetris: o único cartão que o usa é o do
   * gráfico, e é o único cuja leitura melhora com largura — mais intervalos
   * separados em vez de barras coladas. Os outros cinco são três linhas de
   * texto, que a 410px já não ganham nada com 820.
   *
   * Só a `2xl` porque é onde há quatro colunas: a `xl` são três, e um cartão de
   * duas faria seis cartões ocuparem sete lugares — o último sozinho numa
   * terceira fila. É a diferença entre preencher a grelha e desfeá-la.
   */
  readonly largo?: boolean;
  readonly children: ReactNode;
}) {
  return (
    // `relative` por causa da camada esticada do `<Link>`; `overflow-hidden`
    // para as réguas das linhas e o trilho de 4px ficarem dentro do raio.
    // `shadow-sm` é o token de painel do §2 — o fio de luz de 1px na aresta de
    // cima, que é o que separa num fundo preto. Não é uma sombra colorida.
    <article
      className={`group relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-sm transition-colors hover:border-border-strong ${
        largo ? "2xl:col-span-2" : ""
      }`}
    >
      {destino}

      {/* **A precedência dos três estados vive aqui e só aqui**: esperar, depois
          falhar, depois não haver nada, depois mostrar. Escrita como uma cadeia
          de `if` e não como três ternários encadeados no JSX, porque é dela que
          os seis cartões dependem para passarem um `vazio` sem o cercarem de
          guardas — seis cópias da mesma precedência eram seis sítios onde ela
          pode divergir. */}
      {(() => {
        if (aCarregar) {
          // Skeleton e não spinner (DESIGN.md §3), com a forma do que vem a
          // seguir: linhas de 44px, nome à esquerda e dado à direita. Quando os
          // dados chegam, nada salta.
          return (
            <div aria-busy="true" className="flex flex-col">
              <span className="sr-only">{rotuloDeCarga}</span>
              {Array.from({ length: linhasDoEsqueleto }, (_, indice) => indice).map((indice) => (
                <div
                  key={indice}
                  className="flex h-linha items-center gap-3 border-b border-border px-celula-x last:border-b-0"
                >
                  <Skeleton className="h-4 min-w-0 flex-1" />
                  <Skeleton className="h-4 w-16 shrink-0" />
                </div>
              ))}
            </div>
          );
        }

        if (erro !== null) {
          // Compacto, e **não** o `ErroAoCarregar`: aquele é um banner com
          // ícone, título e descrição desenhado para a largura de um ecrã, e
          // numa vidraça de 310px ocupa mais do que as três linhas que devia
          // estar a mostrar. Aqui o cabeçalho do cartão já diz o que falhou,
          // logo o que falta é a razão e a saída.
          //
          // `line-clamp-3`: a mensagem vem do servidor e pode ser comprida, e
          // um cartão que cresce com o tamanho de um erro empurra a grelha.
          return (
            <div className="flex flex-col items-start gap-2 px-celula-x py-3">
              <p role="alert" className="line-clamp-3 text-sm text-danger">
                {erro}
              </p>
              {/* `relative z-20` para ficar acima da camada esticada do link —
                  sem isso o botão existe e não se consegue carregar nele. */}
              <Button
                variant="outline"
                size="sm"
                className="relative z-20"
                onClick={aoTentarOutraVez}
              >
                Tentar outra vez
              </Button>
            </div>
          );
        }

        if (vazio !== null) {
          return (
            <p className="px-celula-x py-3 text-sm text-muted-foreground">{vazio}</p>
          );
        }

        return children;
      })()}
    </article>
  );
}
