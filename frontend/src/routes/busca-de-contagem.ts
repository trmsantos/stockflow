import { z } from "zod";

/**
 * Os filtros do ecrã Contar, no URL e validados — a mesma razão pela qual o ADR
 * 0008 escolheu este router, e aqui ainda mais literal do que no Stock: contar
 * é andar de zona em zona com o telemóvel na mão, e o ecrã tem de voltar à
 * **mesma zona** depois de um recarregamento, de um bloqueio de ecrã ou de uma
 * chamada a meio. Com a zona num `useState`, cada um desses acidentes mandava
 * quem está a contar de volta ao início do percurso.
 *
 * Só há um campo, e os que **não** estão aqui dizem mais:
 *
 *  - **não há `loja`.** A contagem já tem uma localização — é a dela, veio no
 *    payload — e um `?loja=` por cima seria uma segunda fonte de verdade sobre
 *    o que se está a contar;
 *  - **não há `oculto` nem `cego`.** Se o esperado aparece é decisão do
 *    servidor, zona a zona (é a sonda da contagem cega do guião §3): um
 *    interruptor no URL deixava o cliente desligar uma contagem cega, e aí não
 *    havia sonda — havia uma preferência.
 *
 * A `zona` é o `slug` e não o nome: é o que o servidor manda em
 * `zone.slug` e o único valor que o cliente pode pôr no URL sem guardar um
 * catálogo de zonas que não é dele. Tem `.catch(undefined)` como os do Stock,
 * e pela mesma razão medida lá: é o `.catch` que garante que a chave chega ao
 * ecrã sempre presente, pelo que o valor cru do URL nunca sobrevive à fusão que
 * o router faz.
 */
export const buscaDeContagemSchema = z.object({
  /** A zona a contar. Ausente = todas, na ordem do percurso físico. */
  zona: z.string().trim().max(40).optional().catch(undefined),
});

export type BuscaDeContagem = z.output<typeof buscaDeContagemSchema>;

/**
 * O fecho é outra rota (`/contar/fechar`) e leva a contagem no URL.
 *
 * Porque não lê a contagem aberta, como o ecrã de contar: depois de fechar, a
 * contagem **deixa de estar aberta**, e um ecrã que só soubesse encontrar a
 * aberta perdia o resultado que acabou de produzir no primeiro recarregamento.
 * Com o id no URL, a página do fecho continua a valer — e é um link que se pode
 * mostrar a alguém.
 */
export const buscaDeFechoSchema = z.object({
  contagem: z.uuid().optional().catch(undefined),
});

export type BuscaDeFecho = z.output<typeof buscaDeFechoSchema>;
