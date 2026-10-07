import type { components } from "@/lib/api/types";

import { textos } from "./textos";

/**
 * A paleta activa: aplicá-la ao `<html>`, lê-la, e guardar a cópia local que
 * torna a primeira pintura possível (ADR 0016).
 *
 * Até 2026-10-06 isto vivia em `src/dev/tema.ts` e era um interruptor de
 * ensaio: as três paletas do `tokens.css` existiam e não havia **nenhuma** forma
 * de as ver a correr, o que é o mesmo que não terem sido vistas. O que mudou é
 * que a preferência passou a existir a sério — uma coluna no `accounts_user`,
 * um `PATCH /auth/preferencias`, e o nome do tema a viajar no `SessaoOut`.
 *
 * Este módulo é `lib/` e não `features/accounts/` de propósito: é chamado do
 * **módulo de entrada**, antes de montar o React e antes de haver cache, query
 * ou sessão. Uma dependência do `main.tsx` numa feature era a camada partilhada
 * a depender de um domínio pelo caminho mais crítico que existe.
 *
 * ## A ordem de arranque, e o que cada passo custa
 *
 * 1. a folha de estilos entra por `<link>` no `<head>` (ver `index.html`), logo
 *    os tokens existem antes do primeiro pixel;
 * 2. o `main.tsx` chama `aplicarTemaDoEspelho()` **antes** do `createRoot`: é
 *    uma leitura de `localStorage` e um `setAttribute`, sem rede;
 * 3. quando a sessão chega, o `tema` que vem nela é aplicado e o espelho é
 *    reescrito (`features/accounts/api.ts`). O servidor é a fonte da verdade; o
 *    espelho é uma cópia.
 *
 * O que fica pintado antes do passo 2 é o fundo de uma página vazia. Numa
 * máquina nova o primeiro arranque pinta o default e troca quando a sessão
 * chega: é um relâmpago **por máquina** e não um por arranque, e não há forma de
 * o evitar sem um servidor a renderizar o documento (ADR 0016, decisão 4).
 *
 * ## `localStorage`, e porque é que isto não é a excepção que parece
 *
 * O `SECURITY.md` §7 e o `eslint.config.js` proíbem armazenamento local, e o
 * teste que impede a regra de ser esticada está escrito na ADR 0016: *vai para o
 * armazenamento local o que um atacante não ganha nada em ler e nada em
 * escrever.* Um nome de tema não é credencial, não é dado pessoal e não concede
 * âmbito; escrever-lhe lixo dá um tema **errado**, e o valor é fechado a três
 * com queda para o default (ver `temaDe`). A regra não foi suprimida: foi
 * **estreitada**, com âmbito a este ficheiro e com a razão no
 * `eslint.config.js` — o `sessionStorage` continua proibido aqui também.
 *
 * O que fica nomeado em vez de descoberto mais tarde: a cópia **sobrevive ao
 * logout** de propósito (limpá-la trazia o relâmpago de volta ao ecrã de
 * entrada), logo um portátil partilhado diz que a última pessoa que lá entrou
 * preferia o claro. É menos do que o email que o pé da sidebar mostra.
 */

/**
 * As três paletas, **do enum gerado** e não de uma lista escrita aqui.
 *
 * É a mesma mecânica do `RotaId` do `shell/registo-de-rotas.ts`: o
 * `components["schemas"]["TemaEnum"]` vem do `pnpm gen:api`, logo uma paleta
 * nova no `Tema` do Django aparece aqui sem ninguém a inscrever — e o
 * `Record<Tema, …>` do `ROTULO_DO_TEMA` deixa de compilar até alguém lhe dar um
 * rótulo. Uma união escrita à mão compilava com a paleta a faltar e mostrava um
 * selector com dois dos três temas.
 */
export type Tema = components["schemas"]["TemaEnum"];

/**
 * O que vive na `:root` sem atributo: a identidade aprovada (ADR 0015).
 *
 * `satisfies Tema` e não `: Tema`, pela razão do `PAPEL_QUE_CONVIDA`: o tipo
 * fica o literal, logo se o backend deixar de ter `escuro` isto não compila.
 */
export const TEMA_DEFAULT = "escuro" satisfies Tema;

/**
 * Os rótulos do selector. `Record` sobre a união gerada, exaustivo nos dois
 * sentidos sob `pnpm typecheck`.
 *
 * A `descricao` não é decoração: um nome de paleta sozinho não diz a quem
 * escolhe o que vai ver, e "meio termo" é precisamente o que ninguém adivinha.
 * É texto e não um `title`, para estar à vista de quem lê e de quem ouve.
 */
export interface RotuloDeTema {
  readonly nome: string;
  readonly descricao: string;
}

