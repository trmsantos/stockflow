import { Link } from "@tanstack/react-router";

import { ITENS_DE_NAVEGACAO } from "./nav-items";

/**
 * A navegação de desktop: sidebar fixa (DESIGN.md §4).
 *
 * Está sempre no DOM e é escondida por breakpoint (`hidden md:flex`), nunca por
 * `useMediaQuery` — um hook de media query daria duas árvores de componentes,
 * remontagens ao redimensionar e o invólucro errado no primeiro paint (ADR
 * 0008, decisão 1). O `hidden` também a tira da árvore de acessibilidade, logo
 * em mobile não há dois conjuntos de links para um leitor de ecrã percorrer.
 */
export function SidebarNav() {
  return (
    <nav
      aria-label="Navegação principal"
      className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface p-2 md:sticky md:top-0 md:flex md:h-dvh"
    >
      <Link
        to="/"
        activeOptions={{ exact: true }}
        className="mb-2 flex min-h-11 items-center rounded-lg px-3 text-lg font-semibold tracking-tight"
      >
        StockFlow
      </Link>

      {ITENS_DE_NAVEGACAO.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          activeOptions={{ exact: item.to === "/" }}
          title={item.pergunta}
          className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm text-muted-foreground hover:bg-surface-2 hover:text-foreground data-[status=active]:bg-surface-2 data-[status=active]:font-medium data-[status=active]:text-foreground"
        >
          {/* O ícone é decoração: quem lê por áudio ouve o rótulo ao lado. */}
          <item.icone aria-hidden="true" className="size-4 shrink-0" />
          {item.rotulo}
        </Link>
      ))}
    </nav>
  );
}
