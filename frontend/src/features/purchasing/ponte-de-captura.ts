/**
 * O endereço que o código QR transporta — **uma** função, e mais nada.
 *
 * ## O que a ponte é, em duas frases
 *
 * O computador abre um documento vazio (um *slot*) e desenha um código com o
 * endereço deste ecrã mais dois identificadores; o telemóvel lê o código, entra
 * **uma vez** e aterra no mesmo ecrã, já apontado àquele documento. É a decisão
 * 1 do corpo da ADR 0020, restaurada pela adenda 2: *"o QR transporta dois
 * identificadores e o que concede é a sessão do próprio telemóvel"*.
 *
 * ## Não há segredo nenhum aqui, e é por isso que este ficheiro é tão pequeno
 *
 * A adenda 1 dessa ADR desenhou a alternativa — um token ao portador de 32 bytes
 * no fragmento, com hash em coluna, relógio próprio e dois endpoints anónimos —
 * e a adenda 2 revogou-a por uma razão de facto: o *login com retorno* existe no
 * repositório (`routes/destino.ts`, `routes/entrar.tsx`) e o dono escolheu pagar
 * o login. Logo:
 *
 *  - **os dois valores são argumentos e não credenciais** (ADR 0007): o
 *    `estabelecimento` escolhe o âmbito que a sessão do telemóvel já tem de ter,
 *    e o `documento` é lido *dentro* desse âmbito, onde a política de RLS
 *    decide. Quem fotografar este código sem pertença recebe o ecrã de entrada e
 *    mais nada;
 *  - **vão em search params e não no fragmento**, o que é a inversão da adenda 1
 *    pela sua própria razão: o fragmento existe para um segredo não chegar ao
 *    servidor (ADR 0010), e pôr nele uma coisa que não é segredo sugeria ao
 *    próximo leitor que era. Em search params o retorno depois do login funciona
 *    sem uma linha nova — o `alvoDoRegresso` arrasta o fragmento **só** para o
 *    `/ativar`, e alargar essa lista era escrever duas linhas para um payload
 *    que não precisa delas;
 *  - **não há concatenação com um ponto.** A decisão 1 escrevia
 *    `<uuid-do-tenant>.<uuid-do-documento>` por herança do convite; sem segredo
 *    são dois campos com nome, validados por Zod no `busca-de-fotografar.ts`.
 *
 * ## Uma função, porque é isso que o gate 4 mede
 *
 * A adenda 2 exige que o endereço seja *"composto por **uma** função"* e que um
 * teste afirme que ele dá `/receber/fotografar` com **exactamente dois** search
 * params, os dois uuid, **sem fragmento** e sem terceiro campo. Esse teste é o
 * `scripts/check-ponte-de-captura.mjs`, que corre a cada `pnpm lint` e importa
 * **esta** função — não uma cópia dela. É também por isso que este módulo não
 * importa nada: um ficheiro com um `import` de `@/...` não é carregável pelo
 * Node sem um bundler, e um gate que mede uma reimplementação não mede nada.
 */

/**
 * O caminho da rota, escrito **uma vez**.
 *
 * É o mesmo caminho em que o computador já está, e isso é a decisão 7 da ADR
 * 0020: uma rota e não duas, sem ramificar por dispositivo (ADR 0008, decisão
 * 1). O telemóvel não vai a um ecrã diferente — vai a este, com o documento
 * preenchido.
 */
export const CAMINHO_DA_PONTE = "/receber/fotografar";

/** Os dois identificadores que viajam no código, e nada além deles. */
export interface AlvoDaPonte {
  /**
   * A origem da SPA (`location.origin`).
   *
   * Vem do cliente porque **o backend não conhece a origem** — é a decisão 1 do
   * contrato de convites da ADR 0010, e é a razão pela qual o código é desenhado
   * aqui e não servido como imagem.
   */
  readonly origem: string;
  /** O uuid do estabelecimento: argumento, para o telemóvel ficar no certo. */
  readonly estabelecimento: string;
  /** O uuid do documento aberto: o ponto de encontro. */
  readonly documento: string;
}

/**
 * `https://…/receber/fotografar?estabelecimento=<uuid>&documento=<uuid>`.
 *
 * `URL` e `URLSearchParams` em vez de interpolar a string à mão, por duas razões
 * que se conseguem medir: a primeira escapa os valores e normaliza a origem (um
 * `origem` com barra final não produz `//receber`), e a segunda garante que o
 * resultado **não tem fragmento** sem ninguém ter de se lembrar disso — o
 * `new URL(caminho, base)` descarta o fragmento da base, e aqui nunca se escreve
 * `hash`.
 */
export function urlDaPonte({ origem, estabelecimento, documento }: AlvoDaPonte): string {
  const alvo = new URL(CAMINHO_DA_PONTE, origem);
  alvo.search = new URLSearchParams([
    ["estabelecimento", estabelecimento],
    ["documento", documento],
  ]).toString();
  return alvo.toString();
}
