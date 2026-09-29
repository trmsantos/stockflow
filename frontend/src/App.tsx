import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { createQueryClient } from "@/lib/api/query-client";
import { Router } from "@/routes/router";

export function App() {
  // O cliente é criado uma vez por montagem da app, não por render (um
  // `createQueryClient()` inline descartava a cache a cada render).
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <Router />
    </QueryClientProvider>
  );
}
