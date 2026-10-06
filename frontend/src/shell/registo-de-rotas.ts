import type { AbsoluteToPath, RegisteredRouter } from "@tanstack/react-router";
import {
  Boxes,
  ClipboardCheck,
  House,
  MailPlus,
  TriangleAlert,
  Truck,
  type LucideIcon,
} from "lucide-react";

/**
 * O registo de rotas — **a lista fechada do que existe para navegar**, e a
 * garantia que substitui a dos "4 itens" da tab bar (ADR 0009).
 *
 * ## O que morreu aqui, e o que ficou no lugar
 *
 * Até 2026-10-01 este ficheiro era o `nav-items.ts`: um array único cujos itens
 * de mobile eram uma tupla de **quatro** verificada por um filtro ao nível do
 * tipo. A tab bar saiu (ADR 0009) e essa garantia saiu com ela. O que a ADR 0009
 * põe no lugar **não é a cardinalidade** — "ninguém conta ao compilar uma lista
 * que chega por HTTP, e um tenant pode configurar 1 ou 9 itens" —, é a
 * **integridade referencial do menu contra as rotas**, em dois sentidos:
 *
 *  1. **id → registo**: `Record<RotaId, EntradaDoRegisto>` é exaustivo nos dois
 *     sentidos sob `pnpm typecheck`. Um id no registo que a união não tem não
 *     compila (propriedade em excesso), e um id na união que o registo não tem
 *     também não (propriedade em falta). Hoje a união é declarada aqui; no dia
 *     em que o backend servir o menu (ADR 0011) ela passa a ser o enum gerado
 *     (`components["schemas"]["RotaIdEnum"]` do `lib/api/types.ts`) e o **mesmo**
 *     `Record` passa a ser verificado contra a lista do backend. Essa é a troca
 *     de uma linha que a ADR 0009 descreve, e é por isso que `RotaId` é um tipo
 *     e não um `typeof REGISTO`;
 *  2. **registo → rotas**: o `caminho` é do tipo `CaminhoDeRota`, que vem da
 *     **árvore de rotas real** (ver abaixo). Um caminho que não exista na árvore
 *     não compila — nem com um erro de dedo, nem depois de alguém apagar a rota.
 *
 * A **cardinalidade fica sem mecanismo**, e está escrito assim em vez de
 * disfarçado com um teste que mede outra coisa.
 *
 * ## `campo`: o predicado que a configuração por empresa não pode promover
 *
 * `campo: true` marca as rotas desenhadas para 360px — **Contar e Receber**, e
 * só elas (DESIGN.md §1 e §4). Vive em **código** e não na projecção por tenant
 * de propósito: a `EntradaDaProjeccao` (ver `menu.ts`) não tem este campo, logo
 * nenhuma configuração de empresa consegue promover uma rota de escritório para
 * o telemóvel. Não é uma convenção — é a forma do tipo que chega por HTTP.
 *
 * O que o predicado **não** faz é filtrar a gaveta de mobile. A ADR 0009 é
 * explícita noutro ponto ("**a mesma** sidebar como drawer a partir do header em
 * mobile") e as duas frases juntas só são consistentes de uma maneira: a gaveta
 * mostra o menu inteiro — duas listas divergem à primeira pergunta — e o
 * predicado paga-se onde é verdade, na frase que a gaveta mostra sobre o que ali
 * foi desenhado para o telemóvel. Está no relatório como contradição apontada.
 *
 * ## O que não está aqui: o papel — e continua a não estar
 *
 * A ADR 0011 diz que o menu é filtrado **pelo papel** contra o papel mínimo que
 * o registo declara — e esse registo é o **do backend**, porque esconder um item
 * que um `staff` não pode usar é autorização. Um `papelMinimo` aqui era uma
 * segunda definição de autorização no cliente, que é o erro que a ADR 0009
 * nomeia ("esconder é apresentação, não autorização").
 *
 * A 2026-10-06 entrou a primeira rota que **é** de um papel só — `/convites`, que
 * a ADR 0010 dá ao `owner` — e esta secção não mudou: o registo continua sem
 * saber o que é um papel. Quem esconde o item é a **projecção** (`menu.ts`, pelo
 * `visivel` que ela já tinha), e quem decide o que esconder é a camada que pode
 * ver os dois lados — a rota (`routes/involucro.tsx`), com o predicado a vir do
 * `features/accounts`, que é onde o domínio vive. O caminho é o mesmo por onde a
 * tabela da ADR 0011 vai entrar, e é por isso que não houve campo novo aqui.
 */

/**
 * Um caminho que a árvore de rotas tem de facto.
 *
 * Vem da augmentação global do router (`declare module "@tanstack/react-router"`
 * no `routes/router.tsx`), e é por isso que o shell consegue falar de caminhos
 * **sem importar `@/routes/*`** — que o `eslint.config.js` proíbe (ADR 0008,
 * decisão 2). É o mesmo mecanismo que já tipava o `to` do `<Link>`; a diferença
 * é que aqui ele passa a estar numa **declaração**, logo um caminho errado é
 * apanhado no registo e não só no sítio onde se renderiza.
 *
 * `AbsoluteToPath<_, "/">` e não `RoutePaths<...>`: o segundo é o nome óbvio e
 * **não é exportado** pelo `@tanstack/react-router` — vive no
 * `@tanstack/router-core`, que é dependência transitiva e não nossa (importá-lo
 * era declarar uma dependência que o `package.json` não tem). Com `TFrom = "/"`
 * os ramos relativos do `AbsoluteToPath` colapsam em `never` e o que fica é
 * exactamente a união dos caminhos absolutos da árvore. Medido com uma sonda:
 * um `caminho: "/stok"` no registo abaixo dá exit 1 no `pnpm typecheck`.
 */
