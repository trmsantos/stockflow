import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import { abrirConversa, apagarConversa, perguntarNaConversa, RECURSO_CONVERSAS } from "../api";
import type { Conversa, Mensagem } from "../schemas";

/**
 * As três escritas do assistente e o que cada uma invalida.
 *
 * ## Sem update optimista, em nenhuma das três
 *
 * Nenhuma é reversível pelo ecrã: uma pergunta feita é uma chamada paga, e um
 * apagamento é um `DELETE` real. O que se faz é **usar a resposta**: o 202 de
 * abrir traz a conversa inteira e o de perguntar traz o turno `pendente`, logo
 * escrevem-se na cache como verdade do servidor — não como palpite — e o ecrã
 * pinta o turno antes de o primeiro `GET` da sondagem voltar.
 *
 * ## Apagar não remove o detalhe da cache
 *
 * Se a conversa apagada for a que está aberta, o `useConversa` ainda a observa
 * no instante em que o `onSuccess` corre; um `removeQueries` aqui fazia o
 * observador recriar a entrada e pedir um 404. Quem sai primeiro é o ecrã
 * (navega para `/assistente`), e a entrada velha morre pelo `gcTime`.
 */

/** Abrir uma conversa com a primeira pergunta. 202 com a conversa (ADR 0027 d4). */
export function useAbrirConversa(): UseMutationResult<Conversa, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (question: string) => abrirConversa(question),
    onSuccess: async (conversa) => {
      queryClient.setQueryData(queryKeys.detail(tenant, RECURSO_CONVERSAS, conversa.id), conversa);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.list(tenant, RECURSO_CONVERSAS),
      });
    },
  });
}

export interface PerguntaNaConversa {
  readonly conversa: string;
  readonly question: string;
}

/** A pergunta seguinte numa conversa. 202 com o turno `pendente`. */
export function usePerguntar(): UseMutationResult<Mensagem, Error, PerguntaNaConversa> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: ({ conversa, question }: PerguntaNaConversa) =>
      perguntarNaConversa(conversa, question),
    onSuccess: async (mensagem, { conversa }) => {
      const chave = queryKeys.detail(tenant, RECURSO_CONVERSAS, conversa);
      queryClient.setQueryData<Conversa>(chave, (anterior) =>
        anterior === undefined
          ? undefined
          : {
              ...anterior,
              messages: [
                ...anterior.messages.filter((outra) => outra.id !== mensagem.id),
                mensagem,
              ],
            },
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: chave }),
        queryClient.invalidateQueries({ queryKey: queryKeys.list(tenant, RECURSO_CONVERSAS) }),
      ]);
    },
  });
}

/** Apagar uma conversa minha. 204, e é final. */
export function useApagarConversa(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  const tenant = tenantDaCache();

  return useMutation({
    mutationFn: (id: string) => apagarConversa(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.list(tenant, RECURSO_CONVERSAS),
      });
    },
  });
}
