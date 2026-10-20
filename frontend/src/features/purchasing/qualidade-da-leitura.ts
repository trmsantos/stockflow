import { extracaoMostraEuros } from "./euros-do-papel";
import type { ConferenciaDeIva, Extracao } from "./schemas-de-documento";

/**
 * O que o ecrã sabe sobre a **qualidade** de uma leitura, e o que faz com isso.
 *
 * Ao lado do `vocabulario-de-documento.ts` e não dentro dele: aquele traduz o
 * contrato em palavras, este deriva decisões a partir dele. São três perguntas,
 * e as três têm resposta na ADR 0031:
 *
 *  1. **esta linha merece atenção?** (decisão 4 — a confiança ordena a atenção e
 *     nunca bloqueia nada);
 *  2. **ainda se pode pedir outra leitura?** (decisão 7 — três tentativas por
 *     documento, e um botão que o servidor vai recusar é uma mentira);
 *  3. **o QR discorda das linhas?** (decisão 8 e a adenda do QR — é o sinal mais
 *     forte que esta feature produz).
 *
 * ## Nenhuma delas bloqueia o quer que seja, e isso é a decisão
 *
 * A confiança é *"um número auto-reportado por um modelo, calibrado por nada"*;
 * dar-lhe poder de veto era tratá-lo como medição. O portão humano já existe e é
 * a revisão linha a linha. O que estas funções produzem é **ênfase visual**, e o
 * ecrã que a usa põe sempre a palavra ao lado da cor (DESIGN.md §3).
 */

/**
 * Abaixo disto a linha fica marcada. **0,80, por decisão 4 da ADR 0031.**
 *
 * Não é um limiar de aceitação e não é uma afirmação de domínio sobre o que é
 * uma leitura boa: é o ponto a partir do qual vale a pena o olho ir ali
 * primeiro. Fica nomeado como constante — e não enterrado num `<`
 * num JSX — porque é o número que alguém vai querer discutir.
 */
export const LIMIAR_DE_CONFIANCA = 0.8;

/**
 * Esta linha merece atenção?
 *
 * **`null` conta como baixa**, e é a metade menos óbvia da regra: ausência de
 * confiança não é confiança alta. Um modelo que não devolveu número nenhum não
 * disse que a linha está bem — não disse nada.
 *
 * ## Um `Number()` aqui não contradiz "decimais como string"
 *
 * A regra do `schemas-de-documento.ts` existe porque um `float` perde cêntimos
 * em dinheiro e milésimas em quantidades. Aqui não há nada a perder: o que se
 * faz é **comparar** uma razão de 0 a 1 com três casas contra um limiar, e o
 * resultado é um booleano. Nenhum valor convertido chega ao ecrã — o que o ecrã
 * mostra continua a ser a string servida, pelo `formatRate`.
 *
 * Um valor que não seja um número também conta como baixa: o contrato promete um
 * decimal, e se o que chegou não o é, a última coisa a fazer é tratá-lo como
 * bom.
 */
export function confiancaEBaixa(confianca: string | null): boolean {
  if (confianca === null) return true;
  const valor = Number(confianca);
  return Number.isNaN(valor) || valor < LIMIAR_DE_CONFIANCA;
}

/**
 * Quantas leituras um documento admite. **Três, por decisão do dono** (ADR 0031,
 * resposta 3): reabrir acrescenta uma linha de extração, e um ciclo de
 * reaberturas é um ciclo pago.
 *
 * ## Está escrito aqui porque **não há campo nenhum no contrato que o diga**
 *
 * O `ExtracaoOut` serve o `attempt` e mais nada: o `AGENTS_EXTRACTION_MAX_ATTEMPTS`
 * é uma setting do servidor e não viaja. Logo esta constante é uma **cópia** do
 * que o servidor decide, e o modo de falha dela está nomeado: se o tecto do
 * servidor subir e este ficar em três, o ecrã esconde um botão que o servidor
 * aceitaria; se descer, o ecrã oferece um botão que leva 409 — e o 409 é tratado,
 * com a frase do servidor, precisamente para esse dia não ser um ecrã partido.
 *
 * A alternativa — inventar um campo no contrato — era trabalho de backend, e
 * este lado não o inventa.
 */
export const MAXIMO_DE_TENTATIVAS = 3;

/**
 * As tentativas acabaram?
 *
 * Sem extração nenhuma a resposta é não: um documento que nunca foi lido tem as
 * três à frente.
 */
export function tentativasEsgotadas(extracao: Extracao | null): boolean {
  return extracao !== null && extracao.attempt >= MAXIMO_DE_TENTATIVAS;
}

/** Quantas tentativas sobram, nunca negativo. Para a frase ao lado do botão. */
export function tentativasQueSobram(extracao: Extracao | null): number {
  if (extracao === null) return MAXIMO_DE_TENTATIVAS;
  return Math.max(0, MAXIMO_DE_TENTATIVAS - extracao.attempt);
}

/**
 * As conferências de IVA em que a soma das linhas **não** bate com a base do QR.
 *
 * Só as que têm `qr_base`: sem base no QR não há comparação nenhuma a fazer, e
 * um `matches` falso aí seria uma acusação sem acusador.
 *
 * ## E a quem não vê euros o teste **não se pode fazer**, logo não se faz
 *
 * Para um `staff` a `qr_base` não vem a `null` — não vem de todo (ADR 0031,
 * adenda dos euros). Escrever `qr_base !== null` e dar o caso por tratado seria
 * exactamente o erro que esta fatia veio corrigir: `undefined` não é `null`, e
 * aqui ele passava o teste por acidente em vez de por decisão.
 *
 * A decisão é deixar passar, e por quem é servido: o `matches` é o sinal que
 * continua a sair para toda a gente, e esconder a única coisa que ele produz
 * seria voltar a fechar a porta errada — o colaborador deixava de ver que as
 * contas não batem, que é o trabalho dele. Fica nomeado o custo: sem a
 * `qr_base` o ecrã não distingue *"a soma discorda do QR"* de *"o QR não
 * declara esta taxa"*, logo quem não vê euros pode ver **uma linha a mais** do
 * que quem os vê. Um aviso a mais sobre uma leitura que merece uma segunda
 * olhadela é o lado certo para falhar.
 */
export function conferenciasQueNaoBatem(
  extracao: Extracao,
): readonly ConferenciaDeIva[] {
  const comEuros = extracaoMostraEuros(extracao);
  return extracao.vat_checks.filter(
    (conferencia) => !conferencia.matches && (!comEuros || conferencia.qr_base !== null),
  );
}

/* ---------------------------------------------------------------------------
 * **Não há aqui um `temQrParaMostrar`**, e a ausência é a decisão: o
 * `qr_read` é um booleano servido e o painel ramifica sobre ele directamente.
 * Uma função cujo corpo é `extracao.qr_read` acrescenta um nome e esconde o
 * campo — e nenhuma das três perguntas deste ficheiro é essa.
 * ------------------------------------------------------------------------- */
