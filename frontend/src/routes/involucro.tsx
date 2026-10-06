import { useMenuDaSessao, useSessaoDoShell } from "@/features/accounts/api";
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
 * afirmações só são verdadeiras ao mesmo tempo com o shell a **declarar** as
 * interfaces (`shell/sessao-do-shell.ts` e a `EntradaDaProjeccao` do
 * `shell/menu.ts`) e o `accounts` a satisfazê-las — e esta camada é a única que
 * pode importar as duas, que é exactamente o papel que o shell já lhe dava ("é a
 * rota que liga o ecrã da feature ao invólucro", `shell/moldura-publica.tsx`).
 *
 * É também o único ponto onde o compilador consegue confrontar os dois lados: se
 * o `useSessaoDoShell` deixar de trazer `estabelecimentos`, ou se o `rotulo` do
 * `ItemDeMenuOut` mudar de forma, é este ficheiro que deixa de compilar. A
 * contradição entre as duas ADRs está apontada no relatório da sessão que a
 * encontrou (e na adenda 1 de 2026-10-06 da ADR 0009); esta é a forma dela que
 * não enfraquece nenhum dos dois gates.
 *
 * ## O que esta ponte deixou de carregar a 2026-10-06: o filtro de papel
 *
 * Durante uma sessão este ficheiro teve três linhas a esconder `/convites` de
 * quem não é `owner`, com uma tabela `SO_DO_DONO`, o `esconderNoMenu` do
 * `menu.ts` e um `useMemo`. Existiam porque o menu era uma constante de módulo e
 * a primeira rota de um papel só (ADR 0010) tinha de ser escondida em **algum**
 * sítio — e o comentário que as acompanhava dizia, com o prazo à vista, que elas
 * sairiam no dia em que o `menu` do `SessaoOut` deixasse de viajar vazio.
 *
 * Saíram. O menu vem do servidor já filtrado pelo papel, que é onde a ADR 0011
 * põe esse filtro ("esconder um item que um `staff` não pode usar é autorização
 * e não preferência"), e foi medido contra o backend a correr: a sessão de um
 * `owner` da Pastelaria Aurora traz seis itens, a de um `staff` do **mesmo**
 * estabelecimento traz cinco, sem o dos convites. Dois filtros a fazer o mesmo
 * são um a ficar desactualizado — e seria o de cá, na primeira rota restrita que
 * aparecesse sem ninguém se lembrar desta tabela.
 *
 * O `usePodeConvidar` **ficou**, e não é no menu que ele serve: o ecrã de
 * convites precisa dele para dizer algo a quem chega por deep link sem o papel,
 * em vez de disparar um `GET /convites` que já se sabe que dá 403. Esconder no
 * menu era apresentação; isto é o ecrã a falar.
 *
 * ## Porque é que tem ficheiro próprio
 *
 * Medido: com o componente dentro do `app.tsx`, que exporta a rota, o
 * `react-refresh/only-export-components` dá exit 1 — um módulo que exporta uma
 * coisa que não é componente não pode ter fast refresh dos componentes que tem.
 * A casa não suprime lint (CLAUDE.md), e a forma que o linter pede é também a
 * melhor: o ficheiro de rota volta a ser caminho, `beforeLoad` e nada mais.
 *
 * **Não busca dados**: os dois hooks leem a **única** cache que existe (a do
 * TanStack Query), a mesma entrada de `/auth/sessao` que o `beforeLoad` da rota
 * já garantiu — e o menu é um campo dessa resposta, não um segundo pedido
 * (ADR 0011: resolve-se com o que a sessão já resolveu). Montar isto não faz
 * pedido nenhum.
 */
export function InvolucroDaAplicacao() {
  const sessao = useSessaoDoShell();
  const projeccao = useMenuDaSessao();

  return <AppShell sessao={sessao} projeccao={projeccao} />;
}
