import type { AbsoluteToPath, RegisteredRouter } from "@tanstack/react-router";
import {
  Boxes,
  ChartNoAxesColumn,
  ClipboardCheck,
  House,
  TriangleAlert,
  Truck,
  type LucideIcon,
} from "lucide-react";

import type { components } from "@/lib/api/types";
import { textos } from "./textos";

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
 *     também não (propriedade em falta). **Desde 2026-10-06 a união é o enum
 *     gerado** (`components["schemas"]["RotaIdEnum"]`, do `types.ts` que o
 *     `pnpm gen:api` escreve), logo este `Record` é verificado contra a lista
 *     fechada **do backend** — que é quem valida o `route_id` que a projecção
 *     guarda (ADR 0011) — e não contra uma união que o frontend escreveu sozinho.
 *     Era a troca de uma linha que a ADR 0009 descreve, e é por isso que `RotaId`
 *     é um tipo e não um `typeof REGISTO`.
 *
 *     **Medido nas três direcções, e revertido:** um `RotaId` com um sétimo id
 *     (a simular o enum do backend a crescer) dá `TS2741: Property
 *     'configuracao' is missing` no `REGISTO_DE_ROTAS`; uma entrada a mais no
 *     registo dá `TS2353: Object literal may only specify known properties`; e
 *     um `RotaId = "stok"` dá `TS2820`, com os ids gerados listados na
 *     mensagem — que é o que prova que esta união não é `string` nem um `any`
 *     vindo de um import que resolveu para o lado errado;
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
 * o telemóvel. Não é uma convenção — é a forma do tipo que chega por HTTP, e
 * desde que o menu vem do servidor isso deixou de ser uma afirmação sobre um
 * tipo nosso: o `ItemDeMenuOut` do contrato **também** não tem `campo`, nem o
 * `ItemDeMenuInRequest` que o `PUT /menu` aceita. Medido: as linhas que o
 * `GET /auth/sessao` devolve têm cinco campos, e `campo` não é um deles.
 *
 * O preço está nomeado do outro lado: o predicado existe **duas vezes** (aqui e
 * no `apps/accounts/menu.py`) e nada falha se divergirem. É a dívida que o
 * backend já declarou no seu relatório, e não é desta tarefa — o que a UI usa é
 * esta cópia, porque é ela que gera a frase da gaveta.
 *
 * O que o predicado **não** faz é filtrar a gaveta de mobile. A ADR 0009 é
 * explícita noutro ponto ("**a mesma** sidebar como drawer a partir do header em
 * mobile") e as duas frases juntas só são consistentes de uma maneira: a gaveta
 * mostra o menu inteiro — duas listas divergem à primeira pergunta — e o
 * predicado paga-se onde é verdade, na frase que a gaveta mostra sobre o que ali
 * foi desenhado para o telemóvel. Está no relatório como contradição apontada.
 *
 * ## O que não está aqui: o papel — e agora não está em sítio nenhum do cliente
 *
 * A ADR 0011 diz que o menu é filtrado **pelo papel**, e que quem o filtra é o
 * servidor: esconder um item que um `staff` não pode usar é autorização e não
 * preferência. Um `papelMinimo` aqui era uma segunda definição de autorização no
 * cliente, que é o erro que a ADR 0009 nomeia ("esconder é apresentação, não
 * autorização").
 *
 * Entre a manhã e a tarde de 2026-10-06 o cliente teve, por necessidade, um
 * filtro próprio: o menu era uma constante de módulo e a primeira rota de um
 * papel só (`/convites`, do `owner` pela ADR 0010) tinha de ser escondida em
 * algum sítio. **Esse filtro saiu** quando o menu passou a vir do
 * `GET /auth/sessao` — o servidor já não manda a linha a quem não é `owner` — e
 * dois filtros a fazer o mesmo são um a ficar desactualizado.
 *
 * O exemplo de 2026-10-06 era o `convites`, e ele já não está aqui: saiu do
 * registo a 2026-10-07 quando virou secção das Definições (ADR 0019, decisão 7).
 * A propriedade medida é a mesma e a rota restrita que sobra é o `painel`: um
 * `owner` recebe **seis** itens e um `staff` do mesmo estabelecimento recebe
 * **cinco**.
 *
 * E a correcção de 2026-10-06 da ADR 0011 vale ser lida aqui: o que o registo do
 * backend declara é `papeis_permitidos`, um **conjunto** por rota, e não um
 * `papel_minimo` — não existe ordem entre papéis neste projeto, e inventá-la era
 * responder à Q7 sem ninguém ter perguntado.
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

/**
 * Os ids de rota que o menu pode nomear — **o enum fechado do backend**.
 *
 * Não é uma união escrita à mão que por acaso coincide: é o `RotaIdEnum` do
 * `types.ts`, que o `pnpm gen:api` gera do `schema.yaml`, que o drf-spectacular
 * gera do `RotaDeMenu` do Django. O caminho inteiro que a ADR 0009 descreve, com
 * o gate de diff do CI (`ARCHITECTURE.md` §5) a garantir que o ficheiro gerado e
 * commitado não divergiu da API.
 *
 * É também o primeiro consumidor do `types.ts` em código de aplicação — até aqui
 * ele era um artefacto que o CI comparava e ninguém importava. O shell pode
 * importá-lo: a fronteira do `eslint.config.js` proíbe-lhe `@/features/*` e
 * `@/routes/*`, e `@/lib/*` é o `apps/shared` do frontend, que é para ser usado
 * de cima para baixo.
 */
export type RotaId = components["schemas"]["RotaIdEnum"];

export interface EntradaDoRegisto {
  readonly caminho: CaminhoDeRota;
  /** O rótulo por omissão. A projecção por tenant pode sobrepô-lo (ADR 0011). */
  readonly rotulo: string;
  /**
   * O grupo por omissão, e **vive aqui desde 2026-10-07** (ADR 0019, decisão 5).
   *
   * Vinha do servidor, resolvido e obrigatório — e como o `PUT /menu` é
   * substituição total, a primeira gravação congelava "Inventário" na linha do
   * tenant e nenhuma tradução a voltava a alcançar. Medido na base de dados.
   *
   * É copy do produto, como o `rotulo`: o contrato manda `null` quando a empresa
   * não sobrepôs nada e quem resolve é o `montarMenu`. O que a empresa escreveu
   * é texto **dela**, numa língua só, e nunca se traduz.
   *
   * A **ordem dos grupos** continua a ser a do primeiro item de cada um, que
   * agora é a ordem deste ficheiro cruzada com a `ordem` da projecção — não há
   * uma segunda lista a manter.
   */
  readonly grupo: string;
  readonly icone: LucideIcon;
  /** A pergunta de operação que o ecrã responde (DESIGN.md §1). */
  readonly pergunta: string;
  /** Rota de campo: desenhada para 360px. Código, nunca configuração. */
  readonly campo: boolean;
}

export const REGISTO_DE_ROTAS: Record<RotaId, EntradaDoRegisto> = {
  inicio: {
    caminho: "/",
    rotulo: textos.rotas.inicio.rotulo,
    grupo: textos.grupos.painel,
    icone: House,
    pergunta: textos.rotas.inicio.pergunta,
    campo: false,
  },
  painel: {
    caminho: "/painel",
    rotulo: textos.rotas.painel.rotulo,
    grupo: textos.grupos.painel,
    icone: ChartNoAxesColumn,
    pergunta: textos.rotas.painel.pergunta,
    // **Não** é rota de campo: é o ecrã mais denso da aplicação — três abas,
    // tabelas de dinheiro e dois gráficos — e lê-se ao computador. A 360px
    // funciona, com as tabelas a deslizar na horizontal, que é o que o
    // DESIGN.md §4 declara em vez de tratar como defeito.
    //
    // O papel **não** está aqui, e é a regra do ficheiro: quem filtra o menu
    // pelo papel é o servidor (ADR 0011). Esta linha é só o que a rota é.
    campo: false,
  },
  alertas: {
    caminho: "/alertas",
    rotulo: textos.rotas.alertas.rotulo,
    grupo: textos.grupos.painel,
    icone: TriangleAlert,
    pergunta: textos.rotas.alertas.pergunta,
    campo: false,
  },
  stock: {
    caminho: "/stock",
    rotulo: textos.rotas.stock.rotulo,
    grupo: textos.grupos.inventario,
    icone: Boxes,
    pergunta: textos.rotas.stock.pergunta,
    campo: false,
  },
  contar: {
    caminho: "/contar",
    rotulo: textos.rotas.contar.rotulo,
    grupo: textos.grupos.inventario,
    icone: ClipboardCheck,
    pergunta: textos.rotas.contar.pergunta,
    campo: true,
  },
  receber: {
    caminho: "/receber",
    rotulo: textos.rotas.receber.rotulo,
    grupo: textos.grupos.compras,
    icone: Truck,
    pergunta: textos.rotas.receber.pergunta,
    campo: true,
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

/**
 * A entrada deste id, ou `undefined` se o registo não o conhecer.
 *
 * **`string` e não `RotaId`**, e isso é a forma certa desde que o menu chega por
 * HTTP: o `route_id` de uma linha da projecção é texto que veio do servidor, e
 * exigir aqui o tipo fechado obrigava alguém a afirmar, com um cast ou com um
 * `z.enum`, que ele é um dos sete — uma afirmação que um backend mais novo torna
 * falsa no intervalo de um rolling deploy. O `undefined` é a resposta honesta
 * nesse caso, e quem chama (`montarMenu`) ignora a linha.
 *
 * A garantia dos dois sentidos **não** está nesta assinatura e não precisa de
 * estar: está no `Record<RotaId, EntradaDoRegisto>` acima, que é o único sítio
 * do frontend onde os sete ids são escritos — do outro lado são o `RotaDeMenu`
 * do Django, e é exactamente contra essa lista que o `Record` é verificado.
 */
export function entradaDoRegisto(id: string): EntradaDoRegisto | undefined {
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
