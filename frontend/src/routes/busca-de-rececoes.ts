import { z } from "zod";

/**
 * O filtro do ecrã Receber, no URL e validado — a razão pela qual o ADR 0008
 * escolheu este router.
 *
 * Um campo só, e é o que os dois números do topo põem no URL: tocar em "a
 * precisar de revisão" leva `?estado=revisao`, tocar em "confirmadas hoje" leva
 * `?estado=hoje`, tocar outra vez limpa. Com o filtro no URL, um recarregamento, o
 * botão de voltar e um link mostrado a alguém dão o mesmo ecrã — e o detalhe de
 * uma receção carrega o mesmo schema, para o link de voltar devolver a lista
 * exactamente como estava.
 *
 * **`hoje` e não `confirmadas`**: o segundo número conta as receções confirmadas
 * no **dia de negócio corrente**, cuja fronteira é dado do servidor (04:00 numa
 * pastelaria, não a meia-noite). O filtro tem de dar exactamente as linhas que
 * o contador conta, senão é o próprio ecrã a desmentir-se.
 *
 * **Não há `fornecedor` nem `tipo`.** Sete documentos numa semana não se
 * filtram, leem-se; e um seletor de fornecedor obrigaria o cliente a guardar um
 * catálogo de fornecedores que não é dele. Entra no dia em que a lista tiver
 * páginas.
 *
 * **Chama-se `estado` e não `ver`, e isso foi medido:** os tipos de search params
 * do TanStack Router cruzam-se entre rotas. Um `ver` com outro conjunto de
 * valores faz o `search={(anteriores) => ({...anteriores, ...})}` do ecrã
 * Alertas **deixar de compilar**, porque o `anteriores` do reducer é a união dos
 * campos de todas as rotas. Ou seja: o nome de um search param é partilhado por
 * toda a árvore, e dois ecrãs não podem dar significados diferentes ao mesmo
 * nome sem quebrar o `pnpm typecheck` do outro. `estado` é também o nome do
 * parâmetro da API, logo o URL e o pedido dizem a mesma palavra.
 *
 * O `.catch(undefined)` existe pela mesma razão medida no Stock: é ele que
 * garante que a chave chega ao ecrã sempre presente, pelo que o valor cru do URL
 * nunca sobrevive à fusão que o router faz.
 */
export const buscaDeRececoesSchema = z.object({
  estado: z.enum(["revisao", "hoje"]).optional().catch(undefined),
});

export type BuscaDeRececoes = z.output<typeof buscaDeRececoesSchema>;
