/**
 * A língua, vinda do browser — **um sinal só, e nada a ligar os dois lados**
 * (ADR 0019, decisão 2).
 *
 * O `navigator.language` que este módulo lê e o `Accept-Language` que o browser
 * já manda em cada pedido são **a mesma configuração**: os dois lados da app
 * concordam sem contrato, sem campo no `SessaoOut`, sem coluna no
 * `accounts_user` e sem espelho em `localStorage`. É o oposto do tema (ADR
 * 0016), que vive no servidor e por isso **precisou** de uma cópia local para
 * sobreviver à primeira pintura, de uma excepção estreitada no
 * `eslint.config.js` e de três parágrafos sobre CSP.
 *
 * ## E é a ausência de selector que mantém `textos` uma constante
 *
 * Com a língua fixa por documento, o catálogo resolve-se **ao nível do módulo**:
 * é isso que permite que os `z.string().min(1, "Escreva o email…")` dos
 * `schemas.ts` e os `Intl.*Format` do `format.ts` continuem constantes de módulo
 * em vez de funções. Com um selector, cada string passava a valor reactivo e
 * cada constante a função — e reverter isto não é grátis, o que está dito na ADR.
 *
 * ## A lista é fechada e tem um elemento
 *
 * Com o idioma a vir do browser **não se pode "não enviar" inglês**: um browser
 * inglês recebe o que houver. Enquanto esta lista tiver um elemento, um
 * `navigator.language` de `en-US` cai em `pt-PT` e a app é inteiramente
 * portuguesa — que é coerente, porque uma app meio traduzida dá ao leitor inglês
 * uma parede de português exactamente onde a tarefa fica difícil.
 *
 * O inglês liga-se acrescentando `"en"` ao `LINGUAS` **e** a entrada equivalente
 * no `LANGUAGES` do `config/settings/base.py`, no commit em que a última linha da
 * lista fechada do `scripts/check-textos.mjs` sair. São duas linhas, e é a única
 * alteração em que a app muda de estado.
 */

/** As línguas que esta app serve. Fechada, e hoje com um elemento. */
export const LINGUAS = ["pt-PT"] as const;

export type Lingua = (typeof LINGUAS)[number];

/** O que um browser que não fale nenhuma das nossas recebe. */
export const LINGUA_POR_OMISSAO: Lingua = "pt-PT";

const ATRIBUTO = "lang";

/**
 * A língua desta visita, resolvida **uma vez** a partir do browser.
 *
 * Compara por **prefixo** e não por igualdade: um browser diz `pt-BR`, `en-GB`
 * ou `pt`, e exigir `pt-PT` exacto mandava um brasileiro e um português do
 * telemóvel em inglês para o default por razões diferentes. O que se compara é a
 * língua, não a região — e um `pt-BR` é servido em pt-PT de propósito: a ADR 0019
 * faz a afirmação "pt é o de Portugal" e **não** a de excluir o pt-BR, que seria
 * uma terceira língua e não um ajuste.
 *
 * `navigator.languages` e não `navigator.language`: o primeiro é a lista
 * ordenada de preferências, e quem tem o sistema em inglês com português em
 * segundo quer português se o inglês não existir. O segundo é só o primeiro
 * elemento dessa lista.
 */
function resolver(): Lingua {
  for (const pedida of navigator.languages) {
    const prefixo = pedida.split("-")[0]?.toLowerCase();
    const encontrada = LINGUAS.find((nossa) => nossa.split("-")[0]?.toLowerCase() === prefixo);
    if (encontrada !== undefined) return encontrada;
  }
  return LINGUA_POR_OMISSAO;
}

export const LINGUA: Lingua = resolver();

/**
 * Escreve o `lang` no `<html>`. Chamado do módulo de entrada, ao lado do tema.
 *
 * **Não é cosmético.** O `lang` é o que diz ao leitor de ecrã que voz usar — um
 * texto português lido com pronúncia inglesa é inintelegível, não é só feio — e
 * é o que decide a hifenização e as aspas tipográficas do browser. O
 * `index.html` tem `lang="pt-PT"` escrito à mão, que é o certo para a primeira
 * pintura; esta função corrige-o quando a língua resolvida é outra.
 */
