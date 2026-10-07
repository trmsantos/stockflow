import { casaCaminho, entradaDoRegisto, type EntradaDoRegisto } from "./registo-de-rotas";

/**
 * O menu — **dados**, e uma projecção por tenant sobre o registo de rotas
 * (ADR 0009).
 *
 * ## Desde 2026-10-06 a projecção vem do servidor, e isto deixou de ter uma
 *
 * Este ficheiro tinha um `PROJECCAO_EM_CODIGO`: um array com a forma da linha da
 * tabela da ADR 0011, enquanto essa tabela não existia. Existe
 * (`accounts_tenantmenuitem`), o menu viaja no `GET /auth/sessao` filtrado pelo
 * papel de quem pede, e o `ItemDeMenuOut` está no `types.ts`. A constante saiu —
 * um default em código ao lado de um default que o servidor serve são dois
 * defaults, e o de cá era o que ficava desactualizado.
 *
 * Os **defaults continuam a existir e continuam a ser código**, mas do outro
 * lado: `apps/accounts/menu.py`. Um estabelecimento sem nenhuma linha de
 * configuração recebe o menu completo pela ordem do registo (medido: seis itens,
 * `rotulo: null` em todos), porque "os defaults vivem em código e a linha nasce
 * na primeira escrita" (ADR 0011). As razões dos nomes dos grupos ("Equipa" e
 * não "Contas", porque é copy de produto e não o nome do módulo; o "Painel" como
 * sítio das perguntas da manhã) foram com eles e estão lá, citando este ficheiro
 * como origem — não se perderam na troca.
 *
 * Que a troca **não** é um redesenho foi medido item a item: o menu que o
 * servidor serve por omissão compõe exactamente os mesmos quatro grupos, pela
 * mesma ordem, com os mesmos rótulos, e a frase da gaveta continua a nomear
 * "Contar" e "Receber".
 *
 * ## A forma entra por propriedade, e o encaixe é verificado numa linha
 *
 * O shell **declara** a `EntradaDaProjeccao` e não importa o schema que a
 * valida: `src/shell/**` não conhece domínios (ADR 0008, decisão 2, imposta pelo
 * `eslint.config.js`). Quem satisfaz a interface é o `features/accounts`
 * (`useMenuDaSessao`, sobre o `itemDeMenuSchema`) e quem liga os dois é a rota
 * (`routes/involucro.tsx`) — a mesma inversão de dependência do
 * `sessao-do-shell.ts`, e o mesmo ponto único onde o `pnpm typecheck` confronta
 * os dois lados.
 *
 * Os nomes dos campos estão em `snake_case` porque são **contrato** (é a linha
 * que o servidor serve), pela mesma convenção que o `tenant_ativo` do
 * `features/accounts/schemas.ts`: "o campo é contrato, o tipo é nosso".
 *
 * ## Uma lista com um nível de agrupamento, nunca uma árvore
 *
 * ADR 0009, com estas palavras: "esconder e reordenar uma árvore é um problema
 * muito maior e 'cresce' não precisa dele". O grupo é uma **string** e não um id
 * de grupo: a configuração por empresa renomeia um grupo escrevendo outro nome,
 * e não há uma segunda tabela para manter em dia.
 */

export interface EntradaDaProjeccao {
  /**
   * O id da rota, como texto.
   *
   * **`string` e não `RotaId`**, e a razão está no `entradaDoRegisto`: isto é
   * texto que veio por HTTP, e a lista fechada é verificada onde ela está
   * escrita — no `Record<RotaId, EntradaDoRegisto>` do registo. Um id que este
   * bundle não conheça é ignorado por `montarMenu`, em vez de derrubar a
   * resposta da sessão e com ela o arranque da aplicação.
   */
  readonly route_id: string;
  /** O cabeçalho sob o qual o item aparece. Caixa alta é apresentação. */
  /** `null` = usa o grupo do registo. A mesma ausência que o `rotulo`. */
  readonly grupo: string | null;
  /** Ordena **dentro e entre** grupos: a ordem dos grupos é a do seu 1.º item. */
  readonly ordem: number;
  /** Esconder é apresentação, não autorização (ADR 0009): a rota continua lá. */
  readonly visivel: boolean;
  /**
   * Sobrepõe o rótulo do registo. `null` = o do registo.
   *
   * **`string | null` e não `rotulo?: string`**, e a diferença foi medida: o
   * contrato manda `rotulo: null` quando o tenant não sobrepôs nada (e não o
   * default já resolvido, para não prender o tenant a um default que nunca
   * escolheu), e com `exactOptionalPropertyTypes` — que está ligado no
   * `tsconfig.json` — um `null` não entra num campo declarado opcional. O `??`
   * do `montarMenu` serve os dois casos sem mudar.
   */
  readonly rotulo: string | null;
}

/**
 * Um item já resolvido: a projecção do tenant por cima do registo de código.
 *
 * O nome repete-se de propósito nas duas pontas, e as duas coisas são
 * diferentes: o `ItemDeMenu` do `features/accounts/schemas.ts` é a **linha de
 * configuração** que chega por HTTP (cinco campos, nenhum deles um caminho);
 * este é o que a sidebar renderiza, com o caminho, o ícone e a pergunta de
 * operação que só existem em código. O backend tem exactamente o mesmo par de
 * nomes, pela mesma razão.
 */
