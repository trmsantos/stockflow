import { isApiError } from "@/lib/api/errors";

import { textos } from "./textos";

/**
 * As recusas de uma pergunta — o que o servidor responde **em vez** de criar
 * um turno (ADR 0027, decisão 4), mais as duas que não têm `code`.
 *
 * Cada uma é um título, um corpo, uma tinta e um booleano: se repetir a mesma
 * pergunta faz sentido. Só na rede faz — nas outras a resposta não muda com o
 * tempo (503 é configuração, 429 é amanhã, os dois 409 pedem outra acção), e um
 * "tentar outra vez" ali era um botão a prometer o que não pode cumprir.
 *
 * A tinta é a do DESIGN.md §2: `aviso` (`warning-surface`) para o que não é um
 * defeito — o assistente não está ligado, o teto chegou, ainda estou a
 * responder, a conversa encheu —, e `erro` (`danger-surface`) para o que falhou.
 * O 503 é aviso e não erro de propósito: não há nada partido, há uma função que
 * este estabelecimento não activou, e a frase não expõe de que é que ela
 * precisa (modelo, chave) a quem não a pode configurar.
 */

export type CodigoDaRecusa =
  | "assistente_indisponivel"
  | "teto_diario_atingido"
  | "resposta_pendente"
  | "conversa_cheia"
  | "pergunta_invalida"
  | "muitas_seguidas"
  | "sem_ligacao";

export interface Recusa {
  readonly codigo: CodigoDaRecusa;
  readonly titulo: string;
  readonly corpo: string;
  readonly tinta: "aviso" | "erro";
  readonly repetivel: boolean;
}

export function lerRecusa(erro: unknown): Recusa {
  if (isApiError(erro)) {
    switch (erro.code) {
      case "assistente_indisponivel":
        return {
          codigo: "assistente_indisponivel",
          titulo: textos.recusas.indisponivelTitulo,
          corpo: textos.recusas.indisponivelCorpo,
          tinta: "aviso",
          repetivel: false,
        };
      case "teto_diario_atingido":
        return {
          codigo: "teto_diario_atingido",
          titulo: textos.recusas.tetoTitulo,
          corpo: textos.recusas.tetoCorpo,
          tinta: "aviso",
          repetivel: false,
        };
      case "resposta_pendente":
        return {
          codigo: "resposta_pendente",
          titulo: textos.recusas.pendenteTitulo,
          corpo: textos.recusas.pendenteCorpo,
          tinta: "aviso",
          repetivel: false,
        };
      case "conversa_cheia":
        return {
          codigo: "conversa_cheia",
          titulo: textos.recusas.cheiaTitulo,
          corpo: textos.recusas.cheiaCorpo,
          tinta: "aviso",
          repetivel: false,
        };
      default:
        break;
    }
    // O 400 do serializer vem com a recusa por campo e sem `code`.
    if (erro.status === 400) {
      return {
        codigo: "pergunta_invalida",
        titulo: textos.recusas.perguntaInvalidaTitulo,
        corpo: textos.recusas.perguntaInvalidaCorpo,
        tinta: "erro",
        repetivel: false,
      };
    }
    // O throttle do DRF (10/min nas escritas) responde 429 **sem** `code`: o
    // teto diário tem o dele e já saiu acima.
    if (erro.status === 429) {
      return {
        codigo: "muitas_seguidas",
        titulo: textos.recusas.muitasSeguidasTitulo,
        corpo: textos.recusas.muitasSeguidasCorpo,
        tinta: "aviso",
        repetivel: false,
      };
    }
    return {
      codigo: "sem_ligacao",
      titulo: textos.recusas.redeTitulo,
      corpo: erro.detail ?? textos.recusas.redeCorpo,
      tinta: "erro",
      repetivel: true,
    };
  }
  // Um `TypeError` do `fetch`: a rede. O `message` dele é do browser e em
  // inglês, logo não se mostra.
  return {
    codigo: "sem_ligacao",
    titulo: textos.recusas.redeTitulo,
    corpo: textos.recusas.redeCorpo,
    tinta: "erro",
    repetivel: true,
  };
}
