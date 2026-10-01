import { createRoute, createRouter, lazyRouteComponent } from "@tanstack/react-router";

import { ErroDeEcra, EsqueletoDeEcra, NaoEncontrado } from "@/shell/estados-de-rota";

import { rotaDeAlertas } from "./alertas";
import { rotaDeContar } from "./contar";
import { rotaInicial } from "./inicio";
import { rotaDeReceber } from "./receber";
import { rotaRaiz } from "./root";
import { rotaDeStock } from "./stock";

/**
 * A árvore de rotas, **em código** (ADR 0008, decisão 1).
 *
 * Sem o plugin de rotas por ficheiro: um artefacto gerado-e-commitado com gate
 * de diff já existe (`src/lib/api/types.ts`) e um é o que basta; a árvore tem
 * meia dúzia de rotas; e a convenção de nomes do plugin ditaria a pasta das
 * features, que é decisão de arquitetura e não de ferramenta.
 *
 * Code-splitting é **manual**, rota a rota, com `lazyRouteComponent`. Esquecer
 * o `lazyRouteComponent` manda o ecrã para o chunk principal em silêncio, e
 * isto fica nomeado e sem mecanismo — está escrito assim na ADR.
 *
 * Não há `loader`, `loaderDeps` nem `useLoaderData` em sítio nenhum: a única
 * camada de dados é o TanStack Query. O `no-restricted-syntax` do
 * `eslint.config.js` tem um selector contra os três, para o segundo caminho de
 * dados não apodrecer aqui dentro por distração. No dia em que uma rota
 * precisar de `ensureQueryData`, tirar o selector é um diff visível com uma
 * razão.
 */

/**
 * A `/dev/tokens` mantém a propriedade que já tinha: a rota só entra no array
 * de filhos dentro do ramo `import.meta.env.DEV` **e o `import()` fica dentro
 * desse ramo**. No build o `import.meta.env.DEV` é substituído por `false`, o
 * ramo morre e o Rollup elimina o chunk — a página não existe no bundle de
 * produção, e isso é verificado por varredura do `dist/`.
 */
const rotasDeDesenvolvimento = import.meta.env.DEV
  ? [
      createRoute({
        getParentRoute: () => rotaRaiz,
        path: "/dev/tokens",
        component: lazyRouteComponent(() => import("@/dev/tokens-page")),
      }),
    ]
  : [];

const arvoreDeRotas = rotaRaiz.addChildren([
  rotaInicial,
  rotaDeStock,
  rotaDeReceber,
  rotaDeContar,
  rotaDeAlertas,
  ...rotasDeDesenvolvimento,
]);

export const router = createRouter({
  routeTree: arvoreDeRotas,
  // Os três estados obrigatórios do DESIGN.md §3, uma vez para todas as rotas.
  defaultPendingComponent: EsqueletoDeEcra,
  defaultErrorComponent: ErroDeEcra,
  defaultNotFoundComponent: NaoEncontrado,
  // Pré-carrega o **chunk** da rota ao passar o rato ou ao tocar: não há
  // loaders, logo não há dados a pré-carregar aqui. Numa cozinha com Wi-Fi mau
  // é a diferença entre tocar numa tab e esperar pelo JavaScript.
  defaultPreload: "intent",
  // Voltar atrás numa lista longa devolve a posição onde se estava — e a lista
  // está ordenada por "o que está pior primeiro", logo perder a posição é
  // perder o lugar na fila de problemas.
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
