/**
 * O interruptor de tema **de desenvolvimento**: escreve o `data-tema` no
 * `<html>` e deixa quem quiser ouvir a troca.
 *
 * ## Porque é que isto vive em `src/dev/` e não no shell
 *
 * A preferência de tema **da pessoa** vive no servidor (ADR 0016) e o sítio
 * dela na UI é o pé da sidebar, ao lado do email e da saída da conta (ADR 0017
 * e DESIGN.md §4). Nada disso existe ainda, e sem isso as três paletas do
 * `tokens.css` não têm forma nenhuma de serem vistas a correr — o que é o mesmo
 * que não terem sido vistas. Isto é um interruptor **para ver**, na única página
 * que já não entra no bundle de produção (a rota e o `import()` vivem dentro do
 * ramo `import.meta.env.DEV`, o Rollup elimina o chunk e o CI varre o `dist/`).
 *
 * **E por isso não guarda nada.** Nem `localStorage` — que o DESIGN.md proíbe
 * para tokens e que aqui seria pior do que inútil: uma segunda fonte de verdade
 * para a preferência, a competir com a do servidor antes de essa existir, e a
 * sobreviver a um recarregamento com uma paleta que o servidor não conhece. Uma
 * recarga volta ao default, que é o comportamento correcto de um interruptor de
 * ensaio.
 *
 * O `escuro` é escrito no atributo como qualquer outro, apesar de a paleta
 * escura viver na `:root` **sem** atributo: nenhum bloco casa com
 * `data-tema="escuro"`, logo o que fica a valer é a `:root`, que é exactamente
 * a paleta escura. Um estado do selector por paleta, sem um caso especial.
 */
export const TEMAS = ["escuro", "claro", "meio_termo"] as const;

export type Tema = (typeof TEMAS)[number];

/** O que vive na `:root` sem atributo: a identidade aprovada (ADR 0015). */
export const TEMA_DEFAULT: Tema = "escuro";

export const ROTULO_DO_TEMA: Readonly<Record<Tema, string>> = {
  escuro: "Escuro — a identidade aprovada",
  claro: "Claro — cinzento frio, tela em cima",
  meio_termo: "Meio termo — grafite com texto claro",
};

const ATRIBUTO = "data-tema";

function eTema(valor: string | null): valor is Tema {
  return valor !== null && (TEMAS as readonly string[]).includes(valor);
}

export function temaActual(): Tema {
  const escrito = document.documentElement.getAttribute(ATRIBUTO);
  return eTema(escrito) ? escrito : TEMA_DEFAULT;
}

/**
 * Interpreta o valor que vem de um controlo. Existe para o selector não ter de
 * afirmar um tipo com um `as`: o que um `<Select>` devolve é uma string, e uma
 * string que não seja uma paleta é o default — não um estado impossível que o
 * TypeScript finge que não existe.
 */
export function temaDe(valor: string): Tema {
  return eTema(valor) ? valor : TEMA_DEFAULT;
}

export function escolherTema(tema: Tema): void {
  document.documentElement.setAttribute(ATRIBUTO, tema);
}

/**
 * Avisa quando o atributo muda. Serve a página `/dev/tokens` para voltar a ler
 * os tokens do CSSOM — eles são estado externo ao React e a troca de tema é o
 * evento que os muda, que até à ADR 0015 não existia.
 */
export function subscreverTema(aoMudar: () => void): () => void {
  const observador = new MutationObserver(aoMudar);
  observador.observe(document.documentElement, { attributeFilter: [ATRIBUTO] });
  return () => {
    observador.disconnect();
  };
}
