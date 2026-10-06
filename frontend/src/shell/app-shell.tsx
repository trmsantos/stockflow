import { Outlet } from "@tanstack/react-router";
import { useState } from "react";

import { AppHeader } from "./app-header";
import { montarMenu, PROJECCAO_EM_CODIGO } from "./menu";
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
 * O menu, montado **uma vez por módulo** a partir da projecção em código.
 *
 * É esta linha — e só esta — que muda no dia em que a projecção chegar por HTTP
 * (`SessaoOut.menu`, ADR 0011): passa a `montarMenu(sessao.menu)` dentro do
 * componente, e nem o `MenuDeNavegacao`, nem a sidebar, nem a gaveta, nem a
 * barra de topo mudam uma linha. Era isto que a ADR 0009 queria com "estruturado
 * para a projecção por tenant substituir a fonte sem reescrever o shell".
 */
const MENU = montarMenu(PROJECCAO_EM_CODIGO);

export function AppShell({ sessao }: { readonly sessao: SessaoDoShell }) {
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
        menu={MENU}
        sessao={sessao}
        recolhida={recolhida}
        aoAlternar={() => {
          setRecolhida((anterior) => !anterior);
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader menu={MENU} sessao={sessao} />
        <main id="conteudo" className="flex flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
