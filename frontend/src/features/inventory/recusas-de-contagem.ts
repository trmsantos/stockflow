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
 * ## Porque é que o `id` do 409 não é lido aqui
 *
 * O corpo do conflito traz `{code, detail, id}`, e o `id` é o que o contrato pôs
 * lá para o ecrã **levar quem tentou** até à contagem que já está aberta. Este
 * cliente chega ao mesmo sítio por outro caminho e sem ler o campo: só há uma
 * contagem aberta por estabelecimento (é um índice único), o `/contar` já é o
 * ecrã dela, e reler a lista faz o ecrã trocar sozinho — o `id` que voltasse
 * seria sempre o da única aberta que a lista traz. Uma função para o extrair
 * ficava sem chamador, e um leitor sem chamador é uma afirmação que nada
 * verifica. Se um dia houver mais do que uma aberta, o campo volta a ser preciso
 * e esta nota diz porquê.
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
 * Só pode haver **uma contagem aberta por estabelecimento** (ADR 0030, decisão
 * 2), imposto por índice único parcial e não por um `exists()`: dois telemóveis
 * a carregar em "começar" no mesmo instante veem os dois zero abertas e inserem
 * os dois. O segundo leva este código, com o `id` da primeira.
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
