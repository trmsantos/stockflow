import type { QueryClient } from "@tanstack/react-query";

/**
 * O contexto do router: **só** o `QueryClient`, e nada mais.
 *
 * Existe por uma razão só, e é a da ADR 0010: o `beforeLoad` da rota do shell
 * corre **fora** da árvore de componentes, logo não pode usar `useQuery` — e a
 * sessão tem de ser lida antes de montar qualquer ecrã, senão o primeiro paint
 * de um deep link é o ecrã protegido e o redireccionamento vem depois.
 * `context.queryClient.query({ ...opcoesDaSessao(), staleTime: "static" })` é a
 * forma de ler a **única** cache que existe de dentro de um `beforeLoad` — a
 * ADR 0010 chama-lhe `ensureQueryData`, que é o nome que essa chamada tinha
 * antes de ser deprecada nesta versão da biblioteca (ver `app.tsx`).
 *
 * O que isto **não** é: não é o segundo caminho de dados que a ADR 0008 recusou.
 * Essa decisão proibiu `loader`, `loaderDeps` e `useLoaderData` — a cache do
 * router — e continua imposta pelo `no-restricted-syntax` do `eslint.config.js`.
 * O que a ADR 0008 recusou foi a **segunda** cache; isto é a primeira, lida de
 * outro sítio.
 *
 * O cliente entra por `createRouter({ context })` e não por um módulo global
 * (`export const queryClient = ...`): com um global, o `App.tsx` perdia o
 * controlo do ciclo de vida da cache e dois testes no mesmo processo
 * partilhariam-na sem o pedir.
 */
export interface ContextoDoRouter {
  readonly queryClient: QueryClient;
}
