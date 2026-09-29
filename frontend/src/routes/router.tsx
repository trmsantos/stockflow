import { lazy, Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { HomeRoute } from "@/routes/home";

/**
 * Encaminhamento mínimo, deliberadamente.
 *
 * Não há biblioteca de routing ainda: escolher entre TanStack Router e React
 * Router é uma decisão de arquitetura (e uma ADR), não um efeito colateral do
 * passo de ferramentas do kickoff. Até lá o caminho é lido uma vez e os links
 * são `<a href>` — navegação do browser, que Cmd+clique e clique do meio
 * respeitam de graça.
 *
 * A `/dev/tokens` é carregada só em desenvolvimento. O `import.meta.env.DEV`
 * é substituído por `false` no build, e com o `import()` dentro do ramo morto o
 * Rollup elimina o chunk: a página não existe no bundle de produção.
 */
const TokensPage = import.meta.env.DEV ? lazy(() => import("@/dev/tokens-page")) : null;

function RouteFallback() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6" aria-busy="true">
      <span className="sr-only">A carregar…</span>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full max-w-2xl" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export function Router() {
  if (TokensPage !== null && window.location.pathname === "/dev/tokens") {
    return (
      <Suspense fallback={<RouteFallback />}>
        <TokensPage />
      </Suspense>
    );
  }
  return <HomeRoute />;
}
