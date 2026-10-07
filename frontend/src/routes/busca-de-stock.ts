import { z } from "zod";

/**
 * Os filtros do ecrã Stock, no URL e validados — a razão decisiva pela qual o
 * ADR 0008 escolheu este router.
 *
 * O estado que *define* o ecrã pertence ao URL: sem isso, um recarregamento, o
 * botão de voltar e um link mostrado ao dono não reproduzem o ecrã que se
 * estava a ver. Vive em `src/routes/` porque o `validateSearch` é contrato de
 * rota, não produto (ADR 0008, decisão 2) — e por isso o ecrã não importa este
 * ficheiro: lê os valores já validados com `useSearch({ from: "/stock" })`,
 * tipados pela augmentação global do router.
 *
 * Três decisões de forma, e nenhuma é estética:
 *
 *  - **Cada campo é opcional e tem `.catch(undefined)`.** Ausente *é* o default
 *    ("todas as localizações", "sem filtro", "sem procura"), logo não há duas
 *    representações do mesmo estado e `/stock` continua a ser um URL limpo. É
 *    também o que permite navegar com `{ loja: undefined }` para **limpar** o
 *    parâmetro do URL em vez de o deixar lá com um valor vazio, porque o
 *    serializador do router omite as chaves com valor `undefined`.
 *
 *  - **A localização viaja como `id`, não como nome.** O que o ecrã conhece das
 *    localizações é o que a API lhe manda em `by_location` (`{id, name}`), por
 *    isso o único valor que ele pode pôr no URL é o `id`. Qualquer outra coisa
 *    seria o frontend a guardar um catálogo de lojas que não é dele.
 *
 *  - **Não há `horizonte` de validade.** O limiar de "a expirar" é do servidor e
 *    vem no `expiring_within_days` do resumo; dar um campo ao cliente para o
 *    mudar seria o painel de limiares que o guião da sessão 0 §4 proíbe, e
 *    criaria uma segunda definição de "a expirar" ao lado da dos alertas.
 */
export const buscaDeStockSchema = z.object({
  /** Localização ativa. Ausente = consolidado (a parte operacional da Q2). */
  loja: z.uuid().optional().catch(undefined),
  /**
   * Qual dos dois números do topo está a filtrar a lista. Os dois critérios são
   * **veredictos do servidor** (`status` e `nearest_expiry.days_away` contra o
   * `expiring_within_days`), não contas do cliente: filtrar aqui não cria uma
   * segunda definição de "em falta".
   */
  filtro: z.enum(["falta", "validade"]).optional().catch(undefined),
  /** O que está escrito no campo de procurar. 60 caracteres é um nome curto. */
  q: z.string().trim().max(60).optional().catch(undefined),
});

export type BuscaDeStock = z.output<typeof buscaDeStockSchema>;

/**
 * Nota do que foi **medido**, porque a leitura do código do router sugere o
 * contrário e custou meia sessão a esclarecer.
 *
 * O router não substitui a search params pela saída do validador: faz
 * `{...search cru do URL, ...saída do validador}`. Lido assim, uma chave que o
 * schema rejeita seria omitida pelo Zod e o valor **cru** do URL sobreviveria —
 * o ecrã receberia o número `5` em `q` com o tipo a prometer uma string, e a
 * primeira chamada a `q.normalize()` rebentaria.
 *
 * Não acontece, e a razão é o Zod: um campo `.optional().catch(undefined)`
 * devolve a chave **presente** com valor `undefined` (é o `JSON.stringify` que
 * a esconde, não o Zod que a omite). A fusão sobrepõe portanto sempre o valor
 * cru. Medido com `?q=5`: o match da raiz fica com `q: 5` (número) e o match de
 * `/stock` com a chave `q` presente e `undefined`, o campo de procurar aparece
 * vazio e a lista mostra os 22 artigos.
 *
 * Isto é o que torna o `.catch` suficiente aqui. Se um dia um campo deixar de o
 * ter, deixa de haver chave e o valor cru passa a chegar ao ecrã — é a razão
 * pela qual todos os três o têm.
 */