export type CaminhoDeRota = AbsoluteToPath<RegisteredRouter, "/">;

/** Os ids de rota que o menu pode nomear. Hoje código, amanhã o enum gerado. */
export type RotaId = "inicio" | "stock" | "alertas" | "receber" | "contar" | "convites";

export interface EntradaDoRegisto {
  readonly caminho: CaminhoDeRota;
  /** O rótulo por omissão. A projecção por tenant pode sobrepô-lo (ADR 0011). */
  readonly rotulo: string;
  readonly icone: LucideIcon;
  /** A pergunta de operação que o ecrã responde (DESIGN.md §1). */
  readonly pergunta: string;
  /** Rota de campo: desenhada para 360px. Código, nunca configuração. */
  readonly campo: boolean;
}

export const REGISTO_DE_ROTAS: Record<RotaId, EntradaDoRegisto> = {
  inicio: {
    caminho: "/",
    rotulo: "Início",
    icone: House,
    pergunta: "Em que estado está a aplicação?",
    campo: false,
  },
  alertas: {
    caminho: "/alertas",
    rotulo: "Alertas",
    icone: TriangleAlert,
    pergunta: "O que expira? O que falta? Quanto deitei fora?",
    campo: false,
  },
  stock: {
    caminho: "/stock",
    rotulo: "Stock",
    icone: Boxes,
    pergunta: "O que é que eu tenho, e quanto?",
    campo: false,
  },
  contar: {
    caminho: "/contar",
    rotulo: "Contar",
    icone: ClipboardCheck,
    pergunta: "O que está na prateleira é o que o sistema diz?",
    campo: true,
  },
  receber: {
    caminho: "/receber",
    rotulo: "Receber",
    icone: Truck,
    pergunta: "O que chegou, e está certo?",
    campo: true,
  },
  convites: {
    caminho: "/convites",
    rotulo: "Convites",
    icone: MailPlus,
    pergunta: "Quem tem acesso, e quem está por entrar?",
    // **Não** é rota de campo, e isto não é uma omissão: o predicado marca as
    // rotas desenhadas para 360px, que são Contar e Receber e só elas (DESIGN.md
    // §1 e §4). Convidar é um acto de escritório — tem um formulário de três
    // campos e uma tabela de sete colunas, e é feito ao computador. A 360px
    // funciona (nenhuma rota é bloqueada em mobile) com a tabela a deslizar na
    // horizontal, que é o que o §4 declara em vez de tratar como defeito.
    campo: false,
  },
};

/**
 * O registo lido por id, num `Map`.
 *
 * O `Record` acima é a **garantia** (exaustivo nos dois sentidos); este `Map` é
 * por onde se **lê**, porque o `security/detect-object-injection` do
 * `eslint.config.js` recusa — e bem — um `OBJETO[chave]` com chave dinâmica, e
 * esta casa não suprime lint (CLAUDE.md). É o mesmo par que o
 * `NOME_DO_PAPEL`/`NOMES_DOS_PAPEIS` do `features/accounts/schemas.ts`.
 */
const REGISTO_POR_ID = new Map<string, EntradaDoRegisto>(Object.entries(REGISTO_DE_ROTAS));

export function entradaDoRegisto(id: RotaId): EntradaDoRegisto | undefined {
  return REGISTO_POR_ID.get(id);
}

/**
 * Este caminho de rota serve o caminho que está no URL?
 *
 * **Prefixo mais longo** e não igualdade: `/stock/<uuid>` é o detalhe de um
 * artigo e `/contar/fechar` é o fecho de uma contagem — nenhum dos dois está no
 * menu, e os dois pertencem visivelmente a um item que está. Com igualdade, a
 * barra de topo ficava sem rótulo exactamente nos ecrãs mais profundos, que são
 * aqueles em que é mais fácil perder o fio.
 *
 * A raiz (`/`) só casa por igualdade, senão era prefixo de tudo.
 */
export function casaCaminho(caminhoDaRota: string, caminhoActual: string): boolean {
  if (caminhoDaRota === "/") return caminhoActual === "/";
  return caminhoActual === caminhoDaRota || caminhoActual.startsWith(`${caminhoDaRota}/`);
}

/**
 * O rótulo do registo para este caminho, ou `null`.
 *
 * É a rede do `localizarNoMenu` (ver `menu.ts`): um item com `visivel: false`
 * não está no menu e a rota **continua a funcionar** por deep link (ADR 0009),
 * logo a barra de topo tem de conseguir nomeá-la mesmo assim. Esconder é
 * apresentação; o nome do ecrã não é.
 */
export function rotuloDoCaminho(caminho: string): string | null {
  let melhor: EntradaDoRegisto | null = null;
  for (const entrada of REGISTO_POR_ID.values()) {
    if (!casaCaminho(entrada.caminho, caminho)) continue;
    if (melhor === null || entrada.caminho.length > melhor.caminho.length) melhor = entrada;
  }
  return melhor?.rotulo ?? null;
}
