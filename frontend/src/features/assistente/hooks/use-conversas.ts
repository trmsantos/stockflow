import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { Paginated } from "@/lib/api/pagination";
import { queryKeys } from "@/lib/api/query-keys";
import { tenantDaCache } from "@/lib/api/tenant";

import { listarConversas, RECURSO_CONVERSAS } from "../api";
import type { ConversaResumo } from "../schemas";

/**
 * As minhas conversas neste estabelecimento, mais recentes primeiro.
 *
 * Não é o alvo do polling — o `GET` por id é (ADR 0027, decisão 3) — e por isso
 * fica com o `staleTime` default: o que muda nesta lista muda por uma escrita
 * **deste** cliente (abrir, perguntar, apagar), e as três a invalidam.
 */
export function useConversas(): UseQueryResult<Paginated<ConversaResumo>> {
  const tenant = tenantDaCache();

  return useQuery({
    queryKey: queryKeys.list(tenant, RECURSO_CONVERSAS),
    queryFn: ({ signal }) => listarConversas(signal),
  });
}
