import { useMemo } from "react";
import { encode } from "uqr";

/**
 * O código QR, desenhado por nós a partir da **matriz**.
 *
 * ## Porque é que isto é um SVG escrito à mão e não uma imagem da biblioteca
 *
 * O `uqr` foi escolhido por duas propriedades, e a segunda é a que decide esta
 * forma: **zero dependências** (o `qrcode` arrasta 58, com um CLI e o `yargs` lá
 * dentro) e **devolve a matriz, não um PNG**. Uma biblioteca que devolvesse
 * imagem traria as cores dela lá dentro — valores literais que nenhum gate deste
 * repositório consegue ler —, e o `renderSVG` que o `uqr` também tem escreve
 * `white`/`black` por omissão. Com a matriz, a geometria é dela e o desenho é
 * nosso.
 *
 * ## A placa é branca nas três paletas, e isso **não** é um descuido do tema
 *
 * É a única superfície do produto que não segue a paleta, e a razão é de óptica e
 * não de estilo: um leitor de código precisa de contraste entre módulos escuros e
 * fundo claro, e a paleta não tem voto nisto. Um código ciano sobre o preto frio
 * da Cabine, ou escuro sobre o grafite do meio termo, **não lê** — e um código
 * que não lê é a feature inteira a não existir. A alternativa seria inverter a
 * polaridade nas paletas escuras; muitos descodificadores tentam a inversão, mas
 * a norma é escuro sobre claro e a câmara nativa de um telemóvel de cozinha é
 * precisamente o leitor que não se escolhe.
 *
 * As duas cores são **literais em `oklch`**, e a razão é a mesma que está escrita
 * no `public/favicon.svg` sobre o azulejo dele: há sítios onde a cor não pode
 * seguir o tema, e nesses escreve-se o valor com a razão ao lado em vez de se
 * inventar um token que mente. Não é um `bg-[#fff]` — não é hex, não é um valor
 * arbitrário de Tailwind, e está em `oklch` como tudo no `tokens.css`, que é
 * onde `oklch(1 0 0)` já aparece (a primeira camada do `--shadow-sm`). A tinta é
 * o valor exacto do `--color-background` da paleta escura: o preto mais frio que
 * este produto tem, e o mesmo que o favicon usa de azulejo.
 *
 * **O que isto custa, dito por inteiro:** na paleta clara a placa é branca sobre
 * um cinzento quase branco, logo é a borda de componente que a delimita e não a
 * própria tinta. É por isso que quem usa este componente lhe põe
 * `border-border-strong` em volta, e não o separador decorativo.
 *
 * ## O que podia estragar a matriz, e o que o impede
 *
 *  - **arredondamento.** O `viewBox` é a matriz em unidades de módulo e todas as
 *    coordenadas são inteiras; a escala para pixéis é do browser, num só sítio.
 *    Nenhum `Math.round` nosso toca num módulo;
 *  - **margem a menos.** A zona de silêncio é de **quatro** módulos
 *    (`border: 4`), que é o que a norma pede, e vive **dentro** do SVG em vez de
 *    ser um `padding` CSS — um `padding` da cor do painel punha preto frio onde
 *    tem de haver branco, e o leitor perde o enquadramento;
 *  - **costuras entre módulos.** Os módulos escuros de cada linha são fundidos
 *    em corridas horizontais num `<path>` só, e o `shape-rendering="crispEdges"`
 *    desliga a suavização: sem ele, a 4px por módulo, cada fronteira ganha um
 *    pixel cinzento e o que o descodificador vê deixa de ser binário.
 *
 * ## A alternativa textual não é o endereço
 *
 * `role="img"` com um rótulo que diz **o que isto é**, porque ler um URL de 160
 * caracteres em voz alta não serve a ninguém. Quem não pode apontar uma câmara
 * precisa do endereço **copiável**, e isso é trabalho do bloco que compõe este
 * componente — não de um `aria-label`.
 */
export function CodigoDeCaptura({
  url,
  rotulo,
  className,
}: {
  /** O endereço, composto pelo `urlDaPonte`. */
  readonly url: string;
  /** A alternativa textual: o que o código é, não o que ele diz. */
  readonly rotulo: string;
  readonly className?: string;
}) {
  // A matriz é pura: a mesma string dá a mesma, e redesenhá-la a cada sondagem
  // de 2 s era recalcular Reed-Solomon dez vezes por minuto para nada.
  const { size, data } = useMemo(
    () =>
      encode(url, {
        // Quatro módulos de zona de silêncio, como a norma pede. O default do
        // `uqr` é **um**, que é o que torna um código bonito num ecrã e difícil
        // de enquadrar com uma câmara.
        border: 4,
        // `M` e não o `L` por omissão: 15% de recuperação paga o pó no ecrã, o
        // reflexo da luz da copa e o dedo em cima do monitor. Com este payload a
        // versão sobe um degrau e mais nada — o código continua a caber na
        // coluna sem perder resolução por módulo.
        ecc: "M",
      }),
    [url],
  );

  return (
    <svg
      role="img"
      aria-label={rotulo}
      viewBox={`0 0 ${String(size)} ${String(size)}`}
      shapeRendering="crispEdges"
      className={className}
    >
      {/* A placa, incluindo a zona de silêncio: é um rectângulo só e cobre o
          `viewBox` inteiro. */}
      <rect width={size} height={size} fill="oklch(1 0 0)" />
      <path d={corridasEscuras(data)} fill="oklch(0.145 0.008 240)" />
    </svg>
  );
}

/**
 * Os módulos escuros, em corridas horizontais, como um `d` de `<path>`.
 *
 * Um `<rect>` por módulo dariam ~1300 nós no DOM para um código deste tamanho, e
 * cada fronteira entre dois rectângulos vizinhos é uma costura a mais para o
 * rasterizador. Um `<path>` só, com uma corrida por sequência de módulos
 * escuros, dá ~400 subcaminhos e nenhuma fronteira interna.
 *
 * **`.entries()` e não `matriz[y][x]`**, e não é estilo: o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * acesso indexado por variável, e esta casa não suprime lint (CLAUDE.md). A
 * corrida acumula-se num ciclo em vez de se olhar para o módulo seguinte, que é
 * o que torna isso possível sem um índice.
 */
function corridasEscuras(matriz: readonly (readonly boolean[])[]): string {
  const partes: string[] = [];

  for (const [y, linha] of matriz.entries()) {
    let inicio: number | null = null;

    for (const [x, escuro] of linha.entries()) {
      if (escuro) {
        inicio ??= x;
        continue;
      }
      if (inicio !== null) {
        partes.push(corrida(inicio, y, x - inicio));
        inicio = null;
      }
    }

    // A corrida que chega ao fim da linha. Não acontece num código válido — a
    // última coluna é zona de silêncio —, e está aqui porque a alternativa é a
    // última coluna desaparecer no dia em que alguém mudar o `border` para 0.
    if (inicio !== null) partes.push(corrida(inicio, y, linha.length - inicio));
  }

  return partes.join("");
}

/** Um rectângulo de 1 módulo de altura e `largura` módulos, em coordenadas inteiras. */
function corrida(x: number, y: number, largura: number): string {
  const l = String(largura);
  return `M${String(x)} ${String(y)}h${l}v1h-${l}z`;
}
