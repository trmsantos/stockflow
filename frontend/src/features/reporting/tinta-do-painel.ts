import type { IdDeCusto, IdDeSerie } from "./schemas";

/**
 * As tintas do painel — **três slots, e são todos os que esta paleta tem para
 * dinheiro**.
 *
 * O `components/barras-por-periodo.tsx` mediu o tecto e vale repeti-lo aqui,
 * porque é esta tabela que o aplica: a identidade tem **um** acento e três
 * cores de estado (DESIGN.md §2), e num gráfico de dinheiro as cores de estado
 * não estão livres. O verde diz "bom" e um custo não é bom; o âmbar diz
 * "aviso" e um salário não é um aviso. Sobram:
 *
 *  - `bg-primary` — o acento, para a mercadoria e para o dinheiro que entra;
 *  - `bg-danger` — o vermelho, **só para o que é mesmo uma perda**: o
 *    desperdício e a quebra desconhecida. É aqui que ele é sinal e não decoração;
 *  - `bg-border-strong` — o cinzento neutro, para o resto (compras, pessoal,
 *    custos fixos). Uma categoria de custo sem cor honesta agrupa-se em
 *    "outros"; não se lhe inventa uma tinta.
 *
 * **Dentro de uma repartição as parcelas não levam cores diferentes**, e isso é
 * um erro já cometido e documentado no `barras-ordenadas.tsx`: os cinco motivos
 * de desperdício pintados a vermelho, âmbar e ciano pareciam um semáforo num
 * gráfico cuja única pergunta é "qual é a maior parcela". A ordem já diz a
 * grandeza; cor a mais ali é ruído que finge ser sinal. Por isso o desperdício
 * por motivo usa o default do componente e não entra nesta tabela.
 *
 * Vive em módulo próprio e não no `vocabulario.ts` por duas razões: uma tinta
 * não é uma palavra, e é a mesma separação que o `inventory` já faz
 * (`tinta-do-estado.ts`). Os `Record` sobre as uniões fechadas falham nos dois
 * sentidos — um id de custo novo sem tinta não compila.
 */

const TINTA_DE_CUSTO: Record<IdDeCusto, string> = {
  purchases: "bg-border-strong",
  goods_consumed: "bg-primary",
  waste: "bg-danger",
  unknown_shrinkage: "bg-danger",
  payroll: "bg-border-strong",
  other: "bg-border-strong",
};

const TINTAS_DE_CUSTO = new Map<string, string>(Object.entries(TINTA_DE_CUSTO));

export function tintaDeCusto(id: IdDeCusto): string {
  return TINTAS_DE_CUSTO.get(id) ?? "bg-border-strong";
}

/**
 * As duas séries do gráfico de período: o que entrou no acento, o que saiu no
 * neutro. Duas e não quatro, pela razão do `idDeSerieSchema`.
 */
const TINTA_DE_SERIE: Record<IdDeSerie, string> = {
  revenue: "bg-primary",
  purchases: "bg-border-strong",
};

const TINTAS_DE_SERIE = new Map<string, string>(Object.entries(TINTA_DE_SERIE));

export function tintaDeSerie(id: IdDeSerie): string {
  return TINTAS_DE_SERIE.get(id) ?? "bg-border-strong";
}
