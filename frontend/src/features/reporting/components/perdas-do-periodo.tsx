import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatDate, formatMoney, formatMoneyRounded } from "@/lib/format";

import { eZero, type ResumoDoPeriodo } from "../schemas";
import {
  notaDeCusto,
  rotuloDaQuebraDesconhecida,
  rotuloDeMotivo,
} from "../vocabulario";

/**
 * **As perdas são duas linhas e não uma** (ADR 0013, decisão 7), e a segunda
 * nunca aparece sem a data da última contagem ao lado.
 *
 *  - **Desperdício** são os movimentos `waste`: têm motivo, autor e hora, e são
 *    accionáveis sobre um artigo e sobre uma pessoa. Está **dentro** da
 *    mercadoria consumida (ADR 0014) — é decomposição e não parcela a somar;
 *  - **Quebra desconhecida** é o líquido dos `adjustment` de contagem, e é
 *    accionável sobre o **processo**: ninguém viu aquilo sair.
 *
 * Juntá-las num agregado "Perdas" perdia a única coisa que as distingue, que é
 * o que se faz a seguir. Se um agregado existir um dia, é somado pelo servidor.
 *
 * ## Zero quebra desconhecida não é boa notícia
 *
 * É a regra que dá o seu valor a este bloco: um mês sem contar dá zero, e o mês
 * seguinte dá três meses de desvio de uma vez. Por isso o zero **nunca aparece
 * sozinho** — vem com a data da última contagem, e quando essa data é anterior
 * ao início do período a frase di-lo em palavras, não só na cor (DESIGN.md §2).
 *
 * E quando o líquido é positivo a favor da casa, o rótulo passa a **"excedente
 * de contagem"** em vez de desperdício negativo: encontrou-se mais do que o
 * sistema dizia, que é outra conversa e não uma perda ao contrário.
 */

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "perda", rotulo: "Perda", classe: "w-64" },
  { chave: "valor", rotulo: "Valor", classe: "w-40 text-right" },
  { chave: "nota", rotulo: "O que isso quer dizer" },
];

const LARGURA_MINIMA = "min-w-3xl";

/**
 * A contagem aconteceu **dentro** desta janela?
 *
 * Comparação de dois instantes que o servidor mandou, não uma conta: é a
 * diferença entre "contou-se e não havia desvio" (zero é boa notícia) e
 * "ninguém contou" (zero é ausência). As duas chegam ao ecrã como o mesmo
 * `0,00 €`, e é esta linha que as separa.
 */
function contouNestePeriodo(ultimaContagem: string | null, desde: string): boolean {
  if (ultimaContagem === null) return false;
  return new Date(ultimaContagem).getTime() >= new Date(desde).getTime();
}

function notaDaQuebra(resumo: ResumoDoPeriodo): { readonly texto: string; readonly tinta: string } {
  const { last_count_at: ultima } = resumo.data_quality;
  const contou = contouNestePeriodo(ultima, resumo.period.since);
  const zero = eZero(resumo.unknown_shrinkage_eur);

  if (ultima === null) {
    return {
      texto: "nunca se contou: este zero é ausência de contagem, não ausência de quebra",
      tinta: "text-warning",
    };
  }
  if (zero && !contou) {
    return {
      texto: `sem contagem neste período — a última foi a ${formatDate(ultima)}, e o desvio aparece todo na próxima`,
      tinta: "text-warning",
    };
  }
  return {
    texto: `${notaDeCusto("unknown_shrinkage")} — última contagem a ${formatDate(ultima)}`,
    tinta: "",
  };
}

export function PerdasDoPeriodo({ resumo }: { readonly resumo: ResumoDoPeriodo }) {
  const quebra = notaDaQuebra(resumo);

  const barras: readonly BarraOrdenada[] = resumo.waste_by_reason.map((linha) => ({
    chave: linha.reason,
    // O número de movimentos entra no rótulo e não numa coluna: "3 vezes" é
    // accionável de outra maneira que "18,40 €" — uma quebra grande de uma vez
    // é um acidente, dezoito pequenas são um processo. Numa coluna própria
    // seria uma quarta coluna num gráfico de três.
    rotulo: `${rotuloDeMotivo(linha.reason)} · ${String(linha.movements)} ${linha.movements === 1 ? "movimento" : "movimentos"}`,
    // Arredondado ao euro, como todas as leituras da casa
    // (`formatMoneyRounded`): o valor exacto do desperdício está na tabela
    // acima, e numa coluna de 128px um "1 234,56 €" parte em duas linhas e
    // cresce a linha de 44px — medido.
    valor: formatMoneyRounded(linha.amount_eur),
    share: Number(linha.share),
  }));

  return (
    <>
      <MolduraDeTabela
        colunas={COLUNAS}
        larguraMinima={LARGURA_MINIMA}
        rotulo="As duas perdas do período: desperdício e quebra desconhecida"
      >
        <tbody>
          <tr className={CLASSE_LINHA}>
            <th scope="row" className={`${CLASSE_CELULA} w-64 text-left font-medium`}>
              Desperdício
            </th>
            <td data-numeric className={`${CLASSE_CELULA} w-40 text-right`}>
              {formatMoney(resumo.waste_eur)}
            </td>
            <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
              <span className="block truncate" title={notaDeCusto("waste")}>
                {notaDeCusto("waste")}
              </span>
            </td>
          </tr>
          <tr className={CLASSE_LINHA}>
            <th scope="row" className={`${CLASSE_CELULA} w-64 text-left font-medium`}>
              {rotuloDaQuebraDesconhecida(resumo.unknown_shrinkage_eur)}
            </th>
            <td data-numeric className={`${CLASSE_CELULA} w-40 text-right`}>
              {formatMoney(resumo.unknown_shrinkage_eur)}
            </td>
            {/* A tinta é de **texto** (primeiro papel do §2) e a palavra diz o
                mesmo que ela: "sem contagem neste período". Nunca só a cor. */}
            <td className={`${CLASSE_CELULA} max-w-0 ${quebra.tinta || "text-muted-foreground"}`}>
              <span className="block truncate" title={quebra.texto}>
                {quebra.texto}
              </span>
            </td>
          </tr>
        </tbody>
      </MolduraDeTabela>

      {barras.length === 0 ? (
        <p className="px-celula-x py-3 text-sm text-muted-foreground">
          Nada deitado fora neste período. O desperdício aparece aqui por motivo, do maior para o
          menor, à medida que for registado.
        </p>
      ) : (
        <div className="flex flex-col gap-1 py-2">
          <p className="px-celula-x text-xs text-muted-foreground">
            Desperdício por motivo, {formatMoneyRounded(resumo.waste_eur)} no total — a ordem é a
            grandeza.
          </p>
          <BarrasOrdenadas
            barras={barras}
            campo="Motivo"
            rotuloDoValor="Valor"
            rotulo="Desperdício por motivo, do maior para o menor"
          />
        </div>
      )}
    </>
  );
}
