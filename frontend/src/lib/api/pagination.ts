import { z } from "zod";

/**
 * A forma das respostas de lista, fixada pelo backend antes do primeiro
 * endpoint: `PageNumberPagination` com `PAGE_SIZE = 50`
 * (`config/settings/base.py`). Acrescentar paginação depois mudaria a forma de
 * todas as listas — por isso a forma existe desde já, e o cliente também.
 */
export const PAGE_SIZE = 50;

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** `paginated(produtoSchema)` valida `{count, next, previous, results}`. */
export function paginated<Item extends z.ZodType>(
  item: Item,
): z.ZodType<Paginated<z.output<Item>>> {
  return z.object({
    count: z.number().int().nonnegative(),
    // URLs absolutas construídas pelo DRF, ou `null` na primeira/última
    // página. Não são validadas como URL: o que o cliente faz com elas é
    // passar o número de página seguinte, não navegar para a string.
    next: z.string().nullable(),
    previous: z.string().nullable(),
    results: z.array(item),
  });
}

/** Nº total de páginas para um `count`, com o `PAGE_SIZE` do servidor. */
export function pageCount(count: number): number {
  return Math.max(1, Math.ceil(count / PAGE_SIZE));
}
