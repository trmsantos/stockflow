import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { erroDoCampo } from "@/lib/api/erros-por-campo";

/**
 * Ler uma recusa do recurso `/recipes` — e **só** ler: nada aqui reescreve uma
 * frase do servidor.
 *
 * As recusas desta ficha têm três formas, e cada uma pede uma reacção diferente:
 *
 *  - o **409 `receita_ja_existe`** não é um erro: traz o `id` da ficha que o
 *    artigo já tem, e a reacção certa é levar lá quem tentou criar a segunda.
 *    É esse `id` que o distingue de uma mensagem (precedente: o 409 da contagem
 *    já aberta, ADR 0030, decisão 2);
 *  - o **400 por campo** é orientação — a unidade que não é a do artigo, a
 *    quantidade a zero, o ingrediente repetido, o ciclo de receitas —, e a frase
 *    do servidor diz qual o campo;
 *  - o **403** de papel não se provoca: quem não é `owner|manager` não vê os
 *    botões de escrita. Se chegar na mesma (um deep link, uma sessão que mudou
 *    de papel), cai no ramo genérico e mostra o `detail`.
 *
 * O `code` é `CharField` no contrato e não uma união fechada, porque o conjunto
 * é **por endpoint**. O único que muda o desenho deste ecrã está aqui; qualquer
 * outro cai no ramo genérico, que mostra o `detail` e mais nada.
 */

/**
 * `receita_ja_existe` — 409 do `POST /recipes`.
 *
 * `Recipe.product` é `OneToOneField`, logo a segunda inserção é um
 * `IntegrityError` e não um `exists()` em Python: duas pessoas a gravar a ficha
 * do mesmo artigo no mesmo instante veem ambas zero fichas, e a segunda leva
 * este código com o `id` da primeira.
 */
export const CODIGO_RECEITA_JA_EXISTE = "receita_ja_existe";

/** O `code` de uma recusa, ou `null`. */
export function codigoDaRecusa(erro: unknown): string | null {
  return erro instanceof ApiError ? erro.code : null;
}

/**
 * O `id` da ficha que o 409 nomeia, ou `null` — o atalho do
 * `receita_ja_existe`.
 *
 * Validado como `uuid` **aqui** e não no ecrã, pela razão que o
 * `inventory/recusas-de-contagem.ts` já tinha medido: este valor vai para um
 * `<Link params>`, e um id com outra forma sobreviveria ao corpo do erro e
 * daria um botão que não vai a lado nenhum — pior do que não ter botão.
 *
 * Defensivo em cada passo: o payload pode não ser um objecto (um 500 com a
 * página de erro do Django, um proxy que recusa os bytes antes de o Django os
 * ver) e a chave pode não existir. Lê-se por `Map` porque o
 * `security/detect-object-injection` recusa um `OBJETO[chave]` dinâmico.
 */
export function fichaDoConflito(erro: unknown): string | null {
  if (!(erro instanceof ApiError)) return null;

  const payload: unknown = erro.payload;
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }

  const valor: unknown = new Map<string, unknown>(Object.entries(payload)).get("id");
  if (typeof valor !== "string") return null;

  return z.uuid().safeParse(valor).success ? valor : null;
}

/**
 * A frase que o servidor devolveu **sobre as linhas**, ou `null`.
 *
 * É por aqui que saem as recusas que nenhum formulário consegue antecipar: o
 * **ciclo de receitas** (`lines: ["…"]`) — o acabado em qualquer ponto do seu
 * próprio grafo transitivo — e a unidade que não é a base nem a de apresentação
 * daquele ingrediente.
 *
 * O servidor manda, para a unidade, uma **lista com um dicionário por linha**
 * (vazio nas que passaram), porque "a unidade está errada" numa ficha de oito
 * ingredientes é inútil sem dizer em qual. O `erroDoCampo` junta as strings que
 * encontrar e ignora o resto — o ecrã mostra a frase inteira por cima da tabela
 * e não debaixo de uma linha, que é o que a forma do corpo permite afirmar.
 */
export function erroDasLinhas(erro: unknown): string | null {
  return erroDoCampo(erro, "lines");
}

/** A frase sobre a fornada — a unidade que o acabado não aceita, ou o ≤ 0. */
export function erroDaFornada(erro: unknown): string | null {
  return erroDoCampo(erro, "batch_size") ?? erroDoCampo(erro, "batch_unit");
}

/** A frase sobre o rendimento. */
export function erroDoRendimento(erro: unknown): string | null {
  return erroDoCampo(erro, "yield_factor");
}
