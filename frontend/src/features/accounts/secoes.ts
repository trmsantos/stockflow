import { z } from "zod";

import { PAPEL_QUE_CONVIDA, type Papel } from "./schemas";

/**
 * As quatro secções das Definições — **a união, as palavras, a ordem e quem as
 * vê**, num sítio só (ADR 0019, decisão 6).
 *
 * ## Um ecrã com secções, e não dois ecrãs
 *
 * A ADR 0017 tinha decidido **dois** ecrãs e rejeitado por escrito "um ecrã com
 * abas e um 403 por aba", com um argumento que não desaparece por o dono do
 * produto ter mudado de ideias: um ecrã cujo **conteúdo** depende do papel. A
 * ADR 0019 supersede a decisão e responde à objecção em três peças, e a primeira
 * está neste ficheiro: **a secção é um search param com queda para o default**,
 * como o `?aba=` do painel.
 *
 * Um papel que não pode ver uma secção é, para este efeito, o mesmo que um URL
 * malformado — e a ADR 0008 já decidiu o que fazer com esses: *"um URL
 * malformado degrada para o default em vez de explodir dentro de um ecrã"*. Não
 * há 403 por secção porque **não há pedido**: o papel vem na sessão antes de o
 * ecrã montar, as secções da empresa não são renderizadas e os hooks não
 * disparam. O 403 do servidor fica onde a ADR 0017 já o punha — a rede do deep
 * link e da pertença revogada a meio da sessão.
 *
 * ## A queda vive no **render** e não à entrada da rota, e isto é um buraco real
 *
 * O papel é **por tenant**, e o seletor de estabelecimento vive no mesmo pé da
 * sidebar que a entrada para este ecrã. Quem é `owner` de A e `staff` de B,
 * parado em `/definicoes?secao=estabelecimento`, troca de casa e fica com uma
 * secção que o papel novo não tem — **sem o URL mudar**. Um `beforeLoad` ou uma
 * verificação no `validateSearch` não apanham nada, porque nada na rota mudou.
 * Daí o `secaoVisivel`/`primeiraSecaoVisivel` abaixo serem chamados no corpo do
 * componente, contra a sessão viva.
 *
 * ## As quatro, e os nomes
 *
 * "Definições" e não "Configurações" — é o termo pt-PT, e o pt-BR é o outro.
 * "Navegação" e **não "Menu"**, que numa app de restauração se lê como a ementa.
 */
export const secaoSchema = z.enum(["aparencia", "estabelecimento", "navegacao", "equipa"]);

export type SecaoDeDefinicoes = z.output<typeof secaoSchema>;

/**
 * A ordem em que aparecem: a **pessoal primeiro**, e as da empresa depois.
 *
 * Não é alfabética nem arbitrária. A ADR 0017 punha a fronteira entre as duas
 * famílias de definições no **menu** (uma era um item restrito, a outra não), e
 * essa resposta morre com o ecrã único. O que a substitui é esta ordem mais uma
 * separação visível na régua: o que é teu primeiro, o que é da casa depois.
 */
export const SECOES: readonly SecaoDeDefinicoes[] = [
  "aparencia",
  "estabelecimento",
  "navegacao",
  "equipa",
];

/**
 * Os pares `Record`/`Map` de sempre: o `Record` é a garantia (exaustivo nos dois
 * sentidos sob `pnpm typecheck`) e o `Map` é por onde se lê, porque o
 * `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]` com
 * chave dinâmica.
 */
const ROTULO_DA_SECAO: Record<SecaoDeDefinicoes, string> = {
  aparencia: "Aparência",
  estabelecimento: "Estabelecimento",
  navegacao: "Navegação",
  equipa: "Equipa",
};

const ROTULOS = new Map<string, string>(Object.entries(ROTULO_DA_SECAO));

export function rotuloDaSecao(secao: SecaoDeDefinicoes): string {
  return ROTULOS.get(secao) ?? secao;
}

/**
 * O que a secção responde, para o `<h2>` e para quem ouve o ecrã.
 *
 * Quem navega por áudio não vê a secção activa realçada: o que lhe diz onde está
 * é o título a mudar com ela, mais o `aria-current` do link.
 */
const PERGUNTA_DA_SECAO: Record<SecaoDeDefinicoes, string> = {
  aparencia: "Como é que a aplicação se vê?",
  estabelecimento: "Como é que esta casa está configurada?",
  navegacao: "Que ecrãs é que a equipa vê, e com que nomes?",
  equipa: "Quem tem acesso, e quem está por entrar?",
};

