import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import { MolduraDeTabela } from "@/components/tabela";
import { formatMoney, formatMoneyChange, formatMoneyRounded } from "@/lib/format";

import { COLUNAS_DE_RUBRICA, LARGURA_MINIMA_DE_RUBRICA } from "../colunas";
import { eNegativo, type ComponenteDeCusto, type FechoDoMes } from "../schemas";
import { textos } from "../textos";
import { tintaDeCusto } from "../tinta-do-painel";
import {
  ausenciaDe,
  fraseDasExclusoes,
  notaDaBaseDosSalarios,
  notaDaOrigemDosSalarios,
  notaDeCusto,
  rotuloDeCusto,
  rotuloDeOutroCusto,
  rotuloDeParteDeSalarios,
} from "../vocabulario";
import { LinhaDeAusencia, LinhaDeRubrica } from "./linha-de-rubrica";

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
 * ## Duas tabelas que deixaram de existir, e para onde foram
 *
 * Tinha por baixo duas tabelas inteiras: os **custos fixos** por categoria
 * (renda, energia, água, gás, TPA, licenças, contabilista) e a **decomposição do
 * custo-empresa** (bruto, TSU, subsídios, alimentação, seguro). 684px para
 * decompor **duas linhas** desta tabela, num painel que o dono do produto leu
 * como confuso por ter demasiado conteúdo.
 *
 * As duas são agora a **nota** da linha que decompõem — no `title` dela e na
 * sub-linha do `?explicar=1`. Não se perdeu valor nenhum: cada parcela continua
 * com o seu nome e o seu valor, na ordem em que o servidor as manda, e continua
 * a poder ser contestada uma a uma. O que se perdeu foi a moldura de uma tabela
 * à volta de sete linhas que ninguém lê todos os dias.
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

/** "Renda 850 € (Loja Centro e Cozinha); Energia 420 €; …" — a nota da linha. */
function decomposicaoDosCustosFixos(mes: FechoDoMes): string {
  return mes.other_costs
    .map((custo) => {
      const base = `${rotuloDeOutroCusto(custo.category)} ${formatMoney(custo.amount_eur)}`;
      return custo.note === null || custo.note === "" ? base : `${base} (${custo.note})`;
    })
    .join("; ");
}

/** "Bruto base 2 960,08 €; Segurança Social (TSU) 703,02 €; …" */
function decomposicaoDosSalarios(mes: FechoDoMes): string {
  return mes.payroll_breakdown
    .map((parcela) => `${rotuloDeParteDeSalarios(parcela.id)} ${formatMoney(parcela.amount_eur)}`)
    .join("; ");
}

/**
 * A nota de uma parcela: o que ela é, mais o que ela contém quando é um
 * agregado de linhas que já não têm tabela própria.
 *
 * "Não soma" tem de estar escrito na nota, e não deduzido da indentação: as
 * compras aparecem no meio de uma lista de custos e **não** entram no total.
 */
function notaDaParcela(parcela: ComponenteDeCusto, mes: FechoDoMes): string {
  const base = notaDeCusto(parcela.id);
  const partes: string[] = [
    parcela.is_part_of_total ? base : textos.resultado.naoEntraNoTotal(base),
  ];

  if (parcela.id === "other" && mes.other_costs.length > 0) {
    partes.push(decomposicaoDosCustosFixos(mes));
  }
  if (parcela.id === "payroll" && mes.payroll_basis !== null && mes.payroll_source !== null) {
    // As duas palavras longas do pessoal vivem aqui e não num contador: é a
    // nota que tem largura para elas (ver o `vocabulario.ts`, onde está medido
    // o que aconteceu quando a frase inteira foi para a régua).
    //
    // As duas vêm a `null` enquanto não houver salários (ADR 0029, decisão 1), e
    // aí não há nota a escrever: um "custo-empresa" ao lado de um número que não
    // existe descrevia a base de uma conta que ninguém fez.
    partes.push(
      `${notaDaBaseDosSalarios(mes.payroll_basis)}, ${notaDaOrigemDosSalarios(mes.payroll_source)}`,
    );
    if (mes.payroll_breakdown.length > 0) partes.push(decomposicaoDosSalarios(mes));
  }

  return partes.join(". ");
}

