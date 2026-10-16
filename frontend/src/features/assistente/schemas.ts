import { z } from "zod";

import { secaoSchema } from "@/features/accounts/api";
import type { EstadoPedido } from "@/features/purchasing/api";
import { abaSchema, mesSchema, periodoSchema } from "@/features/reporting/api";
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

/* ---------------------------------------------------------------------------
 * As acções de um turno (ADR 0028, decisão 4)
 * ------------------------------------------------------------------------ */

/**
 * O **modelo nunca escreve URLs**: o servidor deriva as acções das tools que o
 * turno chamou, por um mapa fechado em código (`apps/agents/navegacao.py`), e
 * filtra-as pelos papéis de quem pergunta. O que chega é `{rota, parametros,
 * rotulo_id}` — ids de duas listas fechadas mais um mapa de strings.
 *
 * ## Porquê uma união discriminada e não um `z.object` com `parametros` livre
 *
 * Porque é o `rota` que decide **que parâmetros existem** e que tipo cada um
 * tem, e é essa narrowing que depois dá um `<Link>` tipado no `turno.tsx`: no
 * ramo do `alertas` o `parametros` é `{ver?, periodo?}` e o `to="/alertas"`
 * aceita-o sem cast nenhum. Com um `Record<string, string>` o componente teria
 * de afirmar à mão que a rota e os parâmetros combinam — que é exactamente a
 * afirmação que o contrato já faz.
 *
 * Os parâmetros são **os mesmos** que os `validateSearch` das rotas aceitam
 * (`src/routes/busca-de-*.ts`) e o backend tem um teste nas duas pontas. Esta é
 * a terceira cópia da lista só onde não há porta: o `secao`, a `aba`, o
 * `period` e o `month` vêm dos `api.ts` das features que os definem, e a
 * fronteira do `eslint.config.js` deixa — uma feature **não** pode importar
 * `@/routes/*`, logo as uniões que só vivem num `busca-de-*.ts` escrevem-se
 * aqui com o ficheiro nomeado ao lado.
 *
 * ## Uma acção que este cliente não entende é **ignorada**, não é um erro
 *
 * Um cliente antigo contra um servidor novo tem de continuar a mostrar a
 * resposta: a acção é que desaparece. Por isso cada elemento é
 * `.nullable().catch(null)` e a lista filtra os nulos — uma rota nova, um
 * `rotulo_id` novo ou um parâmetro que esta versão não conhece custam **um
 * botão**, nunca o turno. E o `parametros` é `strictObject` de propósito:
 * deixar cair em silêncio um parâmetro desconhecido levaria a pessoa a um ecrã
 * que mostra outra coisa do que a resposta prometeu, e um botão a menos é mais
 * honesto do que um botão que mente.
 */
type RotaDeAcaoGerada = components["schemas"]["RotaEnum"];
type RotuloDeAcaoGerado = components["schemas"]["RotuloIdEnum"];

/** As dez rotas que uma acção pode nomear, do enum gerado e nos dois sentidos. */
const ROTAS_DE_ACAO = {
  inicio: "inicio",
  painel: "painel",
  alertas: "alertas",
  assistente: "assistente",
  stock: "stock",
  artigo: "artigo",
  contar: "contar",
  receber: "receber",
  rececao: "rececao",
  definicoes: "definicoes",
} as const satisfies Record<RotaDeAcaoGerada, RotaDeAcaoGerada>;

/** Os quinze ids de rótulo. A palavra de cada um está no `vocabulario.ts`. */
const ROTULOS_DE_ACAO = {
  ver_artigo: "ver_artigo",
  ver_falta: "ver_falta",
  ver_validade: "ver_validade",
  ver_desperdicio: "ver_desperdicio",
  ver_alertas: "ver_alertas",
  rever_rececoes: "rever_rececoes",
  ver_rececoes_de_hoje: "ver_rececoes_de_hoje",
  ver_rececoes: "ver_rececoes",
  ver_rececao: "ver_rececao",
  ver_contagens: "ver_contagens",
  ver_painel: "ver_painel",
  ver_stock: "ver_stock",
  ver_equipa: "ver_equipa",
  ver_estabelecimento: "ver_estabelecimento",
  ver_inicio: "ver_inicio",
} as const satisfies Record<RotuloDeAcaoGerado, RotuloDeAcaoGerado>;

