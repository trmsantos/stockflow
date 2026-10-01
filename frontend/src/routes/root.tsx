import { createRootRoute } from "@tanstack/react-router";

import { AppShell } from "@/shell/app-shell";

/**
 * A rota raiz: o único layout da app. A sidebar e a tab bar vivem as duas
 * dentro do `AppShell`, escondidas por breakpoint — não há uma árvore de rotas
 * para mobile e outra para desktop (ADR 0008, decisão 1).
 *
 * Os estados pendente, de erro e de não encontrado são os defaults do router
 * (`router.tsx`), e não opções desta rota: as opções de rota não se herdam, e
 * os defaults do router valem para todas as rotas de uma vez.
 */
export const rotaRaiz = createRootRoute({
  component: AppShell,
});
