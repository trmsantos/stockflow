import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useState } from "react";

import { createQueryClient } from "@/lib/api/query-client";
import { router } from "@/routes/router";

export function App() {
  // O cliente é criado uma vez por montagem da app, não por render (um
  // `createQueryClient()` inline descartava a cache a cada render).
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      {/* O router entra **dentro** do QueryClientProvider: a única camada de
          dados é o TanStack Query, e um ecrã que monte por navegação tem de
          encontrar o cliente já no sítio. */}
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
