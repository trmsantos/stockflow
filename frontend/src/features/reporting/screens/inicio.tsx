import { useProjeccaoDoPainel } from "../api";
import {
  CartaoDeContar,
  CartaoDeReceber,
  CartaoDeStock,
  CartaoDoPainel,
  CartaoDoQueExpira,
  CartaoDoQueFalta,
} from "../components/cartoes-do-inicio";
import { textos } from "../textos";

/**
 * O ecrã `/` — **a grelha de pré-visualizações**, e é a mesma para os três
 * papéis menos um cartão.
 *
 * ## O que este ecrã já foi, e porque mudou três vezes
 *
 * Foi uma lista de quatro perguntas com quatro links. A ADR 0013 fez dele o
 * painel de gestão. A 2026-10-06, de manhã, o dono do produto mandou o painel
 * para `/painel` (só do dono) e isto ficou uma **fila de trabalho**: oito linhas
 * com o número e a porta.
 *
 * Nessa mesma tarde viu-a num monitor largo e disse: *"o painel de inicio esta
 * horrivel, faz uns cards pequenos para colocar diferentes previews do que está
 * aqui, mas sem texto, apenas cards e previews"*. E o que ele viu explica a
 * frase: a ~2000px eram oito linhas finas encostadas ao topo e um deserto por
 * baixo — cada linha com 1744px de largura para um número à esquerda, uma frase
 * no meio e um rótulo colado à direita.
 *
 * **Uma lista não tem como usar a largura.** Cresce para baixo, e o que sobra à
 * direita fica vazio por construção; a 1280px isso não se nota porque não sobra
 * nada. A forma mudou por causa da largura do monitor, não por moda — e é por
 * isso que a grelha é o que é: `grid-cols-1`, duas colunas a partir de `sm`,
 * três a `xl`, quatro a `2xl`.
 *
 * ## "Sem texto" lido à letra, e o que isso obrigou
 *
 * Nenhum cartão tem uma frase a descrever o que ele mostra. O cabeçalho é o nome
 * do destino em microrótulo — o tratamento do `<th>` da tabela que vem lá dentro
 * — e o corpo são as **linhas a sério**: o nome do artigo, a frase da validade,
 * a quantidade contra o mínimo, o progresso por zona. É isso que separa isto do
 * anti-padrão do DESIGN.md §5 ("cards com ícone colorido em círculo + título +
 * duas linhas"), e a distância é curta o suficiente para valer a pena escrevê-la:
 * a diferença está em o conteúdo serem **dados** e não uma descrição deles. Sem
 * ícones, sem tinta por cartão, sem sombra colorida.
 *
 * ## As perguntas da manhã saíram, e não foi por falta de espaço
 *
 * Eram quatro linhas no fundo — "O que está a faltar ou a expirar? → Alertas" —
 * e sobreviveram a duas mudanças de direcção com dois argumentos escritos. Os
 * dois caíram com esta forma:
 *
 *  - *"a fila responde com números e esgota-se"*: as quatro perguntas levavam a
 *    Alertas, Stock, Receber e Contar, que é um **subconjunto** dos destinos dos
 *    seis cartões. Um cartão vazio continua a ser o cartão e continua a abrir o
 *    ecrã — "nada a expirar" com o cabeçalho ALERTAS por cima responde à
 *    pergunta e dá a porta na mesma linha;
 *  - *"é a única parte do Início que não depende de pedido nenhum"*: deixou de
 *    ser verdade que isso seja uma vantagem exclusiva. O cabeçalho de cada
 *    cartão é o `<Link>`, e desenha-se antes de o pedido sair e continua lá se
 *    ele falhar. Um cartão em erro é uma porta que funciona com um aviso dentro.
 *
 * Mantê-las era repetir seis destinos em quatro frases, debaixo de uma grelha
 * que o dono do produto pediu sem texto.
 *
 * ## O cartão do painel não se renderiza a quem não é dono
 *
 * A projecção vem da sessão que o `beforeLoad` da rota já leu (`accounts`), não
 * faz pedido nenhum, e decide se o componente **existe**. Como um hook não se
 * chama condicionalmente, é esta a única forma de o `GET /reporting/series` não
 * sair para quem ele vai recusar.
 *
 * Isto não é autorização. Quem recusa é o servidor — os três caminhos de
 * `reporting` são de `{owner}` — e o 403 continua a ser a autoridade; o cartão
 * mostra-o se ele chegar, porque pode chegar com a página aberta (ADR 0007).
 *
 * ## A fronteira entre features
 *
 * Este ecrã vive no `reporting` porque é o módulo-sumidouro da ADR 0013
 * (decisão 3): importa os `api` dos outros, não tem recursos próprios e não
 * escreve nada. Os cartões lêem `@/features/inventory/api` e
 * `@/features/purchasing/api`, que é a única porta aberta entre features (ADR
 * 0008, decisão 2) e a que o `eslint.config.js` verifica.
 */
