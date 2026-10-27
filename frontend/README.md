# frontend — StockFlow

React 18 · TypeScript strict · Vite · Tailwind v4 · shadcn/ui · TanStack Router · TanStack Query · Zod.
`pnpm` sempre; nunca `npm` nem `yarn` (CLAUDE.md).

## Comandos

| Comando | O que faz |
|---|---|
| `pnpm dev` | Vite em `http://localhost:5183` (ADR 0002), com `/api` em proxy para `http://127.0.0.1:8010` |
| `pnpm build` | Build de produção para `dist/` |
| `pnpm preview` | Serve o `dist/` na mesma porta |
| `pnpm typecheck` | `tsc --noEmit`, strict |
| `pnpm lint` | ESLint (type-aware) **e** `scripts/check-design-tokens.mjs` **e** `scripts/check-fixtures.mjs` |
| `pnpm gen:api` | serializers → `openapi/schema.yaml` → `src/lib/api/types.ts` |

Portas sobreponíveis por ambiente, sem prefixo `VITE_` porque não entram no bundle:
`FRONTEND_DEV_PORT` (default 5183; o contentor do compose usa 5173) e `BACKEND_ORIGIN`.

**Não há mais variáveis de desenvolvimento.** Havia quatro — `FIXTURES_ATRASO_MS`,
`FIXTURES_VAZIO`, `FIXTURES_ERRO` e `FIXTURES_SEM_SESSAO` — e saíram com o servidor de dados falsos
(ADR 0034, decisão 7). A perda está nomeada ali e repete-se aqui: os estados "vazio", "erro" e
"sessão expirada a meio" deixaram de ter gatilho. O vazio passa a ser um estabelecimento semeado sem
stock (ADR 0018); os outros dois não têm hoje substituto.

## Onde estão as decisões

- **`src/routes/`** — a árvore de rotas em código (ADR 0008). Um ficheiro por rota: caminho,
  `lazyRouteComponent` e, quando houver filtros, `validateSearch` com Zod. Sem JSX de produto e sem
  buscar dados; se um ficheiro de rota passa de umas vinte linhas, a lógica está no sítio errado.
  **Sem `loader`, `loaderDeps` nem `useLoaderData`** — a única camada de dados é o TanStack Query, e
  o `eslint.config.js` tem um selector contra os três.
- **`src/shell/`** — o invólucro de ERP (ADR 0009): `AppShell`, `SidebarNav` (persistente e
  colapsável), `GavetaDeNavegacao` (a **mesma** sidebar num drawer em mobile), `AppHeader`,
  `RodapeDaSidebar` (o seletor de estabelecimento), `registo-de-rotas.ts`, `menu.ts` e os três
  estados de rota. **Não há tab bar** e não há uma terceira superfície de navegação. A sidebar está
  sempre no DOM e é escondida por breakpoint (`hidden md:flex`), nunca por `useMediaQuery`.
  - O **menu é dados**: uma projecção (`route_id`, `grupo`, `ordem`, `visivel`, `rotulo`) sobre um
    registo de rotas que é código. Hoje a projecção é um array em `menu.ts`; quando a tabela por
    tenant da ADR 0011 existir, muda a fonte e não o shell.
  - A garantia dos "4 itens" da tab bar morreu com ela, e **não foi substituída pela
    cardinalidade** — ninguém conta ao compilar uma lista que chega por HTTP. No lugar ficou a
    **integridade referencial**: um `Record<RotaId, …>` exaustivo nos dois sentidos e um `caminho`
    tipado pela própria árvore de rotas. Três sondas medidas: caminho inexistente, id a mais e id a
    menos dão todos exit 1 no `pnpm typecheck`.
  - O shell **não conhece domínios** (ADR 0008, decisão 2) e ainda assim desenha o seletor de
    estabelecimento (DESIGN.md §4): declara a interface em `sessao-do-shell.ts`, o `accounts`
    satisfaz-na e quem os liga é `routes/involucro.tsx` — a única camada que pode importar os dois,
    e onde o `pnpm typecheck` confronta os dois lados.
- **`src/features/<módulo>/`** — produto, com os nomes dos módulos do backend (`inventory`,
  `purchasing`, …), não nomes de ecrã. Dentro: `screens/`, `components/`, `hooks/`, `api.ts`,
  `schemas.ts`. As quatro fronteiras entre `routes/`, `features/`, `shell/` e `lib/`+`components/`
  são quatro blocos `no-restricted-imports` no `eslint.config.js`, cada um medido com uma sonda.
