import { useId } from "react";

/**
 * Barras por período — "como é que isto variou", dia a dia ou semana a semana.
 *
 * Uma coluna por intervalo, as séries empilhadas ou lado a lado, e **uma única
 * régua horizontal no topo com o máximo do eixo escrito**. Não há grelha de
 * fundo: num painel escuro com réguas de 1px, cinco linhas horizontais atrás das
 * barras competem com o cromado que separa as regiões do ecrã. A régua do
 * máximo basta, porque a pergunta que um painel destes responde é "qual é o pior
 * dia" e não "quanto exactamente no dia 12" — esse número está na tabela que
 * acompanha o gráfico.
 *
 * ## A aritmética é uma multiplicação, e é só isso
 *
 * O `share` de cada ponto e o `scale_max_eur` vêm do servidor (ADR 0013). Aqui
 * faz-se `share × 100%` de altura e mais nada. Não se procura o máximo, não se
 * divide euros, não se soma nada: num `viewBox` ou numa percentagem, uma conta
 * errada produz um gráfico **plausível**, que é a pior espécie de erro — passa
 * todos os gates e engana quem olha.
 *
 * ## Quatro séries é o tecto aritmético; para custos, o tecto honesto é menor
 *
 * A identidade tem um acento e três cores de estado (DESIGN.md §2), e a ADR 0013
 * deduziu daí um limite de quatro séries. A contagem está certa e a conclusão é
 * optimista, e viu-se num ensaio: num gráfico de **gastos por categoria** as
 * cores de estado não estão livres. O verde diz "bom" e um custo não é bom; o
 * âmbar diz "aviso" e um salário não é um aviso. Sobram o acento para a
 * mercadoria, o vermelho para as perdas — que **são** mesmo uma perda — e um
 * cinzento neutro (`bg-border-strong`) para o resto.
 *
 * Ou seja: duas séries com significado e uma neutra. Uma quarta categoria de
 * custo não tem cor honesta nesta paleta, e a resposta certa é agrupá-la em
 * "outros", não inventar-lhe uma tinta. Uma cor nova precisaria dos três papéis
 * do §2 e de passar o gate de contraste e gamut — e precisaria, antes disso, de
 * uma razão que não fosse "faltava-me uma cor".
 *
 * ## O equivalente textual não é um extra
 *
 * O `<svg>`… não existe (ver `barras-ordenadas.tsx`: uma barra é um rectângulo e
 * `height: 44%` num `<div>` é exactamente isso, sem distorção de traço e
 * responsivo de graça). O desenho é `aria-hidden`, e ao lado dele vai uma
 * `<table>` só para áudio com os números a sério. Um gráfico que se descreve num
 * `aria-label` é um gráfico que ninguém pode ler devagar.
 */

export interface PontoDaSerie {
  /** 0 a 1, do servidor. */
  readonly share: number;
  /** Já formatado pelo chamador. */
  readonly valor: string;
}

export interface SerieDeBarras {
  readonly id: string;
  readonly rotulo: string;
  /** A tinta da série. Uma por série, das quatro da paleta. */
  readonly tinta: string;
  /** Um ponto por intervalo, na mesma ordem dos `intervalos`. */
  readonly pontos: readonly PontoDaSerie[];
}

/**
 * Quantos rótulos de intervalo se mostram. Com 30 dias, trinta rótulos de 13px
 * colidem; mostrar um em cada N e deixar os outros só para áudio é mais honesto
 * do que os rodar 45° ou encolher a fonte abaixo do mínimo do §2.
 */
function passoDosRotulos(quantos: number): number {
  if (quantos <= 8) return 1;
  if (quantos <= 16) return 2;
  return Math.ceil(quantos / 8);
}

