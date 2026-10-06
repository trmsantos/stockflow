import { TriangleAlert } from "lucide-react";

import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import {
  CLASSE_CONTADOR,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatMoneyRounded, formatPercentPoints } from "@/lib/format";

import type { FechoDoMes } from "../schemas";
import {
  avisoDoRacioDePessoal,
  notaDaBaseDosSalarios,
  notaDaOrigemDosSalarios,
  rotuloDaBaseDosSalarios,
  rotuloDaOrigemDosSalarios,
  rotuloDeParteDeSalarios,
} from "../vocabulario";

/**
 * O custo da equipa, e os três rácios que só existem aqui.
 *
 * ## Porque é que a decomposição não é um extra
 *
 * Um `payroll_eur` sozinho é ~32% acima do bruto que o dono tem na cabeça, e
 * nessa dist—ncia ele conclui que o painel está errado. A decomposição é o que
 * transforma desconfiança em verificação (ADR 0013, decisão 6): o bruto que ele
 * reconhece, mais a TSU, mais os duodécimos dos subsídios, mais a alimentação,
 * mais o seguro. Cada parcela tem nome e pode ser contestada uma a uma.
 *
 * Os subsídios entram **em duodécimos** independentemente de como são pagos:
 * senão junho e novembro parecem catástrofes e os outros dez meses parecem
 * bons — que é o mesmo argumento com que a ADR recusa ratear um salário por
 * sete dias.
 *
 * ## A decomposição é uma tabela e os cargos são barras, e a diferença é do contrato
 *
 * O `RoleCostOut` traz `share`; o `PayrollPartOut` traz `{id, amount_eur}` e
 * mais nada. Sem `share` não há barra: desenhá-la obrigava o cliente a dividir
 * euros para descobrir o comprimento, que é a regra da casa quebrada no sítio
 * onde o erro é invisível — o resultado continuaria a ser uma barra plausível.
 * Logo a decomposição é uma tabela densa (que é a forma certa para cinco
 * parcelas nomeadas) e os cargos são o gráfico. A assimetria do contrato está
 * apontada no relatório: a conta é do servidor, aqui como em todas as outras
 * listas.
 *
 * ## O cargo não é o papel, e um cargo de uma pessoa não anonimiza nada
 *
 * "Pasteleiro" é uma função; `owner|manager|staff` é o que o pedido pode fazer
 * (ADR 0013, decisão 2). O `headcount` aparece ao lado do custo por uma razão
 * que é de privacidade e não de informação: **um cargo com uma pessoa é o
 * salário dessa pessoa com outro nome**, e é por isso que este bloco inteiro é
 * do dono e o `/month` responde 403 a todos os outros.
 *
 * ## A frase ao lado do rácio de pessoal, que é a decisão mais consequente
 *
 * A remuneração do dono **não entra** nos custos: o que o dono tira é
 * distribuição de lucro e não despesa, e metê-la na mão-de-obra inflacionaria o
 * custo de pessoal em 4 a 5 pontos. A decisão está certa e tem um preço que
 * **tem** de ficar visível: este rácio não é comparável com os benchmarks do
 * sector que o dono encontra escritos. A frase vive ao lado do número e não
 * numa nota de pé de página, porque um número que engana sem mentir é pior do
 * que um número errado.
 */

const COLUNAS_DA_DECOMPOSICAO: readonly ColunaDeTabela[] = [
  { chave: "parcela", rotulo: "Parcela", classe: "w-64" },
  { chave: "valor", rotulo: "Valor", classe: "w-40 text-right" },
  { chave: "nota", rotulo: "Quem paga" },
];

/** Quem paga cada parcela, que é a pergunta que a decomposição responde. */
const QUEM_PAGA = "a empresa, por cima do bruto";

