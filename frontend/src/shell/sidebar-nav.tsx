import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { Button } from "@/components/ui/button";

import { MenuDeNavegacao } from "./menu-de-navegacao";
import type { GrupoDeMenu } from "./menu";
import { RodapeDaSidebar } from "./rodape-da-sidebar";
import type { SessaoDoShell } from "./sessao-do-shell";

/**
 * A sidebar de ERP: **persistente e colapsável** em desktop (DESIGN.md §4,
 * ADR 0009).
 *
 * Substitui a sidebar de quatro links do shell anterior, e a diferença não é de
 * tamanho — é de função. Um menu de ERP **cresce**: tem grupos, cabe um décimo
 * item sem se redesenhar nada, e é uma projecção por tenant (`menu.ts`). Uma tab
 * bar de quatro não carrega isso, e é por isso que ela saiu em vez de ganhar uma
 * quinta aba.
 *
 * Está sempre no DOM e é escondida por breakpoint (`hidden md:flex`), nunca por
 * `useMediaQuery`: um hook de media query daria duas árvores de componentes,
 * remontagens ao redimensionar e o invólucro errado no primeiro paint (ADR 0008,
 * decisão 1). O `hidden` também a tira da árvore de acessibilidade, logo em
 * mobile não há dois conjuntos de links para um leitor de ecrã percorrer — o que
 * lá está é a gaveta, e só quando está aberta.
 *
 * ## Recolhida: 56px, e o estado **não** persiste
 *
 * A largura recolhida é o token `w-cabecalho` (56px, a altura da barra de topo)
 * e não um número novo: a coluna recolhida fica quadrada com o cabeçalho, que é
 * o alinhamento que um painel de operação tem.
 *
 * O estado vive em memória e volta a "aberta" a cada recarregamento, de
 * propósito: a casa proíbe `localStorage` (SECURITY.md §7, e o
 * `no-restricted-syntax` recusa-o em qualquer ficheiro), e o sítio certo para
 * uma preferência destas é a configuração por tenant/utilizador da ADR 0011 —
 * que ainda não existe. Entre inventar um armazenamento proibido e perder a
 * preferência num F5, perde-se a preferência. Está no relatório como limitação
 * nomeada, não como esquecimento.
 */
export function SidebarNav({
  menu,
  sessao,
  recolhida,
  aoAlternar,
}: {
  readonly menu: readonly GrupoDeMenu[];
  readonly sessao: SessaoDoShell;
  readonly recolhida: boolean;
  readonly aoAlternar: () => void;
}) {
  const Icone = recolhida ? PanelLeftOpen : PanelLeftClose;
  const rotulo = recolhida ? "Expandir o menu" : "Recolher o menu";

  return (
    <nav
      aria-label="Navegação principal"
      className={`hidden shrink-0 flex-col border-r border-border bg-surface md:sticky md:top-0 md:flex md:h-dvh ${
        recolhida ? "md:w-cabecalho" : "md:w-sidebar"
      }`}
    >
      <div
        className={`flex h-cabecalho shrink-0 items-center gap-2 border-b border-border px-2 ${
          recolhida ? "justify-center" : ""
        }`}
      >
        {recolhida ? null : (
          <span className="flex min-w-0 items-center gap-2">
            {/* O trilho de 4px da identidade, ao lado do wordmark — a lâmpada do
                painel (DESIGN.md §2). Decoração: o nome está a seguir. */}
            <span aria-hidden="true" className="h-chip w-trilho shrink-0 bg-primary" />
            <span className="truncate text-sm font-bold tracking-microrotulo uppercase">
              StockFlow
            </span>
          </span>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={recolhida ? "shrink-0" : "ml-auto shrink-0"}
          aria-pressed={recolhida}
          title={rotulo}
          onClick={aoAlternar}
        >
          <Icone aria-hidden="true" />
          <span className="sr-only">{rotulo}</span>
        </Button>
      </div>

      <MenuDeNavegacao menu={menu} id="sidebar" recolhida={recolhida} />
      <RodapeDaSidebar sessao={sessao} id="sidebar" recolhida={recolhida} />
    </nav>
  );
}
