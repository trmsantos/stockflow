import { CLASSE_CELULA } from "@/components/tabela";

import { SubLinhaDeNota } from "./explicar";
import { textos } from "../textos";

/**
 * **Duas colunas: a rubrica e o valor.** É a linha das três tabelas de dinheiro
 * do painel — o dinheiro do período, as perdas e o resultado do mês.
 *
 * ## Porque é que são duas colunas e eram três
 *
 * A terceira chamava-se "O QUE É" e era a maior massa de texto do ecrã: cerca de
 * trinta frases num painel de 3630px de altura. Saiu a 2026-10-06, e não se
 * perdeu — cada frase está no `title` da rubrica a que pertence e aparece como
 * sub-linha com o `?explicar=1` (ver `components/explicar.tsx`). O que mudou foi
 * a camada, não o conteúdo. As colunas vivem no `colunas.ts` ao lado, porque um
 * ficheiro que exporta um componente e uma constante desliga o fast refresh.
 *
 * ## Porque é que é **um** componente e eram três
 *
 * Os três renderizadores de linha eram quase o mesmo ficheiro três vezes, com a
 * diferença de um `pl-8` e de um `bg-surface-2`. Duas tabelas com a mesma
 * intenção em dois sítios divergem na primeira correcção feita só numa delas — é
 * a razão que já tinha descido a moldura da tabela para `components/tabela.tsx`,
 * aplicada um degrau mais abaixo.
 *
 * ## O que não mudou
 *
 * Os valores aparecem **ao cêntimo** e alinhados à direita em mono, porque na
 * tabela do dinheiro o cêntimo não é precisão falsa: é a prova de que a
 * identidade `variação = compras − consumo − quebra` fecha. E **nenhum valor
 * leva cor por ser grande ou pequeno**: a cor nesta identidade é sinal e não
 * ênfase (DESIGN.md §2), logo só a tem quem a passa com uma palavra ao lado a
 * dizer o mesmo — hoje, o resultado negativo de um mês fechado.
 */

export function LinhaDeRubrica({
  rubrica,
  valor,
  nota,
  explicar,
  dentroDeOutra = false,
  destacada = false,
  tinta = "",
  tintaDaNota = "",
}: {
  readonly rubrica: string;
  readonly valor: string;
  /**
   * A frase da camada de explicação. Vai para o `title` da rubrica e para a
   * sub-linha; é uma `string` e não um `ReactNode` precisamente por causa do
   * `title`, que só aceita texto — e uma nota que não cabe num `title` é uma
   * nota que desaparece quando o interruptor está desligado.
   */
  readonly nota: string;
  readonly explicar: boolean;
  /** Uma decomposição: indenta e diz "dos quais". */
  readonly dentroDeOutra?: boolean;
  /** Os totais: um degrau de superfície acima, como o cabeçalho da tabela. */
  readonly destacada?: boolean;
  /** Cor do valor. Só com uma palavra ao lado a dizer o mesmo. */
  readonly tinta?: string;
  /** Cor da nota, quando ela é um aviso e não uma explicação. */
  readonly tintaDaNota?: string;
}) {
  const comNota = explicar && nota !== "";

  return (
    <>
      <tr
        // A régua de baixo passa para a sub-linha quando ela existe: a nota e a
        // sua rubrica são uma unidade. `h-linha` sempre — é o alvo de toque do
        // DESIGN.md §2 e o ritmo da tabela, e é por isso que a nota nunca entra
        // dentro desta célula.
        className={`h-linha ${comNota ? "" : "border-b border-border last:border-b-0"} ${
          destacada ? "bg-surface-2" : ""
        }`}
      >
        <th
          scope="row"
          // O `title` é a camada de explicação com o interruptor desligado. Não
          // substitui a sub-linha — complementa-a: um `title` não se lê por
          // áudio nem no telemóvel, e é por isso que o interruptor existe e está
          // no URL.
          title={nota === "" ? undefined : nota}
          className={`${CLASSE_CELULA} w-64 text-left ${
            dentroDeOutra ? "pl-8 font-normal text-muted-foreground" : "font-medium"
          }`}
        >
          {dentroDeOutra ? textos.rubricas.dosQuais : ""}
          {rubrica}
        </th>
        <td data-numeric className={`${CLASSE_CELULA} w-40 text-right ${tinta}`}>
          {valor}
        </td>
      </tr>

      {comNota ? (
        <SubLinhaDeNota destacada={destacada}>
          <span className={tintaDaNota}>{nota}</span>
        </SubLinhaDeNota>
      ) : null}
    </>
  );
}
