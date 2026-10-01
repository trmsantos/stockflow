import { PorConstruir } from "@/components/por-construir";

/**
 * O ecrã Receber. A pasta é `purchasing` porque é o nome do módulo do backend
 * (`backend/apps/purchasing/`), e não `receber`: um ecrã é uma rota, uma
 * feature é um domínio (ADR 0008, decisão 2).
 */
export function EcraDeReceber() {
  return (
    <PorConstruir
      titulo="Receber"
      pergunta="O que chegou, e está certo?"
      conteudo="A lista de receções por revisar e, dentro de cada uma, as linhas da fatura com a conversão da unidade de compra para a de stock à vista, lote e validade por preencher. A receção existe sem encomenda e sem fatura prévia."
    />
  );
}
