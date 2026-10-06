import { z } from "zod";

import { mesSchema, periodoSchema } from "@/features/reporting/api";

/**
 * Os dois parâmetros do painel, no URL e validados — o estado que **define** o
 * ecrã pertence ao URL (ADR 0008, decisão 1).
 *
 * Sem isto, um recarregamento, o botão de voltar e um link mostrado a outra
 * pessoa não reproduzem o painel que se estava a ver — e este é o ecrã que o
 * dono vai mostrar a alguém. Vive em `src/routes/` porque o `validateSearch` é
 * contrato de rota e não produto (ADR 0008, decisão 2), por isso o ecrã não
 * importa este ficheiro: lê os valores já validados com
 * `useSearch({ from: "/app/" })`, tipados pela augmentação global do router.
 *
 * ## Os schemas vêm da feature, e a fronteira deixa
 *
 * `periodoSchema` e `mesSchema` são re-exportados pelo
 * `features/reporting/api.ts`, que é uma das duas portas que uma rota pode
 * atravessar (`screens/<ecrã>` e `api`, ADR 0008 decisão 2 e ADR 0010). A
 * alternativa era escrever aqui outra vez a lista fechada dos cinco períodos —
 * uma segunda definição do mesmo parâmetro, que divergiria da do contrato na
 * primeira vez que um período entrasse ou saísse. Os cinco valores são os do
 * `GET /reporting/summary`; é literalmente o mesmo parâmetro.
 *
 * ## `.catch(undefined)` nos dois, e ausente **é** o default
 *
 * Um URL malformado degrada para o default em vez de explodir dentro do ecrã, e
 * `/` continua a ser um URL limpo — não há duas representações do mesmo estado.
 * É também o que permite navegar com `{ month: undefined }` para **limpar** o
 * parâmetro, porque o serializador do router omite as chaves com valor
 * `undefined`.
 *
 * Os defaults vivem no ecrã e não aqui, e com razão escrita: o período é `7d`
 * (a única janela que tem sempre gráfico — ver `BarraDoPainel`) e o mês é o
 * **último fechado** (ver `features/reporting/meses.ts`, que explica porque é
 * que abrir no mês a correr mostraria um falso prejuízo do dia 1 ao dia 20).
 * Um default escrito no `validateSearch` ficava no URL a cada navegação e
 * passava a haver duas formas de dizer a mesma coisa.
 *
 * ## Dois parâmetros e não um, porque são dois grãos
 *
 * `period` é o que está a acontecer; `month` é o fecho, com salários. Um salário
 * é um facto mensal e ratear 30 dias por uma janela de 7 inventa precisão que
 * ninguém tem (ADR 0013, decisão 5) — por isso mexer num não mexe no outro, e é
 * por isso que são duas chaves.
 */
export const buscaDoPainelSchema = z.object({
  /** A janela do bloco de período. Ausente = `7d`, decidido no ecrã. */
  period: periodoSchema.optional().catch(undefined),
  /**
   * O mês do bloco de fecho, `YYYY-MM`. Ausente = o último mês fechado.
   *
   * Validado pelo formato e não contra uma lista de meses existentes: um
   * `?month=2019-03` é um mês válido de que este estabelecimento não tem dados,
   * e a resposta certa é o ecrã a dizer "não há nada registado" — não um erro de
   * validação que faz o painel inteiro cair.
   */
  month: mesSchema.optional().catch(undefined),
});

export type BuscaDoPainel = z.output<typeof buscaDoPainelSchema>;
