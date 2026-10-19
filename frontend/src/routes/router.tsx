import type { QueryClient } from "@tanstack/react-query";
import { createRoute, createRouter, lazyRouteComponent } from "@tanstack/react-router";

import { ErroDeEcra, EsqueletoDeEcra, NaoEncontrado } from "@/shell/estados-de-rota";

import { rotaDeAlertas } from "./alertas";
import { rotaDoAssistente } from "./assistente";
import { rotaDaApp } from "./app";
import { rotaDeArtigo } from "./artigo";
import { rotaDeAtivacao } from "./ativar";
import { rotaDeContar, rotaDeFechoDeContagem } from "./contar";
import { rotaDeDefinicoes } from "./definicoes";
import { rotaDeEntrada } from "./entrar";
import { rotaInicial } from "./inicio";
import { rotaDoPainel } from "./painel";
import { rotaPublica } from "./publico";
import { rotaDeFotografar, rotaDeRececao, rotaDeReceber } from "./receber";
import { rotaRaiz } from "./root";
import { rotaDeProdutos, rotaCriarProduto, rotaProdutoDetalhe } from "./produtos";
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
 * dados não apodrecer aqui dentro por distração. **Esse selector continua como
 * estava**, e a ADR 0010 explica porquê: há agora dois `beforeLoad` a chamar
 * `ensureQueryData`, mas o que a ADR 0008 recusou foi a **segunda** cache do
 * router, não ler a única que existe.
 *
 * ## Dois ramos por baixo da raiz, desde a ADR 0010
 *
 * A raiz deixou de ser o `AppShell` (ver `root.tsx`) e passou a ter dois filhos
 * sem caminho próprio:
 *
 *  - `rotaPublica` → `/entrar` e `/ativar`, num painel centrado, **sem** sessão;
 *  - `rotaDaApp` → o `AppShell` e os nove ecrãs, com o `beforeLoad` que exige
 *    sessão ativa. Dois deles **não são de todos os papéis**: `/convites` (ADR
 *    0010) e `/painel`, que a 2026-10-06 saiu do Início para ser o painel de
 *    gestão do dono. O que isso muda não é a árvore — as rotas existem para
 *    todos, porque esconder é apresentação e não autorização, e quem recusa é o
 *    servidor com um 403 — mas a projecção do menu, que é calculada no
 *    `involucro.tsx` a partir do que o `GET /auth/sessao` manda.
 *
 * Os URLs dos ecrãs não mudaram: uma rota de layout sem `path` não acrescenta
 * segmento nenhum.
 */

/**
 * A rota de desenvolvimento mantém a propriedade que teve desde o início: só
 * entra no array de filhos dentro do ramo `import.meta.env.DEV` **e o
 * `import()` fica dentro desse ramo**. No build o `import.meta.env.DEV` é
 * substituído por `false`, o ramo morre e o Rollup elimina o chunk — a página
 * não existe no bundle de produção, e isso é verificado por varredura do
 * `dist/`.
 *
 * Fica **dentro** do ramo da app, e portanto atrás do portão de sessão. É uma
 * escolha e tem um custo: ver a `/dev/tokens` passa a exigir um tenant semeado e
 * um login. A alternativa — pendurá-la na raiz, fora dos dois invólucros — era
 * pior por uma razão irónica: a página não tem `<main>` nem atalho de "saltar
 * para o conteúdo" porque os herda do `AppShell`, e tirá-la de lá produzia um
 * defeito de acessibilidade exactamente na página que mede acessibilidade. O
 * custo do login em dev já estava nomeado nas consequências da ADR 0010.
 */
const rotasDeDesenvolvimento = import.meta.env.DEV
  ? [
      createRoute({
        getParentRoute: () => rotaDaApp,
        path: "/dev/tokens",
        component: lazyRouteComponent(() => import("@/dev/tokens-page")),
      }),
    ]
  : [];

const arvoreDeRotas = rotaRaiz.addChildren([
  rotaPublica.addChildren([rotaDeEntrada, rotaDeAtivacao]),
  rotaDaApp.addChildren([
    rotaInicial,
    rotaDoPainel,
    rotaDeStock,
    rotaDeArtigo,
    rotaDeProdutos.addChildren([rotaCriarProduto, rotaProdutoDetalhe]),
    rotaDeReceber,
    rotaDeFotografar,
    rotaDeRececao,
    rotaDeContar,
    rotaDeFechoDeContagem,
    rotaDeAlertas,
    rotaDoAssistente,
    // A única rota da app **sem** entrada no registo de rotas, e por isso a
    // única que o menu não pode nomear nem esconder: definições não respondem a
    // uma pergunta de operação (ADR 0019). Substituiu as três que havia —
    // `/preferencias`, `/configuracao` e `/convites`.
    rotaDeDefinicoes,
    ...rotasDeDesenvolvimento,
  ]),
]);

/**
 * O router, criado a partir do `QueryClient` da aplicação.
 *
 * É uma **fábrica** e não um `const` de módulo desde a ADR 0010, e a razão é o
 * `beforeLoad`: ele precisa do `QueryClient` no `context`, e o cliente é criado
 * no `App.tsx` (uma vez por montagem, não por render). As duas alternativas
 * foram rejeitadas por serem a mesma coisa pior: um `queryClient` global de
 * módulo tira ao `App` o controlo do ciclo de vida da cache, e um
 * `context: { queryClient: undefined! }` com o valor real injectado no
 * `RouterProvider` precisa de uma asserção não-nula, que o
 * `typescript-eslint/strict` recusa — e bem, porque é uma mentira ao
 * compilador durante o intervalo em que ela é verdade.
 */
export function criarRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree: arvoreDeRotas,
    context: { queryClient },
    // Os três estados obrigatórios do DESIGN.md §3, uma vez para todas as
    // rotas. O ramo público sobrepõe o pendente e o de erro, rota a rota,
    // porque o painel dele não tem sidebar nem header.
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
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof criarRouter>;
  }
}
