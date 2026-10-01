import { Link, useRouterState } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";

import { rotuloDoCaminho } from "./nav-items";

/**
 * O header: 48px, fixo no topo (o orçamento de ecrã do guião §0).
 *
 * Em mobile a sidebar está escondida, por isso é aqui que vive o wordmark e o
 * nome do ecrã actual — quem está em pé, com pressa, tem de saber em que ecrã
 * está sem ler a lista de tabs. Não há seletor de estabelecimento nem avatar:
 * o shell não tem autenticação, e um seletor de tenant está explicitamente
 * proibido no guião §4 (pré-decidiria a Q9 e a Q11).
 */
export function AppHeader() {
  const caminho = useRouterState({ select: (estado) => estado.location.pathname });
  const rotulo = rotuloDoCaminho(caminho);

  return (
    <header className="sticky top-0 z-10 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
      <Link to="/" activeOptions={{ exact: true }} className="font-semibold tracking-tight md:hidden">
        StockFlow
      </Link>
      {rotulo === null ? null : (
        <span className="min-w-0 truncate text-sm text-muted-foreground">{rotulo}</span>
      )}
      {import.meta.env.DEV ? (
        // Em desenvolvimento os dados vêm do servidor de fixtures. Dizê-lo no
        // ecrã é a mesma honestidade que se diz na abertura da sessão 0: são
        // dados de demonstração. Em produção este ramo não existe.
        <Badge variant="outline" className="ml-auto shrink-0">
          dados de demonstração
        </Badge>
      ) : null}
    </header>
  );
}
