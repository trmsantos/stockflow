import { createRootRouteWithContext } from "@tanstack/react-router";

import type { ContextoDoRouter } from "./contexto";

/**
 * A rota raiz: **sem componente**, e isso é a mudança desta sessão.
 *
 * Até aqui a raiz *era* o `AppShell`, pelo que qualquer rota nova nascia dentro
 * da sidebar — e o ramo público da ADR 0010 (`/entrar`, `/ativar`) tem de ficar
 * **fora** dela. Uma raiz sem componente rende `<Outlet/>` (é o default do
 * router) e passa a ser o que sempre devia ter sido: o sítio onde se escolhe
 * **qual** dos dois invólucros vale.
 *
 * Por baixo dela há exactamente dois filhos, os dois sem caminho próprio
 * (rotas de layout, identificadas por `id`):
 *
 *  - `rotaPublica` (`routes/publico.tsx`) → a `MolduraPublica`, um painel
 *    centrado, sem navegação e sem sessão;
 *  - `rotaDaApp` (`routes/app.tsx`) → o `AppShell`, com o `beforeLoad` que
 *    exige sessão ativa.
 *
 * `createRootRouteWithContext` e não `createRootRoute`: é o que dá tipo ao
 * `context.queryClient` dentro dos `beforeLoad` (ver `contexto.ts`). Sem ele o
 * contexto é `{}` e o `ensureQueryData` da sessão não compila.
 *
 * Os estados pendente, de erro e de não encontrado continuam a ser os defaults
 * do router (`router.tsx`) e não opções desta rota: as opções de rota não se
 * herdam, e os defaults valem para todas as rotas de uma vez. O ramo público
 * sobrepõe os seus, rota a rota, porque o painel dele é outro.
 */
export const rotaRaiz = createRootRouteWithContext<ContextoDoRouter>()();
