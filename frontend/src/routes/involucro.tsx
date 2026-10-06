import { useMemo } from "react";

import { usePodeConvidar, useSessaoDoShell } from "@/features/accounts/api";
import { AppShell } from "@/shell/app-shell";
import { esconderNoMenu, PROJECCAO_EM_CODIGO } from "@/shell/menu";
import type { RotaId } from "@/shell/registo-de-rotas";

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
 * da sessão que a encontrou; esta é a forma dela que não enfraquece nenhum dos
 * dois gates.
 *
 * ## O que esta ponte passou a carregar a 2026-10-06: a projecção do menu
 *
 * Entrou a primeira rota que **não é de todos os papéis** — `/convites`, que a
 * ADR 0010 dá ao `owner`, com a razão escrita: "é a resposta que não pode estar
 * errada enquanto a Q7 (o conjunto de papéis) é uma das onze perguntas por
 * confirmar com um utilizador real".
 *
 * Esconder esse item é **apresentação** (ADR 0009: "esconder é apresentação, não
 * autorização" — a rota continua a funcionar por deep link, e quem chega lá sem
 * o papel lê uma frase em vez de um 404). Mas é apresentação que depende de um
 * **domínio**, e nenhuma das duas camadas a podia fazer sozinha:
 *
 *  - o **shell** não sabe o que é um `owner`, e não deve: o `SessaoDoShell` nem
 *    deixa o `PapelEnum` atravessar a fronteira — o papel chega lá como string já
 *    traduzida, de propósito;
 *  - a **feature** não sabe o que é uma rota nem um item de menu: o
 *    `eslint.config.js` proíbe `src/features/**` de importar `@/shell/**`, logo
 *    ela não consegue sequer nomear um `RotaId`.
 *
 * Então a divisão é a mesma inversão de dependência de sempre, com mais um
 * degrau: o **shell** dá o mecanismo (`esconderNoMenu`, que é uma transformação
 * de dados sobre o `visivel` que a projecção já tinha), a **feature** dá o
 * predicado (`usePodeConvidar`, que é uma igualdade sobre o papel que o servidor
 * pôs na sessão) e a **rota** — aqui — é o único sítio que pode escrever a tabela
 * que liga um ao outro. Três linhas, num ficheiro cujo papel declarado já era
 * ligar os dois lados.
 *
 * O que isto **não** é: um controlo de acesso. Quem autoriza é o servidor, e foi
 * medido — `GET` e `POST /api/v1/convites` com sessão de um `staff` respondem 403.
 * Se este predicado estiver errado, o pior que acontece é um item a menos no menu
 * de alguém que podia usá-lo, e a rota continua lá para o deep link.
 *
 * ## Porque é que tem ficheiro próprio
 *
 * Medido: com o componente dentro do `app.tsx`, que exporta a rota, o
 * `react-refresh/only-export-components` dá exit 1 — um módulo que exporta uma
 * coisa que não é componente não pode ter fast refresh dos componentes que tem.
 * A casa não suprime lint (CLAUDE.md), e a forma que o linter pede é também a
 * melhor: o ficheiro de rota volta a ser caminho, `beforeLoad` e nada mais.
 *
 * **Não busca dados**: `useSessaoDoShell()` e `usePodeConvidar()` leem a **única**
 * cache que existe (a do TanStack Query), a mesma entrada que o `beforeLoad` da
 * rota já garantiu — montar isto não faz pedido nenhum.
 */

/**
 * As rotas que só o `owner` vê no menu.
 *
 * Uma tabela e não um `if`, porque a segunda entrada vai aparecer: a ADR 0010 diz
 * que "só `owner` convida e só `owner` configura", logo a configuração por tenant
 * da ADR 0011 cai exactamente aqui. Com um `if` solto, a segunda ficava noutro
 * sítio.
 *
 * ## Isto tem prazo, e o prazo está à vista
 *
 * No dia em que o `menu` do `SessaoOut` deixar de viajar vazio, a filtragem por
 * papel passa a ser **do servidor** (é o que a ADR 0011 decide, e é o sítio certo:
 * "esconder um item que um `staff` não pode usar é autorização"). A partir desse
 * dia a lista que o servidor manda já não traz o item, e manter este filtro era
 * ter **dois** a fazer a mesma coisa — e o de cá seria o que fica desactualizado
 * quando a segunda rota restrita aparecer.
 *
 * Logo a troca é esta, e é pequena de propósito: `montarMenu` passa a receber
 * `sessao.menu` em vez do `PROJECCAO_EM_CODIGO`, e este `useMemo`, o
 * `esconderNoMenu` do `menu.ts` e esta constante **saem**. O
 * `usePodeConvidar` **fica**: continua a ser preciso no ecrã, que tem de dizer
 * algo a quem chega por deep link sem o papel — e isso é apresentação, não
 * filtragem de menu.
 */
const SO_DO_DONO: readonly RotaId[] = ["convites"];

export function InvolucroDaAplicacao() {
  const sessao = useSessaoDoShell();
  const podeConvidar = usePodeConvidar();

  const projeccao = useMemo(
    () => (podeConvidar ? PROJECCAO_EM_CODIGO : esconderNoMenu(PROJECCAO_EM_CODIGO, SO_DO_DONO)),
    [podeConvidar],
  );

  return <AppShell sessao={sessao} projeccao={projeccao} />;
}
