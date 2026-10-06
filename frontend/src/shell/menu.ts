import {
  casaCaminho,
  entradaDoRegisto,
  type EntradaDoRegisto,
  type RotaId,
} from "./registo-de-rotas";

/**
 * O menu — **dados**, e uma projecção por tenant sobre o registo de rotas
 * (ADR 0009).
 *
 * ## Porque é que isto é um array em código e ainda assim não é "o menu em
 * código"
 *
 * A tabela `accounts_tenantmenuitem` da ADR 0011 não existe: é backend que
 * ainda não foi escrito, e o `menu` do `SessaoOut` viaja vazio e **sem forma de
 * item declarada** (ADR 0010). Logo a projecção de hoje é o
 * `PROJECCAO_EM_CODIGO` abaixo — mas tem a **forma** da linha da tabela
 * (`route_id`, `grupo`, `ordem`, `visivel`, `rotulo`), e quem a consome é uma
 * função que recebe a projecção por argumento. Trocar a fonte é trocar o
 * argumento de `montarMenu(...)` numa linha do `sidebar-nav.tsx`, sem reescrever
 * o shell — que é exactamente o que a ADR 0009 pede.
 *
 * Os nomes dos campos estão em `snake_case` porque são **contrato** (é a linha
 * que o servidor vai servir), pela mesma convenção que o `tenant_ativo` do
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
  readonly route_id: RotaId;
  /** O cabeçalho sob o qual o item aparece. Caixa alta é apresentação. */
  readonly grupo: string;
  /** Ordena **dentro e entre** grupos: a ordem dos grupos é a do seu 1.º item. */
  readonly ordem: number;
  /** Esconder é apresentação, não autorização (ADR 0009): a rota continua lá. */
  readonly visivel: boolean;
  /** Sobrepõe o rótulo do registo. Ausente = o do registo. */
  readonly rotulo?: string;
}

/**
 * A projecção por omissão, que é a de todos os tenants enquanto a tabela não
 * existir.
 *
 * A `ordem` vai de dez em dez pela razão de sempre: inserir um item entre dois
 * não obriga a renumerar os outros, nem aqui nem na tabela que isto vai
 * substituir.
 *
 * O agrupamento segue os módulos do backend porque é o vocabulário que atravessa
 * as duas pontas (ADR 0008, decisão 2): "Inventário" é o `inventory`, "Compras"
 * é o `purchasing`. O "Painel" é o que responde às perguntas da manhã do
 * DESIGN.md §1 — "o que está mal" — e é onde o dono olha primeiro.
 */
export const PROJECCAO_EM_CODIGO: readonly EntradaDaProjeccao[] = [
  { route_id: "inicio", grupo: "Painel", ordem: 10, visivel: true },
  { route_id: "alertas", grupo: "Painel", ordem: 20, visivel: true },
  { route_id: "stock", grupo: "Inventário", ordem: 30, visivel: true },
  { route_id: "contar", grupo: "Inventário", ordem: 40, visivel: true },
  { route_id: "receber", grupo: "Compras", ordem: 50, visivel: true },
];

/** Um item já resolvido: a projecção do tenant por cima do registo de código. */
export interface ItemDeMenu extends EntradaDoRegisto {
  readonly id: RotaId;
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
 *  - **um `route_id` que o registo não conhece é ignorado.** É inalcançável por
 *    construção (o `Record` é exaustivo nos dois sentidos), e deixa de o ser no
 *    dia em que a projecção chegar por HTTP de um servidor mais novo que este
 *    bundle. Ignorar um item desconhecido é o comportamento certo nesse dia:
 *    uma entrada a mais no menu de um cliente não é razão para o shell não
 *    montar;
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

    const itens = grupos.get(entrada.grupo) ?? [];
    itens.push({
      ...registo,
      id: entrada.route_id,
      rotulo: entrada.rotulo ?? registo.rotulo,
      exacto: registo.caminho === "/",
    });
    grupos.set(entrada.grupo, itens);
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
 * sem uma segunda tabela de nomes.
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
