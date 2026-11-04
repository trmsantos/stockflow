import { z } from "zod";

/**
 * Os filtros do ecrã Receitas, no URL e validados (ADR 0008, decisão 1).
 *
 * O estado que *define* o ecrã pertence ao URL: sem isso, um recarregamento, o
 * botão de voltar e um link mostrado ao dono não reproduzem o ecrã que se estava
 * a ver. Vive em `src/routes/` porque o `validateSearch` é contrato de rota e
 * não produto (ADR 0008, decisão 2) — e por isso o ecrã não importa este
 * ficheiro: lê os valores já validados com `useSearch({ from: "/app/receitas" })`,
 * tipados pela augmentação global do router.
 *
 * ## Cada campo é opcional e tem `.catch(undefined)`
 *
 * Ausente *é* o default ("sem procura", "só as activas", "a ler e não a
 * editar"), logo não há duas representações do mesmo estado e `/receitas`
 * continua a ser um URL limpo. É também o que permite navegar com
 * `{ estado: undefined }` para **limpar** o parâmetro em vez de o deixar lá com
 * um valor vazio, porque o serializador do router omite as chaves `undefined`.
 *
 * O `.catch` é o que torna isto seguro: medido no `busca-de-stock.ts`, o router
 * funde o search cru do URL com a saída do validador, e um campo
 * `.optional().catch(undefined)` devolve a chave **presente** com valor
 * `undefined` — é a presença da chave que sobrepõe o valor cru. Um campo que
 * deixe de ter `.catch` deixa de ter chave, e o valor cru do URL passa a chegar
 * ao ecrã com o tipo a prometer outra coisa.
 *
 * ## `estado` tem os dois valores do contrato, e não um terceiro
 *
 * `activas` (omissão) e `todas`. Um terceiro valor é **400** no servidor e não
 * uma lista a fingir que filtrou, logo o conjunto é fechado dos dois lados — e a
 * união está escrita **duas vezes de propósito**: aqui, porque o `validateSearch`
 * é contrato de rota, e no `features/recipes/schemas.ts`, porque o `api.ts`
 * precisa dela para montar o pedido e uma feature não pode importar
 * `@/routes/*`. É a mesma duplicação declarada que o `busca-de-stock.ts` tem
 * para o `filtro`.
 *
 * ## `editar` é `1` e não `true`
 *
 * É o mesmo idioma do `explicar` do painel: um interruptor no URL escreve-se com
 * o valor que o torna visível (`?editar=1`) e a ausência é o estado normal.
 * `z.literal(1)` e não um booleano — "false" e "0" no URL seriam duas formas de
 * dizer a mesma ausência, e a ADR 0008 manda cair para o default sem dizer nada.
 *
 * Porque é que editar é um **search param** e não uma rota própria: a ficha
 * continua a ser o mesmo documento, com o mesmo cabeçalho e o mesmo custo à
 * vista, e o que muda é a forma de lhe tocar. Criar é que é outra página —
 * `/receitas/nova` —, porque aí ainda não há documento nenhum.
 */
export const buscaDeReceitasSchema = z.object({
  /** O que está escrito no campo de procurar. 60 caracteres é um nome curto. */
  q: z.string().trim().max(60).optional().catch(undefined),
  /** `activas` é a omissão; `todas` traz as arquivadas, **marcadas**. */
  estado: z.enum(["activas", "todas"]).optional().catch(undefined),
  /** `1` abre o formulário sobre a ficha. Ausente = ler. */
  editar: z.literal(1).optional().catch(undefined),
});

export type BuscaDeReceitas = z.output<typeof buscaDeReceitasSchema>;