const PERGUNTAS = new Map<string, string>(Object.entries(PERGUNTA_DA_SECAO));

export function perguntaDaSecao(secao: SecaoDeDefinicoes): string {
  return PERGUNTAS.get(secao) ?? "";
}

/**
 * Os papéis que vêem cada secção. **Conjuntos e nunca um mínimo** — é a regra
 * que o `apps/accounts/menu.py` fixou e que a Q7 obriga: escrever uma ordem
 * entre papéis era responder à Q7 sem ninguém ter perguntado, e um conjunto de
 * um elemento alarga-se sem se desfazer.
 *
 * **Isto não é autorização.** Quem autoriza é o servidor, em cada pedido: o
 * `GET /estabelecimento` e o `GET /convites` respondem 403 a quem não é `owner`
 * — medido. O que este mapa faz é não renderizar um controlo que acaba em 403,
 * que é a mesma distinção da ADR 0011 ("esconder é apresentação").
 */
const PAPEIS_DA_SECAO: Record<SecaoDeDefinicoes, readonly Papel[]> = {
  aparencia: ["owner", "manager", "staff"],
  estabelecimento: [PAPEL_QUE_CONVIDA],
  navegacao: [PAPEL_QUE_CONVIDA],
  equipa: [PAPEL_QUE_CONVIDA],
};

const PAPEIS = new Map<string, readonly Papel[]>(Object.entries(PAPEIS_DA_SECAO));

/** A secção está aberta aos três papéis? Usada para derivar a separação. */
export function eSecaoDeTodos(secao: SecaoDeDefinicoes): boolean {
  return (PAPEIS.get(secao) ?? []).length >= 3;
}

/**
 * A primeira secção da empresa, e é **ela** que a régua marca com a separação.
 *
 * Derivada e não escrita à mão: é a primeira da `SECOES` que não é de todos os
 * papéis, logo acrescentar uma secção pessoal no fim da lista pessoal move a
 * separação sozinha.
 *
 * **Vive aqui, depois do `eSecaoDeTodos`, e não lá em cima com as outras
 * constantes.** Escrita antes dele, isto rebentava no **import** com um
 * `ReferenceError: Cannot access 'PAPEIS' before initialization` — uma zona morta
 * temporal entre constantes de módulo. O custo foi o modo de falha: o React nunca
 * montava, o ecrã de arranque ficava a tapar tudo, e nem o `pnpm typecheck` nem o
 * `eslint` viam nada. Quem apanhou foi um screenshot com `arranque: true` e o
 * `<div id="root">` vazio.
 */
export const PRIMEIRA_SECAO_DA_EMPRESA: SecaoDeDefinicoes | undefined = SECOES.find(
  (secao) => !eSecaoDeTodos(secao),
);

/**
 * Este papel vê esta secção?
 *
 * Aceita `null`/`undefined` porque **não é autorização**: enquanto a sessão não
 * chegou, o papel é `undefined` e a resposta é "só o que é de todos". Na prática
 * é imediato — o `beforeLoad` da rota do shell já leu a sessão antes de montar o
 * invólucro — e o que isto evita é um instante com as secções da empresa à vista
 * de quem não é dono.
 */
export function secaoVisivel(
  secao: SecaoDeDefinicoes,
  papel: Papel | null | undefined,
): boolean {
  if (papel === null || papel === undefined) return eSecaoDeTodos(secao);
  return (PAPEIS.get(secao) ?? []).includes(papel);
}

/** As secções que este papel vê, pela ordem da régua. */
export function secoesVisiveis(papel: Papel | null | undefined): readonly SecaoDeDefinicoes[] {
  return SECOES.filter((secao) => secaoVisivel(secao, papel));
}

/**
 * A secção a mostrar: a pedida, se o papel a vê; a primeira visível, se não.
 *
 * É a queda do URL malformado da ADR 0008 aplicada a um caso que o
 * `validateSearch` **não** consegue apanhar: trocar de estabelecimento muda o
 * papel sem mudar o URL. Por isso isto é chamado no render e recebe o papel.
 *
 * `aparencia` é o fallback do fallback e nunca é alcançado por construção — está
 * aberta aos três papéis, logo `secoesVisiveis` nunca devolve vazio. Existe
 * porque o TypeScript não sabe disso.
 */
export function secaoAMostrar(
  pedida: SecaoDeDefinicoes,
  papel: Papel | null | undefined,
): SecaoDeDefinicoes {
  if (secaoVisivel(pedida, papel)) return pedida;
  return secoesVisiveis(papel)[0] ?? "aparencia";
}
