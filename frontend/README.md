# frontend — StockFlow

React 18 · TypeScript strict · Vite · Tailwind v4 · shadcn/ui · TanStack Query · Zod.
`pnpm` sempre; nunca `npm` nem `yarn` (CLAUDE.md).

## Comandos

| Comando | O que faz |
|---|---|
| `pnpm dev` | Vite em `http://localhost:5183` (ADR 0002), com `/api` em proxy para `http://127.0.0.1:8010` |
| `pnpm build` | Build de produção para `dist/` |
| `pnpm preview` | Serve o `dist/` na mesma porta |
| `pnpm typecheck` | `tsc --noEmit`, strict |
| `pnpm lint` | ESLint (type-aware) **e** `scripts/check-design-tokens.mjs` |
| `pnpm gen:api` | serializers → `openapi/schema.yaml` → `src/lib/api/types.ts` |

Portas sobreponíveis por ambiente, sem prefixo `VITE_` porque não entram no bundle:
`FRONTEND_DEV_PORT` (default 5183; o contentor do compose usa 5173) e `BACKEND_ORIGIN`.

## Onde estão as decisões

- **`src/styles/tokens.css`** — os 18 tokens de cor do DESIGN.md §2, a escala tipográfica, a
  grelha de 4px, os três raios, as duas sombras e o movimento. Modo escuro por
  `prefers-color-scheme`, com os 18 tokens redefinidos. **Nenhuma cor vive fora deste ficheiro.**
- `src/styles/base.css` — liga os tokens aos elementos: alvos de toque ≥ 44px em
  `pointer: coarse`, `prefers-reduced-motion`, `tabular-nums` em `[data-numeric]`.
- `src/styles/fonts.css` — IBM Plex Sans 400/500/600 e Mono 400, subconjunto latin, `woff2`,
  servidas do bundle. A CSP de produção é `font-src 'self'`: um `@import` do Google Fonts
  compilaria, passaria em dev e seria bloqueado em produção.
- `src/components/ui/` — shadcn via CLI. Não editar à mão: personaliza-se pelos tokens.
- `src/lib/api/` — cliente HTTP (cookie de sessão, `X-CSRFToken`, `X-Tenant-ID`), chaves de
  query por tenant, paginação (50/página) e os tipos gerados.
- `src/lib/format.ts` — `Intl` para pt-PT: quantidades com 3 decimais, euros, datas e dias
  relativos. Nenhum formato à mão.

## `/dev/tokens`

Rota só de desenvolvimento (`import.meta.env.DEV` + `lazy()`, eliminada do bundle de produção).
Mostra os 18 tokens como o browser os resolve, **mede** o contraste WCAG de cada par no modo
ativo, e exibe os três papéis de cada cor de estado, as duas bordas lado a lado, a escala
tipográfica, o espaçamento, os dois níveis de sombra e os estados de componente e de dados.

## O que está deliberadamente ausente

- **Router.** Escolher TanStack Router ou React Router é uma ADR, não um efeito colateral do
  passo de ferramentas. Até lá `src/routes/router.tsx` lê o caminho uma vez e os links são `<a>`.
- **Endpoints.** O `paths` do schema OpenAPI está vazio porque a API ainda não tem rotas; o
  `src/lib/api/types.ts` gerado reflete isso e é o resultado correto.
- **Qualquer `VITE_*`.** Tudo o que começa por `VITE_` vai para o bundle público (SECURITY.md §7).
  A API é sempre relativa (`/api/v1`), na mesma origem.
