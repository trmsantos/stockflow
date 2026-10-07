import { z } from "zod";

import { secaoSchema } from "@/features/accounts/api";

/**
 * O **único** parâmetro das Definições: que secção está à vista.
 *
 * Vive em `src/routes/` porque o `validateSearch` é contrato de rota e não
 * produto (ADR 0008, decisão 2), e o ecrã lê-o já validado com
 * `useSearch({ from: "/app/definicoes" })`. O `secaoSchema` vem do
 * `features/accounts/api.ts`, que é uma das duas portas que uma rota pode
 * atravessar: a alternativa era escrever aqui outra vez a lista das quatro
 * secções, e duas definições do mesmo parâmetro divergem na primeira que entre.
 *
 * ## Está no URL, e os rascunhos **não**
 *
 * A secção define o ecrã, logo pertence ao URL: um recarregamento, o botão de
 * voltar e um link mostrado a outra pessoa reproduzem o que se estava a ver. É a
 * decisão 1 da ADR 0008 aplicada ao mesmo grão que o `?aba=` do painel.
 *
 * O que **não** está no URL é o estado de edição — o nome a meio de ser
 * escrito, o menu meio reordenado. Um rascunho não é uma vista partilhável, e
 * pô-lo em search params dava um link que recria um estado que o servidor nunca
 * aceitou.
 *
 * ## `.catch(undefined)` e a queda que **não** se faz aqui
 *
 * Um `?secao=inventado` cai no default em vez de explodir dentro do ecrã (ADR
 * 0008). O que este ficheiro **não** consegue validar é se o papel de quem olha
 * vê a secção pedida — e não é por falta de acesso à sessão: o papel é **por
 * tenant**, e o seletor de estabelecimento vive no mesmo pé da sidebar que a
 * entrada para este ecrã. Quem é `owner` de A e `staff` de B, parado em
 * `?secao=estabelecimento`, troca de casa e fica com uma secção que o papel novo
 * não tem — **sem o URL mudar**, logo sem nada que um `validateSearch` ou um
 * `beforeLoad` possam observar. Essa queda vive no render, contra a sessão viva
 * (`secaoAMostrar`, em `features/accounts/secoes.ts`).
 */
export const buscaDeDefinicoesSchema = z.object({
  /** Ausente = `aparencia`, a única que os três papéis vêem. Decidido no ecrã. */
  secao: secaoSchema.optional().catch(undefined),
});