const ROTULOS: Record<Tema, RotuloDeTema> = {
  escuro: {
    nome: textos.temas.escuroNome,
    descricao: textos.temas.escuroDescricao,
  },
  meio_termo: {
    nome: textos.temas.meioTermoNome,
    descricao: textos.temas.meioTermoDescricao,
  },
  claro: {
    nome: textos.temas.claroNome,
    descricao: textos.temas.claroDescricao,
  },
};

/**
 * O mesmo par `Record`/`Map` do `NOME_DO_PAPEL` das contas, pelas mesmas duas
 * razões: o `Record` é o que falha o typecheck, e o `Map` é por onde se lê
 * porque o `security/detect-object-injection` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica.
 */
const ROTULOS_POR_NOME = new Map<string, RotuloDeTema>(Object.entries(ROTULOS));

const ROTULO_DESCONHECIDO: RotuloDeTema = {
  nome: textos.temas.desconhecidoNome,
  descricao: textos.temas.desconhecidoDescricao,
};

export function rotuloDoTema(tema: Tema): RotuloDeTema {
  return ROTULOS_POR_NOME.get(tema) ?? ROTULO_DESCONHECIDO;
}

const ATRIBUTO = "data-tema";

/**
 * A chave do espelho, com prefixo da aplicação: o `localStorage` é por origem,
 * e em desenvolvimento a origem é partilhada com tudo o que corra no mesmo
 * `localhost`.
 */
const CHAVE_DO_ESPELHO = "stockflow.tema";

/**
 * Interpreta um valor que veio de fora — do servidor, de um controlo, ou do
 * espelho adulterado à mão.
 *
 * Existe para não haver um `as Tema` em sítio nenhum: o que o `localStorage`
 * devolve é `string | null` e o que um `<select>` devolve é `string`. Um valor
 * fora dos três é o **default**, que é a queda que a ADR 0016 pede — um tema
 * errado e nunca uma página sem estilos.
 */
export function temaDe(valor: string | null | undefined): Tema {
  return eTema(valor) ? valor : TEMA_DEFAULT;
}

/**
 * O predicado, e é ele que faz o `temaDe` não precisar de um `as`.
 *
 * O TypeScript não estreita uma `string` para uma união sem um predicado, e um
 * `as Tema` por cima de uma string que veio do `localStorage` era exactamente a
 * afirmação que este ficheiro não pode fazer. A pergunta é ao `Map`, que nasce
 * do `Record` exaustivo: o conjunto que ele conhece **é** a união.
 */
function eTema(valor: string | null | undefined): valor is Tema {
  return valor !== null && valor !== undefined && ROTULOS_POR_NOME.has(valor);
}

/**
 * Os três temas pela ordem em que o selector os mostra, e é a ordem da luz —
 * escuro, meio termo, claro.
 *
 * Derivada do `Record` e não escrita outra vez, logo não há uma segunda lista
 * para ficar sem o tema novo: o `Object.keys` dá a ordem de inserção e o
 * `.map(temaDe)` dá-lhe o tipo **sem um `as`**. A queda do `temaDe` é
 * inalcançável aqui por construção — as chaves do `Record` são, por definição,
 * os valores da união —, e é o mesmo padrão do `?? papel` do `nomeDoPapel`.
 */
export const TEMAS: readonly Tema[] = Object.keys(ROTULOS).map(temaDe);

/** O tema que está escrito no `<html>`, agora. */
export function temaActual(): Tema {
  return temaDe(document.documentElement.getAttribute(ATRIBUTO));
}

/**
 * ## Quatro escritores, e cada um escreve exactamente o que lhe compete
 *
 * O atributo e o espelho são duas coisas, e misturá-las dava um bug com cara de
 * fantasma: enquanto houve um escritor só, a página `/dev/tokens` e a resposta
 * da sessão disputavam o `data-tema` — trocar de paleta para medir e voltar ao
 * separador punha a paleta da conta de volta, a meio de uma medição. Não é um
 * caso raro: o `refetchOnWindowFocus` é o default e alt-tab é o que se faz ao
 * ler notas.
 *
 * Daí quatro funções, e a tabela é o contrato:
 *
 * | função | atributo | espelho | quem chama |
 * |---|---|---|---|
 * | `aplicarTema` | sempre | sempre | o ecrã `/preferencias`, ao guardar |
 * | `aplicarTemaDoEspelho` | sempre | não | o `main.tsx`, antes do React |
 * | `sincronizarTemaDaSessao` | só à primeira | sempre | cada resposta de sessão |
 * | `aplicarTemaSoNoDocumento` | sempre | **não** | a `/dev/tokens`, para medir |
 *
 * O `escuro` é escrito no atributo como qualquer outro, apesar de a paleta
 * escura viver na `:root` **sem** atributo: nenhum bloco casa com
 * `data-tema="escuro"`, logo o que fica a valer é a `:root`, que é exactamente a
 * paleta escura. Um estado do selector por paleta, sem um caso especial.
 *
 * Escrever o atributo é também o que acorda o `theme-color.ts`, que observa
 * **este** atributo para manter a barra do browser igual ao fundo da página.
 */
