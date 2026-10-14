import { Skeleton } from "@/components/ui/skeleton";
import { textos } from "../textos";

/**
 * Esqueleto da tabela de produtos enquanto carrega.
 *
 * Mantém o layout e previne o salto de conteúdo (CLS).
 */

export function SkeletonTabelaDeProdutos() {
  return (
    <div className="relative min-w-0 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border-strong bg-surface-2">
            <th className="h-linha px-celula-x py-0 text-left font-bold uppercase tracking-wider text-xs">
              {textos.colunas.artigo}
            </th>
            <th className="h-linha px-celula-x py-0 text-left font-bold uppercase tracking-wider text-xs">
              {textos.colunas.unidadeBase}
            </th>
            <th className="h-linha px-celula-x py-0 text-left font-bold uppercase tracking-wider text-xs">
              {textos.colunas.apresentacao}
            </th>
            <th className="h-linha px-celula-x py-0 text-center font-bold uppercase tracking-wider text-xs">
              {textos.colunas.lotes}
            </th>
            <th className="h-linha px-celula-x py-0 text-right font-bold uppercase tracking-wider text-xs">
              {textos.colunas.minimo}
            </th>
            <th className="h-linha px-celula-x py-0 text-center font-bold uppercase tracking-wider text-xs">
              {textos.colunas.estado}
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 7 }).map((_, i) => (
            <tr key={i} className="border-b border-border">
              <td className="h-linha px-celula-x py-0">
                <Skeleton className="h-4 w-32" />
              </td>
              <td className="h-linha px-celula-x py-0">
                <Skeleton className="h-4 w-12" />
              </td>
              <td className="h-linha px-celula-x py-0">
                <Skeleton className="h-4 w-16" />
              </td>
              <td className="h-linha px-celula-x py-0 text-center">
                <Skeleton className="h-4 w-8 mx-auto" />
              </td>
              <td className="h-linha px-celula-x py-0 text-right">
                <Skeleton className="h-4 w-12 ml-auto" />
              </td>
              <td className="h-linha px-celula-x py-0 text-center">
                <Skeleton className="h-4 w-14 mx-auto" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
