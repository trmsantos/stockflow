import { textos } from "../textos";

/**
 * Tela de criação de novo produto.
 *
 * Por enquanto, uma tela stub que será completada na próxima iteração.
 * O objetivo é permitir que a lista de produtos compile e funcione.
 */

export function EcraNovoProduto() {
  return (
    <div className="w-full max-w-2xl">
      <h1 className="text-lg font-semibold">{textos.novo.titulo}</h1>
      <p className="text-sm text-muted-foreground mt-2">
        {textos.novo.embreve}
      </p>
    </div>
  );
}
