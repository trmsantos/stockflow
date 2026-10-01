import { Outlet } from "@tanstack/react-router";

import { AppHeader } from "./app-header";
import { SidebarNav } from "./sidebar-nav";
import { TabBar } from "./tab-bar";

/**
 * O invólucro da aplicação: **uma** árvore de componentes, para todos os
 * tamanhos de ecrã.
 *
 * O mobile/desktop do DESIGN.md §4 não é um problema de routing nem de estado:
 * a sidebar e a tab bar estão as duas no DOM e cada uma é escondida por
 * breakpoint (`hidden md:flex` / `md:hidden`). Isso tira-as também da árvore de
 * acessibilidade, logo não há navegação duplicada para um leitor de ecrã (ADR
 * 0008, decisão 1).
 *
 * O `pb-20` do `<main>` reserva os 56px da tab bar mais folga, para a última
 * linha de uma lista não ficar debaixo da barra — em mobile é o último item que
 * costuma ser o mais urgente, porque a ordem é "o que está pior primeiro".
 */
export function AppShell() {
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

      <SidebarNav />

      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader />
        <main id="conteudo" className="flex flex-1 flex-col pb-20 md:pb-0">
          <Outlet />
        </main>
      </div>

      <TabBar />
    </div>
  );
}
