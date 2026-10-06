import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatMoneyChange, formatMoneyRounded } from "@/lib/format";

import { eNegativo, type ComponenteDeCusto, type FechoDoMes } from "../schemas";
import { tintaDeCusto } from "../tinta-do-painel";
import {
  fraseDasExclusoes,
  notaDeCusto,
  rotuloDeCusto,
  rotuloDeOutroCusto,
} from "../vocabulario";

/**
 * Onde foi o dinheiro do mês, e o que **sobrou**.
 *
 * ## A palavra "lucro" não aparece, e o campo chama-se resultado
 *
 * É a decisão 6 da ADR 0013, e a razão é de confiança e não de linguagem: o
 * `result_eur` exclui amortizações, financiamento, IRC e — na Aurora, como em
 * quase toda a pastelaria — a remuneração do dono. Lido como "lucro", é cerca
 * do dobro do lucro real. O que fica de fora viaja no contrato
 * (`result_excludes`) e **imprime-se ao lado do número**, não num rodapé: é a
 * mesma bomba de confiança do stock-up, mais lenta.
 *
 * ## Quem decide o que soma é o servidor
 *
 * As linhas vêm do `costs`, e cada uma traz `is_part_of_total` e `part_of`. O
 * cliente **indenta** e escreve "dos quais"; não soma nada e não decide nada. É
 * o que substituiu o `waste_inside_goods_cost` booleano da primeira versão da
 * ADR, e a razão é que o booleano tinha a forma errada: sob consumo o
 * desperdício está dentro, sob compras não está dentro **e continua a não ser
 * somável** — porque o que se deitou fora em outubro pode ter sido comprado em
 * setembro. Um booleano não sabe dizer isso; dois campos sabem.
 *
 * ## A tinta do resultado só acende num mês fechado
 *
 * Um mês a correr ao dia 6 tem o pessoal e os custos fixos do mês **inteiro**
 * contra as vendas de seis dias: o resultado é negativo por construção e não
 * por desempenho. Pintá-lo de vermelho aí seria um alarme falso todos os meses,
 * do dia 1 ao dia 20 — e um alarme que se aprende a ignorar deixa de ser
 * alarme. Num mês fechado, o vermelho é um veredicto a sério, e a palavra ao
 * lado diz o mesmo que a cor (DESIGN.md §2).
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "rubrica", rotulo: "Rubrica", classe: "w-64" },
  { chave: "valor", rotulo: "Valor", classe: "w-40 text-right" },
  { chave: "nota", rotulo: "O que é" },
];

const LARGURA_MINIMA = "min-w-3xl";

function LinhaDeCusto({
  rubrica,
  valor,
  nota,
  dentroDeOutra = false,
  destacada = false,
  tinta = "",
}: {
  readonly rubrica: string;
  readonly valor: string;
  readonly nota: string;
  /** Uma decomposição: indenta e diz "dos quais". */
  readonly dentroDeOutra?: boolean;
  /** Os totais: um degrau de superfície acima, como o cabeçalho da tabela. */
  readonly destacada?: boolean;
  readonly tinta?: string;
}) {
  return (
    <tr className={`${CLASSE_LINHA} ${destacada ? "bg-surface-2" : ""}`}>
      <th
        scope="row"
        className={`${CLASSE_CELULA} w-64 text-left ${
          dentroDeOutra ? "pl-8 font-normal text-muted-foreground" : "font-medium"
        }`}
      >
        {dentroDeOutra ? "dos quais " : ""}
        {rubrica}
      </th>
      <td data-numeric className={`${CLASSE_CELULA} w-40 text-right ${tinta}`}>
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

function notaDaParcela(parcela: ComponenteDeCusto): string {
  const base = notaDeCusto(parcela.id);
  // "Não soma" tem de estar escrito na linha, e não deduzido da indentação: as
  // compras aparecem no meio de uma lista de custos e **não** entram no total.
  return parcela.is_part_of_total ? base : `não entra no total — ${base}`;
}

export function ResultadoDoMes({ mes }: { readonly mes: FechoDoMes }) {
  const exclusoes = fraseDasExclusoes(mes.result_excludes);
  const prejuizo = mes.closed && eNegativo(mes.result_eur);

  const barras: readonly BarraOrdenada[] = mes.costs
    // Só o que soma: um gráfico de repartição com uma parcela que não é parcela
    // mente sobre o todo. As outras continuam na tabela acima, com a frase.
    .filter((parcela) => parcela.is_part_of_total)
    .map((parcela) => ({
      chave: parcela.id,
      rotulo: rotuloDeCusto(parcela.id),
      // Leitura e não prova: o valor ao cêntimo está na tabela acima, e um
      // "15 505,72 €" não cabe na coluna de valor deste gráfico.
      valor: formatMoneyRounded(parcela.amount_eur),
      share: Number(parcela.share),
      // A tinta é um veredicto dentro de uma leitura mista: o vermelho é só
      // para as perdas, que **são** mesmo uma perda, e o resto fica no acento e
      // no neutro (ver `tinta-do-painel.ts`).
      tinta: tintaDeCusto(parcela.id),
    }));

  return (
    <div className="flex flex-col">
      <MolduraDeTabela
        colunas={COLUNAS}
        larguraMinima={LARGURA_MINIMA}
        rotulo="Vendas, gastos e resultado do mês"
      >
        <tbody>
          <LinhaDeCusto
            rubrica="Vendas, sem IVA"
            valor={formatMoney(mes.revenue_net_eur)}
            nota={`a base dos rácios; com IVA são ${formatMoney(mes.revenue_gross_eur)}`}
          />

          {mes.costs.map((parcela) => (
            <LinhaDeCusto
              key={parcela.id}
              rubrica={rotuloDeCusto(parcela.id)}
              valor={formatMoney(parcela.amount_eur)}
              nota={notaDaParcela(parcela)}
              dentroDeOutra={parcela.part_of !== null}
            />
          ))}

          <LinhaDeCusto
            rubrica="Total de gastos"
            valor={formatMoney(mes.cost_total_eur)}
            nota="mercadoria, perdas, pessoal e custos fixos — somado pelo servidor"
            destacada
          />
          <LinhaDeCusto
            rubrica="Resultado"
            valor={formatMoneyChange(mes.result_eur)}
            nota={
              mes.closed
                ? "vendas sem IVA menos o total de gastos"
                : "mês a correr: o pessoal e os custos fixos são do mês inteiro"
            }
            destacada
            tinta={prejuizo ? "text-danger" : ""}
          />
        </tbody>
      </MolduraDeTabela>

      {exclusoes === null ? null : (
        <p className="px-celula-x py-3 text-sm">
          <span className={prejuizo ? "text-danger" : "text-muted-foreground"}>
            {prejuizo ? "Resultado negativo neste mês. " : ""}
          </span>
          <span className="text-muted-foreground">
            {exclusoes} É o que sobra do que está nesta tabela, e só isso.
          </span>
        </p>
      )}

      {barras.length === 0 ? null : (
        <div className="flex flex-col gap-1 border-t border-border py-2">
          <p className="px-celula-x text-xs text-muted-foreground">
            Repartição dos gastos que somam ao total, do maior para o menor.
          </p>
          <BarrasOrdenadas
            barras={barras}
            campo="Gasto"
            rotuloDoValor="Valor"
            rotulo="Gastos do mês por categoria, do maior para o menor"
          />
        </div>
      )}

      {mes.other_costs.length === 0 ? null : (
        <div className="flex flex-col gap-1 border-t border-border pt-3">
          <p className="px-celula-x text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
            Custos fixos do mês
          </p>
          <MolduraDeTabela
            colunas={COLUNAS}
            larguraMinima={LARGURA_MINIMA}
            rotulo="Custos fixos do mês, por categoria"
          >
            <tbody>
              {mes.other_costs.map((custo) => (
                <LinhaDeCusto
                  key={custo.category}
                  rubrica={rotuloDeOutroCusto(custo.category)}
                  valor={formatMoney(custo.amount_eur)}
                  nota={custo.note ?? ""}
                />
              ))}
            </tbody>
          </MolduraDeTabela>
        </div>
      )}
    </div>
  );
}