export const rotuloDeAcaoSchema = z.enum(ROTULOS_DE_ACAO);

/** `/receber {estado}` — a mesma união que o `purchasing` serve e o ecrã lê. */
const estadoDeRececoes = z.enum({
  revisao: "revisao",
  hoje: "hoje",
} as const satisfies Record<EstadoPedido, EstadoPedido>);

/**
 * O interruptor do painel chega `"1"` (o `parametros` é um mapa de strings) e a
 * rota quer o número — `z.literal(1)` no `busca-do-painel.ts`.
 */
const explicarDoPainel = z
  .literal("1")
  .transform(() => 1 as const)
  .optional();

function destino<R extends RotaDeAcaoGerada, P extends z.ZodType>(rota: R, parametros: P) {
  return z.object({ rota: z.literal(rota), parametros, rotulo_id: rotuloDeAcaoSchema });
}

export const acaoSchema = z.discriminatedUnion("rota", [
  destino(ROTAS_DE_ACAO.inicio, z.strictObject({})),
  destino(
    ROTAS_DE_ACAO.painel,
    // `busca-do-painel.ts`, pelos `api.ts` do `reporting`.
    z.strictObject({
      period: periodoSchema.optional(),
      month: mesSchema.optional(),
      aba: abaSchema.optional(),
      explicar: explicarDoPainel,
    }),
  ),
  destino(
    ROTAS_DE_ACAO.alertas,
    // `busca-de-alertas.ts`.
    z.strictObject({
      ver: z.enum(["expira", "falta", "desperdicio"]).optional(),
      periodo: z.enum(["hoje", "semana"]).optional(),
    }),
  ),
  // `busca-de-assistente.ts`. O servidor nunca a produz (a rota tem conjunto de
  // papéis vazio no registo do menu: já se está lá), e o ramo existe na mesma
  // porque o contrato a lista.
  destino(ROTAS_DE_ACAO.assistente, z.strictObject({ conversa: z.uuid().optional() })),
  destino(
    ROTAS_DE_ACAO.stock,
    // `busca-de-stock.ts`, incluindo os limites — um `q` de 80 caracteres cairia
    // no `.catch(undefined)` da rota e o botão levaria a uma lista sem filtro.
    z.strictObject({
      loja: z.uuid().optional(),
      filtro: z.enum(["falta", "validade"]).optional(),
      q: z.string().trim().max(60).optional(),
    }),
  ),
  // O detalhe de um artigo: o id vem de uma tool que já o validou.
  destino(ROTAS_DE_ACAO.artigo, z.strictObject({ artigo: z.uuid() })),
  // `busca-de-contagem.ts`.
  destino(ROTAS_DE_ACAO.contar, z.strictObject({ zona: z.string().trim().max(40).optional() })),
  destino(ROTAS_DE_ACAO.receber, z.strictObject({ estado: estadoDeRececoes.optional() })),
  destino(ROTAS_DE_ACAO.rececao, z.strictObject({ rececao: z.uuid() })),
  destino(ROTAS_DE_ACAO.definicoes, z.strictObject({ secao: secaoSchema.optional() })),
]);

export type Acao = z.output<typeof acaoSchema>;
export type RotuloDeAcao = z.output<typeof rotuloDeAcaoSchema>;

/**
 * A lista de acções de um turno, com os elementos ilegíveis deitados fora.
 *
 * O `.catch([])` de fora cobre o campo **inteiro** em falta: contra um servidor
 * anterior à ADR 0028 o `acoes` não existe, e isso não é razão para a conversa
 * não abrir.
 */
const acoesSchema = z
  .array(acaoSchema.nullable().catch(null))
  .catch([])
  .transform((acoes) => acoes.filter((acao): acao is Acao => acao !== null));

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
  acoes: acoesSchema,
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
