import { z } from "zod";

import { abaSchema, mesSchema, periodoSchema } from "@/features/reporting/api";

/**
 * Os **quatro** parâmetros do painel, no URL e validados — o estado que
 * **define** o ecrã pertence ao URL (ADR 0008, decisão 1).
 *
 * Sem isto, um recarregamento, o botão de voltar e um link mostrado a outra
 * pessoa não reproduzem o painel que se estava a ver — e este é o ecrã que o
 * dono vai mostrar a alguém. Vive em `src/routes/` porque o `validateSearch` é
 * contrato de rota e não produto (ADR 0008, decisão 2), por isso o ecrã não
 * importa este ficheiro: lê os valores já validados com
 * `useSearch({ from: "/app/painel" })`, tipados pela augmentação global do
 * router.
 *
 * **Os quatro são da rota `/painel` e não do Início.** O painel saiu de `/` a
 * 2026-10-06 por decisão do dono do produto: é um ecrã **só do dono**, e o
 * Início passou a ser a fila de trabalho do dia, que toda a gente vê e que não
 * tem parâmetros nenhuns.
 *
 * ## Dois parâmetros de **grão** e dois de **camada**
 *
 * `period` e `month` dizem de que janela se fala; `aba` e `explicar` dizem
 * quanto do painel está à vista. Os dois primeiros vieram com a ADR 0013; os
 * dois últimos entraram a 2026-10-06, quando o dono do produto olhou para o
 * painel e disse que era confuso e que tinha demasiado conteúdo. Media **3630px
 * de altura**, com nove tabelas e cerca de trinta frases explicativas numa
 * coluna "O QUE É". Nenhuma dessas frases estava errada; juntas eram um manual
 * de instruções em vez de um painel.
 *
 * Nenhum dos dois é preferência de utilizador guardada em `localStorage`, e é
 * de propósito: um painel por camadas só serve se a camada aberta for
 * **partilhável**. "Olha esta linha, liga o explicar" é um link, não uma
 * instrução.
 *
 * ## Os schemas do grão vêm da feature, e a fronteira deixa
 *
 * `periodoSchema` e `mesSchema` são re-exportados pelo
 * `features/reporting/api.ts`, que é uma das duas portas que uma rota pode
 * atravessar (`screens/<ecrã>` e `api`, ADR 0008 decisão 2 e ADR 0010). A
 * alternativa era escrever aqui outra vez a lista fechada dos cinco períodos —
 * uma segunda definição do mesmo parâmetro, que divergiria da do contrato na
 * primeira vez que um período entrasse ou saísse. Os cinco valores são os do
 * `GET /reporting/summary`; é literalmente o mesmo parâmetro.
 *
 * A `aba` **também** vem de lá, e por uma razão diferente: não há campo nenhum
 * no contrato que lhe corresponda — é estado de apresentação —, mas a mesma
 * união tem de valer em dois sítios que não se vêem, o `validateSearch` que a
 * valida e o `Record` que lhe dá as palavras (`features/reporting/abas.ts`).
 * Escrita duas vezes, divergia na primeira aba que entrasse, e o sintoma era uma
 * aba válida no URL sem nome no ecrã.
 *
 * O `explicar` é o único que nasce aqui, e é o que se espera de um interruptor:
 * não tem vocabulário, não tem ordem e não tem mais nenhum sítio onde a sua
 * forma importe.
 *
 * ## `.catch(undefined)` nos quatro, e ausente **é** o default
 *
 * Um URL malformado degrada para o default em vez de explodir dentro do ecrã, e
 * `/` continua a ser um URL limpo — não há duas representações do mesmo estado.
 * É também o que permite navegar com `{ month: undefined }` para **limpar** o
 * parâmetro, porque o serializador do router omite as chaves com valor
 * `undefined`. É assim que o interruptor de explicação se desliga.
 *
 * Os defaults vivem no ecrã e não aqui, e com razão escrita: o período é `7d`
 * (a única janela que tem sempre gráfico — ver `BarraDoPainel`), o mês é o
 * **último fechado** (ver `features/reporting/meses.ts`, que explica porque é
 * que abrir no mês a correr mostraria um falso prejuízo do dia 1 ao dia 20), a
 * aba é `dinheiro` e a explicação está **desligada**. Um default escrito no
 * `validateSearch` ficava no URL a cada navegação e passava a haver duas formas
 * de dizer a mesma coisa.
 */
export const buscaDoPainelSchema = z.object({
  /** A janela do bloco de período. Ausente = `7d`, decidido no ecrã. */
  period: periodoSchema.optional().catch(undefined),
  /**
   * O mês da aba **Pessoal**, `YYYY-MM`. Ausente = o último mês fechado.
   *
   * Validado pelo formato e não contra uma lista de meses existentes: um
   * `?month=2019-03` é um mês válido de que este estabelecimento não tem dados,
   * e a resposta certa é o ecrã a dizer "não há nada registado" — não um erro de
   * validação que faz o painel inteiro cair.
   *
   * Independente do `period`: um salário é um facto mensal e ratear 30 dias por
   * uma janela de 7 inventa precisão que ninguém tem (ADR 0013, decisão 5), por
   * isso mexer num não mexe no outro.
   */
  month: mesSchema.optional().catch(undefined),
  /**
   * Qual das **três perguntas** está no ecrã. Ausente = `dinheiro`.
   *
   * "Quanto entrou e saiu", "o que se perdeu" e "quanto custa a equipa" são
   * perguntas diferentes com as mesmas formas e números diferentes, e empilhá-las
   * no mesmo scroll obrigava a ler as mesmas tabelas três vezes — eram os 3630px.
   * Passaram a três abas, e o parâmetro é o que faz um link apontar para a aba
   * certa.
   *
   * A aba é o **que** se carrega e não só o que se mostra: a série do gráfico só
   * se pede na aba `dinheiro` e o fecho do mês só na aba `pessoal`. Um ecrã que
   * busca o que não mostra paga a latência e o erro de uma coisa que ninguém
   * pediu.
   */
  aba: abaSchema.optional().catch(undefined),
  /**
   * A camada de notas, revelada como sub-linhas. Ausente = **desligada**.
   *
   * É `1` e não `true` para o URL ficar curto (`?explicar=1`) e por simetria com
   * o que se lê num painel: é um interruptor, não uma frase. Qualquer outro
   * valor — `0`, `true`, `sim` — cai no `.catch` e vale desligado, que é o
   * default certo para um URL que alguém escreveu à mão e não percebeu.
   *
   * Desligado por omissão porque quem vê o painel pela primeira vez liga uma
   * vez, entende, e desliga para sempre. O contrário — ligado por omissão — é o
   * painel de 3630px que o dono do produto recusou.
   */
  explicar: z.literal(1).optional().catch(undefined),
});

export type BuscaDoPainel = z.output<typeof buscaDoPainelSchema>;
