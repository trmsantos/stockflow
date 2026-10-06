import type { ReactNode } from "react";

/**
 * Um bloco do painel: a régua de 1px que o separa do anterior, um título de
 * secção, uma nota ao lado e uma acção à direita.
 *
 * Existe porque cada vista do painel tem vários blocos e a alternativa era
 * vários cabeçalhos escritos à mão que divergem no primeiro ajuste feito num
 * só. Não é um cartão: não tem radius, não tem sombra, não tem borda à volta. O
 * que separa é a régua horizontal, que é o mesmo cromado da régua de contadores
 * e das colunas da tabela — e é essa rima que faz o ecrã ler-se como um
 * instrumento em vez de uma grelha de widgets (DESIGN.md §3 e §5).
 *
 * O título é um `<h2>` porque o ecrã tem um `<h1>`, e a hierarquia é o que
 * permite saltar de bloco em bloco por áudio.
 *
 * ## A nota é uma **condição**, não uma explicação
 *
 * A nota fica na mesma linha do título e é onde vive o que delimita os números
 * do bloco: o grão e o máximo do eixo do gráfico, a data da última contagem ao
 * lado da quebra desconhecida. Isso pertence ao título — um painel que não diz
 * de que janela está a falar é um painel que ninguém pode contestar.
 *
 * O que **não** vive aqui, desde 2026-10-06, são as frases que explicam o que
 * uma rubrica significa. Eram seis, uma por bloco, e somavam-se às trinta da
 * coluna "O QUE É" das tabelas: cada uma defendia-se sozinha e juntas eram um
 * manual de instruções. Passaram para a camada do `?explicar=1` (ver
 * `components/explicar.tsx`), que é o que a `acao` deste cabeçalho costuma
 * levar. A distinção que ficou: uma **condição** diz o que o número é e fica; uma
 * **explicação** diz porque é que ele é assim e vai para a camada.
 */
export function BlocoDoPainel({
  titulo,
  nota,
  acao,
  children,
}: {
  readonly titulo: string;
  /** A fronteira, o grão, a condição. Em mono quando é um intervalo. */
  readonly nota?: ReactNode;
  /** Uma navegação ou o interruptor de explicação. À direita, onde não compete
   * com o título. */
  readonly acao?: ReactNode;
  readonly children: ReactNode;
}) {
  return (
    // `scroll-mt-cabecalho`: a barra do painel é sticky a `top-cabecalho`, e sem
    // esta margem de scroll um bloco que receba foco por teclado — ou um salto
    // por âncora — acabava **debaixo** dela. É o mesmo remédio que o formulário
    // de convite e a tabela de linhas de fatura já usam, e é a regra "sticky
    // headers must not cover the focused element" aplicada ao sítio onde ela se
    // paga.
    //
    // `min-w-0`: um bloco pode ser metade de uma `FilaDePaineis`, e uma célula
    // de grelha tem `min-width: auto` por omissão — sem isto a tabela que
    // desliza na horizontal lá dentro esticava a coluna da grelha em vez de
    // deslizar, e punha a página inteira a deslizar com ela.
    <section className="flex min-w-0 scroll-mt-cabecalho flex-col border-b border-border">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-celula-x py-3">
        <h2 className="text-sm font-semibold">{titulo}</h2>
        {nota === undefined ? null : (
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">{nota}</p>
        )}
        {acao === undefined ? null : <div className="ml-auto flex items-center gap-2">{acao}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * Dois blocos lado a lado a partir de 1280px — **duas vidraças de um painel, não
 * dois cartões**.
 *
 * ## Porque é que isto entrou
 *
 * A vista de período tinha cinco blocos empilhados e 1726px de altura depois de
 * o fecho do mês sair para uma vista própria. Um painel que não responde de
 * relance não é um painel, é um relatório: o que fez a diferença entre 1726 e
 * ~950 **não** foi apagar informação, foi deixar de empilhar coisas estreitas.
 * Duas das tabelas do painel têm duas colunas (rubrica e valor) e ocupavam
 * 1024px de largura para mostrar 416 — e, pior, o `table-layout` automático
 * distribuía a folga pelas duas colunas, afastando o número do seu próprio
 * rótulo meio ecrã. Emparelhá-las resolve a altura e o afastamento de uma vez.
 *
 * ## `xl:` e não `lg:`, e isso é medido
 *
 * A fronteira é 1280px de **viewport** (`xl`), que com a sidebar de 16rem dá
 * 1024px de conteúdo e 512px por vidraça — acima do `min-w-md` (448px) das duas
 * colunas da tabela. A `lg` (1024px de viewport) a vidraça ficava em 384px e a
 * tabela passava a deslizar na horizontal dentro dela, que é o defeito que o
 * DESIGN.md §4 só aceita a 360px. Abaixo de 1280 os blocos empilham-se, que é o
 * comportamento que já tinham.
 *
 * A régua vertical entre as duas vidraças é a mesma `border-border` das colunas
 * da tabela, posta no primeiro filho: é cromado contado (DESIGN.md §2) e não um
 * `gap` — um espaço entre os dois blocos fazia-os ler-se como dois cartões a
 * flutuar, que é o §5.
 */
export function FilaDePaineis({ children }: { readonly children: ReactNode }) {
  return (
    <div className="xl:grid xl:grid-cols-2 xl:[&>section:first-child]:border-r">{children}</div>
  );
}
