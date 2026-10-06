import { Outlet } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { AppHeader } from "./app-header";
import { montarMenu, type EntradaDaProjeccao } from "./menu";
import type { SessaoDoShell } from "./sessao-do-shell";
import { SidebarNav } from "./sidebar-nav";

/**
 * O invólucro da aplicação: **um** shell de ERP, desktop-primeiro, com o
 * telemóvel a servir as rotas de campo (DESIGN.md §4, ADR 0009).
 *
 * ## O que mudou a 2026-10-06, e o que não
 *
 * Saiu a **tab bar**. Não foi substituída por nada em baixo: a navegação é a
 * sidebar, persistente em desktop e a mesma numa gaveta em mobile. O que a ADR
 * 0009 recusa explicitamente é uma terceira superfície de navegação, e a tab bar
 * não podia ficar ao lado da sidebar porque um cap de quatro não carrega um menu
 * de ERP — que é a razão pela qual ela saiu em vez de ganhar uma quinta aba.
 *
 * Saiu com ela o `pb-20` do `<main>`, que reservava os 56px da barra: a última
 * linha de uma lista já não fica debaixo de nada. A outra dependência concreta
 * dessa altura estava no ecrã Receber (`bottom-[calc(3.5rem+env(...))]`) e saiu
 * no mesmo diff — era o único sítio onde os 56px da tab bar estavam escritos
 * fora do shell.
 *
 * Continua a não haver `useMediaQuery`: a sidebar está sempre no DOM e é
 * escondida por breakpoint (ADR 0008, decisão 1). A gaveta é um `Dialog`, logo
 * só existe enquanto está aberta, e o que ela mostra é o **mesmo** componente de
 * menu.
 *
 * ## A sessão entra por propriedade
 *
 * O `sessao` vem da rota (`routes/app.tsx`) e não de um hook daqui, porque o
 * shell não conhece domínios (ADR 0008, decisão 2) e o seletor de
 * estabelecimento é do shell (DESIGN.md §4). As duas coisas só são verdadeiras
 * ao mesmo tempo com o shell a **declarar** a interface e a feature a
 * satisfazê-la — a razão inteira está no `sessao-do-shell.ts`.
 *
 * ## As superfícies, e uma divergência do DESIGN.md §2 que é deliberada
 *
 * O §2 escreve o cromado assim: "sidebar no `background` e conteúdo no
 * `surface`". Aqui é o inverso — cromado (sidebar e barra de topo) no `surface`,
 * tela de conteúdo no `background` — e a razão é medível: os quatro ecrãs
 * construídos desenham os seus painéis e mosaicos em `bg-surface` sobre uma tela
 * `background`, e inverter o invólucro fazia **todos** eles deixarem de se ver,
 * por falta de contraste com a própria tela. Honrar a letra do §2 é redesenhar
 * os quatro ecrãs um degrau acima, que é obra própria e não o mínimo que a saída
 * da tab bar obriga. Fica apontado em vez de resolvido em silêncio.
 */

/**
 * ## A projecção entra por propriedade, desde 2026-10-06
 *
 * Era uma constante de módulo (`montarMenu(PROJECCAO_EM_CODIGO)`) com um
 * comentário a dizer que *esta* linha era a única que mudava no dia em que a
 * projecção deixasse de ser código. Esse dia chegou pela metade: a tabela
 * `accounts_tenantmenuitem` da ADR 0011 continua a não existir e o `SessaoOut.menu`
 * continua a viajar vazio, mas entrou a primeira rota que **não é de todos os
 * papéis** — `/convites`, que a ADR 0010 dá ao `owner` — e esconder um item por
 * papel é uma decisão que o shell não pode tomar: ele conhece caminhos de rota,
 * nunca domínios (ADR 0008, decisão 2).
 *
 * Então a projecção passou a entrar por propriedade, e a mudança é exactamente a
 * que estava prevista: quem a calcula é a rota (`routes/involucro.tsx`), que é a
 * única camada que pode ver o shell e a feature ao mesmo tempo. O
 * `MenuDeNavegacao`, a sidebar, a gaveta e a barra de topo não mudaram uma linha
 * — que era a propriedade que a ADR 0009 pedia. No dia em que a projecção chegar
 * por HTTP, muda o argumento na rota e não há nada a fazer aqui.
 */
export function AppShell({
  sessao,
  projeccao,
}: {
  readonly sessao: SessaoDoShell;
  readonly projeccao: readonly EntradaDaProjeccao[];
}) {
  // `useMemo` e não um `const` de render: o menu é a identidade que o
  // `MenuDeNavegacao`, a sidebar e a gaveta recebem, e recalculá-lo a cada render
  // dava três árvores novas de cada vez que a sidebar recolhe.
  const menu = useMemo(() => montarMenu(projeccao), [projeccao]);

  // Em memória, e volta a aberta a cada recarregamento: a razão (e a dívida)
  // está no `sidebar-nav.tsx`.
  const [recolhida, setRecolhida] = useState(false);

  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      {/* Primeiro elemento focável da página: quem navega por teclado salta a
          sidebar inteira com um Tab e um Enter. */}
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-30 focus:rounded-lg focus:border focus:border-border-strong focus:bg-surface focus:px-3 focus:py-2 focus:text-sm"
      >
        Saltar para o conteúdo
      </a>

      <SidebarNav
        menu={menu}
        sessao={sessao}
        recolhida={recolhida}
        aoAlternar={() => {
          setRecolhida((anterior) => !anterior);
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader menu={menu} sessao={sessao} />
        <main id="conteudo" className="flex flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
