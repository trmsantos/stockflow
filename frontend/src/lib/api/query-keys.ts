/**
 * Chaves de query, todas com o tenant à cabeça.
 *
 * A cache do TanStack Query é do browser, não do servidor: se uma chave não
 * levar o tenant, trocar de estabelecimento mostra dados do anterior até a
 * revalidação chegar. Com o tenant no início da chave, a troca invalida tudo
 * de uma vez e não há como duas listas de estabelecimentos diferentes
 * colidirem na mesma entrada.
 *
 * Hierarquia: `["t", tenantId, recurso, "list" | "detail", ...]`. Invalidar
 * `resource(tenantId, "produtos")` apanha as listas e os detalhes desse
 * recurso; invalidar `tenant(tenantId)` apanha tudo do estabelecimento.
 */
export const queryKeys = {
  /**
   * A sessão — **a única chave sem tenant à cabeça**, e a razão é de ordem e
   * não de conveniência: é esta resposta que *determina* qual é o
   * estabelecimento. Uma chave `["t", tenantDaCache(), "sessao"]` mudava de
   * nome no instante em que a resposta chegasse (de `"sessao"` para o uuid
   * real), e a entrada que o `beforeLoad` acabou de escrever ficava
   * inalcançável na navegação seguinte — um pedido novo por navegação, e o
   * `ensureQueryData` a nunca acertar na cache.
   *
   * Não há risco de fuga entre estabelecimentos por isto: o que esta entrada
   * guarda é "quem sou e onde posso estar", que é por utilizador e não por
   * tenant, e qualquer resposta que mude quem ou onde se está esvazia a cache
   * inteira (`features/accounts/api.ts`).
   */
  sessao: () => ["sessao"] as const,

  tenant: (tenantId: string) => ["t", tenantId] as const,

  resource: (tenantId: string, resource: string) => ["t", tenantId, resource] as const,

  list: (tenantId: string, resource: string, params: Readonly<Record<string, unknown>> = {}) =>
    ["t", tenantId, resource, "list", params] as const,

  detail: (tenantId: string, resource: string, id: string) =>
    ["t", tenantId, resource, "detail", id] as const,
} as const;
