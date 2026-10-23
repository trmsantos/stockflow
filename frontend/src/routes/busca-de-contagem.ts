import { z } from "zod";

/**
 * Os filtros do ecrã Contar, no URL e validados — a mesma razão pela qual o ADR
 * 0008 escolheu este router, e aqui ainda mais literal do que no Stock: contar
 * é trabalho de pé com o telemóvel na mão, e o ecrã tem de voltar ao **mesmo
 * sítio** depois de um recarregamento, de um bloqueio de ecrã ou de uma chamada
 * a meio. Com o filtro num `useState`, cada um desses acidentes mandava quem
 * está a contar de volta ao princípio.
 *
 * ## A `zona` **é** a localização (ADR 0030, decisão 3)
 *
 * O schema não muda — continua a ser o `slug` que o servidor manda em
 * `zone.slug` — mas o que ele filtra mudou de nome: o servidor derruba o `slug`
 * do **nome da localização contada**, e há uma zona por contagem. "Contei a
 * câmara fria" responde-se abrindo uma contagem da câmara fria, e não
 * escolhendo uma zona dentro de outra coisa. Zonas como entidade própria —
 * tabela, ordem do percurso, atribuição artigo→zona — estão fora de âmbito por
 * extenso, e no dia em que existirem este campo serve-as sem mudar de forma.
 *
 * Um `slug` desconhecido dá **página vazia** e não erro, que é um estado que o
 * ecrã já tem e desenha.
 *
 * ## A `contagem` entrou porque deixou de haver "a" contagem (ADR 0033)
 *
 * Até aqui o ecrã encontrava a contagem a decorrer com um
 * `results.find(status === "open")` sobre a primeira página, e isso **era**
 * correcto enquanto o servidor garantia uma aberta por estabelecimento. Com a
 * exclusividade a passar a ser **por localização**, a arca e a despensa são
 * duas contagens legítimas ao mesmo tempo e aquela selecção ficou errada de
 * duas maneiras: assumia unicidade e dependia da paginação.
 *
 * Qual delas se está a contar passa a viver no URL, como o `/contar/fechar`
 * já fazia e como a ADR 0008 impõe. É o mesmo argumento do `zona`, e no
 * telemóvel ainda mais literal: quem conta de pé bloqueia o ecrã, atende uma
 * chamada e volta — e tem de voltar à contagem **daquela** localização, não à
 * mais recente.
 *
 * Sem `?contagem=`, o ecrã é a **lista das abertas** e não um palpite.
 * Escolher a primeira seria repor, dentro do cliente, a arbitrariedade que a
 * ADR 0033 tirou do servidor; e escolher automaticamente a única aberta
 * esconderia o botão de abrir exactamente de quem chega para contar **outra**
 * localização, que é o caso que esta fatia existe para desbloquear.
 *
 * Os campos que **não** estão aqui dizem mais do que o que está:
 *
 *  - **não há `loja`.** A contagem já tem uma localização — é a dela, veio no
 *    payload — e um `?loja=` por cima seria uma segunda fonte de verdade sobre
 *    o que se está a contar;
 *  - **não há `oculto` nem `cego`.** A contagem cega não existe nesta fatia (o
 *    `blind` do contrato é `false` e é facto, não marcador de lugar). Se um dia
 *    existir, quem a decide é o servidor: um interruptor no URL deixava o
 *    cliente desligá-la, e aí não havia regra — havia uma preferência.
 *
 * Tem `.catch(undefined)` como os do Stock, e pela mesma razão medida lá: é o
 * `.catch` que garante que a chave chega ao ecrã sempre presente, pelo que o
 * valor cru do URL nunca sobrevive à fusão que o router faz.
 */
export const buscaDeContagemSchema = z.object({
  /**
   * Qual das contagens abertas se está a contar. Ausente = a lista delas.
   *
   * Um `uuid` que não seja de nenhuma contagem aberta — um atalho guardado no
   * telemóvel, uma contagem que outra pessoa fechou entretanto — **não é
   * erro**: o ecrã di-lo e mostra o caminho para as que estão a decorrer.
   */
  contagem: z.uuid().optional().catch(undefined),
  /** A zona a contar — hoje, a localização. Ausente = a contagem toda. */
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
