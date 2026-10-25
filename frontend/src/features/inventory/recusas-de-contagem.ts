import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { erroDoCampo } from "@/lib/api/erros-por-campo";

/**
 * Ler uma recusa do recurso `/stock/counts` — e **só** ler: nada aqui reescreve
 * uma frase do servidor.
 *
 * ## As recusas têm três formas, e é por isso que este ficheiro existe
 *
 * O `ContagemViewSet` devolve `{code, detail, id}` nos **conflitos de estado**
 * (409), a forma normal do DRF — `{"product": ["…"]}`, por campo — no que o
 * serviço recusa sobre o artigo (400), e um 403 nu quando o papel não chega. Os
 * três com corpos diferentes, e cada um com uma reacção diferente:
 *
 *  - o 409 de `contagem_ja_aberta` **não é um erro**: traz o `id` da contagem
 *    que já está aberta, e a reacção certa é levar lá quem tentou abrir a
 *    segunda. É esse `id` que distingue este 409 de uma mensagem;
 *  - o 400 por campo é **orientação**: "faz primeiro a receção" é um passo
 *    seguinte, não uma falha de quem está a contar com o telemóvel na mão;
 *  - o 403 do fecho é a regra dos euros, e o ecrã do colaborador nem sequer o
 *    provoca — não tem botão de fechar nem pede a pré-visualização.
 *
 * ## O `id` do 409 passou a ter leitor, e esse dia tem data
 *
 * Esta secção dizia que o `id` do conflito não era lido, e dizia-o com uma
 * razão verdadeira na altura: havia **uma** contagem aberta por
 * estabelecimento, o `/contar` já era o ecrã dela, e reler a lista fazia o ecrã
 * trocar sozinho — o `id` que voltasse seria sempre o da única aberta. A nota
 * acabava assim: *"se um dia houver mais do que uma aberta, o campo volta a ser
 * preciso"*. A ADR 0033 é esse dia. Com uma aberta **por localização**, reler a
 * lista já não leva a lado nenhum: traz três, e nenhuma delas é "a" contagem.
 * O `id` é o que distingue um beco de um atalho — é por ele que o ecrã leva
 * quem tentou abrir a arca até à contagem da arca que já estava a decorrer.
 *
 * ## Os códigos são por endpoint, de propósito
 *
 * O `ConflitoDeContagemOut` declara `code` como string e não como união fechada
 * porque o conjunto é por endpoint. Os dois que mudam o **desenho** deste ecrã
 * estão aqui; qualquer outro cai no ramo genérico, que mostra o `detail` e mais
 * nada. Quem lê isto ramifica por igualdade e tem sempre um ramo para `null`:
 * nenhuma das três formas é garantida por um status.
 */

/**
 * `contagem_ja_aberta` — 409 do `POST /stock/counts`.
 *
 * Só pode haver **uma contagem aberta por localização** (ADR 0033, decisão 1 —
 * revoga a decisão 2 da ADR 0030, que a punha por estabelecimento). O que não
 * pode acontecer duas vezes ao mesmo tempo são **duas correcções dos mesmos
 * factos**, e dois instantâneos de localizações diferentes não têm uma única
 * linha de nível em comum: a arca e a despensa contam-se em simultâneo.
 *
 * O `code` **não mudou** — o cliente ramifica nele —, mudou o significado: "já
 * há uma contagem aberta **nesta localização**". Continua imposto por índice
 * único parcial e não por um `exists()`: dois telemóveis a carregar em
 * "começar" no mesmo instante veem os dois zero abertas e inserem os dois. O
 * segundo leva este código, com o `id` da primeira.
 */
export const CODIGO_CONTAGEM_JA_ABERTA = "contagem_ja_aberta";

/**
 * `contagem_fechada` — 409 ao contar numa contagem que entretanto fechou, e ao
 * fechar uma que já está fechada.
 *
 * Acontece de verdade e não em teoria: duas pessoas contam ao mesmo tempo e uma
 * delas está no armazém com o ecrã aberto quando a outra fecha. O número que
 * ela acabou de escrever **não entrou**, e dizer-lho é o mínimo.
 */
export const CODIGO_CONTAGEM_FECHADA = "contagem_fechada";

/** O `code` de uma recusa, ou `null`. */
export function codigoDaRecusaDeContagem(erro: unknown): string | null {
  return erro instanceof ApiError ? erro.code : null;
}

/**
 * O `id` da contagem que o 409 nomeia, ou `null` — o atalho do
 * `contagem_ja_aberta`.
 *
 * Validado como `uuid` **aqui** e não no ecrã, e a razão é o que está do outro
 * lado: este valor vai para o `?contagem=` do URL, onde o
 * `buscaDeContagemSchema` o lê com `.catch(undefined)`. Um `id` com outra forma
 * sobreviveria ao corpo do erro, seria posto num link e **desapareceria em
 * silêncio** na validação do router — um botão que não vai a lado nenhum é pior
 * do que não ter botão. Devolvendo `null`, o ecrã mostra a frase sem a saída
 * falsa.
 *
 * Defensivo pelas mesmas razões do `erroDoCampo`: o payload pode não ser um
 * objecto (um 500 com a página de erro do Django, um proxy que recusa os bytes)
 * e a chave pode não existir. E lê-se por `Map` porque o
 * `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]` com
 * chave dinâmica.
 */
export function contagemDoConflito(erro: unknown): string | null {
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
 * A frase que o servidor devolveu **sobre o artigo**, ou `null`.
 *
 * Hoje tem um único emissor e vale a pena nomeá-lo: um artigo com controlo por
 * lotes e **sem lote registado** não se conta, e a mensagem manda fazer a
 * receção (ADR 0030, segunda ronda, resposta 4 — o dono preferiu o rigor ao
 * desbloqueio, porque um lote "por identificar" entraria no stock sem validade
 * e a rastreabilidade do artigo nascia já partida).
 *
 * O ecrã mostra-a como **orientação e não como falha da pessoa**: quem está a
 * contar fez o que lhe competia, e o que falta é um passo noutro ecrã.
 */
export function erroDoArtigo(erro: unknown): string | null {
  return erroDoCampo(erro, "product");
}

/** A frase que o servidor devolveu **sobre a quantidade**, ou `null`. */
export function erroDaQuantidade(erro: unknown): string | null {
  return erroDoCampo(erro, "quantity");
}
