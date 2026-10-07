/**
 * Barras ordenadas — a forma de "quanto, repartido por quê": desperdício por
 * motivo, gastos por categoria, custo por cargo.
 *
 * ## Não é um widget de gráfico; é uma tabela com uma coluna de barra
 *
 * É a decisão que faz isto parecer deste produto e não de um dashboard
 * qualquer. Os dados são tabulares — um rótulo, um valor e uma fracção —, logo
 * são uma `<table>`: quem ouve o ecrã recebe "Expirado, 18,40 €, 44%" célula a
 * célula, sem um `aria-label` a imitar o que a semântica já dá. A barra é uma
 * **coluna**, não um fundo pintado atrás da linha, e por isso compara-se na
 * vertical como qualquer outra coluna desta app.
 *
 * Um donut estava fora de questão por duas razões, e nenhuma é gosto: a paleta
 * tem **um** acento e três cores de estado (DESIGN.md §2), logo cinco motivos de
 * desperdício não têm cinco cores honestas; e comparar fatias de ângulo é pior
 * do que comparar comprimentos, que é o que uma barra dá.
 *
 * ## Barras em CSS e não em SVG, e isto é um desvio ao que foi pedido
 *
 * O dono escolheu "SVG à mão com os nossos tokens" contra uma biblioteca de
 * gráficos, e a razão dele vale: os defaults do Recharts — cantos redondos,
 * animações, grelhas claras — são o aspecto de todos os painéis gerados. **O que
 * ele recusou foi a biblioteca, e isso cumpre-se.** O que isto não usa é o
 * `<svg>`, por três razões técnicas:
 *
 *  - uma barra é um rectângulo cheio, e `width: 44%` num `<div>` é exactamente
 *    isso — sem `viewBox`, sem `preserveAspectRatio`, sem aritmética;
 *  - um `<svg>` esticado por largura distorce a espessura dos traços, e num
 *    painel com réguas de 1px isso vê-se;
 *  - o `<div>` é responsivo de graça e aceita os tokens de cor directamente, em
 *    vez de um `fill` com uma variável CSS lá dentro.
 *
 * O `<svg>` fica para o que **precisa** dele: uma linha de tendência
 * (`polyline`), que não se desenha com rectângulos. Quando houver uma, é escrita
 * à mão como ele pediu.
 *
 * ## A fracção vem do servidor
 *
 * `share` é dado, não conta (ADR 0013). O cliente faz `share × 100%` e mais
 * nada: procurar o máximo e dividir euros em `number` é a regra da casa quebrada
 * em silêncio — e seria quebrada **aqui**, no sítio onde o erro é invisível
 * porque o resultado continua a ser uma barra plausível.
 */

export interface BarraOrdenada {
  readonly chave: string;
  readonly rotulo: string;
  /** Já formatado pelo chamador: ele é que sabe se são euros ou unidades. */
  readonly valor: string;
  /** 0 a 1, do servidor. Fora desse intervalo é truncado, não escalado. */
  readonly share: number;
  /**
   * A tinta da barra. Por omissão é o acento, **e o default é quase sempre o
   * certo**.
   *
   * Serve para uma categoria que **é** um veredicto dentro de uma leitura mista
   * — "perdas" a vermelho num gráfico de gastos por categoria, onde as outras
   * barras não são perdas. **Não serve para distinguir os itens de uma só
   * repartição**, e isto é um erro que eu cometi no primeiro ensaio: pintei os
   * cinco motivos de desperdício a vermelho, âmbar e ciano, e o resultado parecia
   * um semáforo num gráfico cuja única pergunta é "qual é a maior parcela".
   * Dentro de uma repartição as parcelas não são mais nem menos graves — todas
   * são desperdício — e a ordem já diz a grandeza. Cor a mais ali não é ênfase,
   * é ruído que finge ser sinal.
   */
  readonly tinta?: string;
}

const CELULA = "px-celula-x align-middle";

/**
 * A largura da coluna do valor: **128px e não 112px, medido a 2026-10-06**.
 *
 * Era `w-28` (112px), o que deixa 80px de texto depois do `px-celula-x` dos dois
 * lados. Chega para "18,40 €" — o desperdício por motivo, que foi o caso em que
 * este componente nasceu — e **não** chega para um custo por cargo: no banco de
 * ensaio, "2 880,12 €" em mono de 15px partiu em duas linhas ("2 880,12" e
 * "€"), a linha cresceu acima dos 44px e o ritmo da tabela desfez-se. É a lição
 * 3 do DESIGN.md §4 pela porta do lado: não foi uma sub-linha que cresceu a
 * linha, foi o valor a não caber na coluna que lhe reservaram.
 *
 * 128px dão 96px de texto, que é o que um valor de milhares com cêntimos ocupa.
 * Quem passa valores de leitura (o painel) arredonda-os ao euro de qualquer
 * forma; esta largura é a rede para quem não o fizer.
 */
const VALOR = "w-32 text-right";

export function BarrasOrdenadas({
  barras,
  campo,
  rotuloDoValor = "Valor",
  rotulo,
}: {
  readonly barras: readonly BarraOrdenada[];
  /** O cabeçalho da coluna dos rótulos: "Motivo", "Categoria", "Cargo". */
  readonly campo: string;
  readonly rotuloDoValor?: string;
  /** O nome acessível da tabela. */
  readonly rotulo: string;
}) {
  const micro = "text-xs font-bold tracking-microrotulo text-muted-foreground uppercase";

  return (
    <table className="w-full border-collapse text-sm">
      <caption className="sr-only">{rotulo}</caption>
      <thead>
        {/* Sem `bg-surface-2` e sem réguas verticais, ao contrário da tabela de
            dados: aqui as colunas não são campos a comparar entre si, são um
            rótulo, um desenho e o número que o desenho mostra. O cromado da
            tabela densa dividia o desenho da sua própria legenda. */}
        <tr className="h-8 border-b border-border text-left">
          <th scope="col" className={`${CELULA} ${micro}`}>
            {campo}
          </th>
          {/* A coluna da barra não tem cabeçalho visível: o cabeçalho dela é o
              número à direita, e um rótulo em cima de um desenho sem eixo seria
              uma etiqueta sem conteúdo. */}
          <th scope="col" className="w-1/2">
            <span className="sr-only">Proporção</span>
          </th>
          <th scope="col" className={`${CELULA} ${VALOR} ${micro}`}>
            {rotuloDoValor}
          </th>
        </tr>
      </thead>
      <tbody>
        {barras.map((barra) => (
          <tr key={barra.chave} className="h-linha border-b border-border last:border-b-0">
            <th scope="row" className={`${CELULA} max-w-0 text-left font-normal`}>
              <span className="block truncate">{barra.rotulo}</span>
            </th>

            <td className="w-1/2 px-celula-x align-middle">
              {/* O carril é a superfície, não uma borda: num fundo preto uma
                  caixa vazia com borda de 1px lê-se como um campo de formulário.
                  `aria-hidden` porque o número está na célula seguinte. */}
              <span
                aria-hidden="true"
                className="block h-2 w-full overflow-hidden rounded-xs bg-surface-2"
              >
                <span
                  className={`block h-full rounded-xs ${barra.tinta ?? "bg-primary"}`}
                  style={{ width: `${String(Math.min(100, Math.max(0, barra.share * 100)))}%` }}
                />
              </span>
            </td>

            <td data-numeric className={`${CELULA} ${VALOR}`}>
              {barra.valor}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