export function ResultadoDoMes({
  mes,
  explicar,
}: {
  readonly mes: FechoDoMes;
  readonly explicar: boolean;
}) {
  const exclusoes = fraseDasExclusoes(mes.result_excludes);
  const vendas = mes.revenue_net_eur;
  const vendasComIva = mes.revenue_gross_eur;
  const total = mes.cost_total_eur;
  const resultado = mes.result_eur;
  const declaradas = mes.data_quality.unavailable;
  // O vermelho do prejuízo só existe quando **há** resultado e o mês fechou: um
  // veredicto sobre um número que não existe é o alarme falso mais barato de
  // produzir.
  const prejuizo = mes.closed && resultado !== null && eNegativo(resultado);

  const barras: readonly BarraOrdenada[] = mes.costs
    // Só o que soma: um gráfico de repartição com uma parcela que não é parcela
    // mente sobre o todo. As outras continuam na tabela acima, com a nota.
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
        colunas={COLUNAS_DE_RUBRICA}
        larguraMinima={LARGURA_MINIMA_DE_RUBRICA}
        rotulo={textos.resultado.tabela}
      >
        <tbody>
          {vendas === null || vendasComIva === null ? (
            <LinhaDeAusencia
              frase={textos.falta.frase(
                textos.rubricas.vendasSemIva,
                ausenciaDe("revenue", declaradas),
              )}
            />
          ) : (
            <LinhaDeRubrica
              rubrica={textos.rubricas.vendasSemIva}
              valor={formatMoney(vendas)}
              nota={textos.rubricas.comIva(formatMoney(vendasComIva))}
              explicar={explicar}
            />
          )}

          {mes.costs.map((parcela) => (
            <LinhaDeRubrica
              key={parcela.id}
              rubrica={rotuloDeCusto(parcela.id)}
              valor={formatMoney(parcela.amount_eur)}
              nota={notaDaParcela(parcela, mes)}
              dentroDeOutra={parcela.part_of !== null}
              explicar={explicar}
            />
          ))}

          {/* **As rubricas que o servidor ainda não tem continuam na conta**, em
              palavras. O `costs` só traz as parcelas com fonte de dados; sem
              estas duas linhas o dono via uma tabela de gastos sem pessoal nem
              renda e não tinha como saber se isso era um negócio sem despesas ou
              um ecrã incompleto. */}
          {declaradas.includes("payroll") ? (
            <LinhaDeAusencia
              frase={textos.falta.frase(
                textos.custos.pessoalRotulo,
                ausenciaDe("payroll", declaradas),
              )}
            />
          ) : null}
          {declaradas.includes("other_costs") ? (
            <LinhaDeAusencia
              frase={textos.falta.frase(
                textos.custos.fixosRotulo,
                ausenciaDe("other_costs", declaradas),
              )}
            />
          ) : null}

          {total === null ? (
            <LinhaDeAusencia
              frase={textos.falta.frase(
                textos.rubricas.totalDeGastos,
                textos.resultado.dependeDoPessoal,
              )}
            />
          ) : (
            <LinhaDeRubrica
              rubrica={textos.rubricas.totalDeGastos}
              valor={formatMoney(total)}
              nota={textos.resultado.totalDeGastosNota}
              destacada
              explicar={explicar}
            />
          )}
          {resultado === null ? (
            <LinhaDeAusencia
              frase={textos.falta.frase(
                textos.rubricas.resultado,
                textos.resultado.semResultado,
              )}
            />
          ) : (
            <LinhaDeRubrica
              rubrica={textos.rubricas.resultado}
              valor={formatMoneyChange(resultado)}
              nota={mes.closed ? textos.resultado.notaFechado : textos.resultado.notaACorrer}
              destacada
              tinta={prejuizo ? "text-danger" : ""}
              explicar={explicar}
            />
          )}
        </tbody>
      </MolduraDeTabela>

      {/* O que fica de fora do resultado, **ao lado do número e em qualquer
          camada**: um resultado que não inclui amortizações nem a remuneração do
          dono, lido como se incluísse, é cerca do dobro do que é. */}
      {exclusoes === null ? null : (
        <p className="px-celula-x py-3 text-sm">
          <span className={prejuizo ? "text-danger" : "text-muted-foreground"}>
            {prejuizo ? textos.resultado.negativo : ""}
          </span>
          <span className="text-muted-foreground">
            {textos.resultado.comExclusoes(exclusoes)}
          </span>
        </p>
      )}

      {barras.length === 0 ? null : (
        <div className="flex flex-col gap-1 border-t border-border py-2">
          <p className="px-celula-x text-xs text-muted-foreground">
            {textos.resultado.notaDasBarras}
          </p>
          <BarrasOrdenadas
            barras={barras}
            campo={textos.resultado.campoGasto}
            rotuloDoValor={textos.grafico.valor}
            rotulo={textos.resultado.rotuloDasBarras}
          />
        </div>
      )}
    </div>
  );
}
