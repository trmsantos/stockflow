import { ApiError } from "./errors";

/**
 * Ler um erro **por campo** de um 400 do DRF — e só ler: nada aqui reescreve
 * uma frase do servidor.
 *
 * ## Porque desceu para `src/lib/api/`
 *
 * As recusas desta API têm duas formas com o mesmo status: `{code, detail}`,
 * que é para o cliente **ramificar**, e a forma normal do DRF —
 * `{"email": ["…"]}` — que é para aparecer **debaixo do input**. O `errors.ts`
 * já lê o `code` defensivamente; esta é a outra metade, e estava escrita duas
 * vezes.
 *
 * O `recusas-de-documento.ts` do `purchasing` nomeou o gatilho da descida em
 * 2026-10-07, por extenso: *"a alternativa honesta é a descida para
 * `src/lib/api/`, e ela tem um gatilho: o **terceiro** módulo a precisar disto.
 * Hoje são dois"*. As contagens são o terceiro — o `POST /stock/counts/{id}/lines`
 * recusa um artigo com controlo por lotes e sem lote registado em
 * `{"product": ["…"]}` —, logo a descida acontece agora e não há uma terceira
 * cópia a divergir na primeira correcção feita só numa delas.
 *
 * Isto **não** é copy e por isso pode viver aqui: a frase é do servidor e já
 * vem pronta para mostrar. O que fica em cada feature é o que **se faz** com
 * ela, que é decisão de ecrã (ADR 0019, decisão 3).
 *
 * ## Defensivo em cada passo, e de propósito
 *
 * O payload pode ser `null` (uma resposta sem corpo JSON — um 500 com a página
 * de erro do Django, ou um proxy que recusa os bytes antes de o Django os ver),
 * pode não ser um objecto, a chave pode não existir, e o valor pode ser uma
 * string em vez de uma lista. Nenhum desses casos é um erro desta função: é a
 * **ausência** de erro naquele campo, e quem chama cai então na frase genérica.
 *
 * Lê **a chave que lhe é dada** e nenhuma outra. Um `Object.entries(payload)`
 * punha no ecrã o nome de qualquer chave que o servidor inventasse — incluindo
 * `detail` — debaixo de um input que não existe; e um acesso por variável
 * acordava o `security/detect-object-injection` do `eslint.config.js`, que esta
 * casa não suprime (CLAUDE.md). Daí o `Map`.
 */
export function erroDoCampo(erro: unknown, campo: string): string | null {
  if (!(erro instanceof ApiError)) return null;

  const payload: unknown = erro.payload;
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }

  // `Map<string, unknown>` com o tipo escrito: `Object.entries` sobre `object`
  // devolve `[string, any][]`, e sem a anotação o `any` escapava para o resto
  // da função — que é o que o `@typescript-eslint/no-unsafe-assignment` apanha.
  const valor: unknown = new Map<string, unknown>(Object.entries(payload)).get(campo);

  if (typeof valor === "string" && valor !== "") return valor;
  if (!Array.isArray(valor)) return null;

  // Juntas numa frase: a activação de conta devolve três de uma vez para uma
  // password fraca, e as três interessam a quem a está a escolher.
  const frases = valor.filter((linha): linha is string => typeof linha === "string");
  return frases.length === 0 ? null : frases.join(" ");
}
