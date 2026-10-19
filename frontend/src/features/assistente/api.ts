import { apiRequest, apiRequestVoid } from "@/lib/api/http";
import { paginated, type Paginated } from "@/lib/api/pagination";

import {
  conversaResumoSchema,
  conversaSchema,
  mensagemSchema,
  perguntaSchema,
  type Conversa,
  type ConversaResumo,
  type Mensagem,
} from "./schemas";

/**
 * As cinco chamadas do assistente (ADR 0027, decisão 4), pelo cliente HTTP
 * partilhado — mesmo cookie, mesmo `X-CSRFToken`, mesmo `X-Tenant-ID`, mesmo Zod.
 *
 * Só as chamadas: os hooks do TanStack Query vivem em `hooks/`, porque o
 * polling tem relógio próprio e cabe num ficheiro só dele. Este é o `api.py`
 * do frontend para esta feature — a única porta que outra feature ou uma rota
 * podem atravessar (ADR 0008, decisão 2).
 *
 * **Nenhuma destas chamadas escreve no ledger.** As tools do assistente são só
 * de leitura e este cliente também: criar, perguntar e apagar mexem na tabela
 * de conversas e em mais nada.
 */

const CAMINHO = "/assistant/conversations";

/** O recurso na cache: a lista e os detalhes partilham a raiz da chave. */
export const RECURSO_CONVERSAS = "assistant-conversations";

/** `GET` — as minhas conversas neste estabelecimento, mais recentes primeiro. */
export function listarConversas(signal?: AbortSignal): Promise<Paginated<ConversaResumo>> {
  return apiRequest(CAMINHO, paginated(conversaResumoSchema), {
    ...(signal === undefined ? {} : { signal }),
  });
}

/** `GET /<id>` — a conversa com os turnos. É o alvo do polling. */
export function lerConversa(id: string, signal?: AbortSignal): Promise<Conversa> {
  return apiRequest(`${CAMINHO}/${id}`, conversaSchema, {
    ...(signal === undefined ? {} : { signal }),
  });
}

/**
 * `POST` — abre a conversa **e** faz a primeira pergunta: não existe conversa
 * vazia. Responde 202 com a conversa e o turno `pendente`.
 */
export function abrirConversa(question: string): Promise<Conversa> {
  return apiRequest(CAMINHO, conversaSchema, {
    method: "POST",
    body: perguntaSchema.parse({ question }),
  });
}

/** `POST /<id>/messages` — a pergunta seguinte. 202 com o turno `pendente`. */
export function perguntarNaConversa(id: string, question: string): Promise<Mensagem> {
  return apiRequest(`${CAMINHO}/${id}/messages`, mensagemSchema, {
    method: "POST",
    body: perguntaSchema.parse({ question }),
  });
}

/** `DELETE /<id>` — 204, sem corpo. É real: a conversa é da pessoa (decisão 2). */
export function apagarConversa(id: string): Promise<void> {
  return apiRequestVoid(`${CAMINHO}/${id}`, { method: "DELETE" });
}
