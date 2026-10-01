import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { buscaDeStockSchema } from "./busca-de-stock";
import { rotaRaiz } from "./root";

/**
 * `/stock/<id do artigo>` — o detalhe de um artigo.
 *
 * Carrega o **mesmo** `validateSearch` da lista, e não por simetria: é assim
 * que o link de voltar devolve a lista exactamente como estava (mesma loja,
 * mesmo filtro, mesma procura) sem depender do histórico do browser, e que um
 * link para o detalhe mostrado a alguém reproduz também o contexto de onde
 * saiu. Os parâmetros não filtram o detalhe — o detalhe mostra o artigo em
 * todas as localizações, porque é de uma delas que se registará o desperdício.
 */
export const rotaDeArtigo = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/stock/$artigo",
  validateSearch: buscaDeStockSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/artigo"),
    "EcraDeArtigo",
  ),
});