export function EcraInicial() {
  const projeccao = useProjeccaoDoPainel();
  // `null` é "a sessão ainda não chegou" e não "não é dono": com um default o
  // cartão ou dispara um pedido que vai ser recusado, ou pisca a ausência a
  // quem tem acesso. Na prática é imediato — o `beforeLoad` da rota do shell já
  // leu a sessão antes de montar o invólucro.
  const dono = projeccao === "dono";

  return (
    // Sem `max-w`: a grelha usa a largura toda da área de conteúdo, como as
    // tabelas do Stock e dos Alertas (DESIGN.md §4). É precisamente o ponto
    // deste ecrã.
    <section className="flex w-full flex-col">
      <h1 className="sr-only">{textos.inicio.titulo}</h1>

      {/* A régua do topo, com o mesmo cromado dos outros ecrãs: um `<h2>` de
          15px e a linha de 1px por baixo. É a única frase do ecrã. */}
      <div className="border-b border-border px-celula-x py-3">
        <h2 className="text-sm font-semibold">{textos.inicio.oQueEstaAEspera}</h2>
      </div>

      {/* A grelha. Os `gap` e o `p` são os tokens de densidade (`gap-ritmo` são
          os 24px entre painéis do §2), não números soltos.

          Medido na área de conteúdo, que é o viewport menos a sidebar de 16rem:
          a **1280px** três colunas de 315px (área de 1024), a **1600px** quatro
          de 310px (área de 1344) e a **2000px** quatro de 410px (área de 1744).
          Abaixo de `sm` é uma coluna, que é o que um deep link aberto no
          telemóvel tem de dar.

          **A 1600px os cartões ficam 5px mais estreitos do que a 1280**, e isso
          é medido e não um descuido: o `2xl` do Tailwind é 1536px, logo a
          quarta coluna entra antes de haver largura para a pagar. A troca é
          deliberada — quatro cartões lado a lado poupam uma fila inteira de
          altura, e 310 contra 315px não muda uma truncagem sequer (verificado:
          a lista de elementos cortados é a mesma nas duas larguras). Quem
          quiser a quarta coluna só a partir de ~1620px precisa de um
          `--breakpoint-*` novo no `tokens.css`, que é uma decisão de sistema e
          não deste ecrã.

          `items-start`: cada cartão tem a altura do que tem para mostrar, e não
          a do mais alto da fila. Com o esticar por omissão, um Receber com um
          documento só ficava com 90px de vidraça vazia por baixo da sua única
          linha — e uma vidraça vazia dentro de uma borda lê-se como dados que
          faltaram, não como dados que não existem. Um cartão curto é um cartão
          com pouco; um cartão oco é um cartão avariado. */}
      <div className="grid grid-cols-1 items-start gap-ritmo p-celula-x sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {/* A ordem é a do trabalho, não a do menu: primeiro o que corre contra o
            tempo, depois o que chegou e o que está a ser contado, por fim o que
            há. É a mesma ordem de "o que está pior primeiro" das listas. */}
        <CartaoDoQueExpira />
        <CartaoDoQueFalta />
        <CartaoDeReceber />
        <CartaoDeContar />
        <CartaoDeStock />
        {dono ? <CartaoDoPainel /> : null}
      </div>
    </section>
  );
}
