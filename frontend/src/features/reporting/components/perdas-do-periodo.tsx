import { BarrasOrdenadas, type BarraOrdenada } from "@/components/barras-ordenadas";
import { EsqueletoDeTabela, MolduraDeTabela } from "@/components/tabela";
import { formatMoney, formatMoneyRounded } from "@/lib/format";

import { COLUNAS_DE_RUBRICA, LARGURA_MINIMA_DE_RUBRICA } from "../colunas";
import { notaDaContagem } from "../contagem";
import type { ResumoDoPeriodo } from "../schemas";
import { notaDeCusto, rotuloDaQuebraDesconhecida, rotuloDeMotivo } from "../vocabulario";
import { LinhaDeRubrica } from "./linha-de-rubrica";

/**
 * **As perdas são duas linhas e não uma** (ADR 0013, decisão 7), e a segunda
 * nunca aparece sem a data da última contagem.
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
 * ## Zero quebra desconhecida não é boa notícia, e a data **não** entrou na camada
 *
 * É a regra que dá o seu valor a este bloco: um mês sem contar dá zero, e o mês
 * seguinte dá três meses de desvio de uma vez. Por isso o zero **nunca aparece
 * sozinho** — vem com a data da última contagem, e quando essa data é anterior
 * ao início do período a frase di-lo em palavras, não só na cor (DESIGN.md §2).
 *
 * Quando a coluna "O QUE É" saiu das tabelas, esta frase era a única que **não
 * podia** ir para a camada do `?explicar=1`: um `0,00 €` sem a data ao lado é a
 * afirmação optimista que a decisão 7 existe para proibir. Passou para a nota do
 * cabeçalho do bloco (`notaDaContagem`), que é onde o `BlocoDoPainel` guarda as
 * **condições** dos seus números — o mesmo sítio da fronteira ecoada. Fica à
 * vista em qualquer camada e ao lado das duas linhas que delimita.
 *
 * E quando o líquido é positivo a favor da casa, o rótulo passa a **"excedente
 * de contagem"** em vez de desperdício negativo: encontrou-se mais do que o
 * sistema dizia, que é outra conversa e não uma perda ao contrário.
 *
 * ## O desperdício por motivo fica em barras, e é a aba que o permite
 *
 * Num painel de 3630px com nove tabelas, estas barras eram 203px para decompor
 * um único valor da tabela acima, e estiveram a caminho da camada de explicação
 * com as notas. Ficaram à vista porque a aba as paga: nesta aba há **duas**
 * linhas de tabela e mais nada, e a decomposição por motivo é precisamente o que
 * responde a "o que é que eu deitei fora" — a terceira pergunta de operação do
 * DESIGN.md §1. O número de movimentos vai no rótulo de cada barra: "uma quebra
 * grande de uma vez é um acidente, dezoito pequenas são um processo".
 */

export function PerdasDoPeriodo({
  resumo,
  explicar,
}: {
  readonly resumo: ResumoDoPeriodo;
  readonly explicar: boolean;
}) {
  const contagem = notaDaContagem(resumo);

  const barras: readonly BarraOrdenada[] = resumo.waste_by_reason.map((linha) => ({
    chave: linha.reason,
    // O número de movimentos entra no rótulo e não numa coluna: "3 vezes" é
    // accionável de outra maneira que "18,40 €" — uma quebra grande de uma vez
    // é um acidente, dezoito pequenas são um processo.
    rotulo: `${rotuloDeMotivo(linha.reason)} · ${String(linha.movements)} ${linha.movements === 1 ? "movimento" : "movimentos"}`,
    // Arredondado ao euro, como todas as leituras da casa
    // (`formatMoneyRounded`): o valor exacto do desperdício está na tabela
    // acima, e numa coluna de 128px um "1 234,56 €" parte em duas linhas e
    // cresce a linha de 44px — medido.
    valor: formatMoneyRounded(linha.amount_eur),
    share: Number(linha.share),
  }));

  return (
    <>
      <MolduraDeTabela
        colunas={COLUNAS_DE_RUBRICA}
        larguraMinima={LARGURA_MINIMA_DE_RUBRICA}
        rotulo="As duas perdas do período: desperdício e quebra desconhecida"
      >
        <tbody>
          <LinhaDeRubrica
            rubrica="Desperdício"
            valor={formatMoney(resumo.waste_eur)}
            nota={notaDeCusto("waste")}
            explicar={explicar}
          />
          <LinhaDeRubrica
            rubrica={rotuloDaQuebraDesconhecida(resumo.unknown_shrinkage_eur)}
            valor={formatMoney(resumo.unknown_shrinkage_eur)}
            nota={`${notaDeCusto("unknown_shrinkage")} — ${contagem.texto}`}
            tintaDaNota={contagem.tinta}
            explicar={explicar}
          />
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

/** Pendente: a moldura e as duas linhas de 44px que vão lá estar. */
export function EsqueletoDasPerdas() {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS_DE_RUBRICA}
      larguraMinima={LARGURA_MINIMA_DE_RUBRICA}
      rotulo="A carregar as perdas do período…"
      linhas={2}
    />
  );
}
