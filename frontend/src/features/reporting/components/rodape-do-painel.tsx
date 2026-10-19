import { formatDate, formatDayMonth, formatTime } from "@/lib/format";

import type { QualidadeDosDados } from "../schemas";
import { textos } from "../textos";

/**
 * **O rodapé honesto**: o que delimita todos os números que estão acima dele
 * (ADR 0029, respostas do dono).
 *
 * Não é letra miúda e não é um aviso legal. Cada uma destas frases responde a um
 * mal-entendido concreto que custa a confiança do ecrã inteiro, e os três são de
 * famílias diferentes:
 *
 *  - **"quanto comprei" tem duas leituras.** O contabilista soma o que as
 *    faturas dizem; este painel soma o que **entrou em stock**, ao custo gravado
 *    em cada movimento, pela data da receção. As duas são verdadeiras e dão
 *    números diferentes, e o dono escolheu a segunda porque é a que bate com o
 *    stock e com o desperdício. O primeiro bug reportado de um painel que não
 *    diga qual das duas está a mostrar é "o painel diz 8 250 € e a contabilidade
 *    diz outra coisa";
 *  - **o valor de stock é um saldo de agora**, não do fim do período escolhido.
 *    Com "últimos 7 dias" no seletor, um número de stock sem instante ao lado
 *    lê-se como o stock de há sete dias. Daí o `stock_value_as_of`, que viaja de
 *    propósito separado da fronteira da janela;
 *  - **a última contagem**, porque é ela que dá sentido à quebra desconhecida —
 *    "zero quebra não é boa notícia, é ausência de contagem" (ADR 0013, decisão
 *    7). Aparece no bloco do topo e nas perdas, e aqui fecha a leitura.
 *
 * A quarta é condicional e **fiscal**: em `isento_art_53` o IVA suportado nas
 * compras não se deduz, logo *é* custo — e estes euros, que são líquidos, ficam
 * abaixo do que a empresa pagou. Num regime normal a frase seria falsa, e por
 * isso não aparece. O regime chega como id (`vat_regime`) e a palavra é escrita
 * aqui, em cada língua: nenhum rótulo nosso viaja no arame.
 *
 * ## Porque é um `<ul>` e não um parágrafo
 *
 * São afirmações independentes sobre coisas diferentes, e quem procura uma delas
 * procura-a — um parágrafo de quatro frases obriga a ler as quatro. A régua de
 * 1px por cima é o mesmo cromado do resto do ecrã; não é um cartão e não tem
 * borda própria (DESIGN.md §3).
 */
export function RodapeDoPainel({
  qualidade,
  valorDeStockEm,
}: {
  readonly qualidade: QualidadeDosDados;
  /**
   * O `stock_value_as_of` da resposta que esta aba pediu, ou `null` enquanto ela
   * não chegou. `null` e não um default: a hora do cliente não é a do servidor,
   * e inventá-la era escrever um facto que ninguém afirmou.
   */
  readonly valorDeStockEm: string | null;
}) {
  const { last_count_at: ultimaContagem } = qualidade;

  return (
    <section
      aria-label={textos.rodape.rotulo}
      className="border-t border-border px-celula-x py-3"
    >
      <ul className="flex flex-col gap-1 text-xs leading-snug text-muted-foreground">
        {valorDeStockEm === null ? null : (
          <li>
            {textos.rodape.valorDeStock(
              formatDayMonth(valorDeStockEm),
              formatTime(valorDeStockEm),
            )}
          </li>
        )}
        <li>
          {ultimaContagem === null
            ? textos.rodape.nuncaSeContou
            : textos.rodape.ultimaContagem(formatDate(ultimaContagem))}
        </li>
        <li>{textos.rodape.baseDasCompras}</li>
        {qualidade.vat_regime === "isento_art_53" ? <li>{textos.rodape.semIva}</li> : null}
      </ul>
    </section>
  );
}