export function aplicarTema(tema: Tema): void {
  document.documentElement.setAttribute(ATRIBUTO, tema);
  escreverEspelho(tema);
}

/**
 * Aplica o que o espelho diz. Chamado do `main.tsx` antes do `createRoot`.
 *
 * Sem espelho — primeiro arranque nesta máquina — aplica o default, que é o que
 * a `:root` já pinta: a chamada não muda nada e não é por isso que ela sobra. O
 * que ela garante é que o atributo existe desde o primeiro frame, logo o
 * `theme-color.ts` e a página `/dev/tokens` leem um estado e não a ausência de
 * um.
 */
export function aplicarTemaDoEspelho(): Tema {
  const tema = lerEspelho();
  document.documentElement.setAttribute(ATRIBUTO, tema);
  return tema;
}

/**
 * Só o documento, sem tocar no espelho. É o que a `/dev/tokens` usa para medir.
 *
 * Aquela página troca de paleta para voltar a medir contrastes, e isso não é uma
 * preferência: é uma pergunta. Não escrever o espelho é o que faz a pergunta não
 * sobreviver a uma recarga — e é também o que a torna inofensiva, porque o
 * espelho continua a dizer o que a conta prefere.
 */
export function aplicarTemaSoNoDocumento(tema: Tema): void {
  document.documentElement.setAttribute(ATRIBUTO, tema);
}

/**
 * O que cada resposta de sessão faz com o tema que vem nela.
 *
 * **O espelho é actualizado sempre** — é ele que torna a próxima primeira
 * pintura correcta, e é a decisão 3 da ADR 0016 ("o cliente guarda uma cópia do
 * nome do tema sempre que lê a sessão").
 *
 * **O atributo é escrito uma vez por carregamento de página**, e essa é a parte
 * que foi decidida aqui e não na ADR. Depois da primeira resposta, quem muda a
 * paleta deste separador é quem está a usá-lo: o ecrã `/preferencias` ao guardar
 * e a `/dev/tokens` ao medir. Uma revalidação que reaplicasse o mesmo valor não
 * acrescentava nada — e quando o valor do separador é diferente **de
 * propósito**, reaplicar é desfazer o que a pessoa acabou de fazer.
 *
 * O que isto custa fica nomeado: trocar de tema **noutro separador** não muda
 * este até ele recarregar. É o comportamento menos surpreendente dos dois — uma
 * página a repintar-se sozinha porque algo aconteceu noutra janela é o tipo de
 * coisa que se lê como avaria.
 */
let jaAplicadoNesteCarregamento = false;

export function sincronizarTemaDaSessao(tema: Tema): void {
  escreverEspelho(tema);
  if (jaAplicadoNesteCarregamento) return;
  jaAplicadoNesteCarregamento = true;
  document.documentElement.setAttribute(ATRIBUTO, tema);
}

/**
 * Lê o espelho. Nunca levanta, e é essa a propriedade que importa.
 *
 * O `localStorage` **lança** em vez de devolver `null` em casos reais: Safari em
 * navegação privada com a quota a zero, e um browser com os dados do site
 * bloqueados. Um `try` em volta da leitura é a diferença entre "o tema volta ao
 * default" e "a aplicação não arranca", e isto corre antes do React — não há
 * error boundary nenhuma por baixo.
 */
function lerEspelho(): Tema {
  try {
    return temaDe(window.localStorage.getItem(CHAVE_DO_ESPELHO));
  } catch {
    return TEMA_DEFAULT;
  }
}

/**
 * Escreve o espelho. Nunca levanta, pela mesma razão, e com uma a mais: a quota
 * cheia faz o `setItem` lançar, e ficar sem o espelho é perder a pré-pintura —
 * não é perder a preferência, que vive no servidor.
 */
function escreverEspelho(tema: Tema): void {
  try {
    window.localStorage.setItem(CHAVE_DO_ESPELHO, tema);
  } catch {
    // Sem espelho a aplicação funciona: o tema chega com a sessão, um instante
    // depois. O que se perde é o instante.
  }
}

/**
 * Avisa quando o atributo muda.
 *
 * Serve a página `/dev/tokens`, que lê os tokens do CSSOM — eles são estado
 * externo ao React e a troca de tema é o evento que os muda. O `theme-color.ts`
 * tem o seu próprio observador em vez de usar este, porque corre fora do React e
 * não tem onde guardar a função de limpeza.
 */
export function subscreverTema(aoMudar: () => void): () => void {
  const observador = new MutationObserver(aoMudar);
  observador.observe(document.documentElement, { attributeFilter: [ATRIBUTO] });
  return () => {
    observador.disconnect();
  };
}
