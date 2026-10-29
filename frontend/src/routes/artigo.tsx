import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeStockSchema } from "./busca-de-stock";

/**
 * `/stock/<id do artigo>` — o detalhe de um artigo.
 *
 * Carrega o **mesmo** `validateSearch` da lista, e não por simetria: é assim
 * que o link de voltar devolve a lista exactamente como estava (mesma loja,
 * mesmo filtro, mesma procura) sem depender do histórico do browser, e que um
 * link para o detalhe mostrado a alguém reproduz também o contexto de onde
 * saiu. Os parâmetros não filtram o detalhe — o detalhe mostra o artigo em
 * todas as localizações, porque é de uma delas que se registará o desperdício —
 * **e o servidor não os aceita**: o `GET /stock/levels/<artigo>` não tem
 * `?loja=` (ADR 0034, adenda de 29, decisão 16). Era uma intenção do cliente e
 * passou a facto do contrato; um `?loja=` que chegue ali é ignorado como
 * qualquer parâmetro fora do contrato. O cliente não o envia.
 */
export const rotaDeArtigo = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/stock/$artigo",
  validateSearch: buscaDeStockSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/artigo"),
    "EcraDeArtigo",
  ),
});