export function BarrasPorPeriodo({
  intervalos,
  series,
  maximo,
  rotulo,
  empilhado = false,
}: {
  /** Os rótulos curtos de cada intervalo: "12/02", "sem. 7". */
  readonly intervalos: readonly string[];
  readonly series: readonly SerieDeBarras[];
  /** O máximo do eixo, já formatado. Vem do servidor. */
  readonly maximo: string;
  readonly rotulo: string;
  /** Empilhadas (partes de um todo) ou lado a lado (grandezas a comparar). */
  readonly empilhado?: boolean;
}) {
  const idDaTabela = useId();
  const passo = passoDosRotulos(intervalos.length);
  const comLegenda = series.length > 1;

  return (
    <figure className="m-0 flex flex-col gap-2" aria-labelledby={idDaTabela}>
      <figcaption id={idDaTabela} className="sr-only">
        {rotulo}
      </figcaption>

      {comLegenda ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 px-celula-x">
          {series.map((serie) => (
            <li key={serie.id} className="flex items-center gap-1.5 text-xs">
              <span aria-hidden="true" className={`size-2 shrink-0 rounded-xs ${serie.tinta}`} />
              <span className="text-muted-foreground">{serie.rotulo}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div aria-hidden="true" className="px-celula-x">
        {/* A régua do máximo: o número à esquerda e o fio a atravessar. É o
            único elemento de eixo do gráfico. */}
        <div className="flex items-center gap-2">
          <span data-numeric className="shrink-0 text-xs text-muted-foreground">
            {maximo}
          </span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <div className="flex h-40 items-end gap-1">
          {intervalos.map((intervalo, indice) => (
            // `flex-col-reverse` e não `flex-col`, e **isto estava ao contrário**:
            // numa coluna normal o primeiro filho fica em cima, logo a série
            // maior flutuava sobre uma base fina e o gráfico lia-se de pernas
            // para o ar. Com o eixo invertido a primeira série é a **base**, que
            // é a convenção e a leitura certa — o que se empilha assenta.
            //
            // `items-center` com um tecto de largura nas barras: com sete
            // intervalos numa área de 990px cada coluna tinha 140px, e sete
            // blocos de 140px colados por 1px lêem-se como uma área cheia e não
            // como barras. Medido e visto.
            <div
              key={intervalo}
              className={`flex h-full min-w-0 flex-1 items-center justify-end ${
                empilhado ? "flex-col-reverse justify-start" : "gap-px"
              }`}
            >
              {series.map((serie) => {
                // `.at()` e não `pontos[indice]`: o `security/detect-object-injection`
                // do `eslint.config.js` recusa indexação por variável, e é a mesma
                // regra que pôs mapas no `vocabulario.ts`. Aqui o índice vem de um
                // `map` sobre os intervalos, logo é seguro — mas a regra não
                // distingue, e o `.at()` devolve `undefined` em vez de rebentar
                // quando uma série vier mais curta do que os intervalos, que é o
                // caso que importa tratar.
                const ponto = serie.pontos.at(indice);
                const altura = ponto === undefined ? 0 : Math.min(100, Math.max(0, ponto.share * 100));
                return (
                  <span
                    key={serie.id}
                    // `min-h-px` quando há valor: uma barra de 0,3% desapareceria,
                    // e "quase nada" não é "nada" num painel de gastos.
                    className={`block w-full max-w-12 ${serie.tinta} ${altura > 0 ? "min-h-px" : ""}`}
                    style={{ height: `${String(altura)}%` }}
                  />
                );
              })}
            </div>
          ))}
        </div>

        {/* A base: um fio contínuo, porque as colunas assentam nele. */}
        <div className="h-px bg-border-strong" />

        <div className="flex gap-px pt-1">
          {intervalos.map((intervalo, indice) => (
            <span
              key={intervalo}
              className="min-w-0 flex-1 truncate text-center text-xs text-muted-foreground"
            >
              {indice % passo === 0 ? intervalo : " "}
            </span>
          ))}
        </div>
      </div>

      {/* Os números a sério, para quem ouve o ecrã e para quem quer o valor
          exacto de um dia. Um `<caption>` não serve: a figura já tem nome. */}
      <table className="sr-only">
        <tbody>
          {intervalos.map((intervalo, indice) => (
            <tr key={intervalo}>
              <th scope="row">{intervalo}</th>
              {series.map((serie) => (
                <td key={serie.id}>
                  {serie.rotulo}: {serie.pontos.at(indice)?.valor ?? "sem dados"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
