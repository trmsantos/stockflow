import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

/**
 * O `QueryClient` da app.
 *
 * `retry` não repete 4xx: um 403 de âmbito, um 409 de tenant divergente ou um
 * 400 de validação não melhoram à segunda tentativa — só atrasam o erro que o
 * utilizador precisa de ver. 5xx e falhas de rede repetem-se duas vezes, que é
 * o que vale numa cozinha com Wi-Fi mau.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: true,
      },
      mutations: {
        // Uma mutação repetida é uma escrita repetida. Quem quiser repetir
        // passa uma `idempotency_key` e decide-o no sítio.
        retry: 0,
      },
    },
  });
}