export function PessoalDoMes({ mes }: { readonly mes: FechoDoMes }) {
  const aviso = avisoDoRacioDePessoal(mes.result_excludes);

  const cargos: readonly BarraOrdenada[] = mes.roles.map((cargo) => ({
    chave: cargo.role_id,
    rotulo: `${cargo.name} · ${String(cargo.headcount)} ${cargo.headcount === 1 ? "pessoa" : "pessoas"}`,
    // Leitura e não prova, e medido: "2 880,12 €" partia em duas linhas na
    // coluna de valor do gráfico e crescia a linha acima dos 44px.
    valor: formatMoneyRounded(cargo.payroll_eur),
    share: Number(cargo.share),
  }));

  return (
    <div className="flex flex-col gap-3">
      <ReguaDeContadores>
        <div className={CLASSE_CONTADOR}>
          <CorpoDoContador
            campo="pessoal no mês"
            figura={formatMoneyRounded(mes.payroll_eur)}
            // A forma **curta** das duas palavras: a nota de um contador não é
            // uma frase, e com a frase inteira este campo cresceu para 660px e
            // pôs a régua a deslizar (medido — ver o `vocabulario.ts`). A frase
            // longa está na explicação da decomposição, em baixo.
            nota={`${rotuloDaBaseDosSalarios(mes.payroll_basis)} · ${rotuloDaOrigemDosSalarios(mes.payroll_source)}`}
          />
        </div>
        {mes.goods_cost_ratio_pct === null ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo="mercadoria"
              figura={formatPercentPoints(Number(mes.goods_cost_ratio_pct))}
              nota="do que se vendeu, sem IVA"
            />
          </div>
        )}
        {mes.labour_cost_ratio_pct === null ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo="pessoal"
              figura={formatPercentPoints(Number(mes.labour_cost_ratio_pct))}
              nota="sem a remuneração do dono"
            />
          </div>
        )}
        {mes.prime_cost_pct === null ? null : (
          <div className={CLASSE_CONTADOR}>
            <CorpoDoContador
              campo="mercadoria + pessoal"
              figura={formatPercentPoints(Number(mes.prime_cost_pct))}
              nota="sobre vendas sem IVA"
            />
          </div>
        )}
      </ReguaDeContadores>

      {aviso === null ? null : (
        // Ao lado do rácio e no fluxo, com o ícone como decoração e a frase a
        // carregar o sentido: a cor de estado é cor de **texto** (primeiro papel
        // do DESIGN.md §2) e nunca comunica sozinha.
        <p className="flex items-start gap-2 px-celula-x text-sm text-muted-foreground">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span className="text-pretty">{aviso}</span>
        </p>
      )}

      {cargos.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <p className="px-celula-x text-xs text-muted-foreground">
            Custo por cargo. O cargo é a função de quem trabalha, não o acesso que tem à aplicação.
          </p>
          <BarrasOrdenadas
            barras={cargos}
            campo="Cargo"
            rotuloDoValor="Custo"
            rotulo="Custo de pessoal por cargo, do maior para o menor"
          />
        </div>
      )}

      {mes.payroll_breakdown.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <p className="px-celula-x text-xs text-muted-foreground">
            De onde vem o custo-empresa — {notaDaBaseDosSalarios(mes.payroll_basis)},{" "}
            {notaDaOrigemDosSalarios(mes.payroll_source)}. Sem o IRS nem os 11% de Segurança Social
            do trabalhador: esses já estão dentro do bruto.
          </p>
          <MolduraDeTabela
            colunas={COLUNAS_DA_DECOMPOSICAO}
            larguraMinima="min-w-3xl"
            rotulo="Decomposição do custo de pessoal do mês"
          >
            <tbody>
              {mes.payroll_breakdown.map((parcela) => (
                <tr key={parcela.id} className={CLASSE_LINHA}>
                  <th scope="row" className={`${CLASSE_CELULA} w-64 text-left font-medium`}>
                    {rotuloDeParteDeSalarios(parcela.id)}
                  </th>
                  <td data-numeric className={`${CLASSE_CELULA} w-40 text-right`}>
                    {formatMoney(parcela.amount_eur)}
                  </td>
                  <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
                    <span className="block truncate">
                      {parcela.id === "base" ? "a equipa, no recibo" : QUEM_PAGA}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </MolduraDeTabela>
        </div>
      )}
    </div>
  );
}
