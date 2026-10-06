import { z } from "zod";

/**
 * As três abas do painel — **a união, as palavras e a ordem**, num sítio só.
 *
 * ## Porque é que isto é da feature e não do `validateSearch`
 *
 * O `aba` é estado de apresentação e não um campo do contrato: nada no
 * `GET /reporting/*` lhe corresponde. Mesmo assim vive aqui, pela mesma razão
 * que o `periodoSchema` vive nos `schemas.ts` e é a rota que o importa — a
 * união tem de ser **a mesma** em dois sítios que não se vêem: o
 * `validateSearch` que a valida e o `Record` que lhe dá as palavras. Escritas
 * duas vezes, divergem na primeira aba que entre ou saia, e o sintoma seria uma
 * aba válida no URL sem nome no ecrã.
 *
 * Com uma definição só, acrescentar uma quarta aba é uma linha no `z.enum` e o
 * `pnpm typecheck` passa a exigir a palavra e a entrada na ordem — falha nos
 * dois sentidos, como o resto do vocabulário deste módulo.
 *
 * ## As três perguntas, e porque são estas
 *
 * São as três perguntas que o painel já respondia, separadas pelo que cada uma
 * manda fazer a seguir: o dinheiro é para comparar, as perdas são para corrigir
 * um processo, o pessoal é para decidir uma escala. Juntas num scroll só eram
 * 3630px de tabelas com a mesma forma e números diferentes.
 */
export const abaSchema = z.enum(["dinheiro", "perdas", "pessoal"]);

export type AbaDoPainel = z.output<typeof abaSchema>;

/** A ordem em que aparecem: o dinheiro primeiro, que é a pergunta de abertura. */
export const ABAS: readonly AbaDoPainel[] = ["dinheiro", "perdas", "pessoal"];

/**
 * Dois pares `Record`/`Map`, como em toda a casa: o `Record` é a garantia
 * (exaustivo nos dois sentidos sob `pnpm typecheck`) e o `Map` é por onde se lê,
 * porque o `security/detect-object-injection` do `eslint.config.js` recusa — e
 * bem — um `OBJETO[chave]` com chave dinâmica.
 */
const ROTULO_DA_ABA: Record<AbaDoPainel, string> = {
  dinheiro: "Dinheiro",
  perdas: "Perdas",
  pessoal: "Pessoal",
};

const ROTULOS_DAS_ABAS = new Map<string, string>(Object.entries(ROTULO_DA_ABA));

export function rotuloDaAba(aba: AbaDoPainel): string {
  return ROTULOS_DAS_ABAS.get(aba) ?? aba;
}

/**
 * A pergunta que a aba responde (DESIGN.md §1), para o `<h1>` só-para-áudio.
 *
 * Quem ouve o ecrã não vê a aba activa realçada: o que lhe diz onde está é o
 * título da página a mudar com ela, e o `aria-current` do link.
 */
const PERGUNTA_DA_ABA: Record<AbaDoPainel, string> = {
  dinheiro: "Quanto entrou e quanto saiu neste período?",
  perdas: "O que se perdeu, e sabe-se mesmo quanto?",
  pessoal: "Quanto custa a equipa, e como fechou o mês?",
};

const PERGUNTAS_DAS_ABAS = new Map<string, string>(Object.entries(PERGUNTA_DA_ABA));

export function perguntaDaAba(aba: AbaDoPainel): string {
  return PERGUNTAS_DAS_ABAS.get(aba) ?? "";
}

/** A aba manda no mês? É a única que pede o `/reporting/month`. */
export function eAbaDeMes(aba: AbaDoPainel): boolean {
  return aba === "pessoal";
}
