import { TriangleAlert } from "lucide-react";

import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import {
  CLASSE_CONTADOR,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { formatMoneyRounded, formatPercentPoints } from "@/lib/format";

import type { FechoDoMes } from "../schemas";
import { textos } from "../textos";
import { avisoDoRacioDePessoal } from "../vocabulario";

/**
 * Os números da aba **Pessoal**: os três rácios do mês, e o custo por cargo.
 *
 * ## Uma régua, e são os três rácios
 *
 * A régua desta aba tinha **quatro** campos — o custo de pessoal do mês mais os
 * três rácios — e o painel tinha três réguas ao todo. Passou a haver **uma
 * régua por aba** e, nesta, os campos são os três rácios que só existem aqui:
 * mercadoria, pessoal, e os dois somados. O custo de pessoal em euros não
 * desapareceu — é a linha "Pessoal" da tabela do resultado, ao cêntimo e ao lado
 * das outras rubricas, que é onde ele se compara com algo. Repeti-lo em cima era
 * dizer o mesmo número duas vezes no mesmo ecrã, que é metade da razão pela qual
 * o painel parecia confuso.
 *
 * Os rácios são **do servidor** e nenhum é calculado aqui: dividir euros em
 * `number` no cliente é a regra da casa quebrada no sítio onde o erro é
 * invisível, porque o resultado continua a ser uma percentagem plausível.
 *
 * ## A frase ao lado do rácio de pessoal, que é a decisão mais consequente
 *
 * A remuneração do dono **não entra** nos custos: o que o dono tira é
 * distribuição do que o negócio rende e não despesa, e metê-la na mão-de-obra
 * inflacionaria o custo de pessoal em 4 a 5 pontos. A decisão está certa e tem
 * um preço que **tem** de ficar visível: este rácio não é comparável com os
 * benchmarks do sector que o dono encontra escritos. A frase vive ao lado do
 * número e não numa nota de pé de página, porque um número que engana sem mentir
 * é pior do que um número errado.
 *
 * Encurtou a 2026-10-06, de quatro afirmações para duas — a que diz que não é
 * comparável e a que diz quanto. Não saiu, e não podia: é a única coisa no ecrã
 * que impede o dono de se comparar com um número que não mede o mesmo.
 *
 * ## O cargo não é o papel, e um cargo de uma pessoa não anonimiza nada
 *
 * "Pasteleiro" é uma função; `owner|manager|staff` é o que o pedido pode fazer
 * (ADR 0013, decisão 2). O `headcount` aparece ao lado do custo por uma razão
 * que é de privacidade e não de informação: **um cargo com uma pessoa é o
 * salário dessa pessoa com outro nome**, e é por isso que o painel inteiro é do
 * dono e os três caminhos de `reporting` respondem 403 a todos os outros.
 *
 * ## Porque é que os cargos são barras e a decomposição do salário não é
 *
 * O `RoleCostOut` traz `share`; o `PayrollPartOut` traz `{id, amount_eur}` e
 * mais nada. Sem `share` não há barra: desenhá-la obrigava o cliente a dividir
 * euros para descobrir o comprimento. A decomposição do custo-empresa era por
 * isso uma tabela densa, e desde 2026-10-06 é a **nota** da linha "Pessoal" da
 * tabela do resultado — cada parcela com o seu nome e o seu valor, sem a moldura
 * de uma tabela à volta de cinco linhas.
 */

/** A régua da aba: os três rácios, e só os que o servidor mandou. */
export function NumerosDoMes({ mes }: { readonly mes: FechoDoMes }) {
  const aviso = avisoDoRacioDePessoal(mes.result_excludes);

  return (
    <>
      <ReguaDeContadores>
        {/* O rácio de mercadoria **não se renderiza** sem consumo registado: sem
            ele o painel mostrava uma margem que não existe, e um painel
            optimista por omissão destrói a confiança mais depressa do que um
            prejuízo falso (ADR 0013, decisão 7). O `null` do contrato é a
            ausência; o que falta registar está no bloco de qualidade de dados,
            no topo do painel. */}
        {mes.goods_cost_ratio_pct === null || !mes.data_quality.consumption_registered ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo={textos.contadores.mercadoria}
              figura={formatPercentPoints(Number(mes.goods_cost_ratio_pct))}
              nota={textos.contadores.doQueSeVendeu}
            />
          </div>
        )}
        {mes.labour_cost_ratio_pct === null ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo={textos.contadores.pessoal}
              figura={formatPercentPoints(Number(mes.labour_cost_ratio_pct))}
              nota={textos.contadores.semRemuneracaoDoDono}
            />
          </div>
        )}
        {mes.prime_cost_pct === null ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo={textos.contadores.mercadoriaMaisPessoal}
              figura={formatPercentPoints(Number(mes.prime_cost_pct))}
              nota={textos.contadores.sobreVendasSemIva}
            />
          </div>
        )}
      </ReguaDeContadores>

      {aviso === null ? null : (
        // Ao lado do rácio e no fluxo, com o ícone como decoração e a frase a
        // carregar o sentido: a cor de estado é cor de **texto** (primeiro papel
        // do DESIGN.md §2) e nunca comunica sozinha.
        <p className="flex items-start gap-2 border-b border-border px-celula-x py-3 text-sm text-muted-foreground">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span className="text-pretty">{aviso}</span>
        </p>
      )}
    </>
  );
}

/** O custo por cargo, em barras. A ordem e a proporção são do servidor. */
export function CargosDoMes({ mes }: { readonly mes: FechoDoMes }) {
  const cargos: readonly BarraOrdenada[] = mes.roles.map((cargo) => ({
    chave: cargo.role_id,
    rotulo: textos.pessoal.rotuloDoCargo(cargo.name, cargo.headcount),
    // Leitura e não prova, e medido: "2 880,12 €" partia em duas linhas na
    // coluna de valor do gráfico e crescia a linha acima dos 44px.
    valor: formatMoneyRounded(cargo.payroll_eur),
    share: Number(cargo.share),
  }));

  if (cargos.length === 0) {
    return (
      <p className="px-celula-x pb-3 text-sm text-muted-foreground">
        {textos.pessoal.cargosVazio}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1 pb-2">
      <p className="px-celula-x text-xs text-muted-foreground">{textos.pessoal.cargoNaoEPapel}</p>
      <BarrasOrdenadas
        barras={cargos}
        campo={textos.pessoal.campoCargo}
        rotuloDoValor={textos.pessoal.custo}
        rotulo={textos.pessoal.rotuloDosCargos}
      />
    </div>
  );
}
