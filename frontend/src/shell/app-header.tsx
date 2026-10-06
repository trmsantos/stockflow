import { useRouterState } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";

import { GavetaDeNavegacao } from "./gaveta-de-navegacao";
import { localizarNoMenu, type GrupoDeMenu } from "./menu";
import { rotuloDoCaminho } from "./registo-de-rotas";
import type { SessaoDoShell } from "./sessao-do-shell";

/**
 * A barra de topo: 56px (`h-cabecalho`, DESIGN.md §2), fixa, e o único sítio de
 * onde a navegação de mobile se abre.
 *
 * ## O que está aqui e porquê
 *
 * **O botão da gaveta** (`md:hidden`): em mobile a sidebar está escondida por
 * breakpoint, e a ADR 0009 diz que a navegação de telemóvel é a **mesma**
 * sidebar aberta daqui — não uma tab bar, não uma terceira superfície.
 *
 * **Onde se está, com o grupo**: "Inventário / Stock". O grupo vem da projecção
 * do tenant e o rótulo do item também, pelo que uma empresa que renomeie um
 * item vê o nome dela aqui. Num menu que cresce, o nome do ecrã sozinho não
 * situa.
 *
 * Não é um `<h1>`, e isso é deliberado: **todos** os ecrãs já têm o seu
 * (`sr-only` nos que são listas, visível nos de detalhe). Um segundo `<h1>` no
 * invólucro dava dois títulos de página a quem navega por cabeçalhos, e o que o
 * leitor de ecrã deve anunciar é o do ecrã — não o do cromado.
 *
 * **O que não está aqui**: o seletor de estabelecimento (é do pé da sidebar,
 * DESIGN.md §4) e o seletor de loja (é da barra do **ecrã** — parecem a mesma
 * coisa e não são).
 */
export function AppHeader({
  menu,
  sessao,
}: {
  readonly menu: readonly GrupoDeMenu[];
  readonly sessao: SessaoDoShell;
}) {
  const caminho = useRouterState({ select: (estado) => estado.location.pathname });
  const local = localizarNoMenu(menu, caminho);
  // Um item escondido pela projecção continua a ter rota e a ter nome: o
  // registo é a rede (ver `registo-de-rotas.ts`).
  const rotulo = local?.item.rotulo ?? rotuloDoCaminho(caminho);

  return (
    <header className="sticky top-0 z-20 flex h-cabecalho shrink-0 items-center gap-2 border-b border-border bg-surface px-2 md:px-celula-x">
      <GavetaDeNavegacao menu={menu} sessao={sessao} />

      {rotulo === null ? null : (
        <p className="flex min-w-0 items-center gap-2">
          {local === null ? null : (
            <>
              <span className="hidden shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase md:inline">
                {local.grupo}
              </span>
              <span aria-hidden="true" className="hidden shrink-0 text-muted-foreground md:inline">
                /
              </span>
            </>
          )}
          <span className="truncate text-sm font-semibold">{rotulo}</span>
        </p>
      )}

      {import.meta.env.DEV ? (
        // Em desenvolvimento os dados de domínio vêm do servidor de fixtures
        // (ADR 0008, decisão 3) — a autenticação, não: essa é o backend a
        // sério. Dizê-lo no ecrã é a mesma honestidade da abertura da sessão 0.
        // Em produção este ramo não existe.
        <Badge variant="outline" className="ml-auto shrink-0">
          dados de demonstração
        </Badge>
      ) : null}
    </header>
  );
}
