import { z } from "zod";

import type { components } from "@/lib/api/types";

/**
 * O contrato do assistente (ADR 0027, decisão 4), validado à chegada.
 *
 * ## Os enums são os gerados, nos dois sentidos
 *
 * `estadoDaMensagemSchema` e `codigoDeErroSchema` não são uniões escritas à mão
 * que por acaso coincidem com o `types.ts`: cada uma é um `z.enum` sobre um
 * objecto anotado com `satisfies Record<<enum gerado>, …>`, o que falha a
 * compilar nos **dois** sentidos — um valor a mais aqui dá `TS2353`, um valor
 * novo no backend (depois do `pnpm gen:api`) dá `TS2741`. É o mesmo par
 * `Record`/gerado do `REGISTO_DE_ROTAS`, aplicado a um schema.
 *
 * `language` e `role_at_time` ficam `z.string()`: o ecrã não ramifica por
 * nenhum dos dois, e um papel novo no servidor não é razão para a conversa
 * deixar de abrir.
 */

/** `"0.000123"` — o que o DRF serializa a partir de um `DecimalField`. */
const decimal = z.string().regex(/^-?\d+$|^-?\d+\.\d+$/, "decimal inválido");

type EstadoDaMensagemGerado = components["schemas"]["EstadoDaMensagemEnum"];
type CodigoDeErroGerado = components["schemas"]["ErrorCodeEnum"];

const ESTADOS_DA_MENSAGEM = {
  pendente: "pendente",
  a_responder: "a_responder",
  respondida: "respondida",
  erro: "erro",
} as const satisfies Record<EstadoDaMensagemGerado, EstadoDaMensagemGerado>;

const CODIGOS_DE_ERRO = {
  teto_de_iteracoes: "teto_de_iteracoes",
  teto_de_custo: "teto_de_custo",
  tempo_esgotado: "tempo_esgotado",
  resposta_invalida: "resposta_invalida",
  erro_do_modelo: "erro_do_modelo",
  pertenca_revogada: "pertenca_revogada",
} as const satisfies Record<CodigoDeErroGerado, CodigoDeErroGerado>;

export const estadoDaMensagemSchema = z.enum(ESTADOS_DA_MENSAGEM);
export const codigoDeErroSchema = z.enum(CODIGOS_DE_ERRO);

/**
 * Uma chamada a uma tool, **verbatim** do rasto da tarefa: nome, argumentos
 * como o modelo os escreveu, nº de linhas do resultado, se foi truncado, se
 * correu bem, e quanto demorou. Os `args` são `unknown` por campo: o que o
 * modelo produz é texto não confiável (CLAUDE.md), e o `vocabulario.ts` lê
 * cada campo com um `typeof` antes de o mostrar.
 */
export const toolCallSchema = z.object({
  name: z.string(),
  args: z.record(z.string(), z.unknown()),
  rows: z.number().int().nonnegative(),
  truncated: z.boolean(),
  ok: z.boolean(),
  ms: z.number().int().nonnegative(),
});

/** Um turno: pergunta e resposta na mesma linha (ADR 0027, decisão 1). */
export const mensagemSchema = z.object({
  id: z.uuid(),
  position: z.number().int().nonnegative(),
  status: estadoDaMensagemSchema,
  question: z.string(),
  language: z.string(),
  answer: z.string(),
  asked_by_name: z.string(),
  role_at_time: z.string(),
  tool_calls: z.array(toolCallSchema),
  model: z.string(),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  cost_eur: decimal,
  started_at: z.iso.datetime({ offset: true }).nullable(),
  finished_at: z.iso.datetime({ offset: true }).nullable(),
  error_code: codigoDeErroSchema.nullable(),
});

/** Uma linha da lista: sem os turnos, que vêm no detalhe. */
export const conversaResumoSchema = z.object({
  id: z.uuid(),
  title: z.string(),
  created_at: z.iso.datetime({ offset: true }),
  last_message_at: z.iso.datetime({ offset: true }),
});

/** A conversa inteira — o alvo do polling (ADR 0027, decisão 3). */
export const conversaSchema = conversaResumoSchema.extend({
  messages: z.array(mensagemSchema),
});

/** O máximo da coluna `question` (ADR 0027, decisão 1): o contador conta até aqui. */
export const PERGUNTA_MAXIMA = 2000;

/**
 * O corpo dos dois `POST`: a pergunta, e mais nada. O `trim` é o do serializer
 * (uma pergunta só de espaços é um 400 lá, e é um botão desactivado aqui).
 */
export const perguntaSchema = z.object({
  question: z.string().trim().min(1).max(PERGUNTA_MAXIMA),
});

export type EstadoDaMensagem = z.output<typeof estadoDaMensagemSchema>;
export type CodigoDeErro = z.output<typeof codigoDeErroSchema>;
export type ToolCall = z.output<typeof toolCallSchema>;
export type Mensagem = z.output<typeof mensagemSchema>;
export type ConversaResumo = z.output<typeof conversaResumoSchema>;
export type Conversa = z.output<typeof conversaSchema>;
export type Pergunta = z.output<typeof perguntaSchema>;

/**
 * Há um turno **em curso**? É o predicado do polling e do compositor: enquanto
 * for verdade sonda-se a 2 s e não se faz outra pergunta (o servidor recusaria
 * com 409 `resposta_pendente`).
 */
export function temTurnoEmCurso(conversa: Conversa | undefined): boolean {
  if (conversa === undefined) return false;
  return conversa.messages.some(
    (mensagem) => mensagem.status === "pendente" || mensagem.status === "a_responder",
  );
}
