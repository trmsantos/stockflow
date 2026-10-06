import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatMoneyChange } from "@/lib/format";

import type { ResumoDoPeriodo } from "../schemas";
import { notaDaVariacaoDeStock, notaDeCusto, rotuloDoPeriodo } from "../vocabulario";

/**
 * **As quatro linhas, e a conta a fechar à vista.** É o bloco mais importante
 * do painel e a razão pela qual a ADR 0013 revogou o `cost_basis` que a sua
 * primeira versão propunha.
 *
 * O erro revogado não era de valor, era de **classificação**: "compras ou
 * consumo?" foi tratado como uma pergunta de uma resposta só, e é um "e". As
 * duas são verdadeiras e dizem coisas diferentes — compras é dinheiro que saiu,
 * consumo é o que saiu do stock —, e um interruptor sobre um "e" esconde a
 * informação mais útil das três: a diferença.
 *
 * ```
 * Vendas                    8 240 €
 * Compras a fornecedores    5 130 €   ← dinheiro que saiu
 * Mercadoria consumida      3 980 €   ← o que saiu do stock
 * Variação de stock        +1 150 €   ← encheu-se a despensa em 1 150 €
 * ```
 *
 * As três razões da ADR, e a primeira é a que decide o desenho deste bloco: **o
 * mês do stock-up natalício deixa de poder ser lido como prejuízo, porque
 * aparece nomeado**. O dono vê o seu próprio gesto em vez de um resultado
 * estranho. A segunda é que a identidade fica verificável no próprio ecrã, que
 * é a coisa mais próxima de uma prova que este produto consegue dar sobre
 * dinheiro. A terceira é que dois valores atrás de um parâmetro são duas
 * respostas para "quanto gastei?", e o primeiro bug reportado seria "o painel
 * diz 5 130 € num sítio e 3 980 € noutro".
 *
 * ## Três decisões de forma que são lições pagas
 *
 * **As anotações são uma coluna, não sub-linhas.** O `←` do bloco da ADR é a
 * terceira coluna desta tabela, porque uma sub-linha de 13px numa célula de
 * 44px cresce a linha e desfaz o ritmo (DESIGN.md §4, lição 3: foi medido nos
 * Alertas, com metade das linhas a 62px numa tabela de 44).
 *
 * **Os valores aparecem ao cêntimo**, e é a excepção à regra de arredondar ao
 * euro que o `formatMoneyRounded` documenta. Aqui o cêntimo não é precisão
 * falsa: é a **prova**. Com os três termos arredondados, `5 130 − 3 980 − 0`
 * podia dar `1 149` à vista de quem está a verificar a conta, e um ecrã onde a
 * identidade não fecha é pior do que um ecrã sem identidade nenhuma.
 *
 * **A variação não tem cor.** `+2 318,53 €` não é "bom" nem "mau" — é despensa
 * cheia, e é a palavra ao lado que o diz. A cor nesta identidade é sinal e não
 * ênfase (DESIGN.md §2), e pintar de verde uma variação positiva ensinava
 * exactamente a leitura errada: que comprar muito é um ganho.
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "rubrica", rotulo: "Rubrica", classe: "w-64" },
  { chave: "valor", rotulo: "Valor", classe: "w-40 text-right" },
  { chave: "nota", rotulo: "O que é" },
];

const LARGURA_MINIMA = "min-w-3xl";
const ROTULO = "O dinheiro e a mercadoria do período, com a variação de stock";

function Linha({
  rubrica,
  valor,
  nota,
}: {
  readonly rubrica: string;
  readonly valor: string;
  readonly nota: string;
}) {
  return (
    <tr className={CLASSE_LINHA}>
      <th scope="row" className={`${CLASSE_CELULA} w-64 text-left font-medium`}>
        {rubrica}
      </th>
      <td data-numeric className={`${CLASSE_CELULA} w-40 text-right`}>
        {valor}
      </td>
      <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
        <span className="block truncate" title={nota}>
          {nota}
        </span>
      </td>
    </tr>
  );
}

export function DinheiroDoPeriodo({ resumo }: { readonly resumo: ResumoDoPeriodo }) {
  const semConsumo = !resumo.data_quality.consumption_registered;

  return (
    <>
      <MolduraDeTabela colunas={COLUNAS} larguraMinima={LARGURA_MINIMA} rotulo={ROTULO}>
        <tbody>
          <Linha
            rubrica="Vendas, sem IVA"
            valor={formatMoney(resumo.revenue_net_eur)}
            nota={`a base dos rácios; com IVA são ${formatMoney(resumo.revenue_gross_eur)}`}
          />
          <Linha
            rubrica="Compras a fornecedores"
            valor={formatMoney(resumo.purchases_eur)}
            nota={notaDeCusto("purchases")}
          />
          {/* Sem consumo registado o número **não aparece**: um zero aqui lia-se
              como "não saiu mercadoria do stock", que é a afirmação mais cara
              que este ecrã pode fazer errada. O travessão é a ausência, e o que
              falta registar está no bloco de qualidade de dados. */}
          <Linha
            rubrica="Mercadoria consumida"
            valor={semConsumo ? "—" : formatMoney(resumo.goods_consumed_eur)}
            nota={
              semConsumo
                ? "sem consumo registado neste período — ver o que falta, em baixo"
                : notaDeCusto("goods_consumed")
            }
          />
          <Linha
            rubrica="Variação de stock"
            valor={formatMoneyChange(resumo.stock_change_eur)}
            nota={notaDaVariacaoDeStock(resumo.stock_change_eur)}
          />
        </tbody>
      </MolduraDeTabela>

      {/* A identidade, com os três termos e os números. Não é uma frase
          decorativa: é a afirmação que o servidor faz ao cêntimo
          (`stock_change == purchases − goods_consumed − unknown_shrinkage`) e
          que o ecrã mostra para poder ser contestada. O cliente não a calcula —
          imprime os quatro valores que recebeu, na ordem da conta. */}
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-celula-x py-3 text-xs text-muted-foreground">
        <span>
          A conta fecha: variação de stock = compras − mercadoria consumida − quebra desconhecida
          {` ${rotuloDoPeriodo(resumo.period.key)}`}.
        </span>
        <span data-numeric className="text-xs text-foreground">
          {formatMoneyChange(resumo.stock_change_eur)} = {formatMoney(resumo.purchases_eur)} −{" "}
          {formatMoney(resumo.goods_consumed_eur)} − {formatMoney(resumo.unknown_shrinkage_eur)}
        </span>
      </p>
    </>
  );
}

export function EsqueletoDoDinheiro() {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      rotulo="A carregar o dinheiro do período…"
      linhas={4}
    />
  );
}
