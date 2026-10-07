import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeStockSchema } from "./busca-de-stock";

/**
 * `/stock` — o URL é em português porque é copy de produto; a pasta da feature
 * é `inventory` porque é o nome do módulo do backend (ADR 0008, decisão 2).
 *
 * O `validateSearch` é o que faz desta rota mais do que um caminho: a loja, o
 * filtro e o termo de procura entram tipados e validados, e um URL malformado
 * degrada para o default em vez de explodir dentro do ecrã. Ver
 * `busca-de-stock.ts` para a forma e para a razão de cada campo.
 */
export const rotaDeStock = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/stock",
  validateSearch: buscaDeStockSchema,
  component: lazyRouteComponent(() => import("@/features/inventory/screens/stock"), "EcraDeStock"),
});
