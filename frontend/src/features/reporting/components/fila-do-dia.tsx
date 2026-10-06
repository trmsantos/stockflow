/**
 * A **fila de trabalho do dia** — uma linha por coisa que está à espera, com o
 * número e a porta.
 *
 * ## Porque é que isto substituiu as perguntas da manhã
 *
 * O Início era uma lista de quatro perguntas com quatro links: "O que está a
 * faltar ou a expirar? → Alertas". Respondia à pergunta certa e não respondia à
 * pergunta: dizia **onde** se descobre, não **o quê**. O dono do produto pediu
 * o quê — *"ao que está por expirar, coisas a fazer, descargas a chegar, tarefas
 * do dia"* —, e a diferença entre as duas formas é um número: "3 lotes expiram
 * dentro de 3 dias" decide-se de pé, à porta da copa; "o que está a expirar?"
 * obriga a abrir o ecrã para saber se vale a pena abrir o ecrã.
 *
 * ## Linhas, e só as que têm alguma coisa
 *
 * Uma linha com zero não é trabalho: é ruído com a forma de trabalho, e cinco
 * zeros ensinam a não olhar para o ecrã. Por isso cada linha só existe quando o
 * seu número é maior do que zero, e a ordem é **o que está pior primeiro** — a
 * mesma ordem das listas do resto da app. Quando não há nada, quem responde é o
 * estado vazio do ecrã, com as portas: um painel sem trabalho não é um beco.
 *
 * ## O trilho de 4px é o que faz a leitura de dois metros
 *
 * É o idioma da linha da tabela e do item de menu (DESIGN.md §3): a aresta
 * esquerda acende com a cor do sinal e **uma linha saudável não tem trilho**.
 * Aqui todas as linhas que existem são sinal — é uma fila de trabalho —, e o que
 * o trilho distingue é a espécie: âmbar no que está a correr contra o tempo
 * (validades, mínimos, mercadoria por dar entrada) e o acento no que já está em
 * curso (a contagem aberta). A palavra na linha diz sempre o mesmo que a cor.
 *
 * ## Classes e não um componente por linha
 *
 * É a mesma razão que o `regua-de-contadores.tsx` documenta: as linhas são
 * `<Link>`s para destinos **diferentes**, com `search` tipado por rota, e um
 * componente que recebesse "o destino" por propriedade teria de desistir dessa
 * tipagem — que é exactamente o que impede um link para um ecrã que já não
 * existe. O que tem de ser igual é a altura, o espaçamento e o cromado, e é isso
 * que estas duas exportações fixam.
 */

/**
 * A linha: 44px (`h-linha`), régua em baixo, e o trilho ancorado na aresta
 * esquerda. É um `<Link>`, logo leva o `focus-visible` do shell.
 */
export const CLASSE_DA_LINHA_DA_FILA =
  "group relative flex h-linha items-center gap-celula-x border-b border-border px-celula-x transition-colors last:border-b-0 hover:bg-surface-2";

export function CorpoDaLinhaDaFila({
  figura,
  frase,
  ecra,
  trilho,
}: {
  /** O número, em mono. É a razão de esta linha existir. */
  readonly figura: string;
  /** O que ele quer dizer, em prosa. Diz sempre o mesmo que a cor do trilho. */
  readonly frase: string;
  /** O ecrã que a resolve, em microrótulo. */
  readonly ecra: string;
  /** A tinta do trilho: `bg-warning` ou `bg-primary`. Nunca vazia aqui. */
  readonly trilho: string;
}) {
  return (
    <>
      {/* Decoração (`aria-hidden`): o sentido está na frase e no número, e a cor
          nunca comunica sozinha (DESIGN.md §2). */}
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-trilho ${trilho}`} />
      {/* `w-28` (112px) e não `w-20`: medido a 1280, "1 descarga" transbordava
          os 80px e a frase ao lado começava 8px mais à direita do que nas outras
          linhas. A unidade vive **dentro** da célula numérica, como na coluna de
          quantidade do Stock ("24,400 kg"), logo é a palavra mais longa que
          decide a largura. */}
      <span data-numeric className="w-28 shrink-0 text-right text-sm font-semibold">
        {figura}
      </span>
      <span className="min-w-0 flex-1 truncate" title={frase}>
        {frase}
      </span>
      <span className="shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
        {ecra}
      </span>
    </>
  );
}
