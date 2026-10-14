import { textos } from "../textos";

/**
 * Tela de detalhe e edição de um produto.
 *
 * Por enquanto, uma tela stub que será completada na próxima iteração.
 * O objetivo é permitir que a lista de produtos compile e funcione.
 */

export function EcraDetalheProduto() {
  return (
    <div className="w-full max-w-2xl">
      <h1 className="text-lg font-semibold">{textos.detalhe.titulo}</h1>
      <p className="text-sm text-muted-foreground mt-2">
        {textos.detalhe.embreve}
      </p>
    </div>
  );
}
