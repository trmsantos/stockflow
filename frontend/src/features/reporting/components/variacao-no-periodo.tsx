import { BarrasPorPeriodo, type SerieDeBarras } from "@/components/barras-por-periodo";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDayMonth, formatMoneyRounded } from "@/lib/format";

import type { SeriesDoPeriodo } from "../schemas";
import { tintaDeSerie } from "../tinta-do-painel";
import { rotuloDaGranularidade, rotuloDeSerie } from "../vocabulario";

/**
 * "Como é que isto variou" — vendas e compras, intervalo a intervalo.
 *
 * O desenho é o `components/barras-por-periodo.tsx`, que já existe e não se
 * reescreve. Este componente é só a tradução do contrato para o que ele pede:
 * rótulos de intervalo, tintas por série, e o `share` de cada ponto convertido
 * para número.
 *
 * ## A única aritmética é `Number(share)`
 *
 * E é mandada pelo contrato: o `share` e o `scale_max_eur` vêm do servidor
 * precisamente para que a conta do desenho seja `share × píxeis` (ADR 0013,
 * decisão 5). Nenhum euro é somado, dividido ou comparado aqui — os valores dos
 * pontos viajam **já formatados por nós** para a tabela só-para-áudio que o
 * componente desenha ao lado do gráfico, e o máximo do eixo é o que o servidor
 * diz que é. Procurar o máximo no cliente era dividir euros em `number` dentro
 * de um sítio onde o erro é invisível, porque o resultado continua a ser uma
 * barra plausível.
 *
 * ## Duas séries, e o tecto é da paleta
 *
 * Vendas no acento, compras no neutro. A razão está no `tinta-do-painel.ts` e
 * no cabeçalho do componente de barras: num gráfico de dinheiro o verde e o
 * âmbar não estão livres, logo há duas tintas honestas. As outras duas linhas
 * da identidade (consumo e variação) ficam no bloco de números — e a variação
 * por uma segunda razão: **pode ser negativa**, e uma barra de altura negativa
 * não existe.
 *
 * ## Um intervalo não é um gráfico
 *
 * Com menos de dois intervalos — "hoje", ou um mês ao dia 6 com grão semanal —
 * o componente desenharia uma barra solitária com um eixo. Isso não compara
 * nada, e o número já está na régua acima. Mostra-se a frase em vez do desenho,
 * que é a mesma honestidade do estado vazio: dizer o que há em vez de desenhar
 * o que não há.
 */

export function VariacaoNoPeriodo({ series }: { readonly series: SeriesDoPeriodo }) {
  if (series.buckets.length < 2 || series.series.length === 0) {
    return (
      <p className="px-celula-x pb-3 text-sm text-muted-foreground">
        Um só intervalo neste período: não há variação para desenhar. Os totais estão em cima, e os
        outros períodos da barra do topo dão sete dias ou mais.
      </p>
    );
  }

  // O rótulo de um intervalo é a data do seu **início**, também quando o grão é
  // a semana: sete rótulos "29/09 → 05/10" não cabem em 120px, e o cabeçalho do
  // bloco já diz se se está a olhar para dias ou para semanas.
  const intervalos = series.buckets.map((intervalo) => formatDayMonth(intervalo.since));

  const paraDesenhar: SerieDeBarras[] = series.series.map((serie) => ({
    id: serie.id,
    rotulo: `${rotuloDeSerie(serie.id)} — ${formatMoneyRounded(serie.total_eur)} no total`,
    tinta: tintaDeSerie(serie.id),
    pontos: serie.points.map((ponto) => ({
      share: Number(ponto.share),
      valor: formatMoneyRounded(ponto.value_eur),
    })),
  }));

  return (
    <div className="pb-3">
      <BarrasPorPeriodo
        intervalos={intervalos}
        series={paraDesenhar}
        maximo={formatMoneyRounded(series.scale_max_eur)}
        rotulo={`Vendas e compras ${rotuloDaGranularidade(series.granularity)}, com o máximo do eixo em ${formatMoneyRounded(series.scale_max_eur)}`}
        // Lado a lado e não empilhadas: são **grandezas a comparar** e não
        // partes de um todo. Empilhar vendas sobre compras somava dinheiro que
        // entrou com dinheiro que saiu, que é a pior leitura possível deste
        // gráfico.
        empilhado={false}
      />
    </div>
  );
}

export function EsqueletoDaVariacao() {
  return (
    <div aria-busy="true" className="flex flex-col gap-2 px-celula-x pb-3">
      <span className="sr-only">A carregar o gráfico do período…</span>
      <Skeleton className="h-3 w-40" />
      {/* A mesma altura do gráfico (`h-40`), para o bloco não saltar quando os
          dados chegarem. */}
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-3 w-full" />
    </div>
  );
}