export interface ItemDeMenu extends EntradaDoRegisto {
  readonly id: string;
  /** `activeOptions.exact` — só a raiz, senão `/` ficava activa em tudo. */
  readonly exacto: boolean;
}

export interface GrupoDeMenu {
  readonly nome: string;
  readonly itens: readonly ItemDeMenu[];
}

/**
 * O menu que a sidebar (e a gaveta, que é a mesma) renderiza.
 *
 * Três coisas acontecem aqui e nenhuma é cosmética:
 *
 *  - **`visivel: false` desaparece do menu e não da aplicação.** O deep link
 *    continua a funcionar porque a árvore de rotas é código e não dados — é a
 *    razão número um da ADR 0009, e é o que impede "esconder" de se tornar um
 *    controlo de acesso falso e um marcador guardado num 404;
 *  - **um `route_id` que o registo não conhece é ignorado.** Era inalcançável
 *    enquanto a projecção era código; **deixou de ser** agora que ela chega por
 *    HTTP, e o dia em que acontece tem nome: o intervalo de um rolling deploy,
 *    com um backend novo a servir um sétimo id a um bundle antigo. Ignorar o
 *    item é o comportamento certo aí — uma entrada a mais no menu não é razão
 *    para o shell não montar —, e é a mesma escolha que o
 *    `selectors.projeccao_de_menu` do backend faz para o caso simétrico. É
 *    também a razão pela qual o `route_id` do contrato não é validado contra um
 *    `z.enum` à chegada: com um enum fechado em Zod, este ramo nunca corria
 *    porque a **sessão inteira** falhava antes;
 *  - **a ordem dos grupos é a do primeiro item de cada um**, e não uma segunda
 *    coluna de ordenação. Com `ordem` global, reordenar o menu é mexer num
 *    número só.
 */
export function montarMenu(projeccao: readonly EntradaDaProjeccao[]): readonly GrupoDeMenu[] {
  const grupos = new Map<string, ItemDeMenu[]>();

  for (const entrada of [...projeccao].sort((a, b) => a.ordem - b.ordem)) {
    if (!entrada.visivel) continue;
    const registo = entradaDoRegisto(entrada.route_id);
    if (registo === undefined) continue;

    // **`?? registo.grupo` desde 2026-10-07**, a par do `rotulo` e pela mesma
    // razão: o grupo é copy do produto, o contrato manda `null` quando a empresa
    // não sobrepôs nada, e resolvê-lo no servidor congelava-o na linha do tenant
    // no primeiro `PUT` (ADR 0019, decisão 5).
    const grupo = entrada.grupo ?? registo.grupo;
    const itens = grupos.get(grupo) ?? [];
    itens.push({
      ...registo,
      id: entrada.route_id,
      rotulo: entrada.rotulo ?? registo.rotulo,
      exacto: registo.caminho === "/",
    });
    grupos.set(grupo, itens);
  }

  return [...grupos].map(([nome, itens]) => ({ nome, itens }));
}

/**
 * Os rótulos das rotas **de campo** visíveis neste menu, pela ordem do menu.
 *
 * É aqui que o predicado `campo` do registo se paga na UI, e é de propósito que
 * se paga numa **frase** e não num filtro: a gaveta de mobile mostra o menu
 * inteiro (ADR 0009: "a mesma sidebar"), e o que o telemóvel precisa de saber é
 * qual daqueles ecrãs foi desenhado para ele — e, por consequência, que os
 * outros têm uma tabela que desliza na horizontal, o que o DESIGN.md §4 declara
 * em vez de tratar como defeito.
 *
 * A frase é **gerada** a partir do predicado e não escrita à mão: marcar uma
 * terceira rota como de campo muda o texto da gaveta sem ninguém se lembrar
 * dele.
 */
export function rotulosDeCampo(menu: readonly GrupoDeMenu[]): readonly string[] {
  return menu.flatMap((grupo) => grupo.itens.filter((item) => item.campo).map((i) => i.rotulo));
}

/**
 * Onde é que o URL actual está no menu — o item **e o grupo dele**.
 *
 * A barra de topo mostra os dois ("Inventário / Stock") porque num menu que
 * cresce o nome do ecrã sozinho deixa de situar: há quatro sítios onde pode
 * estar um ecrã chamado "Entradas". O grupo vem da **projecção do tenant**, logo
 * uma empresa que renomeie o grupo renomeia também o que a barra de topo diz,
 * sem uma segunda tabela de nomes. Medido com um `PUT /menu` a sério: com o
 * `stock` renomeado para "Armazém", o URL `/stock/<uuid>` passa a situar-se em
 * "Inventário / Armazém".
 *
 * Usa o mesmo casamento por prefixo do registo (`casaCaminho`), e por isso
 * `/stock/<uuid>` continua a situar-se em "Stock" — é nos ecrãs mais profundos
 * que o fio se perde mais depressa.
 */
export function localizarNoMenu(
  menu: readonly GrupoDeMenu[],
  caminho: string,
): { readonly grupo: string; readonly item: ItemDeMenu } | null {
  let melhor: { grupo: string; item: ItemDeMenu } | null = null;
  for (const grupo of menu) {
    for (const item of grupo.itens) {
      if (!casaCaminho(item.caminho, caminho)) continue;
      if (melhor === null || item.caminho.length > melhor.item.caminho.length) {
        melhor = { grupo: grupo.nome, item };
      }
    }
  }
  return melhor;
}
