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
  tenant: (tenantId: string) => ["t", tenantId] as const,

  resource: (tenantId: string, resource: string) => ["t", tenantId, resource] as const,

  list: (tenantId: string, resource: string, params: Readonly<Record<string, unknown>> = {}) =>
    ["t", tenantId, resource, "list", params] as const,

  detail: (tenantId: string, resource: string, id: string) =>
    ["t", tenantId, resource, "detail", id] as const,
} as const;
