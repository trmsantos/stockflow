import { useSessaoDoShell } from "@/features/accounts/api";
import { AppShell } from "@/shell/app-shell";

/**
 * O invólucro da aplicação com a sessão ligada — **a ponte entre a feature e o
 * shell**, e o sítio onde o `pnpm typecheck` a verifica.
 *
 * ## Porque é que isto é uma rota e não shell nem feature
 *
 * O shell desenha o seletor de estabelecimento no pé da sidebar (DESIGN.md §4,
 * ADR 0009) e **não pode conhecer domínios** (ADR 0008, decisão 2, imposta pelo
 * `eslint.config.js`: `src/shell/**` não importa `@/features/*`). As duas
 * afirmações só são verdadeiras ao mesmo tempo com o shell a **declarar** a
 * interface (`shell/sessao-do-shell.ts`) e o `accounts` a satisfazê-la — e esta
 * camada é a única que pode importar as duas, que é exactamente o papel que o
 * shell já lhe dava ("é a rota que liga o ecrã da feature ao invólucro",
 * `shell/moldura-publica.tsx`).
 *
 * É também o único ponto onde o compilador consegue confrontar os dois lados: se
 * o `useSessaoDoShell` deixar de trazer `estabelecimentos`, é este ficheiro que
 * deixa de compilar. A contradição entre as duas ADRs está apontada no relatório
 * desta sessão; esta é a forma dela que não enfraquece nenhum dos dois gates.
 *
 * ## Porque é que tem ficheiro próprio
 *
 * Medido: com o componente dentro do `app.tsx`, que exporta a rota, o
 * `react-refresh/only-export-components` dá exit 1 — um módulo que exporta uma
 * coisa que não é componente não pode ter fast refresh dos componentes que tem.
 * A casa não suprime lint (CLAUDE.md), e a forma que o linter pede é também a
 * melhor: o ficheiro de rota volta a ser caminho, `beforeLoad` e nada mais.
 *
 * **Não busca dados**: `useSessaoDoShell()` lê a **única** cache que existe (a
 * do TanStack Query), a mesma entrada que o `beforeLoad` da rota já garantiu —
 * montar isto não faz pedido nenhum.
 */
export function InvolucroDaAplicacao() {
  const sessao = useSessaoDoShell();
  return <AppShell sessao={sessao} />;
}
