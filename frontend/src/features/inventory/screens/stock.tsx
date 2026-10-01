import { PorConstruir } from "@/components/por-construir";

/**
 * O ecrã Stock. Ainda não mostra stock: a API não tem `/api/v1/stock/levels` do
 * lado do Django, e o `schemas.ts` desta feature é o rascunho do contrato que a
 * sessão do backend vai receber.
 */
export function EcraDeStock() {
  return (
    <PorConstruir
      titulo="Stock"
      pergunta="O que é que eu tenho, e quanto?"
      conteudo="Três números tocáveis no topo — em falta, a expirar em 3 dias, valor em euros — e uma linha por artigo com quantidade, estado e a validade mais próxima, o que está pior primeiro."
    />
  );
}
