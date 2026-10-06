import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { createQueryClient } from "@/lib/api/query-client";
import { ligarPerdaDeSessao } from "@/routes/perda-de-sessao";
import { criarRouter } from "@/routes/router";

export function App() {
  // O cliente é criado uma vez por montagem da app, não por render (um
  // `createQueryClient()` inline descartava a cache a cada render).
  const [queryClient] = useState(createQueryClient);

  // E o router também, **a partir do cliente**: desde a ADR 0010 o `beforeLoad`
  // da rota do shell lê a sessão com `queryClient.ensureQueryData`, logo o
  // router precisa do cliente no seu `context`. É por isso que o
  // `routes/router.tsx` exporta uma fábrica e não um `const` de módulo: um
  // `queryClient` global tirava daqui o controlo do ciclo de vida da cache, e a
  // alternativa documentada pelo TanStack (`context: { queryClient: undefined! }`
  // com o valor injectado no `RouterProvider`) precisa de uma asserção não-nula
  // que o `typescript-eslint/strict` recusa.
  const [router] = useState(() => criarRouter(queryClient));

  // A sessão que expira a meio (ver `routes/router.tsx`). O registo vive num
  // efeito e não dentro do `criarRouter` por uma razão medível: o `StrictMode`
  // chama o inicializador do `useState` duas vezes e descarta um dos
  // resultados, logo um registo feito lá dentro podia ficar a apontar para um
  // router que não é o que está montado. Aqui fecha sobre o `router` que está
  // de facto em uso, e a limpeza desfaz o registo anterior.
  //
  // A corrida que isto não tem: o primeiro pedido com âmbito só sai depois de
  // o `beforeLoad` resolver e de um ecrã montar, que é muito depois deste
  // efeito; e o `GET /auth/sessao`, que é o primeiro pedido de todos, é
  // dispensado de âmbito e nunca responde `sem_sessao`.
  useEffect(() => ligarPerdaDeSessao(router, queryClient), [router, queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      {/* O router entra **dentro** do QueryClientProvider: a única camada de
          dados é o TanStack Query, e um ecrã que monte por navegação tem de
          encontrar o cliente já no sítio. */}
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
