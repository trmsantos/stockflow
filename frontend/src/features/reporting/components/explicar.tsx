import { useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { textos } from "../textos";

/**
 * **A camada de explicação do painel** — o interruptor e a sub-linha que ele
 * revela.
 *
 * ## O que isto substituiu, e porquê
 *
 * As três tabelas do painel tinham uma terceira coluna, "O QUE É", com uma
 * frase por linha: "dinheiro que saiu para fornecedores", "o que saiu do stock,
 * ao custo gravado no movimento", "já está dentro da mercadoria consumida". Cada
 * frase defendia-se sozinha — eram elas que impediam a leitura errada que a ADR
 * 0013 passou a decisão 4 a evitar. Juntas, com as dos outros blocos, eram cerca
 * de **trinta frases** no mesmo ecrã, e o dono do produto leu o painel como um
 * manual de instruções: "demasiado content; uma pessoa olha e nota que é
 * confuso".
 *
 * A resposta não é apagá-las: é **pô-las por camadas**. Cada frase continua a
 * existir em dois sítios, e nenhum deles é um sítio novo de prosa:
 *
 *  - no `title` da célula a que pertence, que é o gesto que o resto da app já
 *    usa para o nome de artigo truncado (DESIGN.md §4);
 *  - como **sub-linha**, quando o `?explicar=1` está no URL.
 *
 * ## Porque é que o estado está no URL e não num `useState`
 *
 * Porque é partilhável, e um painel por camadas só serve se a camada aberta
 * sobreviver a um link e a um recarregamento (ADR 0008, decisão 1). "Olha esta
 * linha, liga o explicar" é um link. E não é `localStorage`: uma preferência
 * guardada no browser não viaja para a pessoa a quem se mostra o ecrã, que é
 * exactamente quem precisa das frases.
 *
 * Desligado por omissão: quem vê o painel pela primeira vez liga uma vez,
 * entende, e desliga para sempre.
 *
 * ## Um botão por bloco, um estado só
 *
 * O interruptor aparece no cabeçalho de cada bloco que tem notas, e os vários
 * botões mexem no **mesmo** parâmetro. É deliberado: um estado por bloco dava
 * cinco parâmetros no URL e cinco decisões a quem só quer entender o ecrã uma
 * vez. O que se ganha com o botão repetido é alcance — o interruptor está sempre
 * à mão do bloco que se está a ler, e não no topo da página.
 */

/**
 * O interruptor. Um `<button>` e não um `<Link>`: é um estado de apresentação
 * que se alterna, e o `aria-pressed` — que é o que diz "ligado" a quem ouve o
 * ecrã — só é válido em `role="button"`. O URL muda de qualquer maneira, logo a
 * partilha não se perde.
 */
export function BotaoDeExplicar({ ligado }: { readonly ligado: boolean }) {
  // `from: "/painel"` e o `to` explícito: sem eles o reducer de `search` era
  // aplicado à rota de onde o router acha que se vem, e o painel saiu de `/`
  // para `/painel` a 2026-10-06. Um `from` desactualizado não dá erro de tipo —
  // dá uma navegação para o Início ao premir "explicar".
  const navegar = useNavigate({ from: "/painel" });

  return (
    <Button
      type="button"
      // Dois dos cinco variantes do DESIGN.md §3 e nenhum componente novo: um
      // degrau de superfície acima quando está ligado, sem moldura quando não.
      // Quem diz o estado é o `aria-pressed` e a palavra, nunca a tinta.
      variant={ligado ? "secondary" : "ghost"}
      size="sm"
      aria-pressed={ligado}
      onClick={() => {
        void navegar({
          to: "/painel",
          search: (anteriores) => ({ ...anteriores, explicar: ligado ? undefined : 1 }),
          // `replace`: ligar e desligar a explicação não é um passo de
          // navegação, e sem isto o botão de voltar passava a desfazer
          // interruptores em vez de sair do ecrã. `resetScroll: false` porque
          // quem liga o interruptor está a ler um bloco a meio da página.
          replace: true,
          resetScroll: false,
        });
      }}
    >
      {ligado ? textos.rubricas.menos : textos.rubricas.explicar}
    </Button>
  );
}

/**
 * A sub-linha de uma nota, dentro de uma tabela.
 *
 * É uma `<tr>` própria e não uma segunda linha dentro da célula, e é uma lição
 * paga: uma sub-linha de 13px **dentro** de uma célula de 44px cresce a linha e
 * desfaz o ritmo da tabela (DESIGN.md §4, lição 3 — medido nos Alertas, com
 * metade das linhas a 62px numa tabela de 44). Numa linha própria, as linhas de
 * dados continuam todas com 44px e a camada de explicação é que acrescenta
 * altura, que é precisamente o que se está a pedir quando se liga o interruptor.
 *
 * A régua de baixo é desta linha e não da linha de dados acima: a nota e a sua
 * rubrica são **uma** unidade, e um fio de 1px entre as duas fazia-as ler-se
 * como duas rubricas.
 */
export function SubLinhaDeNota({
  colunas = 2,
  destacada = false,
  children,
}: {
  /** Quantas colunas atravessar. As tabelas do painel têm duas. */
  readonly colunas?: number;
  /**
   * A linha de cima é um total, logo está um degrau de superfície acima.
   *
   * Sem isto, medido na aba do pessoal com a camada ligada: a faixa do "Total
   * de gastos" acabava e a sua própria nota ficava no fundo normal, o que
   * partia em duas o que é uma unidade — e dava a impressão de haver uma linha
   * de dados entre os dois totais.
   */
  readonly destacada?: boolean;
  readonly children: ReactNode;
}) {
  return (
    <tr
      className={`border-b border-border last:border-b-0 ${destacada ? "bg-surface-2" : ""}`}
    >
      <td
        colSpan={colunas}
        // Indentado pelo mesmo degrau do "dos quais" da tabela do mês: lê-se
        // como pertencente à linha de cima, e não como uma linha nova.
        className="px-celula-x pb-2 pl-8 align-top text-xs leading-snug text-muted-foreground"
      >
        {children}
      </td>
    </tr>
  );
}
