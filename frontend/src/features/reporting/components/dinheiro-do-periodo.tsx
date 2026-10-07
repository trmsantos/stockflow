import { EsqueletoDeTabela, MolduraDeTabela } from "@/components/tabela";
import { formatMoney, formatMoneyChange } from "@/lib/format";

import { COLUNAS_DE_RUBRICA, LARGURA_MINIMA_DE_RUBRICA } from "../colunas";
import type { ResumoDoPeriodo } from "../schemas";
import { textos } from "../textos";
import { notaDaVariacaoDeStock, notaDeCusto, rotuloDoPeriodo } from "../vocabulario";
import { LinhaDeRubrica } from "./linha-de-rubrica";

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
 * ## As anotações saíram da tabela e **não** saíram do ecrã
 *
 * O `←` do bloco acima era uma terceira coluna, "O QUE É". Era a maior massa de
 * texto do painel e saiu a 2026-10-06, para o `title` da rubrica e para a camada
 * do `?explicar=1` (`components/explicar.tsx`). A razão pela qual não voltou a
 * ser uma sub-linha dentro da célula é a mesma de sempre: uma sub-linha de 13px
 * numa célula de 44px cresce a linha e desfaz o ritmo (DESIGN.md §4, lição 3).
 * Quando a camada está ligada, a nota é uma **linha própria** por baixo.
 *
 * ## Duas decisões de forma que continuam a ser lições pagas
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

export function DinheiroDoPeriodo({
  resumo,
  explicar,
}: {
  readonly resumo: ResumoDoPeriodo;
  readonly explicar: boolean;
}) {
  const semConsumo = !resumo.data_quality.consumption_registered;

  return (
    <>
      <MolduraDeTabela
        colunas={COLUNAS_DE_RUBRICA}
        larguraMinima={LARGURA_MINIMA_DE_RUBRICA}
        rotulo={textos.dinheiro.tabela}
      >
        <tbody>
          <LinhaDeRubrica
            rubrica={textos.rubricas.vendasSemIva}
            valor={formatMoney(resumo.revenue_net_eur)}
            nota={textos.rubricas.comIva(formatMoney(resumo.revenue_gross_eur))}
            explicar={explicar}
          />
          <LinhaDeRubrica
            rubrica={textos.custos.comprasRotulo}
            valor={formatMoney(resumo.purchases_eur)}
            nota={notaDeCusto("purchases")}
            explicar={explicar}
          />
          {/* Sem consumo registado o número **não aparece**: um zero aqui lia-se
              como "não saiu mercadoria do stock", que é a afirmação mais cara
              que este ecrã pode fazer errada. O travessão é a ausência, e o que
              falta registar está no bloco de qualidade de dados — que aparece
              sempre, e é por isso que a ausência aqui não fica sem explicação
              quando o interruptor está desligado. */}
          <LinhaDeRubrica
            rubrica={textos.custos.consumoRotulo}
            valor={semConsumo ? "—" : formatMoney(resumo.goods_consumed_eur)}
            nota={semConsumo ? textos.dinheiro.semConsumo : notaDeCusto("goods_consumed")}
            tintaDaNota={semConsumo ? "text-warning" : ""}
            explicar={explicar}
          />
          <LinhaDeRubrica
            rubrica={textos.rubricas.variacaoDeStock}
            valor={formatMoneyChange(resumo.stock_change_eur)}
            nota={notaDaVariacaoDeStock(resumo.stock_change_eur)}
            explicar={explicar}
          />
        </tbody>
      </MolduraDeTabela>

      {/* A identidade, com os três termos e os números. **Fica à vista em
          qualquer camada**, e não é uma frase decorativa: é a afirmação que o
          servidor faz ao cêntimo
          (`stock_change == purchases − goods_consumed − unknown_shrinkage`) e
          que o ecrã mostra para poder ser contestada. O cliente não a calcula —
          imprime os quatro valores que recebeu, na ordem da conta. É a única
          prova que este painel dá, e é por isso que não entrou na camada de
          explicação com as outras frases. */}
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-celula-x py-3 text-xs text-muted-foreground">
        <span>{textos.dinheiro.aContaFecha(rotuloDoPeriodo(resumo.period.key))}</span>
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
      colunas={COLUNAS_DE_RUBRICA}
      larguraMinima={LARGURA_MINIMA_DE_RUBRICA}
      rotulo={textos.dinheiro.aCarregar}
      linhas={4}
    />
  );
}