- **`src/styles/tokens.css`** — os 18 tokens de cor do DESIGN.md §2, a escala tipográfica, a
  grelha de 4px, as medidas de densidade, os raios, as duas sombras e o movimento. **Uma paleta só,
  escura** (identidade "Cabine", escolhida a 2026-10-01): não há `prefers-color-scheme`, há
  `color-scheme: dark`, e o modo claro é dívida nomeada no DESIGN.md §2 — o `pnpm lint` falha se
  alguém começar um segundo modo e o deixar a meio. **Nenhuma cor vive fora deste ficheiro.**
- `src/styles/base.css` — liga os tokens aos elementos: alvos de toque ≥ 44px em
  `pointer: coarse`, `prefers-reduced-motion`, `tabular-nums` em `[data-numeric]`.
- `src/styles/fonts.css` — Archivo 500/600/700 (a família não tem 400) e IBM Plex Mono 400,
  subconjunto latin, `woff2`, servidas do bundle. A CSP de produção é `font-src 'self'`: um
  `@import` do Google Fonts compilaria, passaria em dev e seria bloqueado em produção. O gate falha
  se um token de fonte apontar para uma família sem `@font-face`.
- `src/components/ui/` — shadcn via CLI. Não editar à mão: personaliza-se pelos tokens.
- `src/lib/api/` — cliente HTTP (cookie de sessão, `X-CSRFToken`, `X-Tenant-ID`), chaves de
  query por tenant, paginação (50/página) e os tipos gerados.
- `src/lib/format.ts` — `Intl` para pt-PT: quantidades com 3 decimais, euros, datas e dias
  relativos. Nenhum formato à mão.

## `fixtures/` — apagada, e o gate que o prova ficou

Houve uma pasta `fixtures/`, fora de `src/`, servida por um plugin do Vite com `apply: "serve"` que
respondia aos `/api/v1/…` que o Django ainda não tinha (ADR 0008, decisão 3). A promessa era que o
`api.ts` de cada feature se escrevia na forma final desde o primeiro dia — mesmo `fetch`, mesmo
cookie, mesmo `X-Tenant-ID`, mesmo envelope, mesmo Zod — e que a remoção era por recurso, sem um
ecrã mudar uma linha. **A ADR 0034 cobrou a promessa e ela pagou-se**: com os sete recursos do Stock
e dos Alertas ligados ao Django, o último fixture saiu, a pasta foi-se, e com ela a linha do
`vite.config.ts` e a entrada no `include` do `tsconfig.json`.

**O `scripts/check-fixtures.mjs` fica**, e é por isso que esta secção também fica. Ele falha nos
dois sentidos: com a pasta, exigia que nada em `src/` a importasse, que o plugin tivesse
`apply: "serve"` e que todo o ficheiro trouxesse a sentinela `dados-falsos-stockflow`; **sem** a
pasta, exige que o `vite.config.ts` e o `tsconfig.json` já não falem dela. É ele que torna "a
decisão 3 terminou por apagamento" uma medição e não uma frase.

## `/dev/tokens`

Rota só de desenvolvimento (`import.meta.env.DEV` + `lazyRouteComponent`, com o `import()` dentro
do ramo morto, eliminada do bundle de produção).
Mostra os 18 tokens como o browser os resolve, **mede** o contraste WCAG de cada par na paleta em
vigor, e exibe os três papéis de cada cor de estado, as duas bordas lado a lado, a escala
tipográfica, o espaçamento, os dois níveis de sombra e os estados de componente e de dados.
As duas rotas de comparação de identidade (`/dev/identidade-a` e `-b`) foram apagadas quando o dono
do produto escolheu a "Cabine": a proposta vencedora é o `tokens.css`.

## O que está deliberadamente ausente

- **Autenticação.** O shell não tem login e portanto não tem rota protegida: o `beforeLoad` que
  redirecciona entra com a sessão da autenticação, e é lá que se decide o ecrã de escolha de
  estabelecimento que o ADR 0007 deixou em aberto no cliente.
- **Devtools** do router e do Query: nenhum dos dois está instalado.
- **Endpoints.** O `paths` do schema OpenAPI está vazio porque a API ainda não tem rotas; o
  `src/lib/api/types.ts` gerado reflete isso e é o resultado correto.
- **Qualquer `VITE_*`.** Tudo o que começa por `VITE_` vai para o bundle público (SECURITY.md §7).
  A API é sempre relativa (`/api/v1`), na mesma origem.
