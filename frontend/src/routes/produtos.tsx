import { createRoute, lazyRouteComponent } from "@tanstack/react-router";
import { rotaDaApp } from "./app";

/**
 * Rota do catálogo de produtos.
 *
 * A busca é validada por Zod, e só contém o termo de procura
 * (sem paginação manual — a API devolve a página inteira e é
 * suficiente para a maioria dos catálogos).
 */

export const rotaDeProdutos = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/produtos",
  component: lazyRouteComponent(
    () => import("@/features/catalog/screens/produtos"),
    "EcraDeProdutos",
  ),
});

/**
 * Rota para criar novo produto.
 */
export const rotaCriarProduto = createRoute({
  getParentRoute: () => rotaDeProdutos,
  path: "/novo",
  component: lazyRouteComponent(
    () => import("@/features/catalog/screens/novo-produto"),
    "EcraNovoProduto",
  ),
});

/**
 * Rota para editar/detalhe de um produto.
 */
export const rotaProdutoDetalhe = createRoute({
  getParentRoute: () => rotaDeProdutos,
  path: "/$produtoId",
  component: lazyRouteComponent(
    () => import("@/features/catalog/screens/detalhe-produto"),
    "EcraDetalheProduto",
  ),
});
