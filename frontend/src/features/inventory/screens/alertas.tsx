import { PorConstruir } from "@/components/por-construir";

/**
 * O ecrã Alertas. Três perguntas numa tab, resolvidas com três contadores e
 * **uma** lista — e com a distinção entre "consumir até" e "consumir de
 * preferência antes de", que é a condição para o dono confiar nos alertas.
 */
export function EcraDeAlertas() {
  return (
    <PorConstruir
      titulo="Alertas"
      pergunta="O que expira? O que falta? Quanto deitei fora?"
      conteudo="Três contadores e uma lista: lote, validade e quantidade em risco, com o limiar à vista dentro do próprio alerta. Um toque na linha regista que foi deitado fora; o segundo escolhe o motivo."
    />
  );
}
