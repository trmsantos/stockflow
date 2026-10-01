import { Link } from "@tanstack/react-router";

import { ITENS_DA_TAB_BAR } from "./nav-items";

/**
 * A navegação de mobile: tab bar inferior com quatro itens (DESIGN.md §4).
 *
 * Quatro, e é o tipo `ItensDaTabBar` que o garante — não um comentário. A barra
 * tem 56px de altura (o orçamento de ecrã do guião §0: 360×640 menos 48 de
 * header e 56 daqui dão ~530px úteis) e cada alvo ocupa um quarto da largura,
 * logo nenhum fica abaixo dos 44px que o DESIGN.md §4 exige para toque.
 *
 * Está no DOM em desktop e escondida por breakpoint, como a sidebar. Fica
 * **fora** do `<main>` e depois dele na ordem do documento: quem navega por
 * teclado ou por leitor de ecrã chega ao conteúdo antes de chegar à navegação
 * secundária, e quem usa o polegar alcança-a sem esticar a mão.
 */
export function TabBar() {
  return (
    <nav
      aria-label="Navegação principal (mobile)"
      className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-border bg-surface md:hidden"
      // `env(safe-area-inset-bottom)` não é uma decisão de design: é a altura
      // da barra de gestos do telemóvel, que só o dispositivo conhece.
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {ITENS_DA_TAB_BAR.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          activeOptions={{ exact: item.to === "/" }}
          className="flex h-14 flex-col items-center justify-center gap-1 text-xs text-muted-foreground data-[status=active]:font-medium data-[status=active]:text-primary"
        >
          <item.icone aria-hidden="true" className="size-5 shrink-0" />
          {item.rotulo}
        </Link>
      ))}
    </nav>
  );
}
