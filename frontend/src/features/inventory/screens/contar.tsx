import { PorConstruir } from "@/components/por-construir";

/** O ecrã Contar — contagem de stock, por localização física. */
export function EcraDeContar() {
  return (
    <PorConstruir
      titulo="Contar"
      pergunta="O que está na prateleira é o que o sistema diz?"
      conteudo="Progresso e zona em curso no topo, um campo numérico grande por artigo e a ordem pela localização física — Balcão, Frigorífico, Arca, Armazém. Ao fechar, as diferenças em quantidade e em euros."
    />
  );
}