export function aplicarLingua(lingua: Lingua = LINGUA): void {
  document.documentElement.setAttribute(ATRIBUTO, lingua);
}

/**
 * O catálogo desta visita, escolhido da **lista fechada de línguas**.
 *
 * ## O contrato é um `typeof`, e é mais forte do que um `Record`
 *
 * Cada módulo escreve `export const PT = {...}` e
 * `export const EN: typeof PT = {...}`. Uma chave a faltar no inglês dá
 * `TS2741`; uma a mais dá `TS2353`. **E a interpolação faz parte do contrato**:
 * uma chave com dados é uma função, e mudar `(n: number)` para
 * `(n: number, loja: string)` numa língua e não na outra não compila.
 *
 * Um `Record<Chave, string>` sobre uma união declarada era mais fraco em dois
 * eixos: a união seria uma **terceira** lista escrita à mão (ao contrário do
 * `Record<RotaId, …>` e do `Record<Tema, …>`, onde a união é **gerada** pelo
 * backend), e um `Record<Chave, string>` não consegue guardar uma função, logo
 * não tipa interpolação nenhuma.
 *
 * ## Acesso por propriedade e não por `t("chave")`
 *
 * `textos.titulo` e não `t("titulo")`. Isso elimina de uma vez a união de
 * chaves, o `security/detect-object-injection` do `eslint.config.js` (que recusa
 * um `OBJETO[chave]` com chave dinâmica, e bem) e o ramo de fallback que toda a
 * biblioteca de i18n tem para a chave que não existe — aqui ela não compila.
 *
 * ## Plural é `n === 1`, e o gatilho para isso mudar está escrito
 *
 * O português e o inglês têm as **mesmas duas** categorias de plural do CLDR
 * (`one`/`other`), logo uma função com um ternário resolve-o e uma biblioteca
 * não compra nada. A primeira língua com mais de duas categorias — polaco, russo,
 * árabe — troca isto por `Intl.PluralRules`, e aí a conta muda.
 *
 * ## `Record<Lingua, T>` e não `escolher(pt, en)`, e a diferença é o gate
 *
 * A primeira versão desta função recebia dois argumentos. Com a lista fechada a
 * uma língua, o segundo **nunca era lido** — e o `eslint` apanhou-o pelo outro
 * lado (`LINGUA === "pt-PT"` é sempre verdade, logo o ramo do inglês era código
 * morto). Tinha razão, e a regra desta casa é a de sempre: um valor que nada
 * produz é uma promessa que ninguém cumpre.
 *
 * Um `Record` sobre a `Lingua` diz a mesma coisa e compra o gate que faltava:
 * **acrescentar `"en"` ao `LINGUAS` faz todos os catálogos deixarem de
 * compilar** até terem a entrada inglesa. É o mecanismo a tornar impossível o
 * que a ADR 0019 proibiu por escrito — servir uma língua em que metade dos ecrãs
 * está traduzida. A lista fechada do `check-textos.mjs` mede outra coisa (que
 * ecrãs têm catálogo), e as duas juntas fecham o problema nos dois eixos.
 */
export function escolher<T>(catalogos: Record<Lingua, T>): T {
  // O par `Record`/`Map` de sempre: o `Record` é a garantia (exaustivo sob
  // `pnpm typecheck`) e o `Map` é por onde se lê, porque o
  // `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]` com
  // chave dinâmica, e esta casa não suprime lint.
  //
  // A queda é inalcançável por construção — o `Record` é exaustivo sobre a mesma
  // união de que `LINGUA` é um valor — e existe porque o `Map.get` devolve
  // `undefined` no tipo. É o mesmo `?? papel` do `nomeDoPapel`.
  const porLingua = new Map<string, T>(Object.entries(catalogos));
  return porLingua.get(LINGUA) ?? catalogos["pt-PT"];
}
