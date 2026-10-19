import { z } from "zod";

/**
 * O **único** parâmetro do Assistente: que conversa está aberta.
 *
 * Vive em `src/routes/` porque o `validateSearch` é contrato de rota e não
 * produto (ADR 0008, decisão 2), e o ecrã lê-o já validado com
 * `useSearch({ from: "/app/assistente" })`.
 *
 * A conversa aberta define o ecrã, logo pertence ao URL (ADR 0027, decisão 10):
 * voltar atrás, recarregar e mostrar um link a alguém reproduzem-no. O que
 * **não** está aqui é o rascunho da pergunta — um rascunho não é uma vista
 * partilhável.
 *
 * Ausente = nenhuma conversa aberta, que é o estado inicial e a "nova
 * conversa" — não há duas representações do mesmo estado, e `/assistente`
 * continua a ser um URL limpo. O `.catch(undefined)` é a mesma rede medida no
 * `busca-de-stock.ts`: garante que a chave chega ao ecrã presente, e que um
 * `?conversa=1` escrito à mão cai no default em silêncio em vez de chegar ao
 * ecrã como um valor cru.
 */
export const buscaDeAssistenteSchema = z.object({
  conversa: z.uuid().optional().catch(undefined),
});

export type BuscaDeAssistente = z.output<typeof buscaDeAssistenteSchema>;
