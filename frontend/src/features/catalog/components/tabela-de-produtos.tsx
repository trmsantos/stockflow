import { Link } from "@tanstack/react-router";
import type { Produto } from "../schemas";
import { textos } from "../textos";

/**
 * Tabela densa de produtos do catálogo.
 *
 * Colunas (da esquerda para a direita):
 * - Nome (link para editar)
 * - Unidade base
 * - Unidade de apresentação
 * - Rastreio de lotes (Sim/Não)
 * - Quantidade mínima
 * - Estado (ativo/inativo)
 */

export function TabelaDeProdutos({ produtos }: { readonly produtos: readonly Produto[] }) {
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
          {produtos.map((produto) => (
            <tr key={produto.id} className="border-b border-border">
              <td className="h-linha px-celula-x py-0">
                <Link
                  to="/produtos/$produtoId"
                  params={{ produtoId: produto.id }}
                  className="text-primary hover:underline"
                >
                  {produto.short_name}
                </Link>
              </td>
              <td className="h-linha px-celula-x py-0 text-muted-foreground">
                {produto.base_unit}
              </td>
              <td className="h-linha px-celula-x py-0 text-muted-foreground">
                {produto.display_unit}
              </td>
              <td className="h-linha px-celula-x py-0 text-center">
                {produto.track_lots ? textos.catalogo.sim : textos.catalogo.nao}
              </td>
              <td className="h-linha px-celula-x py-0 text-right font-variant-numeric">
                {produto.min_quantity} {produto.display_unit}
              </td>
              <td className="h-linha px-celula-x py-0 text-center">
                <span
                  className={
                    produto.is_active
                      ? "text-success"
                      : "text-muted-foreground"
                  }
                >
                  {produto.is_active ? "Ativo" : "Inativo"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
